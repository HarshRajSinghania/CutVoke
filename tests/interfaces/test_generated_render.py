"""Real externally rendered files; cache/source integrity and scoped editing."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from cutvoke.editing.service import EditService
from cutvoke.interfaces.httpapi import HttpApi
from cutvoke.interfaces.mcp_server import MCPServer
from cutvoke.storage.generated_media import canonical
from cutvoke.storage.generated_requests import GeneratedRenderCache, snapshot_request, validate_params
from cutvoke.storage.project_directory import ProjectLibraryStore


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    root = tmp_path_factory.mktemp("generated-render-media")
    for color in ("blue", "red"):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=160x96:r=10:d=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-bsf:v",
                        "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
                        str(root / (color + ".mp4"))], check=True)
    return root


@pytest.fixture
def case(tmp_path, media):
    root = tmp_path / "source"
    root.mkdir()
    (root / "scene.py").write_text("raise RuntimeError('request source must NEVER execute')\n")
    (root / "brand.txt").write_text("original declared brand input")
    request = {"kind": "cutvoke.generated-render-request", "schemaVersion": 1,
               "renderer": {"name": "fixture", "version": "1", "build": "fixed-test"},
               "entrypoint": "scene.py", "files": [
                   {"path": name, "sha256": sha(root / name), "role": role}
                   for name, role in (("scene.py", "source"), ("brand.txt", "asset"))],
               "bindings": {"brand": "brand.txt"}, "seed": 7,
               "paramsSchema": {"type": "object", "additionalProperties": False, "required": ["accent", "values"],
                                "properties": {"accent": {"type": "string", "minLength": 1, "maxLength": 8, "enum": ["blue", "red"]},
                                               "values": {"type": "array", "minItems": 2, "maxItems": 2,
                                                          "items": {"type": "number", "minimum": 0, "maximum": 10}}}},
               "params": {"accent": "blue", "values": [2, 6]}, "profile": "final",
               "output": {"width": 160, "height": 96, "fps": {"num": 10, "den": 1}, "durationFrames": 10,
                          "format": "mp4", "alphaMode": "opaque", "colorSpace": "bt709", "audioMode": "none"},
               "frameRange": {"startFrame": 0, "frameCount": 10}}
    path = root / "request.json"
    path.write_bytes(canonical(request))
    library = ProjectLibraryStore(str(tmp_path / "library.sqlite"))
    service = EditService(store=library)
    server = MCPServer(service)
    def call(operation="plan", project="one", **kwargs):
        args = dict(projectId=project, operation=operation, **kwargs)
        if operation != "status":
            args["requestPath"] = str(path)
        result = server.call_tool("generated_render", args)
        assert result["ok"], result
        return result
    for project in ("one", "two"):
        result = server.call_tool("create_project", dict(projectId=project, directory=str(tmp_path / project), width=160, height=96, fps=10))
        assert result["ok"], result
    def register(color="blue", **kwargs):
        plan = call(**kwargs)
        video = media / (color + ".mp4")
        return call("register", expectedRequestKey=plan["requestKey"], renderPath=str(video), renderSha256=sha(video), **kwargs)
    yield root, path, request, service, server, call, register
    server.close()
    library.close()


def test_plan_register_covering_preview_and_project_scope(case):
    root, path, request, service, server, call, register = case
    before = copy.deepcopy(service.get_project("one").to_dict())
    cold = call()
    assert cold["requiresExternalRender"] and not cold["sourceExecution"]
    assert cold["cache"] == {"hit": False, "reason": "not_found"}
    ready = register()
    assert ready["registered"] and ready["cache"]["kind"] == "exact"
    assert service.get_project("one").to_dict() == before
    with zipfile.ZipFile(ready["receipt"]["sourceArchive"]["path"]) as archive:
        frozen = json.loads(archive.read("inputs/cutvoke-request.json"))
        assert frozen == request
        assert archive.read("inputs/scene.py") == (root / "scene.py").read_bytes()
    assert not call()["requiresExternalRender"]
    covered = call(frameRange={"startFrame": 3, "frameCount": 4})
    assert covered["cache"]["kind"] == "covering" and covered["assetId"] == ready["assetId"]
    assert covered["mediaSourceStart"] == {"num": "3", "den": "10"}
    preview = covered["previewCall"]
    assert preview["arguments"]["times"] == [.4, .5, .6]
    assert "projectId" not in preview["arguments"]
    result = server.call_tool(preview["tool"], preview["arguments"])
    assert result["ok"], result
    assert call(project="two")["cache"]["hit"] is False
    assert call("status")["cache"]["entries"] == 1


@pytest.mark.parametrize("change", ["params", "asset", "seed", "runtime", "profile", "duration", "schema"])
def test_all_declared_dependencies_invalidate_cache(case, change):
    root, path, request, _, _, call, register = case
    registered = register()
    if change == "params": request["params"]["accent"] = "red"
    elif change == "asset":
        (root / "brand.txt").write_text("new brand")
        request["files"][1]["sha256"] = sha(root / "brand.txt")
    elif change == "seed": request["seed"] += 1
    elif change == "runtime": request["renderer"]["build"] = "new-build"
    elif change == "profile": request["profile"] = "review"
    elif change == "duration": request["output"]["durationFrames"] = 11
    elif change == "schema": request["paramsSchema"]["properties"]["accent"]["title"] = "Color"
    path.write_bytes(canonical(request))
    plan = call(previousRequestKey=registered["requestKey"])
    assert plan["cache"]["hit"] is False and plan["requestKey"] != registered["requestKey"]
    assert plan["changedFields"]


@pytest.mark.parametrize("mutation", ["unknown-param", "range", "boolean-number", "nested", "unbounded", "ref", "binding", "source", "sha", "duplicate"])
def test_reject_invalid_requests_without_import(case, mutation):
    root, path, request, service, server, _, _ = case
    if mutation == "unknown-param": request["params"]["shell"] = "unsafe"
    elif mutation == "range": request["frameRange"]["startFrame"] = 10
    elif mutation == "boolean-number": request["params"]["values"][0] = True
    elif mutation == "nested": request["paramsSchema"]["properties"]["values"]["items"] = {"type": "object"}
    elif mutation == "unbounded": del request["paramsSchema"]["properties"]["accent"]["maxLength"]
    elif mutation == "ref": request["paramsSchema"]["properties"]["accent"]["$ref"] = "file:///secret"
    elif mutation == "binding": request["bindings"]["brand"] = "scene.py"
    elif mutation == "source": (root / "scene.py").write_text("changed after plan")
    elif mutation == "sha": request["files"][0]["sha256"] = "0" * 64
    if mutation == "duplicate": path.write_text('{"kind":1,"kind":2}')
    else: path.write_bytes(canonical(request))
    result = server.call_tool("generated_render", dict(projectId="one", operation="plan", requestPath=str(path)))
    assert not result["ok"], result
    assert service.get_project("one").revision == "0"
    assert not list((path.parents[1] / "one/media/.generated").glob("*.cvsource.zip"))


def test_snapshot_is_frozen_and_stale_plan_is_rejected(case):
    root, path, request, _, server, call, _ = case
    cold = call()
    with snapshot_request(path) as (frozen, stage, _):
        (root / "scene.py").write_text("later mutation")
        assert (stage / "inputs/scene.py").read_text().startswith("raise RuntimeError")
    assert not stage.exists()
    request["files"][0]["sha256"] = sha(root / "scene.py")
    path.write_bytes(canonical(request))
    result = server.call_tool("generated_render", dict(projectId="one", operation="register", requestPath=str(path),
              expectedRequestKey=cold["requestKey"], renderPath=str(root / "not-created.mp4"), renderSha256="0" * 64))
    assert not result["ok"] and "stale key" in result["error"]["message"]


@pytest.mark.parametrize("target", ["media", "archive"])
def test_corrupt_cached_bytes_are_not_reused(case, target):
    _, _, _, _, _, call, register = case
    ready = register()
    path = Path(ready["receipt"]["asset"]["path"] if target == "media" else ready["receipt"]["sourceArchive"]["path"])
    path.write_bytes(b"corrupt")
    plan = call()
    assert not plan["cache"]["hit"] and "changed" in plan["cache"]["reason"]
    assert path.read_bytes() == b"corrupt"


def test_conflicting_outputs_disable_entire_composition(case):
    _, _, _, _, _, call, register = case
    register()
    second = register("red")  # Same declared request, different actual output.
    assert second["registered"] and second["cache"]["reason"] == "conflicting_outputs"
    assert call(frameRange={"startFrame": 3, "frameCount": 2})["cache"]["reason"] == "conflicting_outputs"
    assert call("status")["cache"]["conflictingCompositions"] == 1


def test_metadata_eviction_and_concurrent_registration_do_not_delete_assets(case, monkeypatch):
    _, path, request, _, _, call, register = case
    ready = register()
    cache = GeneratedRenderCache(Path(ready["receipt"]["sourceArchive"]["path"]).parents[1])
    monkeypatch.setattr("cutvoke.storage.generated_requests.MAX_ENTRIES", 2)
    def record(seed):
        changed = copy.deepcopy(request)
        changed["seed"] = seed
        cache.record(changed, ready["receipt"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record, range(8, 16)))
    assert cache.status()["entries"] == 2
    assert cache.document(ready["requestKey"]) is None
    assert Path(ready["receipt"]["asset"]["path"]).is_file()
    assert Path(ready["receipt"]["sourceArchive"]["path"]).is_file()


def test_http_mcp_parity_and_closed_arguments(case):
    _, path, _, service, server, call, _ = case
    api = HttpApi(service, media_dir=str(path.parent / "unused"))
    args = dict(projectId="one", operation="plan", requestPath=str(path))
    try:
        status, result = api.handle("POST", "/api/v1/agent/generated_render", args)
        assert status == 200 and result == call()
        for invalid in ({**args, "operation": "execute"}, {**args, "shell": "unsafe"},
                        {**args, "params": {"accent": "green"}}, {**args, "operation": "status"}):
            status, result = api.handle("POST", "/api/v1/agent/generated_render", invalid)
            assert status == 400 and not server.call_tool("generated_render", invalid)["ok"]
    finally:
        api.close()


@pytest.mark.parametrize("definition,value", [
    ({"type": "number", "minimum": 0, "maximum": 1}, float("nan")),
    ({"type": "number", "minimum": 0, "maximum": 1}, float("inf")),
    ({"type": "integer", "minimum": 0, "maximum": 1}, True),
    ({"type": "integer", "minimum": 0, "maximum": 1}, 1.0),
    ({"type": "number", "minimum": 0, "maximum": 10**1000}, 1),
    ({"type": "string", "minLength": 0, "maxLength": 2048}, "x" * 2049),
    ({"type": "boolean", "default": True}, True),
    ({"type": "boolean", "enum": [True, True]}, True),
    ({"type": "array", "minItems": 0, "maxItems": 65, "items": {"type": "boolean"}}, []),
    ({"type": "array", "minItems": 0, "maxItems": 2, "items": {"type": "boolean"}}, [True, False, True]),
    ({"type": "string", "minLength": 0, "maxLength": 8, "pattern": ".*"}, "text"),
])
def test_parameter_boundary_rejections(definition, value):
    schema = {"type": "object", "additionalProperties": False, "required": ["value"], "properties": {"value": definition}}
    with pytest.raises(ValueError):
        validate_params(schema, {"value": value})


def test_register_rejects_mismatched_frames_and_bytes(case, media):
    _, path, _, _, server, call, _ = case
    window = {"startFrame": 2, "frameCount": 3}
    planned = call(frameRange=window)
    args = dict(projectId="one", operation="register", requestPath=str(path), frameRange=window,
                expectedRequestKey=planned["requestKey"], renderPath=str(media / "blue.mp4"), renderSha256=sha(media / "blue.mp4"))
    result = server.call_tool("generated_render", args)
    assert not result["ok"] and "frame count" in result["error"]["message"]
    args["renderSha256"] = "0" * 64
    result = server.call_tool("generated_render", args)
    assert not result["ok"] and result["error"]["message"] == "SHA256 mismatch: blue.mp4"
    assert call("status")["cache"]["entries"] == 0

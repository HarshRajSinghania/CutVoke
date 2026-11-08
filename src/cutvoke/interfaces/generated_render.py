"""Plan/cache externally rendered frame windows. Source is always inert data."""
from fractions import Fraction
import hashlib
from pathlib import Path

from cutvoke.storage.generated_media import SHA, MAX_RENDER_BYTES, _copy_checked, canonical, inspect_render
from cutvoke.storage.generated_requests import (
    REQUEST_FILE, GeneratedRenderCache, changes, keys, snapshot_request,
)


TEXT = {"type": "string", "minLength": 1}
TOOL = {"name": "generated_render", "description":
        "Plan an external code render before media exists, validate bounded parameters/bindings and an absolute frame window, or register a rendered result. Reuse verified exact/covering cached media without running source. Source execution is ALWAYS disabled; a cache miss requires an independently trusted external renderer. No timeline edit. Use returned mediaSourceStart for covering assets and normal revision/lease commands to edit; previewCall uses existing preview_frames. Cache eviction removes metadata only.",
        "inputSchema": {"type": "object", "additionalProperties": False,
            "required": ["projectId", "operation"], "properties": {
                "projectId": TEXT, "operation": {"type": "string", "enum": ["plan", "register", "status"]},
                "requestPath": TEXT, "params": {"type": "object", "maxProperties": 32},
                "frameRange": {"type": "object", "additionalProperties": False,
                    "required": ["startFrame", "frameCount"], "properties": {
                        "startFrame": {"type": "integer", "minimum": 0, "maximum": 17999},
                        "frameCount": {"type": "integer", "minimum": 1, "maximum": 18000}}},
                "previousRequestKey": TEXT, "expectedRequestKey": TEXT,
                "renderPath": TEXT, "renderSha256": TEXT}}}


class GeneratedRender:
    def __init__(self, agent):
        self.agent = agent

    def call(self, arguments):
        operation = arguments["operation"]
        project = self.agent._project(arguments)
        if not self.agent.service.store:
            raise ValueError("generated_render requires persistent project storage")
        if operation == "status":
            if set(arguments) - {"projectId", "operation"}:
                raise ValueError("status accepts projectId and operation only")
        elif not arguments.get("requestPath"):
            raise ValueError("requestPath is required for plan/register")
        if operation == "plan" and any(key in arguments for key in ("expectedRequestKey", "renderPath", "renderSha256")):
            raise ValueError("plan does not accept rendered-output arguments")
        if operation == "register":
            if any(not arguments.get(key) for key in ("expectedRequestKey", "renderPath", "renderSha256")):
                raise ValueError("register requires expectedRequestKey, renderPath and renderSha256")
            if not SHA.fullmatch(arguments["renderSha256"]):
                raise ValueError("renderSha256 must be lowercase SHA256")
        cache = GeneratedRenderCache(self.agent.api.media_dir)
        base = {"projectId": project.project_id, "revision": project.revision,
                "timelineChanged": False, "sourceExecution": False,
                "executionPolicy": "external-reviewed-renderer-only"}
        if operation == "status":
            return {**base, "cache": cache.status()}
        with snapshot_request(arguments["requestPath"], arguments.get("params"), arguments.get("frameRange")) as (request, stage, source_root):
            key, composition = keys(request)
            result = {**base, "requestKey": key, "compositionKey": composition,
                      "request": request, "sourceDirectory": str(source_root),
                      "logicalFrameClock": "declared_by_external_renderer",
                      "creativeAcceptance": "not_assessed"}
            previous = arguments.get("previousRequestKey")
            if previous:
                document = cache.document(previous)
                result["changedFields"] = changes(document, request) if document else ["previous_request_not_retained"]
            if operation == "register":
                if arguments["expectedRequestKey"] != key:
                    raise ValueError("render request changed after planning; do not register against a stale key")
                self._register(arguments, request, stage, cache, result)
            else:
                result["cache"] = cache.lookup(request, self.agent.service.store, self.agent.api._imported_media_path)
            hit = result["cache"]
            if hit.get("hit"):
                result.update({"assetId": hit["assetId"], "mediaSourceStart": hit["mediaSourceStart"]})
            if result.get("assetId"):
                fps = Fraction(request["output"]["fps"]["num"], request["output"]["fps"]["den"])
                duration = request["frameRange"]["frameCount"] / fps
                start = Fraction(int(result["mediaSourceStart"]["num"]), int(result["mediaSourceStart"]["den"]))
                # Frame times are source-local, while logical source time stays
                # in the request. Do not add projectId to an asset preview call.
                times = [float(start + duration * Fraction(n, 4)) for n in (1, 2, 3)]
                result["previewCall"] = {"tool": "preview_frames", "arguments": {
                    "assetId": result["assetId"], "times": times, "width": max(160, min(640, request["output"]["width"]))}}
            result["requiresExternalRender"] = not bool(hit.get("hit") or result.get("registered"))
            return result

    def _register(self, arguments, request, stage, cache, result):
        source = Path(arguments["renderPath"]).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("renderPath must name a regular media file")
        output = request["output"]
        suffix = ".mp4" if output["format"] == "mp4" else ".mov"
        target = stage / ("render" + suffix)
        _copy_checked(source, target, arguments["renderSha256"], MAX_RENDER_BYTES)
        files = [{**item, "path": "inputs/" + item["path"]} for item in request["files"]]
        files.append({"path": "inputs/" + REQUEST_FILE,
                      "sha256": hashlib.sha256(canonical(request)).hexdigest(), "role": "asset"})
        manifest = {"schemaVersion": 1, "renderer": request["renderer"],
                    "entrypoint": "inputs/" + request["entrypoint"], "files": files,
                    "params": request["params"], "seed": request["seed"],
                    "output": {**{key: value for key, value in output.items() if key != "format"},
                               "path": target.name, "sha256": arguments["renderSha256"],
                               "durationFrames": request["frameRange"]["frameCount"]}}
        info = inspect_render(manifest, target, self.agent.render.ffprobe)
        expected = "h264" if output["format"] == "mp4" else "prores"
        if info["stream"].get("codec_name") != expected or (expected == "prores" and info["stream"].get("profile") not in ("4444", "XQ")):
            raise ValueError("rendered codec does not match request format")
        path = stage / "manifest.json"
        path.write_bytes(canonical(manifest))
        receipt = self.agent.generated_media({"projectId": arguments["projectId"], "operation": "import", "manifestPath": str(path)})
        result.update({"registered": True, "assetId": receipt["assetId"], "receipt": receipt,
                       "mediaSourceStart": {"num": "0", "den": "1"}})
        cache.record(request, receipt)
        result["cache"] = cache.lookup(request, self.agent.service.store, self.agent.api._imported_media_path)

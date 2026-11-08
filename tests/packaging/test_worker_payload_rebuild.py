"""Checkout-only asset generators must not change a rebuilt worker package."""
import json
from pathlib import Path
import runpy
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[2]
prepare = runpy.run_path(str(ROOT / "tools/build/prepare_extension_payloads.py"))["prepare"]


def make_source(root, *, generators):
    package = root / "src/cutvoke"
    (package / "interfaces").mkdir(parents=True)
    (package / "catalogs").mkdir()
    (package / "__init__.py").write_text('__version__ = "fixture"\n')
    (package / "interfaces/creative_guides.py").write_text(
        'GUIDE_FILES = {"intro": ("SKILL.md", "Introduction")}\n')
    (package / "catalogs/creative_recipes.json").write_text('{"recipes": []}\n')
    (package / "catalogs/optional_extensions.json").write_text(json.dumps({
        "artifacts": {}, "profiles": [{"id": "fixture", "artifacts": []}]}))
    (root / "skills/cutvoke-editor").mkdir(parents=True)
    (root / "skills/cutvoke-editor/SKILL.md").write_text("Original fixture guide\n")
    (root / "tools/build").mkdir(parents=True)
    shutil.copyfile(ROOT / "tools/build/prepare_editor_guides.py",
                    root / "tools/build/prepare_editor_guides.py")
    (root / "LICENSE").write_text("Original fixture license\n")
    if generators:
        (package / "assets/backgrounds").mkdir(parents=True)
        (package / "assets/backgrounds/generate_backgrounds.py").write_text(
            'raise RuntimeError("authoring tool, never worker code")\n')
    return package


def test_source_rebuild_keeps_worker_bytes_and_catalog_identical(tmp_path):
    checkout, sdist = tmp_path / "checkout", tmp_path / "sdist"
    make_source(checkout, generators=True)
    make_source(sdist, generators=False)
    left, right = prepare(checkout), prepare(sdist)
    assert Path(left["path"]).read_bytes() == Path(right["path"]).read_bytes()
    assert left["sha256"] == right["sha256"]
    catalogs = [json.loads((root / "src/cutvoke/catalogs/optional_extensions.json").read_text())
                for root in (checkout, sdist)]
    assert catalogs[0] == catalogs[1]
    with zipfile.ZipFile(left["path"]) as archive:
        assert archive.read("cutvoke/interfaces/creative_guides.py")
        assert archive.read("cutvoke/assets/editor_guides/intro.md") == b"Original fixture guide\n"
        assert archive.read("cutvoke/catalogs/creative_recipes.json") == b'{"recipes": []}\n'
        assert archive.read("cutvoke/WORKER-LICENSE.txt") == b"Original fixture license\n"
        assert not any(name.startswith("cutvoke/assets/backgrounds/") for name in archive.namelist())


def test_runtime_change_replaces_worker_identity_and_profile_reference(tmp_path):
    root = tmp_path / "checkout"
    package = make_source(root, generators=True)
    old = prepare(root)
    (package / "interfaces/creative_guides.py").write_text(
        'GUIDE_FILES = {"intro": ("SKILL.md", "Updated introduction")}\n')
    new = prepare(root)
    assert new["sha256"] != old["sha256"]
    catalog = json.loads((package / "catalogs/optional_extensions.json").read_text())
    identity = new["sha256"][:16]
    assert set(catalog["artifacts"]) == {identity}
    assert catalog["artifacts"][identity]["sha256"] == new["sha256"]
    assert catalog["profiles"][0]["artifacts"] == [identity]
    assert prepare(root)["sha256"] == new["sha256"]

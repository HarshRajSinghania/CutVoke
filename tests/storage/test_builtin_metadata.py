"""Keep startup metadata accurate without per-file media subprocesses."""
import hashlib
from pathlib import Path
import wave

import pytest

from cutvoke.rendering.render import RenderError, RenderService
from cutvoke.storage import builtin_assets as assets
from cutvoke.storage import resource_pack as rp
from cutvoke.storage.store import ProjectStore


@pytest.fixture
def store(tmp_path):
    result = ProjectStore(str(tmp_path / "library.sqlite"))
    yield result
    result.close()


class NoProbe:
    def probe_media(self, path):
        raise AssertionError(f"supported builtin metadata must not spawn ffprobe: {path}")


def test_all_bundled_wavs_preserve_real_decoder_metadata_without_probing(store):
    registered = assets.ensure_builtin_audio(store, render=NoProbe())
    assert len(registered) == 19
    decoder = RenderService()
    for item in registered:
        actual = decoder.probe_media(item["path"])
        assert item["duration"] == pytest.approx(actual["duration"], abs=1e-6)
        assert item["hasAudio"] == actual["has_audio"]
        assert item["assetId"] == "builtin_audio_" + Path(item["path"]).stem
        assert item["builtin"] and item["audioRole"] in ("music", "sound_effect")


def test_wav_frame_count_sets_exact_duration_and_registration_stays_idempotent(store, tmp_path, monkeypatch):
    root = tmp_path / "audio"
    root.mkdir()
    with wave.open(str(root / "chime.wav"), "wb") as stream:
        stream.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 2 * 3000)
    monkeypatch.setattr(assets, "AUDIO_DIR", str(root))
    first = assets.ensure_builtin_audio(store, render=NoProbe())
    assert first == assets.ensure_builtin_audio(store, render=NoProbe())
    assert len(first) == 1 and first[0]["duration"] == .375


@pytest.mark.parametrize("filename", ["compressed.wav", "compressed.ogg"])
def test_unsupported_audio_uses_supplied_decoder_and_preserves_error_fallback(store, tmp_path, monkeypatch, filename):
    (tmp_path / filename).write_bytes(b"unsupported audio header")
    monkeypatch.setattr(assets, "AUDIO_DIR", str(tmp_path))
    class Decoder:
        fail = False
        calls = []
        def probe_media(self, path):
            self.calls.append(path)
            if self.fail:
                raise RenderError("fixture unavailable decoder")
            return {"duration": 2.5, "has_audio": True}
    decoder = Decoder()
    assert assets.ensure_builtin_audio(store, render=decoder)[0]["duration"] == 2.5
    decoder.fail = True
    second = assets.ensure_builtin_audio(store, render=decoder)[0]
    assert second["duration"] is None and second["hasAudio"]
    assert decoder.calls == [str(tmp_path / filename)] * 2


def test_background_metadata_keeps_hashes_dimensions_and_immutable_paths(store, tmp_path, monkeypatch):
    calls = []
    real_manifest = rp.load_resource_pack_manifest
    def manifest(root=None):
        calls.append(root)
        return real_manifest(root)
    monkeypatch.setattr(rp, "load_resource_pack_manifest", manifest)
    root = tmp_path / "immutable"
    registered = assets.ensure_builtin_backgrounds(store, NoProbe(), immutable_root=root)
    assert len(registered) == 42 and len(calls) == 1
    decoder = RenderService()
    declared = real_manifest()
    expected = {item["resourceId"]: item for item in declared["resources"] if item["kind"] == "background"}
    records = {item["path"]: item for item in declared["files"]}
    for item in registered:
        path = Path(item["path"])
        assert path.is_relative_to(root) and item["builtin"]
        actual = decoder.probe_media(str(path))
        assert (item["width"], item["height"]) == (actual["width"], actual["height"])
        resource = expected[item["assetId"]]
        record = records[resource["mediaFiles"][0]]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_background_decoder_fallback_and_bad_hash_exclusion(store, tmp_path, monkeypatch):
    from PIL import Image
    declared = rp.load_resource_pack_manifest()
    backgrounds = [item for item in declared["resources"] if item["kind"] == "background"]
    rejected = backgrounds[0]
    real_matches = rp.file_matches_sha256
    def matches(path, sha256, size=None):
        return False if str(path).endswith(rejected["mediaFiles"][0]) else real_matches(path, sha256, size)
    monkeypatch.setattr(rp, "file_matches_sha256", matches)
    def unavailable(path):
        raise OSError("fixture unsupported image header")
    monkeypatch.setattr(Image, "open", unavailable)
    class Decoder:
        def probe_media(self, path):
            return {"width": 160, "height": 96}
    registered = assets.ensure_builtin_backgrounds(store, Decoder(), immutable_root=tmp_path / "immutable")
    assert len(registered) == 41 and store.get_asset(rejected["resourceId"]) is None
    assert all((item["width"], item["height"]) == (160, 96) for item in registered)

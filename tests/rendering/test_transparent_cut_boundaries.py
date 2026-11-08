"""An expired opaque shot must not show through the next alpha shot."""
import subprocess

import numpy as np
from PIL import Image, ImageDraw
import pytest

from cutvoke.domain.model import AssetReference, Clip, Track
from cutvoke.domain.rational import Rational as R
from cutvoke.editing.service import EditService
from cutvoke.rendering.render import RenderService


@pytest.mark.parametrize("fps", [10, 24])
@pytest.mark.parametrize("split_before", [False, True])
@pytest.mark.parametrize("gap_before", [False, True])
def test_cut_to_alpha_clears_expired_source_in_export_and_preview(tmp_path, fps, split_before, gap_before):
    renderer = RenderService(gpu_effects=False)
    base = tmp_path / "blue.png"
    Image.new("RGB", (160, 96), (0, 0, 255)).save(base)
    transparent = tmp_path / "green-alpha.png"
    picture = Image.new("RGBA", (160, 96), (0, 0, 0, 0))
    ImageDraw.Draw(picture).rectangle((40, 24, 120, 72), fill=(0, 255, 0, 255))
    picture.save(transparent)
    opaque, alpha = tmp_path / "red.mp4", tmp_path / "alpha.mov"
    subprocess.run([renderer.ffmpeg, "-v", "error", "-f", "lavfi", "-i", f"color=red:s=160x96:r={fps}:d=2",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(opaque)], check=True, timeout=30)
    subprocess.run([renderer.ffmpeg, "-v", "error", "-loop", "1", "-i", str(transparent), "-t", "2", "-r", str(fps),
                    "-an", "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(alpha)], check=True, timeout=30)
    project = EditService().create_project("alpha-cut", width=160, height=96, fps=R.of(fps))
    shots = [Clip("red", AssetReference("red", str(opaque)), R.of(0), R.of(1), R.of(0))]
    if split_before:
        shots[0].timeline_end = R.of(1, 2)
        shots.append(Clip("red-tail", AssetReference("red", str(opaque)), R.of(1, 2), R.of(1), R.of(1, 2)))
    alpha_start = R.of(3, 2) if gap_before else R.of(1)
    shots.append(Clip("alpha", AssetReference("alpha", str(alpha)), alpha_start, alpha_start+R.of(1), R.of(0)))
    project.sequence.tracks = [
        Track("base", "video", [Clip("blue", AssetReference("blue", str(base)), R.of(0), R.of(3), R.of(0))]),
        Track("code", "video", shots),
    ]
    preview = tmp_path / "preview.png"
    renderer.extract_frame(project, float((alpha_start+R.of(1,2)).to_fraction()), str(preview))
    with Image.open(preview) as frame:
        assert max(abs(a-b) for a,b in zip(frame.convert("RGB").getpixel((10, 10)), (0,0,255))) < 8
    output = tmp_path / "result.mp4"
    renderer.render(project, str(output), quality="high")
    raw = subprocess.run([renderer.ffmpeg, "-v", "error", "-i", str(output), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True, timeout=30).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 96, 160, 3)
    assert len(frames) == 3*fps
    # Check every decoded frame, especially the first and final frames of the
    # alpha shot, against the native lower track rather than the old red shot.
    assert np.max(abs(frames[:fps,10,10].astype(int) - [253,0,0])) < 10
    assert np.max(abs(frames[fps:,10,10].astype(int) - [0,0,255])) < 10
    start = int(alpha_start.to_fraction()*fps)
    end = start+fps
    assert np.max(abs(frames[start:end,48,80].astype(int) - [0,255,0])) < 10
    if gap_before:
        assert np.max(abs(frames[fps:start,48,80].astype(int) - [0,0,255])) < 10
    assert np.max(abs(frames[end:,48,80].astype(int) - [0,0,255])) < 10

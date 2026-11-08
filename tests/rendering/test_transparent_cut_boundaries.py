"""An expired opaque shot must not show through the next alpha shot."""
import subprocess
import threading

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


@pytest.mark.parametrize("rate", [(24,1), (30,1), (60,1), (30000,1001)])
@pytest.mark.parametrize("leading_frames", [0,2])
@pytest.mark.parametrize("source_kind", ["image", "video"])
def test_single_frame_cuts_use_half_open_sequence_frame_intervals(tmp_path, rate, leading_frames, source_kind):
    fps = R.of(*rate)
    def at(frame):
        return R.of(frame*rate[1], rate[0])
    paths = {}
    renderer = RenderService(gpu_effects=False)
    for name, color in (("blue", (0,0,255,255)), ("red", (255,0,0,255)), ("alpha", (0,0,0,0))):
        path = tmp_path / (name + ".png")
        picture = Image.new("RGBA", (64,64), color)
        if name == "alpha":
            ImageDraw.Draw(picture).rectangle((20,20,43,43), fill=(0,255,0,255))
        picture.save(path)
        if source_kind == "video" and name != "blue":
            video = tmp_path / (name + ".mov")
            subprocess.run([renderer.ffmpeg, "-v", "error", "-loop", "1",
                            "-framerate", f"{rate[0]}/{rate[1]}", "-i", str(path),
                            "-frames:v", "8", "-an", "-c:v", "prores_ks",
                            "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(video)],
                           check=True, timeout=30)
            path = video
        paths[name] = AssetReference(name, str(path))
    project = EditService().create_project("single-frame-alpha", width=64, height=64, fps=fps)
    project.sequence.tracks = [
        Track("base", "video", [Clip("blue", paths["blue"], at(0), at(leading_frames+6), at(0))]),
        Track("shots", "video", [
            Clip("red", paths["red"], at(leading_frames), at(leading_frames+1), at(0)),
            Clip("alpha", paths["alpha"], at(leading_frames+1), at(leading_frames+2), at(0)),
        ]),
    ]
    output = tmp_path / "single-frame.mp4"
    renderer.render(project, str(output), quality="high")
    raw = subprocess.run([renderer.ffmpeg,"-v","error","-i",str(output),"-pix_fmt","rgb24","-f","rawvideo","-"],
                         capture_output=True, check=True, timeout=30).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1,64,64,3)
    assert len(frames) == leading_frames+6
    expected = np.tile([0,0,255], (len(frames),1))
    expected[leading_frames] = [253,0,0]
    assert np.max(abs(frames[:,5,5].astype(int)-expected)) < 10
    centers = expected.copy()
    centers[leading_frames+1] = [0,255,0]
    assert np.max(abs(frames[:,32,32].astype(int)-centers)) < 10
    for index in (leading_frames+1, leading_frames+2):
        preview = tmp_path / f"preview-{index}.png"
        renderer.extract_frame(project, float(at(index).to_fraction()), str(preview))
        with Image.open(preview) as picture:
            actual = np.array(picture.convert("RGB").getpixel((32,32)))
            assert np.max(abs(actual-centers[index])) < 10


def test_subframe_shot_without_a_sequence_sample_stays_invisible(tmp_path, monkeypatch):
    blue, red = tmp_path/"blue.png", tmp_path/"red.png"
    Image.new("RGB", (64,64), (0,0,255)).save(blue)
    Image.new("RGB", (64,64), (255,0,0)).save(red)
    project = EditService().create_project("subframe-shot", width=64, height=64, fps=R.of(24))
    project.sequence.tracks = [
        Track("base", "video", [Clip("blue", AssetReference("blue",str(blue)), R.of(0),R.of(1,4),R.of(0))]),
        Track("shot", "video", [Clip("red", AssetReference("red",str(red)), R.of(1,96),R.of(3,96),R.of(0))]),
    ]
    renderer = RenderService(gpu_effects=False)
    output = tmp_path/"subframe.mp4"
    cancelled = threading.Event()
    processes = []
    real_popen = subprocess.Popen
    def popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process
    def stop_owned_processes():
        cancelled.set()
        for process in processes:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
    # A zero-output branch must finish, not just hide its pictures. Bound the
    # regression even if a stuck encoder does not respond to graceful cancel.
    watchdog = threading.Timer(30, stop_owned_processes)
    watchdog.daemon = True
    watchdog.start()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(subprocess,"Popen",popen)
            renderer.render(project,str(output),cancel_event=cancelled)
        assert not cancelled.is_set()
    finally:
        watchdog.cancel()
        stop_owned_processes()
    raw = subprocess.run([renderer.ffmpeg,"-v","error","-i",str(output),"-pix_fmt","rgb24","-f","rawvideo","-"],
                         capture_output=True,check=True,timeout=30).stdout
    frames = np.frombuffer(raw,np.uint8).reshape(-1,64,64,3)
    assert len(frames)==6
    assert np.max(abs(frames[:,5,5].astype(int)-[0,0,255])) < 10

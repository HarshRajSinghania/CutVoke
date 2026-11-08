"""Reviewed reference renderer for this repository's original scene.py ONLY.

Run explicitly outside CutVoke. This is not an arbitrary-source runner: it calls
the fixed imported frame function, checks that the request declares its bytes,
and never imports/executes the request entrypoint or a supplied shell command.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import scene
from cutvoke.storage.generated_requests import snapshot_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    with snapshot_request(args.request) as (request, _stage, _root):
        declared = {item["path"]: item for item in request["files"]}
        expected = hashlib.sha256(Path(scene.__file__).read_bytes()).hexdigest()
        out = request["output"]
        params = request["params"]
        if (request["entrypoint"] != "scene.py" or declared["scene.py"]["sha256"] != expected
                or set(params) != {"kind", "accent"} or params["kind"] not in ("title", "chart", "annotation")
                or len(params["accent"]) != 3 or any(type(n) is not int or not 0 <= n <= 255 for n in params["accent"])
                or out["width"] != scene.WIDTH or out["height"] != scene.HEIGHT
                or out["fps"] != {"num": scene.FPS, "den": 1} or out["durationFrames"] != scene.FRAMES
                or bool(out["alphaMode"] == "straight") != bool(params["kind"] == "annotation")
                or out["format"] != ("prores4444" if params["kind"] == "annotation" else "mp4")):
            raise ValueError("reference renderer accepts only the fixed original 640x360/24fps/72-frame scene contract")
        window = request["frameRange"]
        command = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "640x360",
                   "-r", "24", "-i", "pipe:0", "-an", "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709",
                   "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
        if out["format"] == "prores4444":
            command += ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
                        "-bsf:v", "prores_metadata=color_primaries=bt709:color_trc=bt709:colorspace=bt709"]
        else:
            command += ["-c:v", "libx264", "-preset", "fast", "-crf", "18" if request["profile"] == "final" else "28",
                        "-pix_fmt", "yuv420p", "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1"]
        command += [str(args.output)]
        hashes = []
        with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
            try:
                # Absolute logical frame number, never reset animation to zero.
                for index in range(window["startFrame"], window["startFrame"] + window["frameCount"]):
                    raw = scene.frame(params["kind"], index, params["accent"]).tobytes()
                    hashes.append(hashlib.sha256(raw).hexdigest())
                    process.stdin.write(raw)
            finally:
                process.stdin.close()
            if process.wait(timeout=60):
                raise RuntimeError("reference scene encoding failed")
        args.proof.write_text(json.dumps({"absoluteFrameRange": window, "rgbaFrameHashes": hashes,
                                          "encoderCommand": command, "sourceExecutionPolicy": "fixed-reviewed-function-only"}, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()

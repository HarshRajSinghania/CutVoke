"""Bounded render requests and a verified-output index. No source execution.

Only metadata is evicted. Imported media and source archives remain ordinary
project assets and must never be removed by this cache.
"""
from __future__ import annotations

from contextlib import contextmanager
from fractions import Fraction
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import time

from cutvoke.storage.generated_media import (
    MAX_INPUT_BYTES, MAX_MANIFEST_BYTES, SHA, _copy_checked,
    _file_entry, _integer, _object, _text, canonical, file_hash,
)

MAX_ENTRIES = 256
REQUEST_FILE = "cutvoke-request.json"
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")


def _number(value):
    return type(value) in (int, float) and abs(value) <= 10**12 and math.isfinite(value)


def _definition(schema, *, scalar_only=False):
    if not isinstance(schema, dict):
        raise ValueError("parameter definitions must be objects")
    kind = schema.get("type")
    allowed = {"type", "title", "description", "enum"}
    if kind in ("number", "integer"):
        allowed |= {"minimum", "maximum"}
        if not all(_number(schema.get(k)) for k in ("minimum", "maximum")):
            raise ValueError("numeric parameters require finite minimum/maximum within ±1e12")
        if kind == "integer" and any(type(schema[k]) is not int for k in ("minimum", "maximum")):
            raise ValueError("integer bounds must be integers")
        if schema["minimum"] > schema["maximum"]:
            raise ValueError("parameter minimum exceeds maximum")
    elif kind == "string":
        allowed |= {"minLength", "maxLength"}
        _integer(schema.get("minLength"), 0, 2048, "minLength")
        _integer(schema.get("maxLength"), schema["minLength"], 2048, "maxLength")
    elif kind == "boolean":
        pass
    elif kind == "array" and not scalar_only:
        allowed = {"type", "title", "description", "items", "minItems", "maxItems"}
        _integer(schema.get("minItems"), 0, 64, "minItems")
        _integer(schema.get("maxItems"), schema["minItems"], 64, "maxItems")
        _definition(schema.get("items"), scalar_only=True)
    else:
        raise ValueError("parameters support scalars and bounded scalar arrays only")
    if set(schema) - allowed:
        raise ValueError("unsupported parameter schema keywords (no references, patterns or code)")
    for field in ("title", "description"):
        if field in schema:
            _text(schema[field], field)
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not 1 <= len(values) <= 32:
            raise ValueError("enum must contain 1..32 values")
        base = {k: v for k, v in schema.items() if k != "enum"}
        for value in values:
            _value(value, base)
        if len({canonical(value) for value in values}) != len(values):
            raise ValueError("enum values must be distinct")


def _value(value, schema):
    kind = schema["type"]
    valid = False
    if kind in ("number", "integer"):
        valid = _number(value) and (kind != "integer" or type(value) is int)
        valid = valid and schema["minimum"] <= value <= schema["maximum"]
    elif kind == "boolean":
        valid = type(value) is bool
    elif kind == "string":
        valid = isinstance(value, str) and schema["minLength"] <= len(value) <= schema["maxLength"]
    elif kind == "array":
        valid = isinstance(value, list) and schema["minItems"] <= len(value) <= schema["maxItems"]
        if valid:
            for item in value:
                _value(item, schema["items"])
    if not valid or ("enum" in schema and canonical(value) not in [canonical(v) for v in schema["enum"]]):
        raise ValueError("parameter value does not match its bounded schema")


def validate_params(schema, params):
    _object(schema, ("type", "properties", "required", "additionalProperties"), "paramsSchema")
    props = schema["properties"]
    if (schema["type"] != "object" or schema["additionalProperties"] is not False
            or not isinstance(props, dict) or not 1 <= len(props) <= 32
            or any(not isinstance(key, str) or not NAME.fullmatch(key) for key in props)):
        raise ValueError("paramsSchema must be a closed flat object with 1..32 named properties")
    required = schema["required"]
    if (not isinstance(required, list) or any(not isinstance(key, str) for key in required)
            or len(required) != len(props) or set(required) != set(props)):
        raise ValueError("all declared parameters must be required exactly once")
    if not isinstance(params, dict) or set(params) != set(props):
        raise ValueError("params must contain exactly the declared properties")
    for key, definition in props.items():
        _definition(definition)
        try:
            _value(params[key], definition)
        except ValueError as error:
            raise ValueError(f"invalid parameter {key}: {error}") from error


def _read(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("render request exceeds 256 KiB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate render-request key: {key}")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def load_request(path, params=None, frame_range=None):
    path = Path(path).expanduser().resolve(strict=True)
    request = _read(path)
    _object(request, ("kind", "schemaVersion", "renderer", "entrypoint", "files", "bindings",
                      "paramsSchema", "params", "seed", "output", "profile", "frameRange"), "render request")
    if request["kind"] != "cutvoke.generated-render-request" or type(request["schemaVersion"]) is not int or request["schemaVersion"] != 1:
        raise ValueError("unsupported render request kind/schemaVersion")
    _object(request["renderer"], ("name", "version", "build"), "renderer")
    for name, value in request["renderer"].items():
        _text(value, "renderer." + name)
    files = request["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 127:
        raise ValueError("files must declare 1..127 inputs")
    names = {}
    for item in files:
        _object(item, ("path", "sha256", "role"), "input")
        _file_entry(item, path.parent, "input")
        if item["path"] in names or item["path"].split("/")[0] in ("manifest.json", REQUEST_FILE):
            raise ValueError("duplicate or reserved input path")
        if item["role"] not in ("source", "asset", "font", "lockfile", "license"):
            raise ValueError("invalid input role")
        names[item["path"]] = item["role"]
    if not isinstance(request["entrypoint"], str) or names.get(request["entrypoint"]) != "source":
        raise ValueError("entrypoint must name a declared source input")
    bindings = request["bindings"]
    if (not isinstance(bindings, dict) or len(bindings) > 32
            or any(not isinstance(name, str) or not NAME.fullmatch(name)
                   or not isinstance(target, str) or names.get(target) not in ("asset", "font")
                   for name, target in bindings.items())):
        raise ValueError("bindings must name declared asset/font files")
    validate_params(request["paramsSchema"], request["params"])
    if params is not None:
        if not isinstance(params, dict) or set(params) - set(request["params"]):
            raise ValueError("parameter overrides must name declared properties")
        request["params"].update(copy.deepcopy(params))
        validate_params(request["paramsSchema"], request["params"])
    _integer(request["seed"], 0, 2**32 - 1, "seed")
    output = request["output"]
    _object(output, ("width", "height", "fps", "durationFrames", "alphaMode", "colorSpace", "audioMode", "format"), "output")
    for field in ("width", "height"):
        _integer(output[field], 16, 4096, field)
    _object(output["fps"], ("num", "den"), "fps")
    _integer(output["fps"]["num"], 1, 120000, "fps.num")
    _integer(output["fps"]["den"], 1, 10000, "fps.den")
    fps = Fraction(output["fps"]["num"], output["fps"]["den"])
    _integer(output["durationFrames"], 1, 18000, "durationFrames")
    if not 1 <= fps <= 120 or output["durationFrames"] / fps > 600:
        raise ValueError("render request must be 1..120 fps and at most 600 seconds")
    if (output["format"] not in ("mp4", "prores4444") or output["alphaMode"] not in ("opaque", "straight")
            or output["colorSpace"] != "bt709" or output["audioMode"] != "none"
            or (output["alphaMode"] == "straight" and output["format"] != "prores4444")):
        raise ValueError("output requires MP4/ProRes 4444, BT.709, separate audio; straight alpha needs ProRes")
    if request["profile"] not in ("review", "final"):
        raise ValueError("profile must be review or final")
    if frame_range is not None:
        request["frameRange"] = copy.deepcopy(frame_range)
    window = request["frameRange"]
    _object(window, ("startFrame", "frameCount"), "frameRange")
    _integer(window["startFrame"], 0, output["durationFrames"] - 1, "startFrame")
    _integer(window["frameCount"], 1, output["durationFrames"] - window["startFrame"], "frameCount")
    if len(canonical(request)) > MAX_MANIFEST_BYTES:
        raise ValueError("effective render request exceeds 256 KiB")
    return request, path.parent


def keys(request):
    source = {key: value for key, value in request.items() if key != "frameRange"}
    return (hashlib.sha256(canonical(request)).hexdigest(), hashlib.sha256(canonical(source)).hexdigest())


@contextmanager
def snapshot_request(path, params=None, frame_range=None):
    request, root = load_request(path, params, frame_range)
    with tempfile.TemporaryDirectory(prefix="cutvoke-request-") as folder:
        stage = Path(folder)
        inputs = stage / "inputs"
        inputs.mkdir()
        budget = MAX_INPUT_BYTES - len(canonical(request))
        if budget < 0:
            raise ValueError("render request input budget exceeded")
        for item in request["files"]:
            target = inputs / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            budget -= _copy_checked(_file_entry(item, root, "input"), target, item["sha256"], budget)
        (inputs / REQUEST_FILE).write_bytes(canonical(request))
        yield request, stage, root


def changes(before, after):
    result = [key for key in ("renderer", "files", "bindings", "paramsSchema", "seed", "output", "profile", "frameRange")
              if before.get(key) != after.get(key)]
    result += ["params." + key for key in sorted(set(before.get("params", {})) | set(after["params"]))
               if before.get("params", {}).get(key) != after["params"].get(key)]
    return result


class GeneratedRenderCache:
    """Small cross-process index; cached asset/source bytes are rehashed on lookup."""
    def __init__(self, media_dir):
        self.directory = Path(media_dir).resolve() / ".generated"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "render-index.sqlite"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    key TEXT PRIMARY KEY, composition TEXT NOT NULL, start INTEGER NOT NULL,
                    count INTEGER NOT NULL, document TEXT NOT NULL, accessed INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS outputs (
                    key TEXT NOT NULL, hash TEXT NOT NULL, asset TEXT NOT NULL,
                    bundle TEXT NOT NULL, archive_hash TEXT NOT NULL, PRIMARY KEY(key,hash));
                CREATE TABLE IF NOT EXISTS conflicts (composition TEXT PRIMARY KEY);
                CREATE INDEX IF NOT EXISTS coverage ON requests(composition,start,count);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def document(self, key):
        if not isinstance(key, str) or not SHA.fullmatch(key):
            raise ValueError("request key must be lowercase SHA256")
        with self._db() as db:
            row = db.execute("SELECT document FROM requests WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def record(self, request, receipt):
        key, composition = keys(request)
        window = request["frameRange"]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?,?,?,?)", (key, composition,
                window["startFrame"], window["frameCount"], canonical(request).decode(), time.time_ns()))
            existing = db.execute("SELECT document FROM requests WHERE key=?", (key,)).fetchone()
            if existing[0] != canonical(request).decode():
                raise ValueError("cached request document failed integrity check")
            if db.execute("SELECT COUNT(*) FROM outputs WHERE key=?", (key,)).fetchone()[0] < 2:
                db.execute("INSERT OR IGNORE INTO outputs VALUES (?,?,?,?,?)", (key,
                    receipt["assetId"].removeprefix("asset_"), receipt["assetId"], receipt["bundleId"], receipt["sourceArchive"]["sha256"]))
            if db.execute("SELECT COUNT(*) FROM outputs WHERE key=?", (key,)).fetchone()[0] > 1:
                db.execute("INSERT OR IGNORE INTO conflicts VALUES (?)", (composition,))
            db.execute("UPDATE requests SET accessed=? WHERE key=?", (time.time_ns(), key))
            # Evict index entries only. No media/archive/source file is deleted.
            old = db.execute("SELECT key FROM requests ORDER BY accessed DESC,key LIMIT -1 OFFSET ?", (MAX_ENTRIES,)).fetchall()
            for (expired,) in old:
                db.execute("DELETE FROM outputs WHERE key=?", (expired,))
                db.execute("DELETE FROM requests WHERE key=?", (expired,))
            db.execute("DELETE FROM conflicts WHERE composition NOT IN (SELECT composition FROM requests)")
        return self.status()

    def status(self):
        with self._db() as db:
            count = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            blocked = db.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0]
        return {"entries": count, "maxEntries": MAX_ENTRIES, "conflictingCompositions": blocked,
                "eviction": "index_only", "sourceExecution": False}

    def lookup(self, request, store, media_path):
        key, composition = keys(request)
        start = request["frameRange"]["startFrame"]
        count = request["frameRange"]["frameCount"]
        with self._db() as db:
            if db.execute("SELECT 1 FROM conflicts WHERE composition=?", (composition,)).fetchone():
                return {"hit": False, "reason": "conflicting_outputs"}
            rows = db.execute("SELECT key,start,count,document FROM requests WHERE composition=? AND start<=? AND start+count>=? ORDER BY count,accessed DESC",
                              (composition, start, start + count)).fetchall()
            reason = "not_found"
            for candidate, rendered_start, rendered_count, document in rows:
                saved = json.loads(document)
                if keys(saved)[0] != candidate or keys(saved)[1] != composition:
                    raise ValueError("cached request document failed integrity check")
                outputs = db.execute("SELECT hash,asset,bundle,archive_hash FROM outputs WHERE key=?", (candidate,)).fetchall()
                if len(outputs) != 1:
                    reason = "invalid_output_index"
                    continue
                digest, asset_id, bundle, archive_hash = outputs[0]
                if not all(isinstance(value, str) and SHA.fullmatch(value) for value in (digest, bundle, archive_hash)) or asset_id != "asset_" + digest:
                    raise ValueError("invalid generated-render cache identity")
                asset = store.get_asset(asset_id)
                path = media_path(asset) if asset else None
                archive = self.directory / (bundle + ".cvsource.zip")
                if not path or not path.is_file():
                    reason = "cached_media_missing"
                    continue
                if file_hash(path) != digest:
                    reason = "cached_media_changed"
                    continue
                if not archive.is_file() or archive.is_symlink() or file_hash(archive) != archive_hash:
                    reason = "cached_source_archive_changed"
                    continue
                db.execute("UPDATE requests SET accessed=? WHERE key=?", (time.time_ns(), candidate))
                fps = Fraction(request["output"]["fps"]["num"], request["output"]["fps"]["den"])
                offset = Fraction(start - rendered_start, 1) / fps
                return {"hit": True, "kind": "exact" if candidate == key else "covering",
                        "renderedRequestKey": candidate, "assetId": asset_id,
                        "mediaSourceStart": {"num": str(offset.numerator), "den": str(offset.denominator)},
                        "renderedFrameRange": {"startFrame": rendered_start, "frameCount": rendered_count},
                        "sourceArchive": {"path": str(archive), "sha256": archive_hash}}
        return {"hit": False, "reason": reason}

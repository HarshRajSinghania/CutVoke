"""Bounded creative discovery and read-only, revision-bound production artifacts.

These contracts organize external judgment; they do not infer meaning, watch
media, validate rights, or assign an artistic score. Repairs use the existing
transaction preview and never commit through this interface.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from cutvoke.domain.protocol import Command
from cutvoke.domain.rational import Rational


CATALOG_PATH = Path(__file__).resolve().parents[1] / "catalogs" / "creative_recipes.json"
TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
ID = {"type": "string", "minLength": 1, "maxLength": 200}


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def array(items, minimum=0, maximum=64):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


TIME = obj({"num": {"type": "string", "pattern": r"^[0-9]{1,16}$"},
            "den": {"type": "string", "pattern": r"^[1-9][0-9]{0,15}$"}})
RANGE = obj({"start": TIME, "end": TIME})
BASE = {"schemaVersion": {"type": "integer", "enum": [1]}, "kind": ID,
        "projectId": ID, "revision": ID, "sequenceId": ID}
CHECKS = ["technical", "frames", "cut-neighborhood", "continuous-av",
          "mobile-readability", "meaning-source-check"]
PLAN = obj({**BASE, "recipeId": ID,
    "brief": obj({"purpose": ID, "audience": TEXT, "takeaway": TEXT, "successCriterion": TEXT}),
    "delivery": obj({"width": {"type": "integer", "minimum": 16, "maximum": 16384},
                     "height": {"type": "integer", "minimum": 16, "maximum": 16384},
                     "viewingContext": TEXT}),
    "assetRoles": array(obj({"id": ID, "assetId": ID, "role": TEXT, "sourceRange": RANGE,
        "provenance": {"type": "string", "enum": ["recorded", "archive", "generated", "illustration"]},
        "rightsNote": TEXT}), 1),
    "protectedRanges": array(obj({"clipId": ID, "range": RANGE, "reason": TEXT})),
    "beats": array(obj({"id": ID, "range": RANGE, "clipIds": array(ID, 1), "selectionIds": array(ID, 1),
                       "intent": TEXT, "audioIntent": TEXT, "captionIntent": TEXT}), 1),
    "gaps": array(TEXT), "intentionalExceptions": array(TEXT),
    "reviewRequirements": array({"type": "string", "enum": CHECKS}, 1)})
REVIEW = obj({**BASE,
    "evidence": array(obj({"id": ID, "kind": {"type": "string", "enum": CHECKS},
        "range": RANGE, "artifact": TEXT,
        "inspection": {"type": "string", "enum": ["pending", "inspected"]},
        "inspector": TEXT, "observation": TEXT}), 1),
    "issues": array(obj({"id": ID, "range": RANGE,
        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
        "observation": TEXT, "evidenceIds": array(ID, 1), "suggestedAction": TEXT,
        "preserve": array(TEXT, 1), "status": {"type": "string", "enum": ["open", "resolved"]}})),
    "unassessed": array(TEXT)})
REPAIR = obj({**BASE, "issueIds": array(ID, 1, 16), "scope": RANGE,
    "commands": array(obj({"type": ID, "payload": {"type": "object"}}), 1, 32),
    "preserveClipIds": array(ID), "rationale": TEXT,
    "recheckRanges": array(RANGE, 1), "recheckRequirements": array({"type": "string", "enum": CHECKS}, 1)})
SCHEMAS = {"plan": PLAN, "review": REVIEW, "repair": REPAIR}
for _kind, _schema in SCHEMAS.items():
    _schema["properties"]["kind"] = {"type": "string", "enum": [_kind]}

TOOL = {"name": "creative_workflow", "description":
    "Discover bilingual purpose/style recipes with bounded topic search, retrieve one recipe or plan/review/repair schema, validate revision-bound artifacts, or dry-run a local repair. No media generation, file reading/writing, upload or project commit. Technical validation never proves artistic acceptance. Start operation=list with query or purpose; help: editor_help(topic=creative).",
    "inputSchema": obj({
        "operation": {"type": "string", "enum": ["list", "recipe", "schema", "validate", "preview-repair"]},
        "query": {"type": "string", "maxLength": 120}, "purpose": ID, "style": ID,
        "locale": {"type": "string", "enum": ["en", "zh-CN"], "default": "en"},
        "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
        "recipeId": ID, "kind": {"type": "string", "enum": list(SCHEMAS)},
        "document": {"type": "object"}, "plan": {"type": "object"}, "review": {"type": "object"}}, ["operation"])}


@lru_cache(maxsize=1)
def _catalog():
    try:
        return json.loads(CATALOG_PATH.read_text("utf8"))
    except (OSError, ValueError) as error:
        raise ValueError("Bundled creative recipes unavailable; repair the CutVoke package") from error


def _budget(value, depth=0):
    if depth > 20:
        raise ValueError("creative artifact nesting exceeds 20")
    if isinstance(value, dict):
        if len(value) > 128:
            raise ValueError("too many artifact fields")
        for child in value.values():
            _budget(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 256:
            raise ValueError("too many artifact items")
        for child in value:
            _budget(child, depth + 1)
    elif isinstance(value, str) and len(value) > 2000:
        raise ValueError("artifact string exceeds 2000 characters")


def _range(value):
    start, end = (Rational.from_json(**value[key]) for key in ("start", "end"))
    if not Rational.of(0) <= start < end:
        raise ValueError("ranges require 0 <= start < end (end exclusive)")
    return start, end


def _contains(outer, inner):
    a, b = _range(outer)
    c, d = _range(inner)
    return a <= c and d <= b


def _overlap(a, b):
    a0, a1 = _range(a)
    b0, b1 = _range(b)
    return a0 < b1 and b0 < a1


def _unique(items, key="id"):
    values = [item[key] for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {key}")


def _contract(document, kind):
    from cutvoke.interfaces.mcp_server import MCPServer
    _budget(document)
    MCPServer._validate_arguments(document, SCHEMAS[kind], kind)
    _string_limits(document, SCHEMAS[kind])
    # MCP's generic validator intentionally supports a subset of JSON Schema.
    # Apply bounded strings here too, including nested command payload values.
    def ranges(value):
        if isinstance(value, dict):
            if set(value) == {"start", "end"}:
                _range(value)
            for child in value.values():
                ranges(child)
        elif isinstance(value, list):
            for child in value:
                ranges(child)
    ranges(document)


def _string_limits(value, schema):
    if isinstance(value, str) and len(value) > schema.get("maxLength", 2000):
        raise ValueError("creative field exceeds its maximum string length")
    if isinstance(value, dict):
        for key, child in value.items():
            _string_limits(child, schema.get("properties", {}).get(key, {}))
    elif isinstance(value, list):
        for child in value:
            _string_limits(child, schema.get("items", {}))


class CreativeWorkflow:
    def __init__(self, service):
        self.service = service

    def call(self, a):
        from cutvoke.interfaces.mcp_server import MCPServer
        _budget(a)
        if len(json.dumps(a, ensure_ascii=False, allow_nan=False).encode("utf8")) > 131072:
            raise ValueError("creative request exceeds 128 KiB")
        MCPServer._validate_arguments(a, TOOL["inputSchema"])
        _string_limits(a, TOOL["inputSchema"])
        op = a["operation"]
        allowed = {"list": {"query", "purpose", "style", "locale", "offset", "limit"},
                   "recipe": {"recipeId", "locale"}, "schema": {"kind"},
                   "validate": {"document", "plan", "review"},
                   "preview-repair": {"document", "plan", "review"}}[op]
        if set(a) - allowed - {"operation"}:
            raise ValueError(f"irrelevant fields for operation={op}")
        if op in ("list", "recipe"):
            return self.discover(a)
        if op == "schema":
            if "kind" not in a:
                raise ValueError("schema requires kind")
            return {"schema": copy.deepcopy(SCHEMAS[a["kind"]]), "schemaVersion": 1,
                    "timeConvention": "Exact rational seconds; end exclusive; sequence-local timeline ranges.",
                    "storage": "Agent-owned project-local JSON; validation does not save artifacts."}
        if "document" not in a:
            raise ValueError(f"{op} requires document")
        kind = a["document"].get("kind")
        if kind not in SCHEMAS:
            raise ValueError("document.kind must be plan, review or repair")
        if op == "preview-repair" and kind != "repair":
            raise ValueError("preview-repair requires a repair document")
        documents = [(kind, a["document"])]
        if kind == "repair":
            for key in ("plan", "review"):
                if key not in a:
                    raise ValueError(f"repair requires {key} context")
                documents.append((key, a[key]))
        elif set(a) & {"plan", "review"}:
            raise ValueError("plan/review context is only accepted for repair")
        for doc_kind, doc in documents:
            _contract(doc, doc_kind)
        document = a["document"]
        project = self.service.get_project(document["projectId"])
        findings = []
        def problem(code, message):
            findings.append({"code": code, "message": message})
        for doc_kind, doc in documents:
            if any(doc[field] != document[field] for field in ("projectId", "revision", "sequenceId")):
                problem("CONTEXT_MISMATCH", f"{doc_kind} belongs to a different project/revision/sequence")
            if doc["revision"] != project.revision:
                problem("STALE_REVISION", f"{doc_kind}: reread current revision {project.revision}, rebuild evidence and preview")
            if doc["sequenceId"] != project.sequence.id:
                problem("SEQUENCE_MISMATCH", f"{doc_kind}: only the active sequence can be validated")
        clips = {clip.id: clip for track in project.sequence.tracks for clip in track.clips}
        duration = max((clip.timeline_end for clip in clips.values()), default=Rational.of(0))
        timeline = {"start": Rational.of(0).to_json(), "end": duration.to_json()}
        def timeline_range(value, name):
            if duration <= Rational.of(0) or not _contains(timeline, value):
                problem("OUTSIDE_TIMELINE", name)
        for doc_kind, doc in documents:
            if doc_kind == "plan":
                self.check_plan(doc, project, clips, problem, timeline_range)
            elif doc_kind == "review":
                self.check_review(doc, problem, timeline_range)
        if kind == "repair":
            self.check_repair(document, a["plan"], a["review"], clips, problem, timeline_range)
        result = {"contractValid": not findings, "findings": findings,
                  "currentRevision": project.revision, "technicalValidationOnly": True,
                  "creativeAcceptance": "not_assessed", "committed": False,
                  "evidenceLimit": "References and inspection declarations are checked, not media bytes, perception, facts or rights."}
        if kind == "review":
            result["pendingEvidenceIds"] = [e["id"] for e in document["evidence"] if e["inspection"] != "inspected"]
        if op == "preview-repair" and not findings:
            self.preview(document, a["plan"], project, clips, result, problem)
            result["contractValid"] = not findings
        return result

    def discover(self, a):
        data = _catalog()
        locale = a.get("locale", "en")
        if a["operation"] == "recipe":
            if "recipeId" not in a:
                raise ValueError("recipe requires recipeId")
            recipe = next((r for r in data["recipes"] if r["id"] == a["recipeId"]), None)
            if recipe is None:
                raise ValueError("unknown recipeId; use operation=list")
            result = {key: copy.deepcopy(value) for key, value in recipe.items() if key != "content"}
            result.update(copy.deepcopy(recipe["content"][locale]))
            result["sources"] = [data["sources"][key] for key in recipe["sourceIds"]]
            result["workflow"] = copy.deepcopy(data["workflow"])
            result["qualityClaim"] = data["qualityClaim"]
            return {"recipe": result, "locale": locale, "version": 1}
        for field, choices in (("purpose", data["purposes"]), ("style", data["styles"])):
            if field in a and a[field] not in choices:
                raise ValueError(f"unknown {field}; choose from {', '.join(choices)}")
        query = a.get("query", "").strip().casefold()
        recipes = [r for r in data["recipes"]
                   if (not a.get("purpose") or a["purpose"] in r["purposes"])
                   and (not a.get("style") or r["style"] == a["style"])
                   and query in json.dumps([r["id"], r["purposes"], r["style"], r["tags"],
                       *[r["content"][lang]["title"] for lang in ("en", "zh-CN")]], ensure_ascii=False).casefold()]
        offset, limit = a.get("offset", 0), a.get("limit", 3)
        return {"recipes": [{"id": r["id"], "purposes": r["purposes"], "style": r["style"],
                             "title": r["content"][locale]["title"],
                             "request": {"operation": "recipe", "recipeId": r["id"], "locale": locale}}
                            for r in recipes[offset:offset + limit]],
                "total": len(recipes), "nextOffset": offset + limit if offset + limit < len(recipes) else None,
                "purposes": data["purposes"], "styles": data["styles"], "version": 1}

    def check_plan(self, doc, project, clips, problem, check_range):
        recipe = next((r for r in _catalog()["recipes"] if r["id"] == doc["recipeId"]), None)
        if recipe is None or doc["brief"]["purpose"] not in recipe["purposes"]:
            problem("RECIPE_PURPOSE", "recipeId and primary purpose must match the catalog")
        if (doc["delivery"]["width"], doc["delivery"]["height"]) != (project.sequence.width, project.sequence.height):
            problem("DELIVERY_MISMATCH", "delivery dimensions differ from the active sequence")
        _unique(doc["beats"])
        _unique(doc["assetRoles"])
        selections = {item["id"]: item for item in doc["assetRoles"]}
        known_assets = {c.asset_ref.asset_id for c in clips.values()}
        for item in doc["assetRoles"]:
            asset = (self.service.store.get_project_asset(project.project_id, item["assetId"])
                     if self.service.store else None)
            if item["assetId"] not in known_assets and not asset:
                problem("UNKNOWN_ASSET", item["assetId"])
            if asset and asset.get("duration") is not None and asset.get("kind") != "image":
                if _range(item["sourceRange"])[1] > Rational.from_float(asset["duration"]):
                    problem("SOURCE_RANGE", item["id"])
        for item in doc["protectedRanges"]:
            clip = clips.get(item["clipId"])
            if clip is None:
                problem("UNKNOWN_CLIP", item["clipId"])
            elif not _contains({"start": clip.timeline_start.to_json(), "end": clip.timeline_end.to_json()}, item["range"]):
                problem("PROTECTION_RANGE", item["clipId"])
        for beat in doc["beats"]:
            check_range(beat["range"], beat["id"])
            for key in beat["selectionIds"]:
                if key not in selections:
                    problem("UNKNOWN_SELECTION", key)
                elif not any(clips[c].asset_ref.asset_id == selections[key]["assetId"]
                             for c in beat["clipIds"] if c in clips):
                    problem("SELECTION_CLIP_ASSET", key)
            for clip_id in beat["clipIds"]:
                clip = clips.get(clip_id)
                if clip is None:
                    problem("UNKNOWN_CLIP", clip_id)
                elif not _overlap(beat["range"], {"start": clip.timeline_start.to_json(), "end": clip.timeline_end.to_json()}):
                    problem("BEAT_CLIP_RANGE", clip_id)

    @staticmethod
    def check_review(doc, problem, check_range):
        _unique(doc["evidence"])
        _unique(doc["issues"])
        evidence = {e["id"]: e for e in doc["evidence"]}
        for item in doc["evidence"]:
            check_range(item["range"], item["id"])
        for issue in doc["issues"]:
            check_range(issue["range"], issue["id"])
            for key in issue["evidenceIds"]:
                if key not in evidence or not _overlap(issue["range"], evidence[key]["range"]):
                    problem("ISSUE_EVIDENCE", f"{issue['id']}: missing or unrelated evidence {key}")

    @staticmethod
    def check_repair(doc, plan, review, clips, problem, check_range):
        check_range(doc["scope"], "repair.scope")
        issues = {i["id"]: i for i in review["issues"]}
        evidence = {e["id"]: e for e in review["evidence"]}
        for key in doc["issueIds"]:
            issue = issues.get(key)
            if issue is None or issue["status"] != "open" or not _contains(doc["scope"], issue["range"]):
                problem("REPAIR_ISSUE", f"{key}: requires an open issue inside scope")
            elif any(evidence.get(e, {}).get("inspection") != "inspected" for e in issue["evidenceIds"]):
                problem("UNINSPECTED_EVIDENCE", key)
        for clip_id in doc["preserveClipIds"]:
            if clip_id not in clips:
                problem("UNKNOWN_CLIP", clip_id)
        for value in doc["recheckRanges"]:
            check_range(value, "repair.recheckRanges")
        if not any(_contains(value, doc["scope"]) for value in doc["recheckRanges"]):
            problem("RECHECK_COVERAGE", "one recheck range must contain the repair scope and affected context")
        if not set(plan["reviewRequirements"]).issubset(doc["recheckRequirements"]):
            problem("RECHECK_REQUIREMENTS", "retain the plan's review requirements after repair")

    def preview(self, doc, plan, project, clips, result, problem):
        if any(c["type"].startswith("composition.") or "compositionPath" in c["payload"]
               for c in doc["commands"]):
            problem("COMPOSITION_REQUIRES_CONTEXT", "Use the ordinary explicit workflow for nested/shared composition edits; instance impact mapping is not supported here")
            result["readyForCommandApply"] = False
            return
        payload = {"commands": doc["commands"]}
        preview = self.service.preview_command(Command(type="edit.batch", payload=payload,
            project_id=project.project_id, expected_revision=doc["revision"]), include_project=True)
        candidate = preview.pop("project")
        after_clips = {c.id: c for t in candidate.sequence.tracks for c in t.clips}
        for key in doc["preserveClipIds"]:
            if key not in after_clips or after_clips[key].to_dict() != clips[key].to_dict():
                problem("PRESERVE_CHANGED", key)
        # A handler's changedEntities is explanatory metadata, not authority for
        # safety. Compare actual candidates, including hidden shared masters and
        # global/track state; nested clip IDs may collide with active IDs.
        def skeleton(value):
            data = value.to_dict(compact=True)
            for sequence in data["sequences"]:
                if sequence["id"] == project.sequence.id:
                    sequence.pop("captions", None)
                    for track in sequence["tracks"]:
                        track.pop("clips", None)
            return data
        if skeleton(candidate) != skeleton(project):
            problem("UNBOUNDED_CHANGE", "non-active sequence, project, sequence or track settings changed")
        def entities(value):
            found = {}
            for track in value.sequence.tracks:
                for clip in track.clips:
                    found[("clip", clip.id)] = ({"trackId": track.id, **clip.to_dict()}, {"start": clip.timeline_start.to_json(), "end": clip.timeline_end.to_json()})
            for caption in value.sequence.captions:
                found[("caption", caption.id)] = (caption.to_dict(), {"start": caption.start.to_json(), "end": caption.end.to_json()})
            return found
        before_entities, after_entities = entities(project), entities(candidate)
        for clip_id in doc["preserveClipIds"]:
            if before_entities.get(("clip", clip_id)) != after_entities.get(("clip", clip_id)):
                problem("PRESERVE_CHANGED", clip_id)
        # A controller can alter an unchanged clip at another time. Until the
        # repair contract carries dependency-expanded impacts, conservatively
        # route clip edits in linked projects to the ordinary explicit workflow.
        linked = any(c.property_links or c.compositing.get("matte")
                     for s in project.sequences for t in s.tracks for c in t.clips)
        # Master/track/bus processors and sidechains can change untouched time
        # ranges (e.g. whole-program loudness normalization or compressor state).
        # Do not equate unchanged mixer JSON with unchanged rendered samples.
        audio_dependencies = any(s.master_audio or s.audio_buses or any(t.audio_mix for t in s.tracks)
                                 for s in project.sequences)
        def sidechain(value):
            if isinstance(value, dict):
                return any("sidechain" in str(key).casefold()
                           or (key == "effectId" and isinstance(child, str) and "sidechain" in child.casefold())
                           or sidechain(child)
                           for key, child in value.items())
            return isinstance(value, list) and any(sidechain(child) for child in value)
        audio_dependencies = audio_dependencies or sidechain(project.to_dict(compact=True))
        if linked and any(key[0] == "clip" and before_entities.get(key) != after_entities.get(key)
                          for key in before_entities.keys() | after_entities.keys()):
            problem("DEPENDENCY_REQUIRES_CONTEXT", "clip edits in projects with propertyLinks/track mattes require dependency-aware ordinary review")
        if audio_dependencies and any(key[0] == "clip" and before_entities.get(key) != after_entities.get(key)
                                      for key in before_entities.keys() | after_entities.keys()):
            problem("AUDIO_DEPENDENCY_REQUIRES_CONTEXT", "clip edits with master/track/bus processing or sidechains require full audio-context review")
        for key in before_entities.keys() | after_entities.keys():
            before, after = before_entities.get(key), after_entities.get(key)
            if before == after:
                continue
            for value in (before[1] if before else None, after[1] if after else None):
                if value and not _contains(doc["scope"], value):
                    problem("OUTSIDE_REPAIR_SCOPE", key[1])
                if value and any(_overlap(value, p["range"]) for p in plan["protectedRanges"]):
                    problem("PROTECTED_RANGE", key[1])
        result["preview"] = preview
        result["readyForCommandApply"] = not result["findings"]
        if not result["findings"]:
            result["nextCall"] = {"tool": "command_apply", "arguments": {
                "projectId": project.project_id, "expectedRevision": doc["revision"],
                "type": "edit.batch", "payload": payload},
                "requires": ["editLeaseId from edit_lock", "stable commandId", "recheck current revision before commit"],
                "afterCommit": "Evidence is stale after any revision change. Rebuild review for the new revision; inspect recheckRanges then full continuous output."}

import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { runInNewContext } from "node:vm";
import ts from "typescript";
const { outputText } = ts.transpileModule(readFileSync(new URL("../src/lib/projectSync.ts", import.meta.url), "utf8"),
  { compilerOptions: {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022} });
const { expandProject, reuseProjectStructure } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const sequence = id => ({id,width:1920,height:1080,fps:{num:"30",den:"1"},tracks:[
  {id:"v",kind:"video",clips:[{id:"a",timelineStart:{num:"0",den:"1"}},{id:"b",timelineStart:{num:"5",den:"1"}}]},
  {id:"audio",kind:"audio",clips:[]}],captions:[]});
const raw = {schemaVersion:"1",projectId:"test",revision:"1",activeSequenceId:"s1",sequences:[sequence("s1"),sequence("s2")]};

test("compact decoding preserves every sequence and aliases the selected sequence", () => {
  const project = expandProject(structuredClone(raw));
  assert.equal(project.sequence,project.sequences[0]);
  const switched = expandProject({...raw,activeSequenceId:"s2"});
  assert.equal(switched.sequence,switched.sequences[1]);
  assert.equal(switched.sequences.length,2);
  assert.throws(()=>expandProject({...raw,activeSequenceId:"missing"}));
});
test("a single changed clip retains other clips, tracks and inactive sequence identities", () => {
  const previous=expandProject(structuredClone(raw)), updated=structuredClone(raw);
  updated.revision="2";
  updated.sequences[0].tracks[0].clips[0].timelineStart.num="1";
  const next=reuseProjectStructure(previous,expandProject(updated));
  assert.notEqual(next.sequence,previous.sequence);
  assert.notEqual(next.sequence.tracks[0].clips[0],previous.sequence.tracks[0].clips[0]);
  assert.equal(next.sequence.tracks[0].clips[1],previous.sequence.tracks[0].clips[1]);
  assert.equal(next.sequence.tracks[1],previous.sequence.tracks[1]);
  assert.equal(next.sequences[1],previous.sequences[1]);
  assert.equal(next.sequence,next.sequences[0]);
  assert.equal(previous.sequence.tracks[0].clips[0].timelineStart.num,"0");
});

// Load the actual transport/cache module with manually delivered HTTP responses.
// Each harness owns its module cache and old-service compatibility flag.
function apiHarness() {
  const requests = [];
  const { outputText } = ts.transpileModule(readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8"),
    { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } });
  const exports = {};
  runInNewContext(outputText, { exports, URLSearchParams, BigInt,
    require: name => ({
      "../i18n": { tr: value => value }, "../i18n/locale": { getLocale: () => "en" },
      "./projectSync": { expandProject, reuseProjectStructure },
    })[name] || {},
    fetch: url => new Promise(resolve => requests.push({ url, respond: (body, status = 200) =>
      resolve({ ok: status >= 200 && status < 300, status, json: async () => body }) })),
  });
  return { api: exports, requests };
}
const syncResponse = revision => ({ token: `token-${revision}`, unchanged: false,
  project: { ...structuredClone(raw), revision } });

for (const staleKind of ["unchanged", "changed"]) {
  test(`a delayed ${staleKind} sync response returns the newer cached project`, async () => {
    const { api, requests } = apiHarness();
    const initial = api.getProject("test");
    requests[0].respond(syncResponse("5"));
    await initial;
    const stale = api.getProject("test"), newer = api.getProject("test");
    assert.equal(requests[1].url, "/api/v1/projects/test/sync?token=token-5");
    requests[2].respond(syncResponse("6"));
    const current = await newer;
    requests[1].respond(staleKind === "unchanged" ? { token: "token-5", unchanged: true } : syncResponse("5"));
    assert.equal(await stale, current);
    // The delayed response must retain the newer conditional token as well.
    const next = api.getProject("test");
    assert.equal(requests[3].url, "/api/v1/projects/test/sync?token=token-6");
    requests[3].respond({ token: "token-6", unchanged: true });
    assert.equal(await next, current);
  });
}

test("an old service without compact sync keeps using the full project endpoint", async () => {
  const { api, requests } = apiHarness();
  const first = api.getProject("test");
  requests[0].respond({ error: { code: "NOT_FOUND", message: "unsupported" } }, 404);
  // Drive the fallback without relying on timers or scheduling races.
  for (let tick = 0; tick < 10 && requests.length < 2; tick++) await Promise.resolve();
  assert.equal(requests[1]?.url, "/api/v1/projects/test");
  const project = expandProject(syncResponse("5").project);
  requests[1].respond(project);
  assert.equal(await first, project);
  const next = api.getProject("test");
  assert.equal(requests[2].url, "/api/v1/projects/test");
  requests[2].respond({ ...project, revision: "6" });
  assert.equal((await next).revision, "6");
});

import { expect, test, type APIRequestContext } from "@playwright/test";

const deferred = () => { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); return { promise, release }; };
const rat = (num: number) => ({ num: String(num), den: "1" });
async function read(request: APIRequestContext, id: string) {
  return (await request.get(`/api/v1/projects/${id}`)).json();
}
async function edit(request: APIRequestContext, id: string, type: string, payload: object) {
  const project = await read(request, id);
  const response = await request.post(`/api/v1/projects/${id}/commands`, { data: { type, payload, expectedRevision: project.revision } });
  expect(response.ok(), await response.text()).toBeTruthy();
}

for (const outcome of ["success", "failure"] as const) {
  test(`obsolete preview reconciliation ${outcome} stays silent after reopening the same project`, async ({ page, request }) => {
    const id = `preview-owner-${outcome}-${Date.now()}`, name = `预览恢复 ${id}`;
    const source = (await read(request, "e2e-fixture")).sequence.tracks[0].clips[0].assetRef.sourcePath;
    expect((await request.post("/api/v1/projects", { data: { projectId: id, name, width: 160, height: 90, fps: 15 } })).ok()).toBeTruthy();
    await edit(request, id, "clip.insert", { clipId: "video", trackId: "v", createTrackKind: "video", sourcePath: source,
      timelineStart: rat(0), timelineEnd: rat(5) });
    for (const [index, text] of ["第一句", "第二句"].entries()) await edit(request, id, "caption.add", {
      captionId: `c${index}`, text, start: rat(index * 2), end: rat(index * 2 + 1),
    });
    const submission = deferred(), refresh = deferred();
    let submissions = 0, captureRefresh = false, captured = false;
    await page.route(`**/projects/${id}/preview-jobs`, async route => {
      if (++submissions === 1) {
        await submission.promise;
        return route.fulfill({ status: 409, json: { error: { code: "REVISION_CONFLICT", message: "superseded preview", retryable: true } } });
      }
      return route.fulfill({ status: 202, json: { jobId: `live-${id}`, state: "running", phase: "rendering", completedWindows: 0, totalWindows: 3, progress: 0 } });
    });
    await page.route(`**/preview-jobs/live-${id}`, route => route.fulfill({ json: {
      jobId: `live-${id}`, state: "running", phase: "rendering", completedWindows: 0, totalWindows: 3, progress: 0,
    } }));
    await page.route(`**/preview-jobs/live-${id}/cancel`, route => route.fulfill({ json: {} }));
    await page.route(`**/projects/${id}/sync*`, async route => {
      if (!captureRefresh) return route.continue();
      captureRefresh = false;
      const response = await route.fetch();
      captured = true;
      await refresh.promise;
      await route.fulfill(outcome === "success" ? { response, headers: { ...response.headers(), "x-obsolete-refresh": "1" } }
        : { status: 503, headers: { "x-obsolete-refresh": "1" }, json: { error: { code: "OLD_REFRESH_FAILED", message: "obsolete refresh must stay silent" } } });
    });
    try {
      await page.goto("/");
      await page.getByRole("button", { name: `打开工程 ${name}` }).click();
      await expect(page.getByRole("heading", { name: "时间线" })).toBeVisible();
      await expect.poll(() => submissions).toBe(1);
      await page.locator("#creative-domain-caption").click();
      await page.getByRole("button", { name: "删除字幕 c0", exact: true }).click();
      await expect(page.locator(".statusbar__msg")).toHaveText("已删除字幕");
      captureRefresh = true;
      submission.release();
      await expect.poll(() => captured).toBe(true);
      // Abort the old worker, then reopen the *same* project. An ID-only guard
      // cannot distinguish the old reconciliation from the new session.
      await page.getByRole("button", { name: "返回工程列表", exact: true }).click();
      await page.getByRole("button", { name: `打开工程 ${name}` }).click();
      await expect(page.getByRole("heading", { name: "时间线" })).toBeVisible();
      await page.locator("#creative-domain-caption").click();
      await page.getByRole("button", { name: "删除字幕 c1", exact: true }).click();
      await expect(page.locator(".statusbar__msg")).toHaveText("已删除字幕");
      const latest = await read(request, id);
      const delivered = page.waitForResponse(response => response.headers()["x-obsolete-refresh"] === "1");
      refresh.release(); await delivered;
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await expect(page.locator(".statusbar__msg")).toHaveText("已删除字幕");
      await expect(page.getByText("obsolete refresh must stay silent", { exact: false })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "删除字幕 c1", exact: true })).toHaveCount(0);
      await page.locator(".statusbar__details summary").click();
      await expect(page.locator(".statusbar__details-body")).toContainText(`Revision：${latest.revision}`);
      expect(await read(request, id)).toEqual(latest);
    } finally { submission.release(); refresh.release(); }
  });
}

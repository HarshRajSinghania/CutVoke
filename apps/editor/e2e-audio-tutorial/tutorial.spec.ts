import { expect, test } from '@playwright/test';

test('real tutorial remains editable in the browser', async ({ page, request }, info) => {
  const projectPath = '/api/v1/projects/audio-first';
  const before = await (await request.get(projectPath)).json();
  expect(before.sequence.captions).toHaveLength(3);
  expect(before.sequence.tracks.filter((t: {kind: string}) => t.kind === 'audio')).toHaveLength(2);
  await page.goto('/');
  await page.getByRole('button', { name: '打开工程 Audio first · editable tutorial', exact: true }).click();
  await page.getByRole('tablist', { name: '创作域' }).getByRole('tab', { name: '字幕', exact: true }).click();
  await page.getByRole('button', { name: '选择字幕 caption-1', exact: true }).click();
  await page.getByRole('textbox', { name: '编辑字幕文字' }).fill('An editable cue');
  await expect.poll(async () => (await (await request.get(projectPath)).json()).sequence.captions.find((c: {id:string}) => c.id === 'caption-1').text).toBe('An editable cue');
  await expect(page.locator('.cv-caption-row__text').filter({ hasText: 'An editable cue' })).toBeVisible();
  const edited = await (await request.get(projectPath)).json();
  const original = before.sequence.captions.find((c: {id:string}) => c.id === 'caption-1');
  const changed = edited.sequence.captions.find((c: {id:string}) => c.id === 'caption-1');
  expect(changed.start).toEqual(original.start); expect(changed.end).toEqual(original.end);
  await page.screenshot({ path: info.outputPath('editable-caption.png'), fullPage: true });
  await page.getByRole('button', { name: /^撤销/ }).first().click();
  await expect.poll(async () => (await (await request.get(projectPath)).json()).sequence.captions.find((c: {id:string}) => c.id === 'caption-1').text).toBe('A small cue');
  // Retain the actual server-rendered PNG, separately from the editor screenshot.
  const frame = await request.get(`${projectPath}/preview-frame?t=2.5&size=640x360`);
  expect(frame.ok()).toBeTruthy();
  const png = await frame.body();
  expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  await info.attach('real-preview.png', { body: png, contentType: 'image/png' });
});

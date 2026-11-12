import { defineConfig } from '@playwright/test';
const port = process.env.CUTVOKE_AUDIO_TUTORIAL_PORT || '8807';
export default defineConfig({
  testDir: './e2e-audio-tutorial', workers: 1, timeout: 90_000,
  outputDir: '../../.artifacts/test-results/audio-tutorial',
  expect: { timeout: 15_000 },
  use: { baseURL: `http://127.0.0.1:${port}`, browserName: 'chromium',
    channel: process.platform === 'win32' ? 'chrome' : undefined,
    launchOptions: { executablePath: process.env.CUTVOKE_E2E_BROWSER },
    viewport: { width: 1600, height: 960 }, locale: 'zh-CN', trace: 'retain-on-failure' },
  webServer: { command: 'python ../../tests/support/audio_tutorial_server.py',
    url: `http://127.0.0.1:${port}/api/v1/capabilities`, reuseExistingServer: false,
    timeout: 240_000, env: { CUTVOKE_AUDIO_TUTORIAL_PORT: port, PYTHONIOENCODING: 'utf-8' } },
});

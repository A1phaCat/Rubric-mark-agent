const { defineConfig } = require('@playwright/test');

const path = require('path');

const python = process.platform === 'win32'
  ? '.venv\\Scripts\\python.exe'
  : '.venv/bin/python';

// Browser tests run against their own throwaway database under data/e2e/ (ignored by Git),
// never the developer's data/, and use the offline FakeLLM, which needs MARKER_ENV=test.
const e2eData = process.env.MARKER_E2E_DATA_DIR || path.join(__dirname, 'data', 'e2e');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  workers: 1,
  use: { baseURL: process.env.MARKER_BASE_URL || 'http://127.0.0.1:8000', trace: 'retain-on-failure' },
  webServer: process.env.MARKER_SKIP_WEBSERVER ? undefined : {
    // API + worker + freshly seeded samples; the API alone never processes queued jobs.
    command: `${python} scripts/tasks.py e2e-server`,
    env: {
      MARKER_ENV: 'test',
      MARKER_DATA_DIR: e2eData,
      MARKER_DATABASE_URL: `sqlite:///${path.join(e2eData, 'marker.sqlite3').split(path.sep).join('/')}`,
    },
    url: 'http://127.0.0.1:8000/healthz',
    reuseExistingServer: true,
    timeout: 120_000
  }
});


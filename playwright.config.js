const { defineConfig } = require('@playwright/test');

const python = process.platform === 'win32'
  ? '.venv\\Scripts\\python.exe'
  : '.venv/bin/python';

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  workers: 1,
  use: { baseURL: process.env.MARKER_BASE_URL || 'http://127.0.0.1:8000', trace: 'retain-on-failure' },
  webServer: process.env.MARKER_SKIP_WEBSERVER ? undefined : {
    command: `${python} scripts/tasks.py api`,
    url: 'http://127.0.0.1:8000/healthz',
    reuseExistingServer: true,
    timeout: 120_000
  }
});


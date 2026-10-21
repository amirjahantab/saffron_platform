const { defineConfig } = require('@playwright/test');
const path = require('node:path');

module.exports = defineConfig({
  testDir: './tests/browser',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8766',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'mobile-small', use: { viewport: { width: 320, height: 740 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
  ],
  webServer: {
    command: `"${path.join(__dirname, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')}" -X utf8 manage.py runserver 127.0.0.1:8766 --noreload`,
    url: 'http://127.0.0.1:8766/health/',
    env: { SITE_URL: 'http://127.0.0.1:8766', PAYMENT_CALLBACK_BASE_URL: 'http://127.0.0.1:8766' },
    reuseExistingServer: false,
    timeout: 30000,
  },
});

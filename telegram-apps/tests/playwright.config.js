const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './',
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
    proxy: {
      server: 'http://127.0.0.1:10808',
    },
  },
});

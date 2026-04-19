const { test, expect } = require('@playwright/test');

test('Smoke test: verify UI elements and form validation', async ({ page }) => {
  await page.goto('/files');
  
  await page.waitForSelector('#sel-file option:nth-child(2)');
  
  const startBtn = page.locator('#btn-start');
  await expect(startBtn).toBeDisabled();

  // Выбор файла и глоссария
  await page.selectOption('#sel-file', { index: 1 });
  await page.selectOption('#glossary-mode', 'create_ai');
  
  // Кнопка должна стать активной
  await expect(startBtn).toBeEnabled();
});

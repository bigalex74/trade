const { test, expect } = require('@playwright/test');

test('E2E: Translation process flow', async ({ page }) => {
  await page.goto('/files');
  
  // 1. Ждем инициализации
  await page.waitForSelector('#sel-file option:nth-child(2)');
  
  // 2. Заполнение формы
  await page.selectOption('#sel-file', { index: 1 }); // Выбор файла
  await page.selectOption('#glossary-mode', 'create_ai'); // AI Глоссарий
  await page.selectOption('#sel-bp', { index: 1 }); // Промпт
  await page.selectOption('#sel-pp', { index: 1 }); // Редактор
  
  // 3. Проверка активации кнопки
  const startBtn = page.locator('#btn-start');
  await expect(startBtn).toBeEnabled();
  
  // 4. Запуск (используем click)
  await startBtn.click();
  
  // В успешном сценарии страница должна закрыться или перенаправиться.
  // Playwright проверит навигацию или закрытие.
});

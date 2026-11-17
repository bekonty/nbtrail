import { expect, test } from '@jupyterlab/galata';

/**
 * Don't load JupyterLab webpage before running the tests.
 * This is required to ensure we capture all log messages.
 */
test.use({ autoGoto: false });

test('activates and starts recording', async ({ page }) => {
  const logs: string[] = [];

  page.on('console', message => {
    logs.push(message.text());
  });

  await page.goto();

  await expect
    .poll(() => logs.filter(s => s === 'nbtrail is recording').length)
    .toBe(1);
});

test('shows the recording badge and pauses on click', async ({ page }) => {
  await page.goto();
  await page.notebook.createNew('badge.ipynb');

  const badge = page.locator('.nbtrail-badge');
  await expect(badge).toHaveText('● nbtrail');

  await badge.click();
  await expect(badge).toHaveText('❚❚ nbtrail paused');

  await badge.click();
  await expect(badge).toHaveText('● nbtrail');
});

const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');

test('public shopping pages fit viewport and use local resources', async ({ page }, testInfo) => {
  const failures = [];
  const external = [];
  page.on('pageerror', error => failures.push(error.message));
  page.on('request', request => {
    if (!request.url().startsWith('http://127.0.0.1:8766/') && !request.url().startsWith('data:')) external.push(request.url());
  });
  for (const path of ['/', '/shop/', '/shop/category/super_negin/', '/cart/', '/auth/login/', '/journal/', '/faq/', '/assistant/', '/preferences/']) {
    const response = await page.goto(path);
    expect(response.status()).toBe(200);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const overflowingControls = await page.locator('main input:not([type=hidden]), main select, main textarea, main button, main h1').evaluateAll(elements => elements.filter(element => {
      const bounds = element.getBoundingClientRect();
      return bounds.width > 0 && bounds.height > 0 && (bounds.left < -1 || bounds.right > innerWidth + 1);
    }).map(element => element.id || element.tagName));
    expect(overflowingControls).toEqual([]);
    await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /.+/);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('16px Vazirmatn'))).toBeTruthy();
    if (path === '/') {
      await page.locator('img[loading=lazy]').evaluateAll(images => images.forEach(image => {image.loading = 'eager';}));
      await page.evaluate(() => Promise.all([...document.images].map(image => image.decode().catch(() => {}))));
      await page.screenshot({ path: testInfo.outputPath('home.png'), fullPage: true });
      const metrics = await page.evaluate(() => ({
        navigationMs: performance.getEntriesByType('navigation')[0].duration,
        resources: performance.getEntriesByType('resource').map(r => ({ url: r.name, bytes: r.encodedBodySize, durationMs: r.duration })),
      }));
      const metricsPath = testInfo.outputPath('performance.json');
      await fs.writeFile(metricsPath, JSON.stringify(metrics, null, 2));
      await testInfo.attach('local-performance', { path: metricsPath, contentType: 'application/json' });
      const css = metrics.resources.find(r => r.url.endsWith('/static/css/tailwind.css'));
      expect(css.bytes).toBeLessThan(60000);
    }
    if (path === '/shop/' || path === '/journal/') await page.screenshot({path: testInfo.outputPath(path === '/shop/' ? 'shop.png' : 'journal.png'), fullPage: true});
  }
  expect(failures).toEqual([]);
  expect(external).toEqual([]);
});

test('product schema follows visible selected variant and images load', async ({ page }, testInfo) => {
  await page.goto('/shop/');
  const link = page.locator('article a[href^="/shop/"]').first();
  await link.click();
  await expect(page.locator('h1')).toBeVisible();
  const buttons = page.locator('[data-variant-id]');
  expect(await buttons.count()).toBeGreaterThan(0);
  for (let i = 0; i < Math.min(2, await buttons.count()); i++) {
    await buttons.nth(i).click();
    const matches = await page.evaluate(() => {
      const selectedId = document.querySelector('[data-variant-id][aria-pressed="true"]').dataset.variantId;
      const variants = JSON.parse(document.getElementById('product-variants-data').textContent);
      const selected = variants.find(v => v.public_id === selectedId);
      const product = JSON.parse(document.getElementById('seo-structured-data').textContent)['@graph'].find(v => v['@type'] === 'Product');
      return product.sku === selected.sku && product.offers.price === String(selected.effective_price_rial);
    });
    expect(matches).toBeTruthy();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(await page.locator('img').evaluateAll(images => images.every(img => img.loading === 'lazy' || img.complete && img.naturalWidth > 0))).toBeTruthy();
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0); });
  await page.screenshot({ path: testInfo.outputPath('product.png'), fullPage: true });
});

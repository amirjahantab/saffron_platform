const {test, expect} = require('@playwright/test');

test('guest completes purchase and receipt is private to its session', async ({page, browser}, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/shop/pushal-authentic-birjand/');
  await page.locator('.js-add-to-cart-form button[type=submit]').first().click();
  await expect(page.locator('#nav-cart-count')).toHaveText('۱');
  await page.goto('/cart/');
  await page.getByRole('link', {name: 'ادامه خرید بدون ساخت حساب'}).click();
  await page.getByLabel('نام و نام خانوادگی گیرنده', {exact: true}).fill('مشتری نمایشی مرورگر');
  await page.getByLabel('شماره موبایل گیرنده', {exact: true}).fill('09121110001');
  await page.getByLabel('استان', {exact: true}).fill('خراسان رضوی');
  await page.getByLabel('شهر', {exact: true}).fill('مشهد');
  await page.getByLabel('نشانی کامل', {exact: true}).fill('نشانی آزمایشی برای بررسی مسیر خرید');
  await page.getByLabel('کد پستی ۱۰ رقمی', {exact: true}).fill('9188144556');
  await page.getByRole('button', {name: 'بررسی قیمت و رزرو سفارش'}).click();
  await expect(page).toHaveURL(/\/guest\/orders\/JHT-/);
  const receipt = page.url();
  await page.getByRole('button', {name: 'پرداخت سفارش', exact: true}).click();
  await expect(page).toHaveURL(/sandbox-gateway/);
  await page.getByRole('link', {name: /شبیه‌سازی پرداخت موفق/}).click();
  await expect(page).toHaveURL(receipt);
  await expect(page.locator('.status-chip')).toHaveText('پرداخت‌شده');
  const stranger = await browser.newContext();
  expect((await stranger.request.get(receipt)).status()).toBe(404);
  await stranger.close();
  expect(errors).toEqual([]);
  await page.screenshot({path: testInfo.outputPath('paid-guest-receipt.png'), fullPage: true});
});

test('assistant shows truthful disabled fallback and privacy choices persist', async ({page}) => {
  await page.goto('/assistant/');
  await page.getByLabel('پرسش شما').fill('برای هدیه زعفران می‌خواهم');
  await page.getByRole('button', {name: /راهنمایی‌ام کن/}).click();
  await expect(page.locator('#assistant-results')).toContainText('غیرفعال');
  await page.goto('/preferences/');
  await page.locator('[name=analytics]').check();
  await page.getByRole('button', {name: 'ذخیره انتخاب‌ها'}).click();
  await expect(page.locator('[name=analytics]')).toBeChecked();
  await page.locator('[name=analytics]').uncheck();
  await page.getByRole('button', {name: 'ذخیره انتخاب‌ها'}).click();
  await expect(page.locator('[name=analytics]')).not.toBeChecked();
});

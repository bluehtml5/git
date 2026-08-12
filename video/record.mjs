/**
 * 相關商品推薦 — 影片錄製腳本
 *
 *   npm i -D playwright && npx playwright install chromium
 *
 *   node record.mjs --mock                          錄本地 mockup（16.5 秒，9:16）
 *   node record.mjs --live https://example.com/item/315537
 *   node record.mjs --live <url> --selector "[data-recs]"   指定推薦區塊的選擇器
 *
 * 輸出：out/<timestamp>.webm　（轉 mp4 的指令見 README.md）
 */

import { chromium, devices } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

const here = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const arg = (flag) => {
  const i = argv.indexOf(flag);
  return i === -1 ? null : (argv[i + 1] ?? true);
};

const MODE = argv.includes('--live') ? 'live' : 'mock';
const URL_LIVE = arg('--live');
// 推薦區塊的選擇器。先用 --selector 指定；沒指定就用常見的文案去猜。
const REC_SELECTOR = arg('--selector');
const REC_TEXT = /you may also like|related|recommend|你可能|相關商品|推薦/i;

const OUT = resolve(here, 'out');
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* 用 requestAnimationFrame 做等速捲動，比 scrollIntoView 平順，錄影不會跳格 */
async function smoothScroll(page, toY, duration = 1100) {
  await page.evaluate(
    ([to, dur]) =>
      new Promise((res) => {
        const from = window.scrollY;
        const t0 = performance.now();
        const ease = (t) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
        (function step(now) {
          const k = Math.min(1, (now - t0) / dur);
          window.scrollTo(0, from + (to - from) * ease(k));
          k < 1 ? requestAnimationFrame(step) : res();
        })(t0);
      }),
    [toY, duration]
  );
}

async function recordMock(browser) {
  const ctx = await browser.newContext({
    viewport: { width: 540, height: 960 },
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: { width: 1080, height: 1920 } },
  });
  const page = await ctx.newPage();
  await page.goto('file://' + resolve(here, 'mockup.html') + '?clean=1');
  await sleep(600);          // 讓第一幀穩定
  await sleep(17_000);       // 一整輪動畫
  await ctx.close();
}

async function recordLive(browser) {
  const ctx = await browser.newContext({
    ...devices['iPhone 13'],
    recordVideo: { dir: OUT, size: { width: 1080, height: 1920 } },
  });
  const page = await ctx.newPage();

  await page.goto(URL_LIVE, { waitUntil: 'networkidle', timeout: 60_000 });

  // 關掉會毀掉畫面的東西：cookie 橫幅、電子報彈窗
  for (const t of [/accept|同意|接受/i, /close|關閉|×/i]) {
    const btn = page.getByRole('button', { name: t }).first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click().catch(() => {});
      await sleep(400);
    }
  }
  await sleep(1500);                       // 0:00 停在商品頁上方

  // 找推薦區塊
  const recs = REC_SELECTOR
    ? page.locator(REC_SELECTOR).first()
    : page.getByText(REC_TEXT).first();

  const box = await recs.boundingBox().catch(() => null);
  if (!box) {
    console.error(
      '找不到推薦區塊。用 --selector 指定，例如：--selector "section.product-recommendations"'
    );
    await ctx.close();
    return;
  }

  const targetY = (await page.evaluate(() => window.scrollY)) + box.y - 120;

  await smoothScroll(page, targetY * 0.55, 1100);   // 0:02 中途停一下
  await sleep(600);
  await smoothScroll(page, targetY, 900);            // 0:04 推薦區塊進畫面
  await sleep(2200);

  // 0:06 橫向滑動推薦卡片（若是 carousel）
  const rail = recs.locator('xpath=.//*[contains(@style,"overflow") or contains(@class,"scroll") or contains(@class,"carousel")]').first();
  const railBox = await rail.boundingBox().catch(() => null);
  if (railBox) {
    await page.mouse.move(railBox.x + railBox.width - 40, railBox.y + railBox.height / 2);
    await page.mouse.down();
    for (let i = 0; i <= 24; i++) {
      await page.mouse.move(railBox.x + railBox.width - 40 - i * 12, railBox.y + railBox.height / 2);
      await sleep(24);
    }
    await page.mouse.up();
  }
  await sleep(1600);

  // 0:09 點第二張推薦商品 → 換頁
  const card = recs.locator('a').nth(1);
  if (await card.isVisible().catch(() => false)) {
    await card.click().catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {});
    await sleep(2400);
    await smoothScroll(page, 320, 800);
    await sleep(1800);
  }

  await ctx.close();
}

const browser = await chromium.launch();
try {
  MODE === 'live' ? await recordLive(browser) : await recordMock(browser);
} finally {
  await browser.close();
}
console.log('完成，影片在 ' + OUT);

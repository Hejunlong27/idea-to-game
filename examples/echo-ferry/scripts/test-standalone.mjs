#!/usr/bin/env node
/**
 * file:// 启动行为回归测试 —— 这类 bug 的核心特征是「静默」：页面永远停在 Loading，
 * 控制台一句报错都没有，纯靠肉眼只能看出"卡死"。所以必须自动化断言。
 *
 * 覆盖两半：
 *   A. 单文件版（npm run standalone 的产物）在 file:// 下**必须能跑**
 *   B. 常规构建产物在 file:// 下**必须给出可操作的提示**，不能静默停在 Loading
 *
 * 断言明细：
 *   A1 启动成功（window.__bootDone）  A2 看门狗未触发（#boot 已隐藏）
 *   A3 无 pageerror / 无请求失败       A4 真的出画面（截图解码后非纯黑）
 *   B1 看门狗触发并显示 file:// 提示   B2 提示文案里含可执行动作（standalone / serve）
 *
 * ⚠️ 项目落地后：请把本测试纳入 QA 流程，并在项目版脚本里**补真实交互断言**
 *    （进关卡 + 点一下真的生效），单文件版"能显示菜单"不等于"能玩"。
 *
 * 用法：node scripts/test-standalone.mjs [单文件HTML] [常规产物目录]
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer-core';

const STANDALONE = path.resolve(process.argv[2] ?? 'dist/standalone.html');
const BUILT_DIR = path.resolve(process.argv[3] ?? 'dist/crazygames');
const SHOT = 'docs/07-qa/screenshots';
const CHROME = process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

if (!fs.existsSync(STANDALONE)) {
  console.error(`ERROR: 单文件版不存在：${STANDALONE}（先跑 npm run standalone）`);
  process.exit(1);
}
fs.mkdirSync(SHOT, { recursive: true });

/**
 * 截图 → 回灌浏览器解码 → 数非黑像素。
 *
 * ⚠️ 不要用 `canvas.drawImage(webglCanvas)` 直接读回：WebGL 默认不保留绘制缓冲，
 *    拿到的必然是空图（这个坑踩了两次）。截图走的是合成后的真实画面，可靠。
 */
async function paintedPixels(page) {
  const b64 = await page.screenshot({ encoding: 'base64' });
  return page.evaluate(async (b) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + b;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = 64;
    c.height = 64;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0, 64, 64);
    const d = ctx.getImageData(0, 0, 64, 64).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i] + d[i + 1] + d[i + 2] > 30) n += 1;
    }
    return n;
  }, b64);
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: [
    '--no-sandbox',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--mute-audio',
    '--autoplay-policy=no-user-gesture-required',
  ],
});

const results = [];
const check = (name, ok, detail = '') => {
  results.push({ name, ok: !!ok, detail });
  return !!ok;
};

async function open(target) {
  const page = await browser.newPage();
  await page.setViewport({ width: 720, height: 1280 });
  const errors = [];
  const requestFailed = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(`PAGEERROR: ${e.message}`));
  page.on('requestfailed', (r) => {
    if (!r.url().startsWith('data:')) requestFailed.push(`${r.url().slice(0, 90)} :: ${r.failure()?.errorText}`);
  });
  await page.goto(pathToFileURL(target).href, { waitUntil: 'load', timeout: 60000 });
  return { page, errors, requestFailed };
}

try {
  // ── A. 单文件版：必须能跑 ──────────────────────────────────
  {
    const { page, errors, requestFailed } = await open(STANDALONE);
    await sleep(3000);
    const bootDone = await page.evaluate(() => window.__bootDone === true);
    const bootHidden = await page.evaluate(() => {
      const b = document.getElementById('boot');
      return !b || getComputedStyle(b).display === 'none';
    });
    const painted = await paintedPixels(page);
    await page.screenshot({ path: path.join(SHOT, 'standalone.png') });
    check('A1 单文件版 file:// 下启动成功', bootDone);
    check('A2 启动看门狗未触发（说明没走到失败分支）', bootHidden);
    check('A3 无控制台报错 / 无请求失败', errors.length === 0 && requestFailed.length === 0, [...errors, ...requestFailed].join(' | '));
    check('A4 真的出画面（截图非纯黑）', painted > 8, `非黑采样点 ${painted}/4096`);
    await page.close();
  }

  // ── B. 常规产物 file:// 直开：必须给出可操作提示，不能静默 ──
  {
    const normal = path.join(BUILT_DIR, 'index.html');
    if (!fs.existsSync(normal)) {
      check('B0 常规产物存在（用于回归测试）', false, normal);
    } else {
      const { page } = await open(normal);
      await sleep(1500);
      const bootText = await page.evaluate(() => {
        const b = document.getElementById('boot');
        return b ? b.innerText.replace(/\s+/g, ' ').trim() : '';
      });
      const booted = await page.evaluate(() => window.__bootDone === true);
      await page.screenshot({ path: path.join(SHOT, 'file-protocol-guard.png') });
      check('B1 file:// 直开时看门狗立即给出提示（而非静默 Loading）', !booted && /served over HTTP|file:\/\//i.test(bootText), bootText.slice(0, 120));
      check('B2 提示里含可执行动作（standalone / serve）', /standalone/i.test(bootText) && /serve/i.test(bootText), bootText.slice(0, 160));
      await page.close();
    }
  }
} finally {
  await browser.close();
}

for (const r of results) {
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? `\n        ${r.detail}` : ''}`);
}
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? `\n${failed.length} 项失败` : '\n全部通过：file:// 下的两种情形都符合预期');
process.exit(failed.length ? 1 : 0);

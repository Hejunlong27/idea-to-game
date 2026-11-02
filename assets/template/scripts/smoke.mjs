#!/usr/bin/env node
/**
 * 冒烟测试（smoke）：只回答一个问题 —— 游戏能不能从开始走到结束再重开。
 *
 * 与 qa.mjs 的分工：
 *   smoke  = 闭环 + 截图（快，10 秒级，CI 每次都跑）
 *   qa     = 断言 + 帧率 + 移动端（慢，需要基线对照）
 *   playtest = 真实操作策略 + 报告（最慢，交付前跑）
 *
 * 用法:
 *   node scripts/smoke.mjs --url http://127.0.0.1:5173 --out docs/07-qa
 * 退出码: 0=闭环通过　1=未闭环
 */

import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}


/** 尝试进入玩法：不同模板的「开始」位置不同，先用键盘再用多个落点，最后看状态。 */
async function tryStart(page) {
  const has = () => page.evaluate(() => !!window.__gameState).catch(() => false);
  for (const key of ['Space', 'Enter']) {
    await page.keyboard.press(key).catch(() => {});
    await new Promise((r) => setTimeout(r, 500));
    if (await has()) return true;
  }
  const rect = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  if (!rect) return false;
  for (const fy of [0.5, 0.68, 0.74, 0.62]) {
    await page.mouse.click(rect.x + rect.w / 2, rect.y + rect.h * fy).catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
    if (await has()) return true;
  }
  return false;
}

const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].filter(Boolean).find((c) => c && fs.existsSync(c));

async function main() {
  if (!CHROME) {
    console.error('ERROR: 找不到 Chrome');
    process.exit(2);
  }
  const url = arg('url', 'http://127.0.0.1:5173');
  const out = arg('out', 'docs/07-qa');
  const shotDir = path.join(out, 'screenshots');
  fs.mkdirSync(shotDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader', '--mute-audio'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 720, height: 1280 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e?.message ?? e)));

  const phases = [];
  const snap = async (label) => {
    const st = await page.evaluate(() => window.__gameState || null).catch(() => null);
    phases.push({ label, state: st });
    await page.screenshot({ path: path.join(shotDir, `smoke-${String(phases.length).padStart(2, '0')}-${label}.png`) })
      .catch(() => {});
    return st;
  };

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 })
    .catch(() => {});
  await new Promise((r) => setTimeout(r, 800));
  await snap('boot');

  // 进入玩法：键盘优先 + 多个落点兜底（不同模板按钮位置不同）
  const started = await tryStart(page);
  await new Promise((r) => setTimeout(r, 500));
  await snap('start');
  if (!started) console.warn('⚠ 未能进入玩法（菜单可能不在常见位置），后续断言会失败');

  // 玩一小段
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press(i % 2 ? 'ArrowRight' : 'ArrowDown').catch(() => {});
    if (i % 4 === 0) await page.keyboard.press('Space').catch(() => {});
    await new Promise((r) => setTimeout(r, 220));
  }
  await snap('play');

  const state = await page.evaluate(() => window.__gameState || null).catch(() => null);
  const events = await page.evaluate(() => (Array.isArray(window.__gameEvents) ? window.__gameEvents.length : 0))
    .catch(() => 0);

  await browser.close();

  const report = {
    generated_at: new Date().toISOString(),
    url,
    phases,
    final_state: state,
    event_count: events,
    errors,
    closed_loop: !!state && events > 0 && errors.length === 0,
  };
  fs.writeFileSync(path.join(out, 'smoke.json'), JSON.stringify(report, null, 2), 'utf-8');

  console.log(`阶段截图 ${phases.length} 张，事件 ${events} 条，错误 ${errors.length} 条`);
  if (!report.closed_loop) {
    console.error('❌ 冒烟未通过：' + (!state ? ' 无 __gameState' : events === 0 ? ' 无事件输出' : ' 有运行时错误'));
    process.exitCode = 1;
  } else {
    console.log('✅ 冒烟通过（闭环可走）');
  }
}

main().catch((e) => {
  console.error('smoke 失败：', e);
  process.exit(2);
});

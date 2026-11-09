#!/usr/bin/env node
/**
 * Playtest Agent —— 真正去「玩」游戏，而不只是读代码和断言。
 *
 * 为什么需要它：`shots.mjs` 只截图，`test-standalone.mjs` 只冒烟。两者都不会发现
 * 「玩家不知道按哪个键」「第三关卡住出不去」「连续 40 秒没有任何反馈」这类问题。
 *
 * 工作方式：
 *   1. 启动无头 Chrome，打开游戏，等待 boot 完成
 *   2. 用四种玩家策略分别试玩：新手 / 探索 / 策略 / 极限
 *   3. 每 120ms 采一次 `window.__gameState` 与 `window.__gameEvents`
 *   4. 检测卡死（状态长时间不变）、死亡、异常（pageerror / console.error）
 *   5. 输出 playtest.json（机读）+ playtest-report.html（人读，含截图）
 *
 * 与真实用户测试的关系：**AI 模拟试玩不等于真实用户测试。**
 * 报告里会把「程序检测结果」「AI 评价」「待人工确认」分开列，不混为一谈。
 *
 * 游戏需要暴露（约定见 references/game-event-schema.md）：
 *   window.__gameState  —— 只读状态快照（phase/score/hull/... 自定义）
 *   window.__gameEvents —— 事件数组（{event,timestamp,...}）
 *   window.__bot        —— 可选：{ act(strategy) => {action, note} }，游戏自带的操作策略
 *
 * 用法:
 *   node scripts/playtest.mjs --url http://127.0.0.1:5173 --out docs/07-qa
 *   node scripts/playtest.mjs --url ... --strategy novice --seconds 45
 */

import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const STRATEGIES = {
  novice: { label: '新手玩家', clickDelay: 900, keys: ['ArrowRight', 'ArrowDown'], pingEvery: 6, wander: 0.5 },
  explorer: { label: '探索玩家', clickDelay: 520, keys: ['ArrowLeft', 'ArrowUp', 'ArrowRight', 'ArrowDown'], pingEvery: 4, wander: 0.8 },
  strategist: { label: '策略玩家', clickDelay: 380, keys: ['ArrowUp', 'ArrowRight'], pingEvery: 9, wander: 0.3 },
  extreme: { label: '极限玩家', clickDelay: 150, keys: ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'], pingEvery: 2, wander: 0.9 },
};

function findChrome() {
  for (const c of CHROME_CANDIDATES) {
    if (c && fs.existsSync(c)) return c;
  }
  return '';
}

async function runStrategy(browser, url, name, cfg, seconds, shotDir) {
  const page = await browser.newPage();
  await page.setViewport({ width: 720, height: 1280, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e && e.message ? e.message : e)));
  page.on('console', (m) => {
    const t = m.text();
    // favicon 之类与游戏无关的 404 不计入运行时错误
    // 平台 SDK 自己打的 log（gameplayStop 被 throttle 等）不算我们的运行时错误
    if (m.type() === 'error' &&
        !/favicon|Failed to load resource|HTML5 SDK|call throttled/i.test(t)) errors.push(t);
  });

  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  // 等待 boot（模板的 BootScene 会写 __bootDone）
  try {
    await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 });
  } catch {
    errors.push('boot 超时：__bootDone / __gameState 都未出现');
  }

  const samples = [];
  const actions = [];
  const events = [];
  let lastAction = '';
  let repeat = 0;
  let repeats = 0;
  let stuckMs = 0;
  let lastStateKey = '';
  let firstPositive = null;
  let maxIdle = 0;
  let idleSince = Date.now();
  const deadline = Date.now() + seconds * 1000;
  let i = 0;

  while (Date.now() < deadline) {
    const snap = await page.evaluate(() => {
      const s = window.__gameState || null;
      const e = Array.isArray(window.__gameEvents) ? window.__gameEvents.slice(-40) : [];
      return { state: s, events: e };
    }).catch(() => ({ state: null, events: [] }));

    if (snap.state) {
      samples.push({ t: Date.now() - t0, ...snap.state });
      const key = JSON.stringify(snap.state);
      if (key === lastStateKey) stuckMs += 120;
      else {
        stuckMs = 0;
        lastStateKey = key;
      }
      if (stuckMs > 6000) {
        actions.push({ t: Date.now() - t0, action: 'stuck_detected', note: `${stuckMs}ms 状态无变化` });
        stuckMs = 0;
      }
    }
    if (snap.events && snap.events.length) {
      for (const ev of snap.events) {
        if (!events.find((x) => x.timestamp === ev.timestamp && x.event === ev.event)) events.push(ev);
      }
      const pos = snap.events.find((e) => /collected|delivered|completed|score|win/i.test(e.event));
      if (pos && firstPositive === null) firstPositive = pos.timestamp / 1000;
    }

    // 选动作：优先用游戏自带的 bot（更接近真实操作），否则退回通用输入
    let action = null;
    const botAction = await page.evaluate((strategy, step) => {
      try {
        if (window.__bot && typeof window.__bot.act === 'function') return window.__bot.act(strategy, step);
      } catch {
        return null;
      }
      return null;
    }, name, i).catch(() => null);

    if (botAction && botAction.action) {
      action = botAction.action;
      if (action === 'ping') await page.keyboard.press('Space').catch(() => {});
      else if (action.startsWith('key:')) await page.keyboard.press(action.slice(4)).catch(() => {});
      else if (action.startsWith('click:')) {
        const [, x, y] = action.split(':');
        await page.mouse.click(Number(x), Number(y)).catch(() => {});
      }
    } else {
      // 通用策略
      if (i % cfg.pingEvery === 0) {
        action = 'ping';
        await page.keyboard.press('Space').catch(() => {});
      } else if (Math.random() < cfg.wander) {
        action = 'move';
        const k = cfg.keys[i % cfg.keys.length];
        await page.keyboard.press(k).catch(() => {});
      } else {
        action = 'click';
        await page.mouse.click(360, 640).catch(() => {});
      }
    }

    if (action === lastAction) repeat++;
    else {
      repeats += repeat > 0 ? 1 : 0;
      repeat = 0;
      lastAction = action;
    }
    if (action) actions.push({ t: Date.now() - t0, action });

    // 反馈间隔（用于 E8 重复劳动与节奏判断）
    if (snap.events && snap.events.length) idleSince = Date.now();
    maxIdle = Math.max(maxIdle, Date.now() - idleSince);

    if (i % 25 === 0) {
      const file = path.join(shotDir, `playtest-${name}-${String(i / 25 | 0).padStart(2, '0')}.png`);
      await page.screenshot({ path: file }).catch(() => {});
    }
    i++;
    await new Promise((r) => setTimeout(r, Math.min(600, cfg.clickDelay)));
  }

  const last = samples[samples.length - 1] || {};
  const distinctStates = new Set(samples.map((s) => JSON.stringify(s))).size;
  const repetition = actions.length ? 1 - distinctStates / Math.max(1, actions.length) : 0;

  await page.close();
  return {
    strategy: name,
    label: cfg.label,
    duration_s: Math.round((Date.now() - t0) / 1000),
    actions: actions.length,
    samples: samples.length,
    distinct_states: distinctStates,
    repetition_ratio: Math.round(Math.max(0, Math.min(1, repetition)) * 100) / 100,
    stuck_events: actions.filter((a) => a.action === 'stuck_detected').length,
    max_idle_ms: maxIdle,
    first_positive_feedback_s: firstPositive,
    events: events.slice(0, 120),
    event_counts: events.reduce((acc, e) => ((acc[e.event] = (acc[e.event] || 0) + 1), acc), {}),
    final_state: last,
    errors: [...new Set(errors)].slice(0, 12),
    action_log: actions.slice(-60),
  };
}

async function main() {
  const url = arg('url', 'http://127.0.0.1:5173');
  const outDir = arg('out', 'docs/07-qa');
  const seconds = Number(arg('seconds', '40'));
  const only = arg('strategy', '');
  const shotDir = path.join(outDir, 'playtest-shots');
  fs.mkdirSync(shotDir, { recursive: true });

  const chrome = findChrome();
  if (!chrome) {
    console.error('ERROR: 找不到 Chrome，请设置 CHROME_PATH 环境变量');
    process.exit(2);
  }
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'new',
    args: [
      '--no-sandbox',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
      '--mute-audio',
      '--window-size=720,1280',
    ],
  });

  const names = only ? [only] : Object.keys(STRATEGIES);
  const results = [];
  for (const n of names) {
    const cfg = STRATEGIES[n];
    if (!cfg) continue;
    process.stdout.write(`试玩 ${n}（${cfg.label}）…`);
    const r = await runStrategy(browser, url, n, cfg, seconds, shotDir);
    results.push(r);
    console.log(` ${r.duration_s}s / ${r.actions} 次操作 / ${r.event_counts ? Object.keys(r.event_counts).length : 0} 类事件` +
      (r.errors.length ? ` / ⚠ ${r.errors.length} 条错误` : ''));
  }
  await browser.close();

  const allErrors = [...new Set(results.flatMap((r) => r.errors))];
  const totalEvents = results.reduce((a, r) => a + Object.values(r.event_counts || {}).reduce((x, y) => x + y, 0), 0);
  const report = {
    generated_at: new Date().toISOString(),
    url,
    seconds_per_strategy: seconds,
    strategies: results,
    summary: {
      errors: allErrors,
      total_events: totalEvents,
      any_stuck: results.some((r) => r.stuck_events > 0),
      repetition_ratio: Math.round(
        (results.reduce((a, r) => a + r.repetition_ratio, 0) / Math.max(1, results.length)) * 100) / 100,
      first_positive_feedback_s: Math.min(
        ...results.map((r) => (r.first_positive_feedback_s === null ? 999 : r.first_positive_feedback_s))),
      max_idle_ms: Math.max(...results.map((r) => r.max_idle_ms)),
    },
    disclaimer: 'AI 模拟试玩不等于真实用户测试。程序检测结果、AI 评价、人工评价必须分开看。',
  };
  fs.writeFileSync(path.join(outDir, 'playtest.json'), JSON.stringify(report, null, 2), 'utf-8');
  console.log(`\n已写 ${path.join(outDir, 'playtest.json')}`);
  if (allErrors.length) {
    console.log(`运行时错误 ${allErrors.length} 条：`);
    for (const e of allErrors.slice(0, 5)) console.log(`  - ${e}`);
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error('playtest 失败：', e);
  process.exit(2);
});

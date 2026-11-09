#!/usr/bin/env node
/**
 * Compare —— Prototype Comparison（原型对比）。
 *
 * 解决的问题：创意/数值方案不能靠「看着不错」来选。
 * 同一套代码、同一套用例、同一个 bot，只改变量，用实测数据比。
 *
 * 每个变体跑两件事：
 *   1. 全量用例  → 机制完整性（改数值有没有把玩法改坏）
 *   2. bot 试玩  → 能不能通关、多久通关、按了多少次
 *
 * 为什么 bot 只跑一局：游戏是确定性的（固定波次 / 固定 seed），
 * 同样输入必得同样结果。多跑几局只是重复同一个样本，不增加信息。
 *
 * 用法：
 *   node scripts/compare.mjs                     # 跑 variants/ 下所有变体
 *   node scripts/compare.mjs --only fast-pace
 *   node scripts/compare.mjs --out docs/04-core-loop
 *
 * 变体文件（variants/*.json）：
 *   {
 *     "id": "fast-pace",
 *     "name": "快节奏",
 *     "desc": "2 波但更密，开局钱更多",
 *     "override": { "waves": [{ "grunt": 5 }, { "grunt": 4, "swift": 3 }], "startGold": 150 }
 *   }
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
];
const arg = (n, d = '') => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

function findChrome() {
  for (const c of CHROME_CANDIDATES) if (c && fs.existsSync(c)) return c;
  return '';
}

/** 起 vite（变体要重新 goto，所以整个对比过程共用同一个 server） */
async function startServer(projectDir, port) {
  const viteBin = path.join(projectDir, 'node_modules', 'vite', 'bin', 'vite.js');
  const proc = spawn(process.execPath, [viteBin, '--port', String(port), '--strictPort'], {
    cwd: projectDir,
    stdio: 'ignore',
  });
  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (r.ok) return { proc, url };
    } catch {
      /* 还没起来 */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  proc.kill();
  throw new Error(`vite 启动超时 ${url}`);
}

/** 进玩法场景（键盘 + 点击交替，同 scenario.mjs 的策略） */
async function ensureInGame(page) {
  await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 });
  const spots = [[0.5, 0.5], [0.5, 0.68], [0.5, 0.8], [0.5, 0.35]];
  for (let i = 0; i < 8; i++) {
    if (await page.evaluate(() => !!(window.__test && window.__test.ready)).catch(() => false)) return;
    if (i % 2 === 0) await page.keyboard.press('Space').catch(() => {});
    else {
      const box = await page.evaluate(() => {
        const c = document.querySelector('canvas');
        if (!c) return null;
        const r = c.getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
      }).catch(() => null);
      const [fx, fy] = spots[(i >> 1) % spots.length];
      await page.mouse.click(box ? box.x + box.w * fx : 360, box ? box.y + box.h * fy : 640).catch(() => {});
    }
    await new Promise((r) => setTimeout(r, 320));
  }
  throw new Error('进不去玩法场景');
}

/** 跑全量用例，返回通过率 */
async function runScenarios(page, scenarioDir) {
  const files = fs.readdirSync(scenarioDir).filter((f) => f.endsWith('.json')).sort();
  let pass = 0;
  for (const f of files) {
    const sc = JSON.parse(fs.readFileSync(path.join(scenarioDir, f), 'utf-8'));
    try {
      await page.evaluate((lvl) => window.__test.reset(lvl), (sc.level ?? 1) - 1);
      await page.waitForFunction('window.__test && window.__test.ready', { timeout: 8000 });
      await page.evaluate(() => window.__test.settle(120));
      const run = async (actions) => {
        for (const a of actions ?? []) {
          if (a.type === 'wait') {
            // 按游戏时间等（有 clock 时）
            const hasClock = await page.evaluate(() => window.__test.clock?.() != null).catch(() => false);
            if (hasClock) {
              const t0 = await page.evaluate(() => window.__test.clock());
              const dl = Date.now() + (a.ms ?? 200) * 8 + 4000;
              while (Date.now() < dl) {
                await page.evaluate(() => window.__test.settle(60));
                if ((await page.evaluate(() => window.__test.clock())) - t0 >= (a.ms ?? 200)) break;
              }
            } else {
              await page.evaluate((ms) => window.__test.settle(ms), a.ms ?? 200);
            }
          } else {
            await page.evaluate((act) => window.__test.exec(act), a);
            if (a.type === 'reset') {
              await page.waitForFunction('window.__test && window.__test.ready', { timeout: 8000 });
              await page.evaluate(() => window.__test.settle(150));
            }
          }
        }
      };
      await run(sc.setup);
      await run(sc.steps);
      const state = await page.evaluate(() => window.__test.getState());
      const OPS = {
        eq: (a, b) => a === b, ne: (a, b) => a !== b, gt: (a, b) => a > b,
        gte: (a, b) => a >= b, lt: (a, b) => a < b, lte: (a, b) => a <= b,
        truthy: (a) => !!a, falsy: (a) => !a,
      };
      const pick = (o, d) => d.split('.').reduce((x, k) => (x == null ? undefined : x[k]), o);
      const ok = (sc.assertions ?? []).every((a) => {
        const actual = pick(state, a.path);
        const expected = 'valuePath' in a ? pick(state, a.valuePath) : a.value;
        return OPS[a.op]?.(actual, expected);
      });
      if (ok) pass += 1;
    } catch {
      /* 该用例算失败 */
    }
  }
  return { pass, total: files.length };
}

/** bot 试玩一局：能不能通关、游戏内耗时、操作次数 */
async function playOnce(page, maxWallMs = 90000, maxSteps = 400) {
  await page.evaluate(() => window.__test.reset(0));
  await page.waitForFunction('window.__test && window.__test.ready', { timeout: 8000 });
  await page.evaluate(() => window.__test.settle(200));

  const t0 = await page.evaluate(() => window.__test.clock?.() ?? 0);
  const start = Date.now();
  let steps = 0;

  while (Date.now() - start < maxWallMs && steps < maxSteps) {
    const over = await page.evaluate(() => window.__test.isOver()).catch(() => true);
    if (over) break;

    const action = await page.evaluate(() => {
      try {
        return window.__bot?.act?.('strategist', 0) ?? null;
      } catch {
        return null;
      }
    }).catch(() => null);

    if (!action || !action.action || action.action === 'none') {
      await page.evaluate(() => window.__test.settle(120));
    } else if (action.action.startsWith('click:')) {
      const [, x, y] = action.action.split(':');
      await page.mouse.click(Number(x), Number(y)).catch(() => {});
      await page.evaluate(() => window.__test.settle(80));
    } else if (action.action.startsWith('act:')) {
      await page.evaluate((id) => window.__test.exec({ type: 'act', id }), action.action.slice(4));
    } else if (action.action.startsWith('choose:')) {
      await page.evaluate((i) => window.__test.exec({ type: 'choose', index: i }), Number(action.action.slice(7)));
    } else if (action.action === 'ping') {
      await page.evaluate(() => window.__test.exec({ type: 'ping' }));
    } else if (action.action.startsWith('key:')) {
      await page.keyboard.press(action.action.slice(4)).catch(() => {});
      await page.evaluate(() => window.__test.settle(80));
    }
    steps += 1;
  }

  const state = await page.evaluate(() => window.__test.getState());
  const t1 = await page.evaluate(() => window.__test.clock?.() ?? 0);
  const won = state.phase === 'won';
  const lost = state.phase === 'lost';
  return {
    outcome: won ? 'won' : lost ? 'lost' : 'timeout',
    game_ms: Math.max(0, t1 - t0),
    steps,
    // 模拟器用 turn 表达进度，动作类用游戏毫秒
    progress: state.turn ?? Math.round(Math.max(0, t1 - t0) / 1000),
  };
}

async function main() {
  const projectDir = process.cwd();
  const variantDir = path.resolve(projectDir, arg('dir', 'variants'));
  const scenarioDir = path.resolve(projectDir, 'tests', 'scenarios');
  const outDir = path.resolve(projectDir, arg('out', 'docs/04-core-loop'));
  const only = arg('only', '');
  const port = Number(arg('port', '5195'));

  if (!fs.existsSync(variantDir)) {
    console.error(`没有变体目录：${variantDir}\n先建 variants/*.json`);
    process.exit(2);
  }
  let variants = fs
    .readdirSync(variantDir)
    .filter((f) => f.endsWith('.json'))
    .sort()
    .map((f) => JSON.parse(fs.readFileSync(path.join(variantDir, f), 'utf-8')));
  if (only) variants = variants.filter((v) => v.id === only || v.id.includes(only));
  if (!variants.length) {
    console.error('没有匹配的变体');
    process.exit(2);
  }

  const chrome = findChrome();
  if (!chrome) {
    console.error('找不到 Chrome，请设置 CHROME_PATH');
    process.exit(2);
  }

  process.stdout.write(`启动 dev server (${port}) … `);
  const { proc, url } = await startServer(projectDir, port);
  console.log('ok');

  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'new',
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--mute-audio'],
  });

  const results = [];
  for (const v of variants) {
    process.stdout.write(`  ${v.id} … `);
    const page = await browser.newPage();
    await page.setViewport({ width: 720, height: 1280, deviceScaleFactor: 1 });
    // 在页面脚本执行前注入变体，create() 时才读得到
    await page.evaluateOnNewDocument((ov) => {
      window.__VARIANT = ov;
    }, v.override ?? {});
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await ensureInGame(page);

    const scen = await runScenarios(page, scenarioDir);
    const play = await playOnce(page);
    results.push({
      id: v.id,
      name: v.name ?? v.id,
      desc: v.desc ?? '',
      scenarios: scen,
      play,
    });
    console.log(`${scen.pass}/${scen.total} 用例 · ${play.outcome} · ${play.progress} 单位 · ${play.steps} 步`);
    await page.close();
  }

  await browser.close();
  proc.kill();

  // ---- 对比表
  console.log('\n原型对比');
  console.log('═'.repeat(84));
  console.log(
    '变体'.padEnd(18) +
      '用例'.padEnd(10) +
      '结果'.padEnd(10) +
      '进度'.padEnd(12) +
      '操作'.padEnd(8) +
      '说明',
  );
  console.log('─'.repeat(84));
  for (const r of results) {
    console.log(
      `${r.id.padEnd(18)}` +
        `${`${r.scenarios.pass}/${r.scenarios.total}`.padEnd(10)}` +
        `${r.play.outcome.padEnd(10)}` +
        `${String(r.play.progress).padEnd(12)}` +
        `${String(r.play.steps).padEnd(8)}` +
        `${r.desc}`,
    );
  }

  // ---- 推荐：先看用例全过，再看通关，最后比进度（越短越紧凑）
  const viable = results.filter((r) => r.scenarios.pass === r.scenarios.total && r.play.outcome === 'won');
  console.log('\n结论');
  console.log('─'.repeat(84));
  if (viable.length) {
    viable.sort((a, b) => a.play.progress - b.play.progress);
    const best = viable[0];
    console.log(`推荐 ${best.id}（${best.name}）：用例全过、bot 能通关，且节奏最紧凑（${best.play.progress}）。`);
    const slowest = viable[viable.length - 1];
    if (slowest.id !== best.id) {
      console.log(`最拖的是 ${slowest.id}（${slowest.play.progress}）——同样的机制多花 ${
        slowest.play.progress - best.play.progress
      } 单位，除非有明确理由否则不选。`);
    }
  } else {
    const broken = results.filter((r) => r.scenarios.pass < r.scenarios.total);
    const unbeatable = results.filter((r) => r.play.outcome !== 'won');
    if (broken.length) console.log(`这些变体把机制改坏了：${broken.map((r) => r.id).join(', ')}`);
    if (unbeatable.length) console.log(`这些变体 bot 打不过：${unbeatable.map((r) => `${r.id}(${r.play.outcome})`).join(', ')}`);
    console.log('没有可推荐的变体。');
  }
  console.log('\n口径：bot 只代表「一个会按规则出牌的玩家」，不代表真实玩家手感。');

  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, 'prototype-comparison.json');
  fs.writeFileSync(
    outFile,
    JSON.stringify({ generated_at: new Date().toISOString(), url, variants: results }, null, 2) + '\n',
    'utf-8',
  );
  console.log(`\n报告: ${path.relative(projectDir, outFile)}`);
}

main().catch((e) => {
  console.error('compare 失败：', e?.message ?? e);
  process.exit(2);
});

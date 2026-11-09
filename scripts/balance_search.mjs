#!/usr/bin/env node
/**
 * Balance Search —— 数值平衡搜索。
 *
 * ## 它回答什么问题
 *
 * 不是「这个配置能不能过」，而是「**这个难度对新手的容错窗口有多大**」。
 *
 * 单靠一个人测是测不出来的：同一个人玩同一个配置只有一种结果。
 * 所以用两个不同水平的策略跑同一配置：
 *
 *   novice  按阅读顺序建塔、不评估覆盖、钱不够多就攒着  → 像第一次玩的人
 *   expert  逐个候选格算「射程内覆盖多少路径格」，选最多的 → 像算过的人
 *
 * ## 为什么不用「胜率」
 *
 * 塔防是确定性的：同一配置 + 同一策略 + 同一操作序列 = 同一结果。
 * 跑 10 次得到的是同一个样本，报「80% 胜率」是自欺欺人。
 *
 * 所以输出**二值结果 + 通关余量**（剩余生命 / 用时）。
 * 余量比胜负更有信息量：「新手剩 6 血勉强过」和「剩 10 血轻松过」是两种难度。
 *
 * ## 甜点判定
 *
 *   新手能过（生命 > 0）+ 老手轻松（生命满 + 用时短）= 甜点
 *   新手过不了 + 老手能过                        = 只有高手能玩
 *   两者都过不了                                  = 太难
 *   两者都轻松                                    = 太简单
 *
 * ## 用法
 *
 *   node scripts/balance_search.mjs                 # 用小网格（约 8 分钟）
 *   node scripts/balance_search.mjs --full          # 完整网格
 *   node scripts/balance_search.mjs --only towerCostMul=1.0
 *
 * 配置在 `balance-search.json`。
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
];
const arg = (n, d = '') => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};
const flag = (n) => process.argv.includes(`--${n}`);

function findChrome() {
  for (const c of CHROME_CANDIDATES) if (c && fs.existsSync(c)) return c;
  return '';
}

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
      /* 等 */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  proc.kill();
  throw new Error('vite 启动超时');
}

async function ensureInGame(page) {
  await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 });
  for (let i = 0; i < 8; i++) {
    if (await page.evaluate(() => !!(window.__test && window.__test.ready)).catch(() => false)) return;
    await page.keyboard.press('Space').catch(() => {});
    await new Promise((r) => setTimeout(r, 320));
  }
  throw new Error('进不去玩法场景');
}

/** 跑一局，返回结果与余量 */
async function playOnce(page, strategy, maxWallMs = 120000, maxSteps = 600) {
  await page.evaluate(() => window.__test.reset(0));
  await page.waitForFunction('window.__test && window.__test.ready', { timeout: 10000 });
  await page.evaluate(() => window.__test.settle(220));

  const t0 = await page.evaluate(() => window.__test.clock?.() ?? 0);
  const start = Date.now();
  let steps = 0;

  while (Date.now() - start < maxWallMs && steps < maxSteps) {
    if (await page.evaluate(() => window.__test.isOver()).catch(() => true)) break;

    const action = await page
      .evaluate((s) => {
        try {
          return window.__bot?.act?.(s, 0) ?? null;
        } catch {
          return null;
        }
      }, strategy)
      .catch(() => null);

    if (!action || !action.action || action.action === 'none') {
      await page.evaluate(() => window.__test.settle(120));
    } else if (action.action.startsWith('click:')) {
      const [, x, y] = action.action.split(':');
      await page.mouse.click(Number(x), Number(y)).catch(() => {});
      await page.evaluate(() => window.__test.settle(80));
    }
    steps += 1;
  }

  const st = await page.evaluate(() => window.__test.getState());
  const t1 = await page.evaluate(() => window.__test.clock?.() ?? 0);
  return {
    outcome: st.phase === 'won' ? 'won' : st.phase === 'lost' ? 'lost' : 'timeout',
    lives: st.lives ?? null,
    maxLives: st.startLives ?? null,
    gameSec: Math.round((t1 - t0) / 1000),
    towers: st.towerCount ?? null,
    kills: st.kills ?? null,
  };
}

function cartesian(params) {
  const keys = Object.keys(params);
  let out = [{}];
  for (const k of keys) {
    const next = [];
    for (const base of out) {
      for (const v of params[k]) next.push({ ...base, [k]: v });
    }
    out = next;
  }
  return out;
}

/** 甜点判定：新手能过 + 老手轻松 */
function verdictOf(novice, expert) {
  const nOk = novice && novice.outcome === 'won';
  const eOk = expert && expert.outcome === 'won';
  if (!nOk && !eOk) return { tag: 'TOO_HARD', note: '两个水平都过不了' };
  if (!nOk && eOk) return { tag: 'EXPERT_ONLY', note: '只有算过的人才过得了' };
  if (nOk && !eOk) return { tag: 'INCONSISTENT', note: '新手过、老手不过（策略可能有 bug）' };
  // 都过：看余量
  const nRatio = novice.maxLives ? novice.lives / novice.maxLives : 0;
  if (nRatio >= 0.9 && expert.gameSec < 25) return { tag: 'TOO_EASY', note: '两个水平都轻松' };
  if (nRatio >= 0.3) return { tag: 'SWEET_SPOT', note: '新手能过但有余量压力' };
  return { tag: 'TIGHT', note: '新手险过（余量 <30%）' };
}

async function main() {
  const projectDir = process.cwd();
  const specPath = path.resolve(projectDir, arg('spec', 'balance-search.json'));
  const outDir = path.resolve(projectDir, arg('out', 'docs/04-core-loop'));
  const port = Number(arg('port', '5192'));

  if (!fs.existsSync(specPath)) {
    console.error(`没有搜索配置：${specPath}`);
    process.exit(2);
  }
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf-8'));
  const strategies = spec.strategies ?? ['novice', 'expert'];
  const params = spec.params ?? {};
  if (!Object.keys(params).length) {
    console.error('params 为空，没东西可搜');
    process.exit(2);
  }

  // --only towerCostMul=1.0 收敛单参数
  const only = arg('only', '');
  if (only) {
    const [k, v] = only.split('=');
    if (k in params) params[k] = [Number(v)];
  }

  const grid = cartesian(params);
  console.log(`参数网格：${grid.length} 个配置 × ${strategies.length} 个策略 = ${grid.length * strategies.length} 局`);
  console.log(`预计耗时约 ${Math.round((grid.length * strategies.length * 55) / 60)} 分钟\n`);

  // --reanalyze：读已有报告重算结论，不重跑（改判定逻辑时用，省 5 分钟）
  if (flag('reanalyze')) {
    const prev = path.join(outDir, 'balance-search.json');
    if (!fs.existsSync(prev)) {
      console.error(`没有历史报告：${prev}`);
      process.exit(2);
    }
    const data = JSON.parse(fs.readFileSync(prev, 'utf-8'));
    console.log('重算历史结果（不重跑）\n');
    printReport(data.rows, Object.keys(data.params), data.strategies);
    return;
  }

  const chrome = findChrome();
  if (!chrome) {
    console.error('找不到 Chrome，设置 CHROME_PATH');
    process.exit(2);
  }

  process.stdout.write(`启动 dev server (${port}) … `);
  const { proc, url } = await startServer(projectDir, port);
  console.log('ok\n');

  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'new',
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--mute-audio'],
  });

  const rows = [];
  for (let i = 0; i < grid.length; i++) {
    const cfg = grid[i];
    const label = Object.entries(cfg)
      .map(([k, v]) => `${k}=${v}`)
      .join(' ');
    process.stdout.write(`[${i + 1}/${grid.length}] ${label} … `);

    const result = { config: cfg, runs: {} };
    for (const s of strategies) {
      const page = await browser.newPage();
      await page.setViewport({ width: 720, height: 1280, deviceScaleFactor: 1 });
      await page.evaluateOnNewDocument((ov) => {
        window.__VARIANT = ov;
      }, cfg);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await ensureInGame(page);
      result.runs[s] = await playOnce(page, s);
      await page.close();
      process.stdout.write(`${s}:${result.runs[s].outcome} `);
    }
    const v = verdictOf(result.runs[strategies[0]], result.runs[strategies[1]]);
    result.verdict = v;
    rows.push(result);
    console.log(`→ ${v.tag}`);
  }

  await browser.close();
  proc.kill();

  printReport(rows, Object.keys(params), strategies);

  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, 'balance-search.json');
  fs.writeFileSync(
    outFile,
    JSON.stringify({ generated_at: new Date().toISOString(), params, strategies, rows }, null, 2) + '\n',
    'utf-8',
  );
  console.log(`\n报告：${path.relative(projectDir, outFile)}`);
}

/** 打印表格与结论。抽出来是为了 --reanalyze 能复用，不必重跑。 */
function printReport(rows, keys, strategies) {
  // ---- 输出表
  console.log('\n平衡搜索');
  console.log('═'.repeat(90));
  const head = keys.map((k) => k.padEnd(14)).join('') + strategies.map((s) => s.padEnd(20)).join('') + '判定';
  console.log(head);
  console.log('─'.repeat(90));
  for (const r of rows) {
    const cfgStr = keys.map((k) => String(r.config[k]).padEnd(14)).join('');
    const runStr = strategies
      .map((s) => {
        const run = r.runs[s];
        if (!run) return '—'.padEnd(20);
        const mark = run.outcome === 'won' ? '✓' : '✗';
        return `${mark} ${run.lives}/${run.maxLives}血 ${run.gameSec}s`.padEnd(20);
      })
      .join('');
    console.log(cfgStr + runStr + r.verdict.tag);
  }

  // ---- 结论
  const sweet = rows.filter((r) => r.verdict.tag === 'SWEET_SPOT' || r.verdict.tag === 'TIGHT');
  console.log('\n结论');
  console.log('─'.repeat(90));
  if (sweet.length) {
    console.log(`甜点配置 ${sweet.length} 个：`);
    for (const r of sweet) {
      const label = keys.map((k) => `${k}=${r.config[k]}`).join(' ');
      const n = r.runs[strategies[0]];
      console.log(`  ${label}  →  新手 ${n.lives}/${n.maxLives} 血 ${n.gameSec}s（${r.verdict.note}）`);
    }
    /**
     * 推荐：余量合适 **且不能明显拖沓**。
     *
     * 只按余量选会踩坑：塔价调高后新手也能过，但用时翻倍 ——
     * 那是「节奏拖沓」不是「有压力」，玩家体验是变差而不是变好。
     * 所以先筛掉用时超过最短 1.3 倍的配置，再挑余量最接近 50% 的。
     */
    const times = sweet.map((r) => r.runs[strategies[0]].gameSec);
    const fastest = Math.min(...times);
    const eligible = sweet.filter((r) => r.runs[strategies[0]].gameSec <= fastest * 1.3);

    const scored = eligible
      .map((r) => {
        const n = r.runs[strategies[0]];
        const ratio = n.maxLives ? n.lives / n.maxLives : 0;
        return { r, ratio, dist: Math.abs(ratio - 0.5) };
      })
      .sort((a, b) => a.dist - b.dist);
    const best = scored[0];
    const label = keys.map((k) => `${k}=${best.r.config[k]}`).join(' ');
    const n = best.r.runs[strategies[0]];
    console.log(
      `\n推荐 ${label}：新手剩 ${Math.round(best.ratio * 100)}% 生命、${n.gameSec}s，` +
        `压力合适且节奏不拖。`,
    );
    const dropped = sweet.filter((r) => !eligible.includes(r));
    if (dropped.length) {
      console.log(
        `（排除了 ${dropped.length} 个「能过但拖沓」的配置：用时超过最快配置的 1.3 倍）`,
      );
    }
  } else {
    console.log('没有甜点配置。');
    const hard = rows.filter((r) => r.verdict.tag === 'TOO_HARD').length;
    const easy = rows.filter((r) => r.verdict.tag === 'TOO_EASY').length;
    const expertOnly = rows.filter((r) => r.verdict.tag === 'EXPERT_ONLY').length;
    if (hard) console.log(`  ${hard} 个配置太难（两个水平都过不了）`);
    if (expertOnly) console.log(`  ${expertOnly} 个只有老手能过`);
    if (easy) console.log(`  ${easy} 个太简单`);
  }
  console.log('\n口径：两个 bot 代表两种「按规则出牌」的水平，不代表真实玩家手感。');
}

main().catch((e) => {
  console.error('balance_search 失败：', e?.message ?? e);
  process.exit(2);
});

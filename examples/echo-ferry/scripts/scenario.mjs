#!/usr/bin/env node
/**
 * Scenario Runner —— 用声明式用例驱动游戏，做确定性断言。
 *
 * 与 `playtest.mjs` 的分工：
 *   playtest.mjs  探索型，随机操作，找「有没有异常」（不知道正确答案，只能看卡死/报错）
 *   scenario.mjs  验证型，确定动作 + 确定断言，判「行为对不对」（有明确期望值）
 *
 * 后者才是自动修复闭环的基础：修复前后跑同一批用例，才能算出质量变化。
 *
 * 用例格式见 references/game-test-schema.md。核心结构：
 *   {
 *     "id": "soul-delivery-memory-cap",
 *     "level": 1,
 *     "setup":  [{ "type": "set", "patch": { "memory": 5 } }],
 *     "steps":  [{ "type": "teleport", "c": 5, "r": 2 }, { "type": "move", "dc": 1, "dr": 0 }],
 *     "assertions": [
 *       { "path": "delivered", "op": "eq", "value": 1 },
 *       { "path": "memory", "op": "lte", "valuePath": "memoryMax" }
 *     ]
 *   }
 *
 * 用法:
 *   node scripts/scenario.mjs --serve                       # 自己起 vite，跑全部用例
 *   node scripts/scenario.mjs --url http://127.0.0.1:5199   # 连已有服务
 *   node scripts/scenario.mjs --only soul-delivery-memory-cap
 *   node scripts/scenario.mjs --repeat 3                     # 验证可复现性
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
  '/usr/bin/chromium',
].filter(Boolean);

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
function flag(name) {
  return process.argv.includes(`--${name}`);
}

function findChrome() {
  for (const c of CHROME_CANDIDATES) if (c && fs.existsSync(c)) return c;
  return '';
}

/** 点号路径取值：`player.c` → state.player.c */
function pick(obj, dotted) {
  return dotted.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

const OPS = {
  eq: (a, b) => a === b,
  ne: (a, b) => a !== b,
  gt: (a, b) => a > b,
  gte: (a, b) => a >= b,
  lt: (a, b) => a < b,
  lte: (a, b) => a <= b,
  truthy: (a) => !!a,
  falsy: (a) => !a,
};

/**
 * 求值一条断言。
 * `valuePath` 让断言可以「跟另一个字段比」——这是抓「忘 clamp」这类 bug 的关键：
 * 写死 `memory <= 5` 只能测一关，写 `memory <= memoryMax` 每关都成立。
 */
function evalAssertion(state, a) {
  const actual = pick(state, a.path);
  const expected = 'valuePath' in a ? pick(state, a.valuePath) : a.value;
  const op = OPS[a.op];
  if (!op) return { status: 'ERROR', expr: `${a.path} ${a.op} ?`, detail: `未知操作符 ${a.op}` };
  const ok = op(actual, expected);
  return {
    status: ok ? 'PASS' : 'FAIL',
    expr:
      a.op === 'truthy' || a.op === 'falsy'
        ? `${a.path} is ${a.op}`
        : `${a.path} ${a.op} ${'valuePath' in a ? a.valuePath : JSON.stringify(a.value)}`,
    expected,
    actual,
  };
}

async function startServer(projectDir, port) {
  const viteBin = path.join(projectDir, 'node_modules', 'vite', 'bin', 'vite.js');
  if (!fs.existsSync(viteBin)) throw new Error(`找不到 vite: ${viteBin}`);
  const proc = spawn(process.execPath, [viteBin, '--port', String(port), '--strictPort'], {
    cwd: projectDir,
    stdio: ['ignore', 'pipe', 'pipe'],
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
  throw new Error(`vite 启动超时（${url}）`);
}

/**
 * 确保已经进入可驱动的场景。
 *
 * 鸡生蛋问题：`__test` 只在玩法场景里注册，但页面启动后先停在菜单。
 * 通用做法是先按一次「开始键」（大多数小游戏都有），不行再点画布中心。
 * 这里不写死场景名——写死就把 runner 绑死在某一个游戏上了。
 */
async function ensureInGame(page, bootKey = 'Space') {
  try {
    await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 });
  } catch {
    throw new Error('boot 超时：__bootDone / __gameState 都未出现');
  }
  for (let i = 0; i < 4; i++) {
    const ready = await page.evaluate(() => !!(window.__test && window.__test.ready)).catch(() => false);
    if (ready) return;
    if (i === 3) await page.mouse.click(360, 640).catch(() => {});
    else await page.keyboard.press(bootKey).catch(() => {});
    await new Promise((r) => setTimeout(r, 350));
  }
  throw new Error(`进不去玩法场景：按了 ${bootKey} 与点击都没让 __test 就绪`);
}

async function runScenario(page, sc, url) {
  const t0 = Date.now();
  const log = [];

  // 重置到目标关卡：先 reset，等新场景的适配器挂上
  await page.evaluate(
    (level) => {
      if (!window.__test) throw new Error('__test 未安装：确认走的是 dev server（import.meta.env.DEV）');
      window.__test.reset(level);
    },
    (sc.level ?? 1) - 1,
  );
  await page.waitForFunction('window.__test && window.__test.ready', { timeout: 10000 });
  await page.evaluate(() => window.__test.settle(120));

  // 动作执行器：wait 走 settle，reset 要等新场景重建，其余直接 exec（同步生效）
  const run = async (actions) => {
    for (const a of actions ?? []) {
      if (a.type === 'wait') {
        await page.evaluate((ms) => window.__test.settle(ms), a.ms ?? 200);
      } else {
        await page.evaluate((act) => window.__test.exec(act), a);
        if (a.type === 'reset') {
          // scene.restart 会先 SHUTDOWN 再 create，适配器要重新注册
          await page.waitForFunction('window.__test && window.__test.ready', { timeout: 10000 });
          await page.evaluate(() => window.__test.settle(150));
        }
      }
      log.push(a.type);
    }
  };

  await run(sc.setup);
  await run(sc.steps);

  const state = await page.evaluate(() => window.__test.getState());
  const results = (sc.assertions ?? []).map((a) => evalAssertion(state, a));
  const failed = results.filter((r) => r.status !== 'PASS');

  return {
    id: sc.id,
    name: sc.name ?? sc.id,
    status: failed.length ? 'FAIL' : 'PASS',
    duration_ms: Date.now() - t0,
    actions: log,
    assertions: results,
    // 失败时把完整状态存下来，供 Issue Analyzer 定位
    state_on_failure: failed.length ? state : undefined,
  };
}

async function main() {
  const projectDir = process.cwd();
  const scenariosDir = arg('dir', path.join(projectDir, 'tests', 'scenarios'));
  const outDir = arg('out', path.join(projectDir, 'docs', '07-qa'));
  const only = arg('only', '');
  const repeat = Math.max(1, Number(arg('repeat', '1')));
  const port = Number(arg('port', '5199'));
  const bootKey = arg('boot-key', 'Space');

  if (!fs.existsSync(scenariosDir)) {
    console.error(`找不到用例目录: ${scenariosDir}`);
    process.exit(2);
  }

  const files = fs
    .readdirSync(scenariosDir)
    .filter((f) => f.endsWith('.json'))
    .sort();
  let scenarios = files.map((f) => JSON.parse(fs.readFileSync(path.join(scenariosDir, f), 'utf-8')));
  if (only) scenarios = scenarios.filter((s) => s.id === only || s.id.includes(only));
  if (!scenarios.length) {
    console.error('没有匹配的用例');
    process.exit(2);
  }

  let server = null;
  let url = arg('url', '');
  if (!url || flag('serve')) {
    process.stdout.write(`启动 dev server (${port}) … `);
    const s = await startServer(projectDir, port);
    server = s.proc;
    url = s.url;
    console.log('ok');
  }

  const chrome = findChrome();
  if (!chrome) {
    console.error('ERROR: 找不到 Chrome，请设置 CHROME_PATH');
    if (server) server.kill();
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

  const allRuns = [];
  for (let round = 1; round <= repeat; round++) {
    if (repeat > 1) console.log(`\n── 第 ${round}/${repeat} 轮（可复现性验证）`);
    const page = await browser.newPage();
    await page.setViewport({ width: 720, height: 1280, deviceScaleFactor: 1 });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e?.message ?? e)));
    page.on('console', (m) => {
      if (m.type() === 'error' && !/favicon|Failed to load resource|HTML5 SDK|throttled/i.test(m.text())) {
        pageErrors.push(m.text());
      }
    });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    try {
      await ensureInGame(page, bootKey);
    } catch (e) {
      pageErrors.push(String(e?.message ?? e));
      console.log(`  [ERROR] 无法进入玩法场景：${e?.message ?? e}`);
      await page.close();
      continue;
    }

    for (const sc of scenarios) {
      const r = await runScenario(page, sc, url).catch((e) => ({
        id: sc.id,
        name: sc.name ?? sc.id,
        status: 'ERROR',
        duration_ms: 0,
        assertions: [{ status: 'ERROR', expr: '执行异常', detail: String(e?.message ?? e) }],
      }));
      allRuns.push({ round, ...r, page_errors: pageErrors.slice(0, 5) });
      const mark = r.status === 'PASS' ? 'PASS' : r.status;
      console.log(`  [${mark}] ${r.id}  (${r.duration_ms}ms)`);
      if (r.status !== 'PASS') {
        for (const a of r.assertions.filter((x) => x.status !== 'PASS')) {
          if (a.detail) console.log(`         ${a.detail}`);
          else console.log(`         ${a.expr}  期望 ${JSON.stringify(a.expected)}  实际 ${JSON.stringify(a.actual)}`);
        }
      }
    }
    await page.close();
  }

  await browser.close();
  if (server) server.kill();

  // 可复现性：同一用例多轮结果必须一致
  const reproducible = repeat === 1 ? null : (() => {
    const byId = {};
    for (const r of allRuns) (byId[r.id] ??= []).push(r.status);
    const unstable = Object.entries(byId).filter(([, v]) => new Set(v).size > 1).map(([k]) => k);
    return { stable: unstable.length === 0, unstable };
  })();

  const total = allRuns.length;
  const passed = allRuns.filter((r) => r.status === 'PASS').length;
  const report = {
    generated_at: new Date().toISOString(),
    url,
    rounds: repeat,
    total,
    passed,
    failed: total - passed,
    pass_rate: total ? Math.round((passed / total) * 1000) / 10 : 0,
    reproducible,
    scenarios: allRuns,
    disclaimer: '场景断言验证的是「逻辑行为是否符合契约」，不等于玩家体验评价。',
  };

  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, 'scenario-report.json');
  fs.writeFileSync(outFile, JSON.stringify(report, null, 2), 'utf-8');

  console.log(`\n结果: ${passed}/${total} 通过 (${report.pass_rate}%)`);
  if (reproducible) console.log(`可复现性: ${reproducible.stable ? '稳定' : '不稳定 → ' + reproducible.unstable.join(', ')}`);
  console.log(`报告: ${outFile}`);
  if (passed !== total) process.exitCode = 1;
}

main().catch((e) => {
  console.error('scenario runner 失败：', e);
  process.exit(2);
});

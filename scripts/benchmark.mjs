#!/usr/bin/env node
/**
 * Benchmark —— 跨项目的质量基准，用于版本间对比。
 *
 * 为什么需要：单项目的用例只能回答「这次改坏了没」。要回答
 * 「新版本整体是变好了还是变差了」，必须有一组固定的项目、固定的指标、可对比的历史。
 * 没有基准，每次「优化」都只是感觉。
 *
 * 设计取舍：
 *   - **默认只读已有报告**（快、可频繁跑）。加 `--run` 才真跑测试。
 *   - 指标只取能自动算的。玩家满意度这类要真人数据，不塞进来假装是数字。
 *   - 每次输出带时间戳的快照，自动和上一次比，直接告诉你哪里退化。
 *
 * 用法：
 *   node scripts/benchmark.mjs                 # 汇总已有报告
 *   node scripts/benchmark.mjs --run           # 真跑每个项目的测试（慢）
 *   node scripts/benchmark.mjs --baseline      # 把本次结果标记为基线
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(__dirname, '..');
const BENCH_DIR = path.join(SKILL_DIR, 'benchmarks');
const REPORT_DIR = path.join(BENCH_DIR, 'reports');
const PROJECTS_FILE = path.join(BENCH_DIR, 'projects.json');

const flag = (n) => process.argv.includes(`--${n}`);
const arg = (n, d = '') => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

function readJson(p, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return fallback;
  }
}

/** 统计某项目的历史迭代结论，用于算回归率与人工介入率 */
function iterationStats(projDir) {
  const dir = path.join(projDir, '.gamedev', 'iterations');
  if (!fs.existsSync(dir)) return { total: 0, accepted: 0, rejected: 0, regressions: 0 };
  let total = 0;
  let accepted = 0;
  let rejected = 0;
  let regressions = 0;
  for (const d of fs.readdirSync(dir)) {
    const r = readJson(path.join(dir, d, 'iteration-report.json'));
    if (!r) continue;
    total += 1;
    if (r.verdict === 'ACCEPT') accepted += 1;
    else rejected += 1;
    if (Array.isArray(r.regressions) && r.regressions.length) regressions += 1;
  }
  return { total, accepted, rejected, regressions };
}

/** 产物体积：优先看 preview 构建 */
function bundleKb(projDir) {
  const candidates = [
    'dist/preview/index.js',
    'dist/crazygames/index.js',
    'dist/taptap/index.js',
  ];
  for (const rel of candidates) {
    const p = path.join(projDir, rel);
    if (fs.existsSync(p)) return Math.round(fs.statSync(p).size / 1024);
  }
  return null;
}

/** 素材台账（asset_registry.py 的产物）。没有就返回 null，不代表失败。 */
function assetStats(projDir) {
  const reg = readJson(path.join(projDir, 'assets', 'registry.json'));
  if (!reg?.summary) return null;
  return {
    images: reg.summary.images,
    image_kb: reg.summary.image_kb,
    audio: reg.summary.audio,
    audio_kb: reg.summary.audio_kb,
    ai: reg.summary.ai,
    procedural: reg.summary.procedural ?? 0,
    unknown: reg.summary.unknown,
    budget_kb: reg.budget_kb ?? null,
  };
}

function collect(proj) {
  const dir = path.resolve(path.dirname(PROJECTS_FILE), proj.path);
  const reportPath = path.join(dir, 'docs', '07-qa', 'scenario-report.json');
  const report = readJson(reportPath);

  if (!report) {
    return {
      id: proj.id,
      genre: proj.genre,
      path: proj.path,
      status: 'NO_REPORT',
      note: '没有 scenario-report.json，先跑 node scripts/scenario.mjs --serve',
    };
  }

  const it = iterationStats(dir);
  const scenarios = report.scenarios ?? [];
  const durations = scenarios.map((s) => s.duration_ms ?? 0);
  const failing = scenarios.filter((s) => s.status !== 'PASS').map((s) => s.id);

  return {
    id: proj.id,
    genre: proj.genre,
    path: proj.path,
    status: 'OK',
    pass_rate: report.pass_rate ?? null,
    passed: report.passed ?? 0,
    total: report.total ?? 0,
    rounds: report.rounds ?? 1,
    reproducible: report.reproducible?.stable ?? null,
    scenario_count: new Set(scenarios.map((s) => s.id)).size,
    avg_duration_ms: durations.length
      ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
      : 0,
    bundle_kb: bundleKb(dir),
    assets: assetStats(dir),
    failing,
    iterations: it,
    report_at: report.generated_at ?? null,
  };
}

function runScenarios(proj) {
  const dir = path.resolve(path.dirname(PROJECTS_FILE), proj.path);
  const script = path.join(dir, 'scripts', 'scenario.mjs');
  if (!fs.existsSync(script)) return { ok: false, note: '没有 scenario.mjs' };
  console.log(`  跑 ${proj.id} …`);
  const r = spawnSync(process.execPath, [script, '--serve', '--port', String(5190 + Math.floor(Math.random() * 8))], {
    cwd: dir,
    encoding: 'utf-8',
    timeout: 600000,
  });
  return { ok: r.status === 0, code: r.status };
}

function fmt(v, suffix = '') {
  return v === null || v === undefined ? '—' : `${v}${suffix}`;
}

function main() {
  const projects = readJson(PROJECTS_FILE);
  if (!projects?.projects?.length) {
    console.error(`没有基准项目清单：${PROJECTS_FILE}`);
    console.error('格式：{ "projects": [{ "id": "...", "path": "../xxx", "genre": "..." }] }');
    process.exit(2);
  }

  if (flag('run')) {
    console.log('重新跑所有项目的用例…');
    for (const p of projects.projects) runScenarios(p);
    console.log('');
  }

  const rows = projects.projects.map(collect);

  console.log('IdeaToGame Benchmark');
  console.log('═'.repeat(78));
  for (const r of rows) {
    if (r.status !== 'OK') {
      console.log(`${r.id.padEnd(16)} ${r.status}  ${r.note ?? ''}`);
      continue;
    }
    console.log(
      `${r.id.padEnd(16)} ${String(r.pass_rate).padStart(5)}%  ` +
        `${String(r.passed).padStart(3)}/${String(r.total).padEnd(3)}  ` +
        `用例 ${String(r.scenario_count).padStart(2)}  平均 ${String(r.avg_duration_ms).padStart(5)}ms  ` +
        `产物 ${fmt(r.bundle_kb, 'KB').padStart(8)}  ` +
        `迭代 ${r.iterations.total}（收 ${r.iterations.accepted} / 拒 ${r.iterations.rejected}）`,
    );
    if (r.failing.length) console.log(`${''.padEnd(16)} 失败: ${r.failing.join(', ')}`);
    if (r.assets) {
      const a = r.assets;
      console.log(
        `${''.padEnd(16)} 素材 图 ${a.images}（${a.image_kb}KB` +
          (a.budget_kb ? `/${a.budget_kb}KB` : '') +
          `）音频 ${a.audio}（${a.audio_kb}KB）· AI ${a.ai} / 程序化 ${a.procedural} / 不明 ${a.unknown}`,
      );
    } else {
      console.log(`${''.padEnd(16)} 素材 未登记（跑 asset_registry.py scan）`);
    }
  }

  // 与上一次对比
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const history = fs
    .readdirSync(REPORT_DIR)
    .filter((f) => f.endsWith('.json'))
    .sort();
  const prevPath = history.length ? path.join(REPORT_DIR, history[history.length - 1]) : null;
  const prev = prevPath ? readJson(prevPath) : null;

  if (prev) {
    console.log('\n与上次对比（' + path.basename(prevPath) + '）');
    console.log('─'.repeat(78));
    for (const r of rows) {
      const p = (prev.rows ?? []).find((x) => x.id === r.id);
      if (!p || r.status !== 'OK' || p.status !== 'OK') continue;
      const diffs = [];
      if (p.pass_rate !== r.pass_rate) diffs.push(`通过率 ${p.pass_rate}% → ${r.pass_rate}%`);
      if (p.scenario_count !== r.scenario_count) diffs.push(`用例 ${p.scenario_count} → ${r.scenario_count}`);
      if (p.avg_duration_ms !== r.avg_duration_ms) diffs.push(`耗时 ${p.avg_duration_ms} → ${r.avg_duration_ms}ms`);
      if (p.bundle_kb !== r.bundle_kb) diffs.push(`产物 ${fmt(p.bundle_kb)} → ${fmt(r.bundle_kb)}KB`);
      if (p.assets?.image_kb !== r.assets?.image_kb && r.assets) {
        diffs.push(`素材图 ${fmt(p.assets?.image_kb)} → ${fmt(r.assets.image_kb)}KB`);
      }
      if (diffs.length) console.log(`${r.id.padEnd(16)} ${diffs.join('；')}`);
      else console.log(`${r.id.padEnd(16)} 无变化`);
    }
  } else {
    console.log('\n（首次运行，已记为基线）');
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const outFile = path.join(REPORT_DIR, `${stamp}.json`);
  const payload = {
    generated_at: new Date().toISOString(),
    baseline: flag('baseline'),
    rows,
  };
  fs.writeFileSync(outFile, JSON.stringify(payload, null, 2) + '\n', 'utf-8');

  // 基线固定写一份，方便长期对照
  if (flag('baseline')) {
    fs.writeFileSync(path.join(BENCH_DIR, 'baseline.json'), JSON.stringify(payload, null, 2) + '\n', 'utf-8');
    console.log('\n已写入基线 benchmarks/baseline.json');
  }

  console.log(`\n快照: ${path.relative(SKILL_DIR, outFile)}`);
  console.log('\n口径说明：通过率只统计「用例断言」，不代表玩家体验；产物体积是未压缩 JS。');
}

try {
  main();
} catch (e) {
  console.error('benchmark 失败：', e?.message ?? e);
  process.exit(2);
}

#!/usr/bin/env node
/**
 * Playtest Report —— 把真人试玩的遥测 JSON 转成可行动的结论。
 *
 * ## 为什么需要它
 *
 * 遥测只记了「发生了什么」，不告诉你「哪里有问题」。
 * 这个脚本做的是**判断**：哪些指标越界、越界意味着什么、下一步该改什么。
 *
 * ## 三个核心指标
 *
 * | 指标 | 健康值 | 越界说明什么 |
 * |---|---|---|
 * | 首次建塔延迟 | < 10s | 太长 = 引导没让人看懂该干什么 |
 * | 最长空闲 | < 12s | 太长 = 卡住了或在找东西 |
 * | 崩盘波次 | ≥ 倒数第二波 | 太早 = 前中期难度陡增 |
 *
 * ## 用法
 *
 *   node scripts/playtest_report.mjs --dir ~/Downloads
 *   node scripts/playtest_report.mjs --file playtest-1699000000000.json
 *   node scripts/playtest_report.mjs --dir . --json docs/07-qa/playtest-analysis.json
 *
 * 多个文件会做聚合（平均首次建塔延迟、平均崩盘波次）。
 */

import fs from 'node:fs';
import path from 'node:path';

const arg = (n, d = '') => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

const THRESHOLDS = {
  firstBuildSec: 10,
  longestIdleSec: 12,
  /** 崩盘波次低于「总波数 - 1」就偏早 */
  earlyCollapseMargin: 1,
};

function loadFiles() {
  const file = arg('file', '');
  if (file) {
    const p = path.resolve(file);
    return fs.existsSync(p) ? [p] : [];
  }
  const dir = path.resolve(arg('dir', process.env.USERPROFILE ? path.join(process.env.USERPROFILE, 'Downloads') : '.'));
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => /^playtest-\d+\.json$/.test(f))
    .map((f) => path.join(dir, f))
    .sort();
}

function analyze(dump) {
  const s = dump.summary ?? {};
  const events = dump.events ?? [];
  const ev = (t) => events.filter((e) => e.type === t);

  // 点击热区：按格子聚合
  const heat = new Map();
  for (const c of ev('click')) {
    const cell = c.data?.cell;
    if (!cell) continue;
    heat.set(cell, (heat.get(cell) ?? 0) + 1);
  }
  const hotCells = [...heat.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);

  // 波次耗时
  const waves = ev('wave_clear').map((e) => ({ wave: e.data?.wave, t: e.t }));
  const waveDurations = waves.map((w, i) => ({
    wave: w.wave,
    sec: Math.round(((w.t - (i === 0 ? 0 : waves[i - 1].t)) / 1000) * 10) / 10,
  }));

  const issues = [];
  if (s.firstBuildSec !== null && s.firstBuildSec > THRESHOLDS.firstBuildSec) {
    issues.push({
      level: 'WARN',
      code: 'slow_first_build',
      msg: `首次建塔用了 ${s.firstBuildSec}s（>${THRESHOLDS.firstBuildSec}s）——引导可能没让人看懂该点哪`,
    });
  }
  if (s.longestIdleSec > THRESHOLDS.longestIdleSec) {
    issues.push({
      level: 'WARN',
      code: 'long_idle',
      msg: `最长空闲 ${s.longestIdleSec}s（>${THRESHOLDS.longestIdleSec}s）——玩家卡住了或在找东西`,
    });
  }
  if (s.outcome === 'lost' && s.waveReached > 0) {
    issues.push({
      level: 'INFO',
      code: 'collapse_point',
      msg: `在第 ${s.waveReached} 波后崩盘——这是难度陡增点`,
    });
  }
  if (s.builds === 0) {
    issues.push({ level: 'FAIL', code: 'no_build', msg: '整局没有建过塔——完全没理解玩法' });
  }
  if (s.clicks > 0 && s.builds > 0 && s.clicks / s.builds > 12) {
    issues.push({
      level: 'INFO',
      code: 'many_wasted_clicks',
      msg: `点击 ${s.clicks} 次只建了 ${s.builds} 座塔——大量无效点击，可能是误触或 UI 不明确`,
    });
  }

  return {
    game: dump.game,
    durationSec: Math.round((dump.durationMs ?? 0) / 100) / 10,
    outcome: s.outcome,
    clicks: s.clicks,
    builds: s.builds,
    upgrades: ev('upgrade').length,
    sells: ev('sell').length,
    leaks: s.leaks,
    firstBuildSec: s.firstBuildSec,
    longestIdleSec: s.longestIdleSec,
    waveReached: s.waveReached,
    waveDurations,
    hotCells: hotCells.map(([cell, n]) => ({ cell, clicks: n })),
    issues,
  };
}

function main() {
  const files = loadFiles();
  if (!files.length) {
    console.error('没找到 playtest-*.json。');
    console.error('  → 用 ?playtest=1 打开游戏玩一局，结束后会自动下载到「下载」目录');
    console.error('  → 或者用 --file / --dir 指定位置');
    process.exit(2);
  }

  console.log(`找到 ${files.length} 份试玩数据\n`);
  const results = [];
  for (const f of files) {
    try {
      const dump = JSON.parse(fs.readFileSync(f, 'utf-8'));
      results.push({ file: path.basename(f), ...analyze(dump) });
    } catch (e) {
      console.warn(`跳过 ${path.basename(f)}：${e.message}`);
    }
  }
  if (!results.length) {
    console.error('没有可解析的文件');
    process.exit(2);
  }

  // ---- 逐份
  for (const r of results) {
    console.log('─'.repeat(70));
    console.log(`${r.file}  ·  ${r.game}`);
    console.log(`  结果 ${r.outcome}  用时 ${r.durationSec}s  到第 ${r.waveReached} 波`);
    console.log(`  点击 ${r.clicks} · 建塔 ${r.builds} · 升级 ${r.upgrades} · 出售 ${r.sells} · 漏怪 ${r.leaks}`);
    console.log(`  首次建塔 ${r.firstBuildSec ?? '—'}s · 最长空闲 ${r.longestIdleSec}s`);
    if (r.waveDurations.length) {
      console.log(`  波次耗时 ${r.waveDurations.map((w) => `W${w.wave}:${w.sec}s`).join('  ')}`);
    }
    if (r.hotCells.length) {
      console.log(`  点击最多 ${r.hotCells.map((h) => `${h.cell}×${h.clicks}`).join('  ')}`);
    }
    for (const i of r.issues) console.log(`  [${i.level}] ${i.msg}`);
  }

  // ---- 聚合
  if (results.length > 1) {
    const avg = (key) => {
      const vals = results.map((r) => r[key]).filter((v) => typeof v === 'number');
      return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : null;
    };
    const winRate = results.filter((r) => r.outcome === 'won').length / results.length;
    console.log('\n' + '═'.repeat(70));
    console.log('聚合');
    console.log(`  样本 ${results.length} 份 · 通关率 ${Math.round(winRate * 100)}%`);
    console.log(`  平均首次建塔 ${avg('firstBuildSec')}s · 平均最长空闲 ${avg('longestIdleSec')}s`);
    console.log(`  平均崩盘波次 ${avg('waveReached')}`);
  }

  // ---- 结论
  console.log('\n' + '═'.repeat(70));
  const allIssues = results.flatMap((r) => r.issues);
  const fails = allIssues.filter((i) => i.level === 'FAIL');
  const warns = allIssues.filter((i) => i.level === 'WARN');
  if (!allIssues.length) {
    console.log('没有发现明显问题。但这只说明「没崩」，不代表好玩——趣味性仍需主观反馈。');
  } else {
    if (fails.length) {
      console.log(`必须修 ${fails.length} 项：`);
      for (const i of fails) console.log(`  ✗ ${i.msg}`);
    }
    if (warns.length) {
      console.log(`建议改 ${warns.length} 项：`);
      for (const i of warns) console.log(`  ! ${i.msg}`);
    }
    const infos = allIssues.filter((i) => i.level === 'INFO');
    if (infos.length) {
      console.log(`参考 ${infos.length} 项：`);
      for (const i of infos) console.log(`  · ${i.msg}`);
    }
  }
  console.log('\n口径：遥测只记录行为，不记录感受。觉得「好不好玩」必须问人。');

  const out = arg('json', '');
  if (out) {
    const p = path.resolve(out);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify({ generated_at: new Date().toISOString(), samples: results }, null, 2) + '\n', 'utf-8');
    console.log(`\n报告：${out}`);
  }
}

try {
  main();
} catch (e) {
  console.error('playtest_report 失败：', e?.message ?? e);
  process.exit(2);
}

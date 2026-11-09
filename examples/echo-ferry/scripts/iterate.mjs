#!/usr/bin/env node
/**
 * Iteration Manager —— 自动修复闭环的护栏。
 *
 * 它自己不改代码。它负责三件事，而这正是「自动修复」能不能信的前提：
 *   1. 改动前留 checkpoint（能回滚）
 *   2. 改动后校验「只改了允许改的地方」（防止修 A 崩 B）
 *   3. 跑目标用例 + 全量回归，算出质量变化（拒绝口头声称「修好了」）
 *
 * 为什么不直接 `git commit`：本项目不是 git 仓库，且工作区禁 rebase。
 * 文件快照同样能精确回滚，还不污染历史。
 *
 * 子命令：
 *   start    --issue <issue.json>   快照当前代码 + 备份基线测试报告
 *   verify   --issue <issue.json>   校验改动范围 → 跑测试 → 出质量变化 → 判定
 *   rollback --issue <issue.json>   恢复快照
 *   list                            列出所有迭代
 *
 * Issue 定义（docs/10-iteration/ISS-xxx.json）：
 *   {
 *     "id": "ISS-001",
 *     "type": "gameplay_bugfix",
 *     "severity": "high",
 *     "detected_by": "02-memory-cap",
 *     "description": "送达奖励突破记忆上限",
 *     "allowed_paths": ["src/game/"],
 *     "forbidden_paths": ["assets/", "docs/09-review/"],
 *     "validation": ["02-memory-cap", "01-core-loop"]
 *   }
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const ROOT = process.cwd();
const ITER_DIR = path.join(ROOT, '.gamedev', 'iterations');
const QA_DIR = path.join(ROOT, 'docs', '07-qa');
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '.gamedev', '__pycache__']);

function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex').slice(0, 16);
}

/** 递归收集某个相对路径下的文件（相对 ROOT）。 */
function collect(relPath) {
  const abs = path.join(ROOT, relPath);
  const out = [];
  if (!fs.existsSync(abs)) return out;
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(e.name)) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.isFile()) out.push(path.relative(ROOT, full).replace(/\\/g, '/'));
    }
  };
  const st = fs.statSync(abs);
  if (st.isFile()) out.push(relPath.replace(/\\/g, '/'));
  else walk(abs);
  return out;
}

function iterPath(issue) {
  return path.join(ITER_DIR, issue.id);
}

function snapshot(issue) {
  const dir = iterPath(issue);
  const snapDir = path.join(dir, 'snapshot');
  fs.rmSync(snapDir, { recursive: true, force: true });
  fs.mkdirSync(snapDir, { recursive: true });

  const files = [...new Set(issue.allowed_paths.flatMap(collect))].sort();
  const manifest = {};
  for (const rel of files) {
    const buf = fs.readFileSync(path.join(ROOT, rel));
    manifest[rel] = sha256(buf);
    const dst = path.join(snapDir, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.writeFileSync(dst, buf);
  }
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({ id: issue.id, files: manifest }, null, 2));

  // 备份基线报告，verify 时用来算质量变化
  const baseline = path.join(QA_DIR, 'scenario-report.json');
  if (fs.existsSync(baseline)) {
    fs.copyFileSync(baseline, path.join(dir, 'before-report.json'));
  }
  fs.writeFileSync(path.join(dir, 'issue.json'), JSON.stringify(issue, null, 2));
  return { dir, count: files.length };
}

/** 对比快照，找出增删改。 */
function diffAgainstSnapshot(issue) {
  const dir = iterPath(issue);
  const manifestPath = path.join(dir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) throw new Error(`没有 checkpoint，先跑 start：${issue.id}`);
  const old = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')).files;

  // 现在 allowed_paths 下的文件
  const now = {};
  for (const rel of [...new Set(issue.allowed_paths.flatMap(collect))].sort()) {
    now[rel] = sha256(fs.readFileSync(path.join(ROOT, rel)));
  }

  const changed = [];
  const added = [];
  const deleted = [];
  for (const [rel, h] of Object.entries(now)) {
    if (!(rel in old)) added.push(rel);
    else if (old[rel] !== h) changed.push(rel);
  }
  for (const rel of Object.keys(old)) if (!(rel in now)) deleted.push(rel);
  return { changed, added, deleted };
}

/** 路径合规：改动必须在 allowed 内、不在 forbidden 内。 */
function checkScope(issue, diff) {
  const norm = (p) => p.replace(/\\/g, '/');
  const inside = (p, prefixes) => prefixes.some((pre) => norm(p).startsWith(norm(pre)));
  const violations = [];
  for (const rel of [...diff.changed, ...diff.added, ...diff.deleted]) {
    if (issue.forbidden_paths?.length && inside(rel, issue.forbidden_paths)) {
      violations.push({ path: rel, reason: '命中 forbidden_paths' });
    } else if (!inside(rel, issue.allowed_paths)) {
      violations.push({ path: rel, reason: '不在 allowed_paths 内' });
    }
  }
  return violations;
}

/** 生成可读 diff（Git Bash 自带 diff；没有就跳过，不阻断）。 */
function makePatch(issue, diff) {
  const dir = iterPath(issue);
  const snapDir = path.join(dir, 'snapshot');
  const chunks = [];
  for (const rel of [...diff.changed, ...diff.deleted]) {
    const a = path.join(snapDir, rel);
    const b = path.join(ROOT, rel);
    const r = spawnSync('diff', ['-u', '--label', `a/${rel}`, a, '--label', `b/${rel}`, b], {
      encoding: 'utf-8',
    });
    if (r.stdout) chunks.push(r.stdout);
  }
  const text = chunks.join('\n');
  if (text) fs.writeFileSync(path.join(dir, 'patch.diff'), text, 'utf-8');
  return text;
}

function runScenarios(outDir, only) {
  const args = [path.join(ROOT, 'scripts', 'scenario.mjs'), '--serve', '--port', '5199', '--out', outDir];
  if (only) args.push('--only', only);
  const r = spawnSync(process.execPath, args, { cwd: ROOT, encoding: 'utf-8', timeout: 300000 });
  const reportPath = path.join(outDir, 'scenario-report.json');
  const report = fs.existsSync(reportPath) ? JSON.parse(fs.readFileSync(reportPath, 'utf-8')) : null;
  return { report, stdout: (r.stdout || '') + (r.stderr || ''), code: r.status };
}

function cmdStart(issue) {
  const { dir, count } = snapshot(issue);
  console.log(`checkpoint 已建: ${dir}`);
  console.log(`  快照 ${count} 个文件（${issue.allowed_paths.join(', ')}）`);
  console.log(`  基线报告: ${fs.existsSync(path.join(dir, 'before-report.json')) ? '已备份' : '无（先跑一次 scenario）'}`);
}

function cmdVerify(issue) {
  const dir = iterPath(issue);
  const diff = diffAgainstSnapshot(issue);
  const violations = checkScope(issue, diff);
  const patch = makePatch(issue, diff);

  console.log(`\n迭代 ${issue.id} · ${issue.description}`);
  console.log('─'.repeat(56));
  console.log(`改动: ${diff.changed.length} 改 / ${diff.added.length} 增 / ${diff.deleted.length} 删`);
  for (const f of [...diff.changed, ...diff.added]) console.log(`  M ${f}`);
  for (const f of diff.deleted) console.log(`  D ${f}`);
  if (patch) console.log(`  patch.diff: ${patch.split('\n').filter((l) => l.startsWith('+') || l.startsWith('-')).length} 行变更`);

  if (violations.length) {
    console.log('\n越界改动（直接判 REJECT）：');
    for (const v of violations) console.log(`  ✗ ${v.path} — ${v.reason}`);
  }

  if (!diff.changed.length && !diff.added.length && !diff.deleted.length) {
    console.log('\n没有任何改动，无法验证修复。');
    writeReport(issue, { diff, violations, verdict: 'NO_CHANGE' });
    process.exitCode = 1;
    return;
  }

  console.log('\n跑测试…');
  const afterDir = path.join(dir, 'after');
  const { report: after } = runScenarios(afterDir);

  const beforePath = path.join(dir, 'before-report.json');
  const before = fs.existsSync(beforePath) ? JSON.parse(fs.readFileSync(beforePath, 'utf-8')) : null;

  const beforeMap = {};
  for (const s of before?.scenarios ?? []) beforeMap[s.id] = s.status;
  const afterMap = {};
  for (const s of after?.scenarios ?? []) afterMap[s.id] = s.status;

  console.log('\n质量变化:');
  const allIds = [...new Set([...Object.keys(beforeMap), ...Object.keys(afterMap)])].sort();
  const regressions = [];
  const fixed = [];
  for (const id of allIds) {
    const b = beforeMap[id] ?? '—';
    const a = afterMap[id] ?? '—';
    const arrow = b === a ? '=' : `${b} → ${a}`;
    console.log(`  ${id.padEnd(26)} ${arrow}`);
    if (b === 'PASS' && a !== 'PASS') regressions.push(id);
    if (b !== 'PASS' && a === 'PASS') fixed.push(id);
  }

  const targetOk = issue.validation.every((id) => afterMap[id] === 'PASS');
  const passRate = after ? `${after.passed}/${after.total}` : '未跑出报告';

  let verdict = 'ACCEPT';
  const reasons = [];
  if (violations.length) {
    verdict = 'REJECT';
    reasons.push('存在越界改动');
  }
  if (!targetOk) {
    verdict = 'REJECT';
    reasons.push(`目标用例未全部通过: ${issue.validation.filter((id) => afterMap[id] !== 'PASS').join(', ')}`);
  }
  if (regressions.length) {
    verdict = 'REJECT';
    reasons.push(`引入回归: ${regressions.join(', ')}`);
  }

  console.log('\n判定: ' + verdict);
  console.log(`  通过率: ${passRate}`);
  if (fixed.length) console.log(`  修复: ${fixed.join(', ')}`);
  if (reasons.length) for (const r of reasons) console.log(`  原因: ${r}`);
  if (verdict === 'ACCEPT') console.log(`  下一步: node scripts/iterate.mjs rollback --issue ${issue.id} 可随时回滚`);

  writeReport(issue, { diff, violations, before: beforeMap, after: afterMap, fixed, regressions, verdict, reasons, passRate });
  if (verdict !== 'ACCEPT') process.exitCode = 1;
}

function writeReport(issue, data) {
  const dir = iterPath(issue);
  fs.mkdirSync(dir, { recursive: true });
  const report = { issue: issue.id, description: issue.description, at: new Date().toISOString(), ...data };
  fs.writeFileSync(path.join(dir, 'iteration-report.json'), JSON.stringify(report, null, 2), 'utf-8');
  console.log(`\n报告: ${path.join(dir, 'iteration-report.json')}`);
}

function cmdRollback(issue) {
  const dir = iterPath(issue);
  const snapDir = path.join(dir, 'snapshot');
  const manifestPath = path.join(dir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) throw new Error(`没有 checkpoint: ${issue.id}`);
  const files = Object.keys(JSON.parse(fs.readFileSync(manifestPath, 'utf-8')).files);
  let n = 0;
  for (const rel of files) {
    const src = path.join(snapDir, rel);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(ROOT, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    n++;
  }
  console.log(`已回滚 ${n} 个文件到 checkpoint 状态（${issue.id}）`);
}

function cmdList() {
  if (!fs.existsSync(ITER_DIR)) {
    console.log('还没有迭代记录');
    return;
  }
  for (const d of fs.readdirSync(ITER_DIR)) {
    const rp = path.join(ITER_DIR, d, 'iteration-report.json');
    if (fs.existsSync(rp)) {
      const r = JSON.parse(fs.readFileSync(rp, 'utf-8'));
      console.log(`${d.padEnd(12)} ${String(r.verdict).padEnd(10)} ${r.description ?? ''}`);
    } else {
      console.log(`${d.padEnd(12)} (checkpoint 已建，未验证)`);
    }
  }
}

function main() {
  const cmd = process.argv[2];
  const issuePath = arg('issue', '');
  if (cmd === 'list') return cmdList();
  if (!issuePath) {
    console.error('用法: iterate.mjs <start|verify|rollback|list> --issue docs/10-iteration/ISS-001.json');
    process.exit(2);
  }
  const issue = JSON.parse(fs.readFileSync(path.resolve(ROOT, issuePath), 'utf-8'));
  if (!issue.id || !issue.allowed_paths) throw new Error('issue 缺少 id / allowed_paths');
  if (!Array.isArray(issue.validation)) issue.validation = [];

  if (cmd === 'start') return cmdStart(issue);
  if (cmd === 'verify') return cmdVerify(issue);
  if (cmd === 'rollback') return cmdRollback(issue);
  console.error(`未知子命令: ${cmd}`);
  process.exit(2);
}

try {
  main();
} catch (e) {
  console.error('iterate 失败：', e?.message ?? e);
  process.exit(2);
}

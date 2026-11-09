#!/usr/bin/env node
/**
 * Diagnose —— Issue Analyzer + Iteration Planner。
 *
 * 补上自动修复闭环里缺的那一环：**从失败报告定位到代码行**。
 * 在此之前这一步是人看的，人是瓶颈；只有定位自动化，`iterate.mjs` 才谈得上闭环。
 *
 * 定位不靠大模型，靠三件事：
 *   1. 断言里的字段名（`memory lte memoryMax` → 找 `memory` 的写入点）
 *   2. 断言的失败方向（实际值偏大 → 找「增加」的赋值；偏小 → 找「减少」的）
 *   3. 代码位置上下文（在 update/hit 等逻辑函数里加分，在 create/init 里减分）
 *
 * 这是启发式，会给候选而不是「唯一答案」。它的价值是**把搜索范围从整个仓库
 * 缩到 2–3 行**，人只需要在这几行里判断。
 *
 * 用法：
 *   node scripts/diagnose.mjs                                  # 读默认报告，打印候选
 *   node scripts/diagnose.mjs --report docs/07-qa/scenario-report.json
 *   node scripts/diagnose.mjs --write                          # 生成 issue JSON 到 docs/10-iteration/
 *   node scripts/diagnose.mjs --src src                        # 指定源码根目录
 */

import fs from 'node:fs';
import path from 'node:path';

const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '__pycache__', '.gamedev', 'docs', 'tests']);
const CODE_EXT = new Set(['.ts', '.js', '.tsx', '.jsx', '.mjs']);

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const flag = (name) => process.argv.includes(`--${name}`);

/** 从断言路径里取出最有信息量的字段名 */
function fieldOf(assertPath) {
  const parts = String(assertPath ?? '').split('.');
  let last = parts[parts.length - 1];
  if (/^\d+$/.test(last)) last = parts[parts.length - 2];
  // c / r / 0 这种太短，退回第一段（player.c → player 反而没信息，就用 c）
  return last || parts[0] || '';
}

/** 递归收集源码文件 */
function collectSources(root) {
  const out = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (SKIP_DIRS.has(e.name)) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.isFile() && CODE_EXT.has(path.extname(e.name))) out.push(full);
    }
  };
  walk(root);
  return out;
}

/** 向上找最近的函数/方法名，用于判断这段代码在什么上下文里 */
function enclosingFn(lines, idx) {
  for (let i = idx; i >= 0 && i > idx - 60; i--) {
    const m = lines[i].match(/^\s*(?:private\s+|public\s+|protected\s+|static\s+|async\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*[:{]/);
    if (m) return m[1];
    const f = lines[i].match(/^\s*(?:export\s+)?function\s+([A-Za-z_$][\w$]*)/);
    if (f) return f[1];
  }
  return '';
}

/**
 * 给候选行打分。分数只用于排序，不代表「一定是这里」。
 */
function scoreCandidate(match, failure) {
  const { line, fn } = match;
  let score = 0;
  const reasons = [];

  const hasArith = /[+\-*/]=|[+\-]\s*\d/.test(line);
  if (hasArith) {
    score += 3;
    reasons.push('含运算赋值');
  }
  if (fn && /update|hit|deliver|spawn|fire|step|move|apply|resolve|kill|leak|damage/i.test(fn)) {
    score += 2;
    reasons.push(`在逻辑函数 ${fn}() 内`);
  }
  if (fn && /create|init|reset|constructor|setup/i.test(fn)) {
    score -= 2;
    reasons.push(`在初始化函数 ${fn}() 内（不太可能是 bug 点）`);
  }

  // 失败方向：实际值比期望大 → 多加了；比期望小 → 少加了 / 多减了
  const { op, expected, actual } = failure;
  const over = typeof actual === 'number' && typeof expected === 'number' && actual > expected;
  const under = typeof actual === 'number' && typeof expected === 'number' && actual < expected;
  if (['lte', 'lt'].includes(op) && over && /[+]=|\+\s*\d/.test(line)) {
    score += 4;
    reasons.push('实际值偏大，该行在做增加');
  }
  if (['gte', 'gt'].includes(op) && under && /[-]=|-\s*\d/.test(line)) {
    score += 4;
    reasons.push('实际值偏小，该行在做减少');
  }
  if (op === 'eq' && hasArith) {
    score += 1;
    reasons.push('等值断言，运算赋值是常见原因');
  }

  return { score, reasons };
}

/** 在源码里找某个字段的写入点 */
function findAssignments(sources, field) {
  if (!field) return [];
  // 匹配 `field =` / `field +=` / `this.field -=` / `field:`（对象字面量）
  // 注意不能排除 `.`：`e.hp -= dmg` 这种成员赋值恰恰是最常见的 bug 点。
  // 靠「字段名后必须紧跟赋值符」来排除 `hpBar` 这类误匹配。
  const re = new RegExp(`(^|[^\\w$])${field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*(?:[-+*/]?=|:)`, '');
  const hits = [];
  for (const file of sources) {
    const text = fs.readFileSync(file, 'utf-8');
    const lines = text.split(/\r?\n/);
    lines.forEach((line, i) => {
      if (/^\s*(\/\/|\*|\/\*)/.test(line)) return; // 跳过注释
      if (re.test(line)) {
        const hit = { file, lineNo: i + 1, line: line.trim(), fn: enclosingFn(lines, i), related: null };
        // 二跳：`e.hp -= dmg` 里 dmg 是怎么算出来的，往往才是真正的 bug 行
        const rhs = line.match(/[-+*/]=\s*([A-Za-z_$][\w$]*)/);
        if (rhs) {
          const varName = rhs[1];
          for (let j = i; j >= 0 && j > i - 40; j--) {
            if (new RegExp(`(?:const|let|var)\\s+${varName}\\s*=`).test(lines[j])) {
              hit.related = { lineNo: j + 1, line: lines[j].trim() };
              break;
            }
          }
        }
        hits.push(hit);
      }
    });
  }
  return hits;
}

/** 从断言与状态快照推断「问题现象」的一句话描述 */
function describeFailure(sc, a) {
  const dir =
    typeof a.actual === 'number' && typeof a.expected === 'number'
      ? a.actual > a.expected
        ? '偏大'
        : '偏小'
      : '不符';
  return `${sc.id}：${a.expr}（期望 ${JSON.stringify(a.expected)}，实际 ${JSON.stringify(a.actual)}，${dir}）`;
}

function main() {
  const projectDir = process.cwd();
  const reportPath = path.resolve(projectDir, arg('report', 'docs/07-qa/scenario-report.json'));
  const srcRoot = path.resolve(projectDir, arg('src', 'src'));
  const write = flag('write');

  if (!fs.existsSync(reportPath)) {
    console.error(`找不到测试报告：${reportPath}\n先跑 node scripts/scenario.mjs --serve`);
    process.exit(2);
  }
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
  const failures = (report.scenarios ?? []).filter((s) => s.status !== 'PASS');

  console.log(`诊断报告：${reportPath}`);
  console.log(`通过 ${report.passed ?? 0}/${report.total ?? 0}`);

  if (!failures.length) {
    console.log('\n没有失败用例，无需诊断。');
    return;
  }

  const sources = collectSources(srcRoot);
  console.log(`源码文件 ${sources.length} 个（${path.relative(projectDir, srcRoot) || '.'}）\n`);

  const issues = [];
  for (const sc of failures) {
    console.log('─'.repeat(64));
    console.log(`${sc.status}  ${sc.id}  ${sc.name ?? ''}`);
    const bad = (sc.assertions ?? []).filter((a) => a.status !== 'PASS');
    if (!bad.length) {
      console.log('  （用例整体失败但没有断言明细，可能是执行异常）');
      if (sc.page_errors?.length) for (const e of sc.page_errors) console.log(`  page_error: ${e}`);
      continue;
    }

    const candidates = [];
    for (const a of bad) {
      console.log(`  断言 ${a.expr}`);
      const field = fieldOf(a.path);
      const hits = findAssignments(sources, field);
      const scored = hits
        .map((h) => {
          const { score, reasons } = scoreCandidate(h, a);
          return { ...h, score, reasons };
        })
        .filter((h) => h.score > 0)
        .sort((x, y) => y.score - x.score)
        .slice(0, 3);

      if (!scored.length) {
        console.log(`    （没找到字段 ${field} 的写入点，可能问题在读取侧或数值配置）`);
        continue;
      }
      scored.forEach((h, i) => {
        const rel = path.relative(projectDir, h.file).replace(/\\/g, '/');
        console.log(`    ${i + 1}. ${rel}:${h.lineNo}  ${h.line}`);
        if (h.related) {
          console.log(`       ↑ 计算来源 ${rel}:${h.related.lineNo}  ${h.related.line}`);
        }
        console.log(`       得分 ${h.score} · ${h.reasons.join('；')}`);
        candidates.push({ ...h, rel, field, assertion: a });
      });
    }

    if (!candidates.length) continue;

    // allowed_paths 取候选文件所在目录（去重）
    const dirs = [...new Set(candidates.map((c) => path.posix.dirname(c.rel) + '/'))];
    // validation：失败用例 + 同目录其它用例（最多 3 条）
    const siblings = (report.scenarios ?? [])
      .filter((s) => s.status === 'PASS' && s.id !== sc.id)
      .slice(0, 3)
      .map((s) => s.id);

    const issue = {
      id: `ISS-AUTO-${String(issues.length + 1).padStart(3, '0')}`,
      type: 'gameplay_bugfix',
      severity: bad.some((a) => a.op === 'eq') ? 'high' : 'medium',
      detected_by: sc.id,
      detected_at: new Date().toISOString().slice(0, 10),
      description: describeFailure(sc, bad[0]),
      evidence: bad.map((a) => ({ assertion: a.expr, expected: a.expected, actual: a.actual })),
      candidate_locations: candidates.map((c) => ({
        file: c.rel,
        line: c.lineNo,
        code: c.line,
        related_line: c.related?.lineNo ?? null,
        related_code: c.related?.line ?? null,
        score: c.score,
        reasons: c.reasons,
      })),
      root_cause: `待确认（候选 ${candidates.length} 处，优先看第 1 条）`,
      allowed_paths: dirs,
      forbidden_paths: ['assets/', 'docs/09-review/', 'tests/scenarios/'],
      validation: [sc.id, ...siblings],
    };
    issues.push(issue);

    console.log('\n  建议 issue：');
    console.log(`    allowed_paths : ${JSON.stringify(issue.allowed_paths)}`);
    console.log(`    validation    : ${JSON.stringify(issue.validation)}`);
  }

  if (write && issues.length) {
    const outDir = path.join(projectDir, 'docs', '10-iteration');
    fs.mkdirSync(outDir, { recursive: true });
    for (const it of issues) {
      const f = path.join(outDir, `${it.id}.json`);
      fs.writeFileSync(f, JSON.stringify(it, null, 2) + '\n', 'utf-8');
      console.log(`\n已写入 ${path.relative(projectDir, f)}`);
    }
    console.log('\n下一步：node scripts/iterate.mjs start --issue <上面生成的 json>');
  }

  console.log('\n提醒：候选位置是启发式排序，不是结论。确认根因后再改代码。');
}

try {
  main();
} catch (e) {
  console.error('diagnose 失败：', e?.message ?? e);
  process.exit(2);
}

#!/usr/bin/env node
/**
 * Phaser 场景生命周期契约：create() 必须同步返回。
 *
 * 用法：
 *   node scripts/check_scene_lifecycle.mjs --project .
 *   node scripts/check_scene_lifecycle.mjs --project . --typescript <typescript-module>
 *
 * 只检查 create() 方法自身直接包含的 await；事件回调等嵌套函数中的 await
 * 不属于 create() 的直接异步点，不会被误报。
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

function arg(name, fallback = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

if (process.argv.includes('--help')) {
  console.log('Usage: node check_scene_lifecycle.mjs --project <dir> [--typescript <module-path>]');
  process.exit(0);
}

const project = path.resolve(arg('project', '.'));
const scenesDir = path.join(project, 'src', 'game', 'scenes');
if (!fs.existsSync(scenesDir)) {
  console.log(`SKIP: no scene directory at ${scenesDir}`);
  process.exit(0);
}

function loadTypeScript() {
  const requireFromProject = createRequire(path.join(project, 'package.json'));
  const explicit = arg('typescript');
  try {
    return explicit ? requireFromProject(path.resolve(explicit)) : requireFromProject('typescript');
  } catch (error) {
    console.error(`ERROR: cannot load TypeScript for ${project}`);
    console.error(String(error?.message ?? error));
    process.exit(2);
  }
}

const ts = loadTypeScript();

function walkTs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkTs(full));
    else if (entry.isFile() && entry.name.endsWith('.ts')) out.push(full);
  }
  return out;
}

function methodName(node, sourceFile) {
  if (!node.name) return '';
  if (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name)) return node.name.text;
  return node.name.getText(sourceFile);
}

function hasAsyncModifier(node) {
  return Boolean(node.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword));
}

const violations = [];
let createCount = 0;

for (const file of walkTs(scenesDir)) {
  const source = fs.readFileSync(file, 'utf-8');
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const rel = path.relative(project, file).replaceAll('\\', '/');

  function visit(node) {
    if (ts.isMethodDeclaration(node) && methodName(node, sourceFile) === 'create') {
      createCount += 1;
      const start = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      const where = `${rel}:${start.line + 1}`;

      if (hasAsyncModifier(node)) {
        violations.push(`${where} async create() is forbidden`);
      }

      if (node.body) {
        function findDirectAwait(child) {
          if (child !== node.body && ts.isFunctionLike(child)) return;
          if (ts.isAwaitExpression(child)) {
            const p = sourceFile.getLineAndCharacterOfPosition(child.getStart(sourceFile));
            violations.push(`${rel}:${p.line + 1} direct await inside create()`);
          }
          ts.forEachChild(child, findDirectAwait);
        }
        findDirectAwait(node.body);
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
}

if (createCount === 0) {
  console.log(`SKIP: no create() methods under ${scenesDir}`);
  process.exit(0);
}

if (violations.length) {
  console.error(`FAIL: ${violations.length} scene lifecycle violation(s)`);
  for (const item of violations) console.error(`  - ${item}`);
  process.exit(1);
}

console.log(`PASS: ${createCount} create() method(s) are synchronous and contain no direct await`);

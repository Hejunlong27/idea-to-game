#!/usr/bin/env node
/**
 * 把 dist/<platform>/ 各自打包成 dist/<platform>.zip。
 * 压缩包内根目录直接是 index.html —— 平台提交要求。
 *
 * 用法: node scripts/zip-all.mjs [platform...]
 *       不带参数时打包 dist/ 下所有子目录。
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, statSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { platform as osPlatform } from 'node:os';

const distDir = resolve('dist');
if (!existsSync(distDir)) {
  console.error('ERROR: dist/ 不存在，请先运行 npm run build:all');
  process.exit(1);
}

const requested = process.argv.slice(2);
const targets = requested.length
  ? requested
  : readdirSync(distDir).filter((n) => statSync(join(distDir, n)).isDirectory());

if (!targets.length) {
  console.error('ERROR: dist/ 下没有可打包的目录');
  process.exit(1);
}

// 只接受安全字符集的目录名，避免路径穿越与命令参数注入
const SAFE = /^[A-Za-z0-9._-]+$/;
const unsafe = targets.filter((n) => !SAFE.test(n) || n === '.' || n === '..');
if (unsafe.length) {
  console.error(`ERROR: 目录名含不安全字符，已中止：${unsafe.join(', ')}`);
  process.exit(1);
}

const isWin = osPlatform() === 'win32';

for (const name of targets) {
  const src = join(distDir, name);
  if (!existsSync(src)) {
    console.warn(`SKIP: ${name} 不存在`);
    continue;
  }
  const zipPath = join(distDir, `${name}.zip`);
  if (existsSync(zipPath)) rmSync(zipPath);

  try {
    if (isWin) {
      execFileSync(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          `Compress-Archive -Path '${src}\\*' -DestinationPath '${zipPath}' -Force`,
        ],
        { stdio: 'inherit' },
      );
    } else {
      execFileSync('zip', ['-r', '-q', zipPath, '.'], { cwd: src, stdio: 'inherit' });
    }
    const size = statSync(zipPath).size;
    console.log(`OK: ${name}.zip  (${(size / 1048576).toFixed(2)} MB)`);
  } catch (e) {
    console.error(`FAIL: ${name} 打包失败 —— ${e.message}`);
    process.exitCode = 1;
  }
}

console.log('\n下一步: python <skill>/scripts/precheck.py --dir dist/<platform> --platform <platform>');

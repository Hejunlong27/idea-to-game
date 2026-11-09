#!/usr/bin/env node
/**
 * 实机截图（模块 10 用）—— 产出商店素材所需的真机截图。
 *
 * 用法:
 *   npm run shots                          # 默认截 dist/taptap，移动端竖屏 390x844
 *   node scripts/shots.mjs --dir dist/crazygames --out docs/07-qa/screenshots
 *   node scripts/shots.mjs --w 1920 --h 1080 --count 3
 *
 * 产物:
 *   <out>/shot-1.png … shot-N.png     按时间顺序的游玩截图
 *   <out>/shots.json                  本次截图元数据 + 控制台错误（有错误直接退出码 1）
 *
 * 说明:
 *   - 用系统已安装的 Chrome（puppeteer-core，不下载浏览器）
 *   - 截图必须来自**真实运行**，不是美术稿 —— 平台审核会对比
 *   - 若游戏暴露只读的 window.__gameState，会一并记录到 shots.json 便于排查
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, cur, i, arr) => {
    if (cur.startsWith('--')) acc.push([cur.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
    return acc;
  }, []),
);

const DIR = path.resolve(args.dir || 'dist/taptap');
const OUT = path.resolve(args.out || 'docs/07-qa/screenshots');
const COUNT = Number(args.count || 3);
const W = Number(args.w || 390);
const H = Number(args.h || 844);

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.mp3': 'audio/mpeg',
  '.ogg': 'audio/ogg',
  '.wav': 'audio/wav',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    try {
      if (fs.existsSync(p)) return p;
    } catch {
      /* ignore */
    }
  }
  return null;
}

function serve(root) {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent((req.url || '/').split('?')[0]);
    // 浏览器会无条件请求 favicon，返回 204 避免污染控制台错误统计
    if (url === '/favicon.ico') {
      res.writeHead(204).end();
      return;
    }
    const rel = url === '/' ? '/index.html' : url;
    const file = path.join(root, path.normalize(rel).replace(/^([/\\])+/, ''));
    if (!file.startsWith(root)) {
      res.writeHead(403).end('forbidden');
      return;
    }
    fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(404).end('not found');
        return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' });
      res.end(buf);
    });
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function main() {
  if (!fs.existsSync(path.join(DIR, 'index.html'))) {
    console.error(`ERROR: ${DIR}/index.html 不存在 —— 先构建：npm run build:taptap`);
    process.exit(1);
  }
  const chrome = findChrome();
  if (!chrome) {
    console.error('ERROR: 找不到 Chrome。设置环境变量 CHROME_PATH 指向可执行文件。');
    process.exit(1);
  }
  fs.mkdirSync(OUT, { recursive: true });

  const server = await serve(DIR);
  const port = server.address().port;
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--hide-scrollbars',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
      '--autoplay-policy=no-user-gesture-required',
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 2, isMobile: true, hasTouch: true });

  const errors = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 300)}`);
  });
  page.on('requestfailed', (r) => errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText || ''}`));

  const shots = [];
  const snap = async (label) => {
    const name = `shot-${shots.length + 1}.png`;
    const file = path.join(OUT, name);
    await page.screenshot({ path: file, type: 'png' });
    const state = await page.evaluate(() => {
      try {
        return typeof window.__gameState === 'object' ? window.__gameState : null;
      } catch {
        return null;
      }
    });
    shots.push({ file: name, label, state, at: new Date().toISOString() });
    console.log(`  ✓ ${name}  (${label})`);
  };

  try {
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'networkidle2', timeout: 45000 });
    await page.waitForSelector('canvas', { timeout: 20000 });
    await sleep(1800);
    await snap('menu');

    // 进游戏：盲点常见按钮位置（开始按钮多在 0.6–0.8H 之间）。
    // 有 window.__gameState 时用它判断是否已离开菜单，避免无效点击。
    const phaseOf = () =>
      page.evaluate(() => {
        const s = window.__gameState;
        return s && typeof s === 'object' ? s.phase || s.state || null : null;
      });
    let phase = await phaseOf();
    for (const [fx, fy] of [[0.5, 0.72], [0.5, 0.5], [0.5, 0.8], [0.5, 0.62]]) {
      if (phase && !['menu', 'ready', 'title', 'idle'].includes(String(phase).toLowerCase())) break;
      await page.mouse.click(W * fx, H * fy);
      await sleep(600);
      phase = await phaseOf();
    }
    await sleep(1600);
    await snap('play-1');

    // 玩法内随机点击（坐标级事件，Phaser canvas 内元素无法用 DOM 选择器点）
    const taps = [
      { x: W * 0.5, y: H * 0.45, wait: 1400, label: 'play-2' },
      { x: W * 0.32, y: H * 0.55, wait: 1400, label: 'play-3' },
      { x: W * 0.68, y: H * 0.4, wait: 1400, label: 'play-4' },
    ];
    for (const t of taps) {
      if (shots.length >= COUNT) break;
      await page.mouse.click(t.x, t.y);
      await sleep(t.wait);
      await snap(t.label);
    }
  } catch (e) {
    errors.push(`fatal: ${String(e).slice(0, 300)}`);
  }

  await browser.close();
  server.close();

  const report = {
    dir: DIR,
    viewport: { width: W, height: H, dpr: 2 },
    shots,
    errors,
    generated_at: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(OUT, 'shots.json'), JSON.stringify(report, null, 2), 'utf-8');

  console.log(`\n截图 ${shots.length} 张 → ${OUT}`);
  if (errors.length) {
    console.log(`控制台错误 ${errors.length} 条（写进 docs/07-qa/report.html）：`);
    errors.slice(0, 6).forEach((e) => console.log(`  - ${e}`));
    process.exit(1);
  }
  console.log('控制台零错误。');
}

main().catch((e) => {
  console.error('ERROR:', e);
  process.exit(1);
});

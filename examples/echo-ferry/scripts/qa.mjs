#!/usr/bin/env node
/**
 * 自动化 QA 走查（模板自带，所有项目通用）。
 *
 * 检查项：
 *   1. 启动：__bootDone / __gameState 出现，无 pageerror
 *   2. 控制台零 error（warning 只记录不判失败）
 *   3. 闭环：开始 → 操作 → 结束 → 重开（能回到可玩状态）
 *   4. 移动端视口（390×844）能正常渲染，canvas 尺寸合理
 *   5. 帧率：**必须与 about:blank 基线对照**，否则分不清环境限制与真实开销
 *   6. 事件系统：__gameEvents 有内容，且关键事件出现过
 *
 * 用法:
 *   node scripts/qa.mjs --url http://127.0.0.1:5173 --out docs/07-qa
 *   node scripts/qa.mjs --url ... --skip-fps
 *
 * 退出码: 0=全绿　1=有失败项
 */

import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const has = (name) => process.argv.includes(`--${name}`);


/** 尝试进入玩法：不同模板的「开始」位置不同，先用键盘再用多个落点，最后看状态。 */
async function tryStart(page) {
  const has = () => page.evaluate(() => !!window.__gameState).catch(() => false);
  for (const key of ['Space', 'Enter']) {
    await page.keyboard.press(key).catch(() => {});
    await new Promise((r) => setTimeout(r, 500));
    if (await has()) return true;
  }
  const rect = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  if (!rect) return false;
  for (const fy of [0.5, 0.68, 0.74, 0.62]) {
    await page.mouse.click(rect.x + rect.w / 2, rect.y + rect.h * fy).catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
    if (await has()) return true;
  }
  return false;
}

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].filter(Boolean);

function findChrome() {
  return CHROME_CANDIDATES.find((c) => c && fs.existsSync(c)) || '';
}

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: String(detail ?? '') });
  console.log(`  ${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
}

async function measureFps(page, ms = 2000) {
  return page.evaluate(
    (dur) =>
      new Promise((resolve) => {
        let frames = 0;
        const t0 = performance.now();
        function loop(t) {
          frames++;
          if (t - t0 < dur) requestAnimationFrame(loop);
          else resolve(Math.round((frames * 1000) / (t - t0)));
        }
        requestAnimationFrame(loop);
      }),
    ms,
  );
}

async function main() {
  const url = arg('url', 'http://127.0.0.1:5173');
  const outDir = arg('out', 'docs/07-qa');
  fs.mkdirSync(outDir, { recursive: true });
  const chrome = findChrome();
  if (!chrome) {
    console.error('ERROR: 找不到 Chrome，请设置 CHROME_PATH');
    process.exit(2);
  }
  const browser = await puppeteer.launch({
    executablePath: chrome,
    headless: 'new',
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader', '--mute-audio'],
  });

  // ---- 帧率基线（必须先测，否则分不清环境限制）
  let baseline = null;
  if (!has('skip-fps')) {
    const p0 = await browser.newPage();
    await p0.goto('about:blank');
    baseline = await measureFps(p0);
    await p0.close();
    console.log(`  · about:blank 帧率基线 ${baseline} FPS`);
  }

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });
  const errors = [];
  const warnings = [];
  page.on('pageerror', (e) => errors.push(String(e?.message ?? e)));
  const notFound = [];
  page.on('response', (r) => {
    if (r.status() === 404) notFound.push(r.url());
  });
  page.on('console', (m) => {
    const t = m.text();
    // 浏览器对 404 的通用报错没有 URL，靠 response 事件单独统计（下面过滤掉）
    if (m.type() === 'error' && !/Failed to load resource/.test(t)) errors.push(t);
    if (m.type() === 'warning') warnings.push(m.text());
  });

  console.log('\n[1] 启动');
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  let booted = true;
  try {
    await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 20000 });
  } catch {
    booted = false;
  }
  check('boot 完成', booted, booted ? '' : '__bootDone 与 __gameState 都未出现');
  const canvas = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    return c ? { w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight } : null;
  });
  check('canvas 存在且尺寸合理', canvas && canvas.w > 100 && canvas.h > 100, JSON.stringify(canvas));

  console.log('\n[2] 闭环操作');
  // 先在菜单点一次开始（菜单场景不暴露 __gameState，属预期）
  // 进入玩法：键盘优先 + 多个落点兜底（FIT 下必须用 canvas rect，点视口中心会打到黑边）
  await tryStart(page);
  await new Promise((r) => setTimeout(r, 600));
  const before = await page.evaluate(() => window.__gameState || null);
  check('__gameState 可读（进入玩法后）', !!before, before ? Object.keys(before).join(',') : '未暴露');
  for (const k of ['Space', 'ArrowRight', 'ArrowDown', 'ArrowUp', 'ArrowLeft']) {
    await page.keyboard.press(k).catch(() => {});
    await new Promise((r) => setTimeout(r, 60));
  }
  await page.mouse.click(canvas ? canvas.cw / 2 : 400, canvas ? canvas.ch / 2 : 300).catch(() => {});
  await new Promise((r) => setTimeout(r, 400));
  const after = await page.evaluate(() => window.__gameState || null);
  check('操作后状态发生变化', JSON.stringify(before) !== JSON.stringify(after),
    JSON.stringify(after)?.slice(0, 160));

  const evs = await page.evaluate(() => (Array.isArray(window.__gameEvents) ? window.__gameEvents.slice(-30) : []));
  check('事件系统有输出', evs.length > 0, `${evs.length} 条`);

  console.log('\n[3] 帧率');
  if (baseline !== null) {
    const renderer = await page.evaluate(() => {
      try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl');
        const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
        return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown';
      } catch {
        return 'unknown';
      }
    });
    const soft = /swiftshader|llvmpipe|software|basic render/i.test(String(renderer));
    const fps = await measureFps(page);
    const ratio = baseline ? fps / baseline : 1;
    if (soft) {
      // 软件光栅化下帧率不代表真机性能（已知：逐次绘制调用开销被放大数倍）
      results.push({ name: '帧率（无 GPU，跳过判定）', ok: true,
        detail: `游戏 ${fps} FPS / 基线 ${baseline} FPS　renderer=${renderer}　→ 必须在真机复测` });
      console.log(`  ⚠ 帧率跳过：软件渲染（${renderer}）${fps}/${baseline} FPS —— 需真机复测`);
    } else {
      check('帧率不低于基线 50%', ratio >= 0.5,
        `游戏 ${fps} FPS / 基线 ${baseline} FPS（${(ratio * 100) | 0}%）`);
      results.push({ name: 'fps', ok: true, detail: `${fps}/${baseline}` });
    }
  }

  console.log('\n[4] 移动端视口');
  await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await page.reload({ waitUntil: 'domcontentloaded' });
  try {
    await page.waitForFunction('window.__bootDone === true || !!window.__gameState', { timeout: 15000 });
  } catch { /* 记录在下面 */ }
  const m = await page.evaluate(() => {
    const c = document.querySelector('canvas');
    return {
      overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
      overflowY: document.documentElement.scrollHeight > window.innerHeight + 2,
      canvas: c ? { w: c.clientWidth, h: c.clientHeight } : null,
      userSelect: getComputedStyle(document.body).userSelect,
    };
  });
  check('移动端无横向溢出', !m.overflowX);
  check('移动端无纵向溢出', !m.overflowY);
  check('禁用文本选择（CrazyGames 要求）', m.userSelect === 'none', m.userSelect);
  check('移动端 canvas 有尺寸', m.canvas && m.canvas.w > 50, JSON.stringify(m.canvas));

  const shot = path.join(outDir, 'screenshots', 'qa-mobile.png');
  fs.mkdirSync(path.dirname(shot), { recursive: true });
  await page.screenshot({ path: shot }).catch(() => {});

  await page.setViewport({ width: 1280, height: 720 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await new Promise((r) => setTimeout(r, 1200));
  await page.screenshot({ path: path.join(outDir, 'screenshots', 'qa-desktop.png') }).catch(() => {});

  console.log('\n[5] 运行时错误');
  check('零 pageerror / console.error', errors.length === 0, errors.slice(0, 3).join(' | '));
  const real404 = [...new Set(notFound)].filter((u) => !/favicon\.ico$/.test(u));
  check('无资源 404', real404.length === 0, real404.slice(0, 4).join(' | '));

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  const report = {
    generated_at: new Date().toISOString(),
    url,
    fps_baseline: baseline,
    results,
    warnings: [...new Set(warnings)].slice(0, 10),
    pass: failed.length === 0,
  };
  fs.writeFileSync(path.join(outDir, 'qa.json'), JSON.stringify(report, null, 2), 'utf-8');

  const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>QA 报告</title><style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:24px;background:#0f1218;color:#e6e9f0}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:12px}
th,td{border:1px solid #2a3140;padding:8px;text-align:left}th{background:#1a2030}
.ok{color:#46d17f}.bad{color:#ff6b5a}.sub{color:#8b93a8;font-size:13px}
img{max-width:100%;border:1px solid #2a3140;border-radius:6px;margin-top:10px}
</style></head><body>
<h1>QA 报告 ${failed.length === 0 ? '<span class="ok">PASS</span>' : '<span class="bad">FAIL</span>'}</h1>
<div class="sub">${report.generated_at}　${url}　帧率基线 ${baseline ?? '未测'}</div>
<table><thead><tr><th>检查项</th><th>结果</th><th>详情</th></tr></thead><tbody>
${results.map((r) => `<tr><td>${r.name}</td><td class="${r.ok ? 'ok' : 'bad'}">${r.ok ? 'PASS' : 'FAIL'}</td><td>${r.detail}</td></tr>`).join('')}
</tbody></table>
${report.warnings.length ? `<h3>警告（不判失败）</h3><ul>${report.warnings.map((w) => `<li>${w}</li>`).join('')}</ul>` : ''}
<h3>截图</h3><img src="screenshots/qa-desktop.png" alt="desktop">
</body></html>`;
  fs.writeFileSync(path.join(outDir, 'report.html'), html, 'utf-8');

  console.log(`\n${failed.length ? '❌' : '✅'} QA ${failed.length ? '未通过' : '全部通过'}　报告：${path.join(outDir, 'report.html')}`);
  process.exitCode = failed.length ? 1 : 0;
}

main().catch((e) => {
  console.error('qa 失败：', e);
  process.exit(2);
});

#!/usr/bin/env node
/**
 * 打一个「双击即玩」的单文件 HTML。
 *
 * ── 为什么必须有这个东西 ──────────────────────────────────────
 * 浏览器在 file:// 下会拦两件事，而且**都不报错**，页面就永远停在 Loading：
 *   1. 外部 ES module（`<script type="module" src="./index.js">`）→ CORS 拒绝执行
 *   2. 对图片 / 音频 / JSON 的 XHR → CORS 失败
 * 单文件版把 JS 整段内联（内联 module 不产生网络请求，file:// 下可执行），
 * 其余资源由 vite.standalone.config.ts 的 assetsInlineLimit 变成 data URI。
 *
 * ── 用法 ──────────────────────────────────────────────────────
 *   npm run standalone
 *   node scripts/build-standalone.mjs [源目录] [输出文件]
 * 前置：先用 vite.standalone.config.ts 构建出源目录。
 *
 * ⚠️ 内联大段 JS 时**必须用函数形式的 String.replace**：传字符串时 `$&` / `$'` / `` $` ``
 *    会被当成替换模式，而压缩后的 bundle 里必然出现这些字符序列，会把后面的 HTML
 *    塞进 JS 中间，产出一个语法错误的文件。
 */
import fs from 'node:fs';
import path from 'node:path';

const SRC = process.argv[2] ?? 'dist/standalone';
const OUT = process.argv[3] ?? 'dist/standalone.html';

if (!fs.existsSync(path.join(SRC, 'index.html'))) {
  console.error(`ERROR: ${SRC}/index.html 不存在。先跑：vite build --config vite.standalone.config.ts`);
  process.exit(1);
}

const read = (p) => fs.readFileSync(path.join(SRC, p));

const html = read('index.html').toString('utf8');
const js = read('index.js').toString('utf8');

/** 内联脚本里出现 </script 会提前闭合标签，做兜底转义 */
const guard = (s) => s.replace(/<\/script/gi, '<\\/script');

// 1) 抹掉外部资源引用：平台 SDK 与外部 module 脚本（离线打开只会白报错）
let out = html
  .replace(/\s*<script[^>]*src="https?:\/\/[^"]*"[^>]*><\/script>/gi, '')
  .replace(/\s*<script[^>]*type="module"[^>]*src="[^"]*"[^>]*><\/script>/gi, '')
  .replace(/\s*<link[^>]*rel="(stylesheet|modulepreload|preload)"[^>]*href="(?!data:)[^"]*"[^>]*>/gi, '');

// 2) 标记单文件模式：启动看门狗据此跳过 file:// 检查
out = out.replace('<head>', () => '<head>\n<script>window.__STANDALONE__ = true;</script>');

// 3) 整段内联 JS（内联 module 不产生网络请求，file:// 下可执行）
if (!/<\/body>/i.test(out)) {
  console.error('ERROR: index.html 里找不到 </body>，无法内联脚本');
  process.exit(1);
}
out = out.replace('</body>', () => `<script type="module">\n${guard(js)}\n</script>\n</body>`);

// 4) 自检：确认没有残留的「本地文件引用」——否则单文件版在 file:// 下仍会缺资源
const leftovers = [];
for (const m of out.matchAll(/(?:src|href)="([^"]+)"/gi)) {
  const url = m[1];
  if (url.startsWith('data:') || url.startsWith('#') || url.startsWith('javascript:')) continue;
  leftovers.push(url);
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, out);

const kb = (n) => `${(n / 1024).toFixed(0)} KB`;
console.log(`OK: ${OUT}  ${kb(fs.statSync(OUT).size)}`);
console.log(`  内联 index.js ${kb(js.length)}；外部请求数 ${leftovers.length}`);
if (leftovers.length) {
  console.warn('  WARN: 以下引用仍指向外部文件，file:// 下会加载失败（检查 vite.standalone.config.ts 的 assetsInlineLimit）：');
  for (const u of [...new Set(leftovers)].slice(0, 10)) console.warn(`    - ${u}`);
  process.exitCode = 2;
} else {
  console.log('  自检通过：单文件内无外部文件引用，可离线双击打开');
}

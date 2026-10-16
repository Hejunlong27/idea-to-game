#!/usr/bin/env node
/**
 * 极简静态服务器 —— 用于本地预览与自动化测试。
 *
 * HTML5 游戏产物不能双击打开（Vite 产出外部 ES module，file:// 下被 CORS 拒绝），
 * 必须走 HTTP。
 *
 * 用法:
 *   node scripts/serve.mjs                 # 默认服务仓库根目录（dev，走源码）
 *   node scripts/serve.mjs dist/crazygames # 服务构建产物
 *   PORT=5199 node scripts/serve.mjs dist/crazygames
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';

const root = resolve(process.argv[2] ?? '.');
const port = Number(process.env.PORT ?? 5199);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.ico': 'image/x-icon',
  '.map': 'application/json; charset=utf-8',
};

/** 把 URL 路径安全地映射到磁盘路径，禁止越出根目录 */
function safeJoin(base, urlPath) {
  const decoded = decodeURIComponent(urlPath.split('?')[0]);
  const target = normalize(join(base, decoded));
  if (!target.startsWith(base)) return null;
  return target;
}

const server = createServer(async (req, res) => {
  try {
    let filePath = safeJoin(root, req.url ?? '/');
    if (!filePath) {
      res.writeHead(403).end('Forbidden');
      return;
    }
    let info = await stat(filePath).catch(() => null);
    if (info?.isDirectory()) {
      filePath = join(filePath, 'index.html');
      info = await stat(filePath).catch(() => null);
    }
    if (!info?.isFile()) {
      res.writeHead(404, { 'content-type': 'text/plain' }).end('Not found');
      return;
    }
    const body = await readFile(filePath);
    res.writeHead(200, {
      'content-type': MIME[extname(filePath).toLowerCase()] ?? 'application/octet-stream',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    });
    res.end(body);
  } catch (e) {
    res.writeHead(500, { 'content-type': 'text/plain' }).end(String(e));
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(`serve: http://127.0.0.1:${port}/  (root=${root})`);
});

export { server };

import { defineConfig, type Plugin } from 'vite';

/**
 * 各平台的 SDK script 标签。
 *
 * ⚠️ 这些 URL 必须在提交前对照平台官方文档核对一次 —— 平台可能更换 CDN 地址。
 *    CrazyGames : https://docs.crazygames.com/
 *    Poki       : https://sdk.poki.com/
 *    Playgama   : https://wiki.playgama.com/playgama/bridge-sdk/getting-started
 *    GD         : https://gamedistribution.com/developers/
 *    TapTap     : https://developer.taptap.cn/minigameapidoc/quick-start/document-guide/
 *
 * 留空表示该平台不使用 script 标签注入：
 *   - playgama：需自行加入 Bridge SDK script，或改用 npm 包静态 import
 *   - taptap  ：网页游戏形态无需 SDK；Tap 小游戏形态由 TapTap 容器注入全局 `tap`，
 *               不需要也不允许自行引入 SDK script
 */
const SDK_SCRIPTS: Record<string, string> = {
  crazygames: 'https://sdk.crazygames.com/crazygames-sdk-v3.js',
  poki: 'https://game-cdn.poki.com/scripts/v2/poki-sdk.js',
  gamedistribution: 'https://html5.api.gamedistribution.com/main.min.js',
  playgama: '',
  taptap: '',
};

function sdkInjectPlugin(mode: string): Plugin {
  const src = SDK_SCRIPTS[mode];
  return {
    name: 'i2g-sdk-inject',
    transformIndexHtml(html: string) {
      if (!src) return html;
      // 经典 script 在 head 中同步执行，会早于 type="module" 的入口，保证 SDK 已就绪
      return html.replace('</head>', `  <script src="${src}"></script>\n</head>`);
    },
  };
}

export default defineConfig(({ mode }) => ({
  // base: './' 保证构建产物全部使用相对路径 —— CrazyGames 会因绝对路径直接拒审
  base: './',
  plugins: [sdkInjectPlugin(mode)],
  build: {
    target: 'es2019',
    assetsInlineLimit: 0,
    cssCodeSplit: false,
    chunkSizeWarningLimit: 8192,
    rollupOptions: {
      output: {
        manualChunks: undefined,
        entryFileNames: 'index.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    host: true,
    port: 5173,
  },
}));

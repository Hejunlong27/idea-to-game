import { defineConfig } from 'vite';

/**
 * 「双击即玩」单文件版的 Vite 配置。
 *
 * 与主配置的差别只有两点，但都必不可少：
 *   1. `assetsInlineLimit` 拉到极大 —— 让 Vite 把 mp3 等资源全部内联成 data URI，
 *      产物里不再有需要额外请求的文件（file:// 下这些请求会被拦）。
 *   2. `inlineDynamicImports` —— 强制只产出一个 JS，便于后续整段内联进 HTML。
 *
 * mode 保持默认（production）→ createPlatform() 落到 mock 适配器，
 * 且本配置不挂 sdkInjectPlugin，所以不会注入任何平台 SDK（离线打开不报错）。
 *
 * 由 scripts/build-standalone.mjs 接着把 index.js 内联进 index.html。
 */
export default defineConfig({
  base: './',
  build: {
    target: 'es2019',
    outDir: 'dist/standalone',
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    chunkSizeWarningLimit: 8192,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'index.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
});

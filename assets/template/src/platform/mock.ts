/**
 * mock 适配器 —— 本地开发默认使用。
 * 广告直接返回成功，存档走 localStorage。生产构建不会注入本实现。
 */
import type { PlatformBridge, SaveData } from '../types';

const KEY = 'i2g:save';

export function createMockPlatform(): PlatformBridge {
  return {
    name: 'i2g-platform:mock',

    async init() {
      // eslint-disable-next-line no-console
      console.info('[platform] mock adapter (dev only)');
    },

    gameplayStart() {},
    gameplayStop() {},

    async showMidroll() {
      return true;
    },

    async showRewarded() {
      return true;
    },

    async save(data: SaveData) {
      try {
        localStorage.setItem(KEY, JSON.stringify(data));
      } catch {
        /* 隐私模式下 localStorage 可能不可用，静默降级 */
      }
    },

    async load() {
      try {
        const raw = localStorage.getItem(KEY);
        return raw ? (JSON.parse(raw) as SaveData) : null;
      } catch {
        return null;
      }
    },
  };
}

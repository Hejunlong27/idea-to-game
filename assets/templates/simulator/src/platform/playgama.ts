/**
 * Playgama Bridge 适配器。
 *
 * 文档: https://wiki.playgama.com/playgama/bridge-sdk/getting-started
 * 一套 SDK 覆盖 25+ 平台（Y8 / Lagged / Yandex Games / Playhop / GD / MS Store 等）。
 *
 * 接入方式（二选一）：
 *   A. 在 index.html 中加入 Bridge SDK 的 script 标签，SDK 会挂到 window.bridge
 *   B. npm i @playgama/bridge 后改为静态 import
 *
 * 本适配器只读取 window.bridge，不做任何网络请求；SDK 缺失时自动降级为本地行为，
 * 不会导致构建或运行失败。
 */
import type { PlatformBridge, SaveData } from '../types';

const KEY = 'i2g:save';

type BridgeLike = {
  initialize?(): Promise<void>;
  platform?: { sendMessage(msg: string, payload?: unknown): void };
  advertisement?: {
    showInterstitial(): Promise<void>;
    showRewarded(): Promise<{ success: boolean } | boolean>;
  };
  storage?: {
    set(key: string, value: unknown): Promise<void>;
    get(key: string): Promise<unknown>;
  };
};

function getBridge(): BridgeLike | null {
  const b = (globalThis as unknown as { bridge?: BridgeLike }).bridge;
  return b && typeof b === 'object' ? b : null;
}

export function createPlaygamaPlatform(): PlatformBridge {
  return {
    name: 'i2g-platform:playgama',

    async init() {
      const bridge = getBridge();
      if (!bridge) {
        console.warn('[platform] 未检测到 Playgama Bridge SDK，已降级为本地行为');
        return;
      }
      try {
        await bridge.initialize?.();
        bridge.platform?.sendMessage('game_ready');
      } catch (e) {
        console.warn('[platform] Playgama Bridge 初始化失败，已降级', e);
      }
    },

    gameplayStart() {
      try {
        getBridge()?.platform?.sendMessage('gameplay_started');
      } catch {
        /* 静默降级 */
      }
    },

    gameplayStop() {
      try {
        getBridge()?.platform?.sendMessage('gameplay_stopped');
      } catch {
        /* 静默降级 */
      }
    },

    async showMidroll() {
      try {
        const ad = getBridge()?.advertisement;
        if (!ad) return false;
        await ad.showInterstitial();
        return true;
      } catch {
        return false;
      }
    },

    async showRewarded() {
      try {
        const ad = getBridge()?.advertisement;
        if (!ad) return false;
        const r = await ad.showRewarded();
        return typeof r === 'boolean' ? r : Boolean(r?.success);
      } catch {
        return false;
      }
    },

    async save(data: SaveData) {
      const bridge = getBridge();
      if (bridge?.storage) {
        try {
          await bridge.storage.set(KEY, JSON.stringify(data));
          return;
        } catch {
          /* 落到 localStorage */
        }
      }
      try {
        localStorage.setItem(KEY, JSON.stringify(data));
      } catch {
        /* 静默降级 */
      }
    },

    async load() {
      const bridge = getBridge();
      if (bridge?.storage) {
        try {
          const raw = await bridge.storage.get(KEY);
          if (typeof raw === 'string' && raw) return JSON.parse(raw) as SaveData;
          if (raw && typeof raw === 'object') return raw as SaveData;
        } catch {
          /* 落到 localStorage */
        }
      }
      try {
        const raw = localStorage.getItem(KEY);
        return raw ? (JSON.parse(raw) as SaveData) : null;
      } catch {
        return null;
      }
    },
  };
}

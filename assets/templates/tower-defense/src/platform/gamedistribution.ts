/**
 * GameDistribution SDK 适配器。
 *
 * 文档: https://gamedistribution.com/developers/
 * 注意: GD 强制要求集成 SDK，审核最长 3 周，且不接受目录内同款游戏。
 */
import type { PlatformBridge, SaveData } from '../types';

declare global {
  interface Window {
    gdsdk?: {
      showAd(type?: string): Promise<void>;
      preloadAd(type?: string): Promise<void>;
    };
    GD_OPTIONS?: Record<string, unknown>;
  }
}

const KEY = 'i2g:save';

export function createGameDistributionPlatform(): PlatformBridge {
  return {
    name: 'i2g-platform:gamedistribution',

    async init() {
      if (!window.gdsdk) {
        console.warn('[platform] GameDistribution SDK 未加载（广告拦截器？），已降级');
        return;
      }
      try {
        await window.gdsdk.preloadAd('interstitial');
        await window.gdsdk.preloadAd('rewarded');
      } catch {
        /* 静默降级 */
      }
    },

    gameplayStart() {},
    gameplayStop() {},

    async showMidroll() {
      try {
        await window.gdsdk?.showAd('interstitial');
        return true;
      } catch {
        return false;
      }
    },

    async showRewarded() {
      try {
        await window.gdsdk?.showAd('rewarded');
        return true;
      } catch {
        return false;
      }
    },

    async save(data: SaveData) {
      try {
        localStorage.setItem(KEY, JSON.stringify(data));
      } catch {
        /* 静默降级 */
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

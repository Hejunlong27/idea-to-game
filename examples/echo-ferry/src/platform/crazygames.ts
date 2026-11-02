/**
 * CrazyGames SDK v3 适配器。
 *
 * 文档: https://docs.crazygames.com/sdk/intro/
 * 注意: Basic Launch 阶段广告被禁用，但 SDK 事件仍应正常上报。
 */
import type { PlatformBridge, SaveData } from '../types';
import { emptySave } from '../types';

declare global {
  interface Window {
    CrazyGames?: {
      SDK: {
        init(): Promise<void>;
        game: {
          loadingStart(): void;
          loadingStop(): void;
          gameplayStart(): void;
          gameplayStop(): void;
          happytime(): void;
        };
        ad: {
          requestAd(type: 'midgame' | 'rewarded'): Promise<void>;
        };
        data: {
          getItem(key: string): Promise<string | null>;
          setItem(key: string, value: string): Promise<void>;
        };
      };
    };
  }
}

const SAVE_KEY = 'save';

function sdk() {
  const s = window.CrazyGames?.SDK;
  if (!s) throw new Error('CrazyGames SDK 未加载');
  return s;
}

export function createCrazyGamesPlatform(): PlatformBridge {
  return {
    name: 'i2g-platform:crazygames',

    async init() {
      if (!window.CrazyGames?.SDK) {
        console.warn('[platform] CrazyGames SDK 不可用（广告拦截器？），已降级');
        return;
      }
      try {
        await sdk().init();
        sdk().game.loadingStart();
      } catch (e) {
        console.warn('[platform] CrazyGames init 失败，已降级', e);
      }
    },

    gameplayStart() {
      try {
        sdk().game.loadingStop();
        sdk().game.gameplayStart();
      } catch {
        /* 静默降级 */
      }
    },

    gameplayStop() {
      try {
        sdk().game.gameplayStop();
      } catch {
        /* 静默降级 */
      }
    },

    async showMidroll() {
      try {
        await sdk().ad.requestAd('midgame');
        return true;
      } catch {
        return false;
      }
    },

    async showRewarded() {
      try {
        await sdk().ad.requestAd('rewarded');
        return true;
      } catch {
        return false;
      }
    },

    async save(data: SaveData) {
      try {
        await sdk().data.setItem(SAVE_KEY, JSON.stringify(data));
      } catch {
        /* 静默降级 */
      }
    },

    async load() {
      try {
        const raw = await sdk().data.getItem(SAVE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw) as SaveData;
        return { ...emptySave(), ...parsed };
      } catch {
        return null;
      }
    },
  };
}

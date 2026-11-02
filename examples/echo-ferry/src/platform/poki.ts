/**
 * Poki SDK v2 适配器。
 *
 * 文档: https://sdk.poki.com/
 * 注意: 官方 Phaser 插件 @poki/phaser-3 仅支持 Phaser 3，本适配器为手写实现，
 *       不依赖该插件，因此对 Phaser 版本无约束。
 */
import type { PlatformBridge, SaveData } from '../types';

declare global {
  interface Window {
    PokiSDK?: {
      init(onReady: () => void, onError?: () => void): void;
      gameLoadingFinished(): void;
      gameplayStart(): void;
      gameplayStop(): void;
      commercialBreak(): Promise<void>;
      rewardedBreak(): Promise<boolean>;
      setDebug(v: boolean): void;
    };
  }
}

const KEY = 'i2g:save';

export function createPokiPlatform(): PlatformBridge {
  let ready = false;

  return {
    name: 'i2g-platform:poki',

    async init() {
      if (!window.PokiSDK) {
        console.warn('[platform] Poki SDK 不可用（广告拦截器？），已降级');
        return;
      }
      try {
        await new Promise<void>((resolve) => {
          window.PokiSDK!.init(
            () => {
              ready = true;
              resolve();
            },
            () => {
              console.warn('[platform] Poki init 失败，已降级');
              resolve();
            },
          );
          // 兜底：SDK 不回调时不让游戏卡死
          setTimeout(resolve, 3000);
        });
        if (ready) window.PokiSDK.gameLoadingFinished();
      } catch {
        /* 静默降级 */
      }
    },

    gameplayStart() {
      try {
        window.PokiSDK?.gameplayStart();
      } catch {
        /* 静默降级 */
      }
    },

    gameplayStop() {
      try {
        window.PokiSDK?.gameplayStop();
      } catch {
        /* 静默降级 */
      }
    },

    async showMidroll() {
      try {
        await window.PokiSDK?.commercialBreak();
        return true;
      } catch {
        return false;
      }
    },

    async showRewarded() {
      try {
        return (await window.PokiSDK?.rewardedBreak()) ?? false;
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

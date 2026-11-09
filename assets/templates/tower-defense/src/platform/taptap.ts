/**
 * TapTap 适配器 —— 覆盖 TapTap 的两种 Web 形态：
 *
 *   A. 网页游戏（H5 / WEB）—— 即点即玩，TapTap 只是链接跳转/内嵌宿主，
 *      运行环境不注入 SDK，本适配器自动降级为本地行为。
 *   B. Tap 小游戏 —— 运行在 TapTap 小游戏容器内，宿主注入全局对象 `tap`，
 *      可调用登录、广告、云存档、排行榜等能力。
 *
 * 文档: https://developer.taptap.cn/minigameapidoc/quick-start/document-guide/
 *
 * ⚠️ 上线前必须完成「小游戏前置备案」（中国大陆合规要求），且广告位需先在
 *    Dirichlet 广告平台（https://ssp.dirichlet.cn/）创建并拿到 adUnitId。
 *
 * 本适配器做全量能力探测：任一 API 不存在时静默降级，不影响游戏运行。
 * 广告 API 的确切签名以官方文档为准 —— 接入前需核对一次。
 */
import type { PlatformBridge, SaveData } from '../types';

const KEY = 'i2g:save';

/** 广告位 ID —— 上线前替换为 Dirichlet 后台创建的真实 adUnitId */
export const AD_UNITS = {
  /** 插屏广告位（关卡切换、暂停等自然间隙） */
  interstitial: '',
  /** 激励视频广告位（复活、双倍奖励等） */
  rewarded: '',
  /** Banner 广告位（主界面、暂停界面） */
  banner: '',
};

type TapLike = {
  onShow?(cb: () => void): void;
  onHide?(cb: () => void): void;
  createInterstitialAd?(opts: { adUnitId: string }): TapAd;
  createRewardedVideoAd?(opts: { adUnitId: string }): TapAd;
  createBannerAd?(opts: { adUnitId: string }): TapAd;
  setStorage?(opts: { key: string; data: unknown }): void;
  getStorage?(opts: { key: string; success?: (r: { data: unknown }) => void; fail?: () => void }): void;
};

type TapAd = {
  load?(): Promise<void> | void;
  show?(): Promise<void> | void;
  destroy?(): void;
  onLoad?(cb: () => void): void;
  onError?(cb: (e: unknown) => void): void;
  onClose?(cb: (r?: { isEnded?: boolean }) => void): void;
};

function getTap(): TapLike | null {
  const t = (globalThis as unknown as { tap?: TapLike }).tap;
  return t && typeof t === 'object' ? t : null;
}

/** 播放一次广告。返回是否完整播放（激励视频用于判定是否发奖）。 */
async function playAd(
  factory: ((opts: { adUnitId: string }) => TapAd) | undefined,
  adUnitId: string,
  opts: { expectReward: boolean },
): Promise<boolean> {
  if (!factory || !adUnitId) return false;
  try {
    const ad = factory({ adUnitId });
    await Promise.resolve(ad.load?.());

    if (opts.expectReward) {
      return await new Promise<boolean>((resolve) => {
        let settled = false;
        const done = (v: boolean) => {
          if (settled) return;
          settled = true;
          try {
            ad.destroy?.();
          } catch {
            /* 忽略 */
          }
          resolve(v);
        };
        ad.onError?.(() => done(false));
        ad.onClose?.((r) => done(r?.isEnded !== false));
        // 兜底：60s 内无回调则视为失败，避免流程卡死
        setTimeout(() => done(false), 60_000);
        Promise.resolve(ad.show?.()).catch(() => done(false));
      });
    }

    await Promise.resolve(ad.show?.());
    try {
      ad.destroy?.();
    } catch {
      /* 忽略 */
    }
    return true;
  } catch {
    return false;
  }
}

export function createTapTapPlatform(): PlatformBridge {
  return {
    name: 'i2g-platform:taptap',

    async init() {
      const tap = getTap();
      if (!tap) {
        // 网页游戏（H5/WEB）形态：宿主不注入 SDK，属预期内，不算失败
        console.info('[platform] TapTap 网页游戏形态（无 tap 全局对象），使用本地行为');
        return;
      }
      if (!AD_UNITS.interstitial && !AD_UNITS.rewarded) {
        console.warn('[platform] TapTap AD_UNITS 未配置，广告将不可用（需先在 Dirichlet 创建广告位）');
      }
      tap.onShow?.(() => {
        /* 由 main.ts 的 visibilitychange 统一处理音频恢复 */
      });
    },

    gameplayStart() {
      // TapTap 未提供统一的生命周期上报接口，保留占位以便后续扩展
    },

    gameplayStop() {
      /* 同上 */
    },

    async showMidroll() {
      const tap = getTap();
      return playAd(tap?.createInterstitialAd?.bind(tap), AD_UNITS.interstitial, { expectReward: false });
    },

    async showRewarded() {
      const tap = getTap();
      return playAd(tap?.createRewardedVideoAd?.bind(tap), AD_UNITS.rewarded, { expectReward: true });
    },

    async save(data: SaveData) {
      const tap = getTap();
      if (tap?.setStorage) {
        try {
          tap.setStorage({ key: KEY, data });
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
      const tap = getTap();
      if (tap?.getStorage) {
        const raw = await new Promise<string | null>((resolve) => {
          let done = false;
          const finish = (v: string | null) => {
            if (!done) {
              done = true;
              resolve(v);
            }
          };
          try {
            tap.getStorage!({
              key: KEY,
              success: (r) => finish(typeof r?.data === 'string' ? r.data : JSON.stringify(r?.data ?? null)),
              fail: () => finish(null),
            });
          } catch {
            finish(null);
          }
          setTimeout(() => finish(null), 2000);
        });
        if (raw) {
          try {
            return JSON.parse(raw) as SaveData;
          } catch {
            /* 落到 localStorage */
          }
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

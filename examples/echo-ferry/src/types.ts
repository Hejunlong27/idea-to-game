/**
 * 共享类型。
 *
 * 放在 src/ 根目录而不是 src/platform/ 下，是为了让 src/game/ 能引用平台接口类型，
 * 同时保持「src/game/ 不依赖 src/platform/」这条契约（便于换平台时不改玩法代码）。
 */

/** 平台桥接接口。所有平台差异都必须收敛到这里。 */
export interface PlatformBridge {
  /** 平台标识，用于日志与调试 */
  readonly name: string;

  /** 初始化。必须在任何其他调用之前 await 完成。 */
  init(): Promise<void>;

  /**
   * 进入可玩状态时调用。
   * CrazyGames 用它测量首包体积（加载开始 → 首次 gameplayStart），
   * Poki 用它标记加载完成。必须在「真正可玩」时触发，不含菜单与额外加载。
   */
  gameplayStart(): void;

  /** 离开可玩状态（暂停、结束、切后台）时调用。 */
  gameplayStop(): void;

  /** 插屏广告（用于暂停点）。返回是否成功播放。 */
  showMidroll(): Promise<boolean>;

  /** 激励视频。返回是否完整观看（中途退出返回 false）。 */
  showRewarded(): Promise<boolean>;

  /** 存档。 */
  save(data: SaveData): Promise<void>;

  /** 读档。无存档时返回 null。 */
  load(): Promise<SaveData | null>;
}

/** 存档结构。必须带 version，便于后续迁移。 */
export interface SaveData {
  version: number;
  best: number;
  [key: string]: unknown;
}

export const SAVE_VERSION = 1;

export function emptySave(): SaveData {
  return { version: SAVE_VERSION, best: 0 };
}

/**
 * 全部可调数值集中在这里。P3 打磨阶段调参只改本文件。
 *
 * 本文件是模板自带的占位玩法「点靶子」的参数。
 * 执行 modules/04-core-loop.md 时，按 GDD 替换为真实玩法的参数。
 */

export const LAYOUT = {
  width: 720,
  height: 1280,
  /** 'portrait' | 'landscape'，需与 docs/01-brief/scope.json 一致 */
  orientation: 'portrait' as 'portrait' | 'landscape',
};

/**
 * 帧动画配置：key → 帧数。
 * 帧名约定 `<key>_0 … <key>_N-1`，由 `gen_assets.py` 的网格帧模式产出，
 * 打成图集后由 `anim.ts` 的 registerFrameAnims 注册为 `<key>_loop`。
 *
 * 例：slime_idle: 4  →  slime_idle_0 / _1 / _2 / _3
 */
export const ANIM: Record<string, number> = {
  // slime_idle: 4,
};

/** 默认帧率（超休闲一般 8–12 帧/秒就够） */
export const ANIM_FPS = 10;

export const COLORS = {
  bg: 0x10121a,
  panel: 0x1c2030,
  text: '#e8ebf5',
  textDim: '#8b93a8',
  accent: 0x4ea1ff,
  good: 0x46d17f,
  bad: 0xff5c5c,
};

/** 占位玩法参数 */
export const GAME = {
  /** 单局时长（毫秒） */
  roundMs: 15_000,
  /** 靶子半径 */
  targetRadius: 56,
  /** 靶子存活时间（毫秒），越短越难 */
  targetLifetimeMs: 1_100,
  /** 同时存在的靶子上限 */
  maxTargets: 3,
  /** 生成间隔（毫秒） */
  spawnIntervalMs: 620,
  /** 每次命中得分 */
  scorePerHit: 1,
  /** 命中时的缩放回弹 */
  hitScalePunch: 1.18,
  /** 未命中扣分 */
  missPenalty: 0,
  /** 连击加成：每连击增加的分值 */
  comboBonus: 1,
};

/** 难度曲线：随时间推进的参数插值（P3 使用） */
export const DIFFICULTY = {
  /** 每经过该毫秒数，难度提升一档 */
  stepMs: 4_000,
  /** 每档降低的靶子存活时间比例 */
  lifetimeDecay: 0.12,
  /** 每档缩短的生成间隔比例 */
  spawnDecay: 0.1,
  /** 存活时间下限（毫秒） */
  minLifetimeMs: 420,
  /** 生成间隔下限（毫秒） */
  minSpawnMs: 260,
};

/** juice 反馈参数（P3 使用） */
export const JUICE = {
  shakeOnHit: { duration: 70, intensity: 0.004 },
  shakeOnMiss: { duration: 90, intensity: 0.006 },
  tweenDurationMs: 160,
};

/** 资源开关：P2 生图与切图完成后置为 true，并填入图集键名 */
export const ASSETS = {
  useAtlas: false,
  atlasKey: 'game',
  atlasPng: 'assets/atlas/atlas.png',
  atlasJson: 'assets/atlas/atlas.json',
};

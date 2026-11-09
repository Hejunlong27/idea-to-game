/**
 * 塔防品类模板 —— 全部可调数值与关卡数据集中在这里。
 *
 * 三张表构成整个玩法：
 *   TOWER_TYPES  塔的种类与成长
 *   ENEMY_TYPES  敌人的种类与属性
 *   LEVELS       地图（路径）+ 波次编排
 *
 * 换一张地图只改 LEVELS，逻辑层（td.ts / PlayScene）不动。
 */

export const LAYOUT = {
  width: 720,
  height: 1280,
  orientation: 'portrait' as 'portrait' | 'landscape',
};

/** 网格：7 列 × 9 行，格子 84px，水平居中（7×84=588，两侧各留 66） */
export const GRID = {
  cols: 7,
  rows: 9,
  cell: 84,
  originX: 66,
  originY: 240,
};

export const COLORS = {
  bg: 0x0d1017,
  panel: 0x1a1f2b,
  panelEdge: 0x2f3a4d,
  text: '#e8ebf5',
  textDim: '#8b93a8',
  accent: 0x4ea1ff,
  good: 0x46d17f,
  bad: 0xff5c5c,
  gold: 0xf0c674,
  ground: 0x1a2130,
  groundAlt: 0x161c29,
  road: 0x3a3226,
  roadEdge: 0x4d4334,
};

// ---------------------------------------------------------------- 塔

export interface TowerType {
  id: string;
  name: string;
  desc: string;
  /** 建造费 */
  cost: number;
  damage: number;
  /** 射程（格） */
  range: number;
  cooldownMs: number;
  /** 主色，同时用于塔身与弹道 */
  color: number;
  /** 溅射半径（格）。有值即范围伤害 */
  splash?: number;
  /** 减速比例（0.5 = 移速减半）与持续时间 */
  slowFactor?: number;
  slowMs?: number;
}

/**
 * 三种塔的分工（设计意图，不要随便改数值破坏它）：
 *   箭塔   —— 便宜、单体、稳。前中期主力，逼玩家先铺量。
 *   炮塔   —— 贵、溅射、慢。专治成群小怪，怕单只高血。
 *   冰塔   —— 不靠伤害，靠减速拖时间。让「输出不够」变成可解的题。
 */
export const TOWER_TYPES: TowerType[] = [
  {
    id: 'arrow',
    name: '箭塔',
    desc: '单体高伤，便宜好铺',
    cost: 50,
    damage: 8,
    range: 1.7,
    cooldownMs: 600,
    color: 0x6fb6ff,
  },
  {
    id: 'cannon',
    name: '炮塔',
    desc: '溅射伤害，专打成群',
    cost: 80,
    damage: 14,
    range: 1.5,
    cooldownMs: 1100,
    color: 0xf08a5d,
    splash: 0.9,
  },
  {
    id: 'frost',
    name: '冰塔',
    desc: '伤害低，但能减速',
    cost: 70,
    damage: 4,
    range: 1.9,
    cooldownMs: 700,
    color: 0x8fd6e8,
    slowFactor: 0.5,
    slowMs: 1500,
  },
];

/** 升级规则：每级乘算，费用递增 */
export const UPGRADE = {
  maxLevel: 3,
  /** 每级伤害乘数 */
  damageMul: 1.45,
  /** 每级射程加成（格） */
  rangeAdd: 0.12,
  /** 升级费 = 建造费 × 该系数 × 当前等级 */
  costMul: 0.9,
};

/** 出售返还比例 */
export const SELL_REFUND = 0.6;

// ---------------------------------------------------------------- 敌人

export interface EnemyType {
  id: string;
  name: string;
  hp: number;
  /** 格/秒 */
  speed: number;
  /** 击杀奖励 */
  reward: number;
  /** 每次受伤减免的点数（最低仍造成 1 点） */
  armor: number;
  color: number;
  /** 视觉半径 */
  radius: number;
}

export const ENEMY_TYPES: Record<string, EnemyType> = {
  grunt: { id: 'grunt', name: '小妖', hp: 20, speed: 1.2, reward: 15, armor: 0, color: 0xff5c5c, radius: 20 },
  armored: { id: 'armored', name: '甲兽', hp: 55, speed: 0.75, reward: 30, armor: 4, color: 0x9b6bd6, radius: 24 },
  swift: { id: 'swift', name: '疾影', hp: 12, speed: 2.2, reward: 12, armor: 0, color: 0xffd166, radius: 16 },
};

// ---------------------------------------------------------------- 关卡

/** 一波里各类型敌人的数量，如 { grunt: 3, swift: 2 } */
export type WaveDef = Record<string, number>;

export interface LevelDef {
  id: number;
  name: string;
  /** 敌人行进路线（格子坐标，相邻点必须共线） */
  path: Array<[number, number]>;
  waves: WaveDef[];
  startGold: number;
  startLives: number;
  /** 首波准备时间 */
  firstWaveDelayMs: number;
}

/**
 * 两张地图。第一张考「铺量」，第二张考「搭配」——
 * 短路径 + 高护甲甲兽，光靠箭塔过不去，必须上炮塔与冰塔。
 */
export const LEVELS: LevelDef[] = [
  {
    id: 1,
    name: '第一关 · 长路',
    path: [
      [0, 0],
      [5, 0],
      [5, 2],
      [1, 2],
      [1, 4],
      [5, 4],
      [5, 6],
      [1, 6],
      [1, 8],
      [6, 8],
    ],
    waves: [{ grunt: 3 }, { grunt: 4, swift: 2 }, { grunt: 3, armored: 2 }],
    startGold: 100,
    startLives: 10,
    firstWaveDelayMs: 1200,
  },
  {
    id: 2,
    name: '第二关 · 短径',
    path: [
      [0, 8],
      [4, 8],
      [4, 5],
      [1, 5],
      [1, 2],
      [6, 2],
      [6, 0],
    ],
    waves: [{ swift: 4 }, { armored: 3, grunt: 3 }, { swift: 4, armored: 2 }, { armored: 4, grunt: 4 }],
    startGold: 130,
    startLives: 8,
    firstWaveDelayMs: 1500,
  },
];

/**
 * 星级规则。星级不是「分数高就三星」，而是**看漏怪**——
 * 它衡量的是「你守住了没有」，这才是塔防的核心能力。
 */
export const STARS = {
  /** 3 星：零漏怪 */
  threeStarMaxLeaks: 0,
  /** 2 星：漏怪不超过这个数 */
  twoStarMaxLeaks: 3,
  /** 1 星：只要通关 */
};

/** 存档里每关的记录结构 */
export interface LevelRecord {
  stars: number;
  best: number;
}

export const TD = {
  /** 同波内敌人出生间隔 */
  spawnGapMs: 800,
  /** 波与波之间间隔 */
  waveGapMs: 2200,
};

export const BASE_MARK = 'base';

/** 帧动画（默认无，接 AI 图后填） */
export const ANIM: Record<string, number> = {};
export const ANIM_FPS = 10;

export const JUICE = {
  shakeOnHit: { duration: 70, intensity: 0.004 },
  shakeOnMiss: { duration: 90, intensity: 0.006 },
  tweenDurationMs: 160,
};

export const ASSETS = {
  useAtlas: false,
  atlasKey: 'game',
  atlasPng: 'assets/atlas/atlas.png',
  atlasJson: 'assets/atlas/atlas.json',
};

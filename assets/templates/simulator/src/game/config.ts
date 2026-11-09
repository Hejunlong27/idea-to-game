/**
 * 模拟器品类模板 —— 全部可调数值集中在这里。
 *
 * 内容（行动 / 事件 / 境界）在 `src/game/content/*.json`；
 * 本文件只放**运行参数**（初始属性、事件频率、界面尺寸）。
 *
 * 平衡思路（见 references/genre-playbook.md 的模拟器拆解）：
 *   - 单回合修为产出 ≈ 8，筑基门槛 50 → 约 7 回合可突破，玩家能很快看到第一次成长
 *   - 寿元 80、起始 16 岁 → 64 个回合，够撑到金丹但很难到化神（需要做选择）
 *   - 心境掉到 0 不直接结束，但会频繁触发心魔事件，用「机会成本」惩罚而不是硬失败
 */

export const LAYOUT = {
  width: 720,
  height: 1280,
  orientation: 'portrait' as 'portrait' | 'landscape',
};

export const SIM = {
  /** 初始属性。改这里就是改开局难度 */
  startStats: {
    age: 16,
    lifespan: 80,
    qi: 0,
    stones: 20,
    mood: 60,
  } as Record<string, number>,

  /** 每回合触发事件的概率（0 = 关闭，测试用） */
  eventChance: 0.45,

  /** 日志保留条数 */
  maxLog: 8,

  /** 属性条的显示顺序与中文名 */
  statOrder: ['qi', 'stones', 'mood'] as string[],
  statNames: { qi: '修为', stones: '灵石', mood: '心境' } as Record<string, string>,
  /** 属性条上限（心境 100，其余按当前境界下一档动态算） */
  moodMax: 100,
};

export const COLORS = {
  bg: 0x0b1412,
  panel: 0x14231f,
  panelEdge: 0x2a4a3f,
  text: '#e6f2ec',
  textDim: '#8aa79c',
  accent: 0x7fd1a8,
  gold: 0xd8b96a,
  danger: 0xe0655c,
  qi: 0x7fd1a8,
  stones: 0xd8b96a,
  mood: 0x8fb8e0,
};

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

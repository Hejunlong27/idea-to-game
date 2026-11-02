/* eslint-disable */
// 默认 Juice 配置（模板自带）。项目执行
//   python scripts/juice_forge.py --project . --emit-ts
// 后会从 docs/04-core-loop/juice-plan.json 重新生成 —— 那时它是真相源，不要手改。

export interface EffectSpec {
  type:
    | 'squash_stretch'
    | 'anticipation'
    | 'follow_through'
    | 'secondary_motion'
    | 'parallax'
    | 'particles'
    | 'environmental'
    | 'ui_motion'
    | 'camera_shake'
    | 'camera_zoom'
    | 'hit_stop'
    | 'slow_motion'
    | 'screen_flash'
    | 'transition';
  /** 相对强度倍率（1 = 按事件严重度原样） */
  scale?: number;
  /** 时长覆盖（毫秒） */
  durationMs?: number;
  /** 粒子数 / 缩放倍率等 */
  amount?: number;
  /** 颜色（#RRGGBB），留空用视觉 DNA 的强调色 */
  color?: string;
}

export interface JuiceRule {
  event: string;
  /** 低于该严重度不触发（防止小事件用大表现） */
  minIntensity?: number;
  effects: EffectSpec[];
}

/** 规则按事件严重度分级：micro / light / medium / heavy */
export const JUICE_RULES: JuiceRule[] = [
  { event: 'player_move', effects: [{ type: 'squash_stretch', scale: 0.4 }] },
  { event: 'player_action', effects: [{ type: 'squash_stretch', scale: 0.6 }, { type: 'particles', amount: 6 }] },
  {
    event: 'player_hit',
    effects: [
      { type: 'squash_stretch', scale: 1 },
      { type: 'camera_shake', scale: 0.6 },
      { type: 'particles', amount: 10, color: '#FF6B5A' },
      { type: 'screen_flash', scale: 0.25, color: '#FF6B5A' },
    ],
  },
  { event: 'item_collected', effects: [{ type: 'particles', amount: 8 }, { type: 'ui_motion', scale: 0.5 }] },
  { event: 'enemy_defeated', effects: [{ type: 'particles', amount: 18 }, { type: 'hit_stop', durationMs: 60 }] },
  {
    event: 'level_completed',
    effects: [
      { type: 'camera_zoom', scale: 1 },
      { type: 'particles', amount: 40 },
      { type: 'hit_stop', durationMs: 90 },
      { type: 'ui_motion', scale: 1 },
    ],
  },
  {
    event: 'player_death',
    effects: [
      { type: 'slow_motion', durationMs: 420 },
      { type: 'screen_flash', scale: 0.7, color: '#C6463C' },
      { type: 'camera_shake', scale: 1 },
      { type: 'particles', amount: 24, color: '#C6463C' },
    ],
  },
];

export const JUICE_SETTINGS = {
  /** 同屏粒子上限（低端设备会自动减半） */
  maxParticles: 120,
  /** 震动强度上限（超过会晕动） */
  shakeCap: 0.012,
  /** 闪屏频率上限（次/秒）—— 光敏性癫痫防护，硬上限 */
  flashMaxPerSecond: 1,
  /** 震动时长上限（毫秒） */
  shakeMaxMs: 300,
  /** 视觉 DNA 的强调色，粒子与闪屏默认用它 */
  accentColor: '#F2B04A',
  /** 危险色 */
  dangerColor: '#C6463C',
};

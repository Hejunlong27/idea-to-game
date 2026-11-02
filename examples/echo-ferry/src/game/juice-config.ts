/* eslint-disable */
// 由 scripts/juice_forge.py --emit-ts 生成，**不要手改**。
// 真相源：docs/04-core-loop/juice-plan.json

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
  scale?: number;
  durationMs?: number;
  amount?: number;
  color?: string;
}

export interface JuiceRule {
  event: string;
  minIntensity?: number;
  effects: EffectSpec[];
}

export const JUICE_RULES: JuiceRule[] = [
  {
    event: 'game_start',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 0.8 }, { type: 'particles', amount: 8, color: '#84F24A' }, { type: 'ui_motion', scale: 0.5 }],
  },
  {
    event: 'game_over',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 32, color: '#C6463C' }, { type: 'camera_shake', scale: 1.0 }, { type: 'hit_stop', durationMs: 90 }, { type: 'camera_zoom', scale: 1.0 }, { type: 'screen_flash', scale: 0.5, color: '#C6463C' }],
  },
  {
    event: 'player_move',
    minIntensity: 0.15,
    effects: [{ type: 'squash_stretch', scale: 0.35 }, { type: 'environmental', scale: 0.5 }],
  },
  {
    event: 'player_action',
    minIntensity: 0.15,
    effects: [{ type: 'squash_stretch', scale: 0.8 }, { type: 'particles', amount: 8, color: '#84F24A' }, { type: 'ui_motion', scale: 0.5 }],
  },
  {
    event: 'player_hit',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 14, color: '#84F24A' }, { type: 'camera_shake', scale: 0.6 }, { type: 'hit_stop', durationMs: 60 }],
  },
  {
    event: 'player_death',
    minIntensity: 0.0,
    effects: [{ type: 'slow_motion', durationMs: 420 }, { type: 'screen_flash', scale: 0.7, color: '#C6463C' }, { type: 'camera_shake', scale: 1.0 }, { type: 'particles', amount: 24, color: '#C6463C' }, { type: 'hit_stop', durationMs: 120 }],
  },
  {
    event: 'enemy_spawn',
    minIntensity: 0.15,
    effects: [{ type: 'particles', amount: 6, color: '#84F24A' }, { type: 'squash_stretch', scale: 0.5 }, { type: 'environmental', scale: 0.6 }],
  },
  {
    event: 'enemy_defeated',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 14, color: '#84F24A' }, { type: 'camera_shake', scale: 0.6 }, { type: 'hit_stop', durationMs: 60 }],
  },
  {
    event: 'item_collected',
    minIntensity: 0.15,
    effects: [{ type: 'squash_stretch', scale: 0.4 }, { type: 'ui_motion', scale: 0.3 }],
  },
  {
    event: 'level_started',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 0.8 }, { type: 'particles', amount: 8, color: '#84F24A' }, { type: 'ui_motion', scale: 0.5 }],
  },
  {
    event: 'level_completed',
    minIntensity: 0.0,
    effects: [{ type: 'camera_zoom', scale: 1.0 }, { type: 'particles', amount: 40, color: '#C6463C' }, { type: 'hit_stop', durationMs: 90 }, { type: 'ui_motion', scale: 1.0 }, { type: 'screen_flash', scale: 0.35, color: '#C6463C' }],
  },
  {
    event: 'boss_appeared',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 32, color: '#C6463C' }, { type: 'camera_shake', scale: 1.0 }, { type: 'hit_stop', durationMs: 90 }, { type: 'camera_zoom', scale: 1.0 }, { type: 'screen_flash', scale: 0.5, color: '#C6463C' }],
  },
  {
    event: 'boss_defeated',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 32, color: '#C6463C' }, { type: 'camera_shake', scale: 1.0 }, { type: 'hit_stop', durationMs: 90 }, { type: 'camera_zoom', scale: 1.0 }, { type: 'screen_flash', scale: 0.5, color: '#C6463C' }],
  },
  {
    event: 'story_reveal',
    minIntensity: 0.0,
    effects: [{ type: 'hit_stop', durationMs: 220 }, { type: 'particles', amount: 12, color: '#84F24A' }, { type: 'ui_motion', scale: 0.8 }, { type: 'environmental', scale: 0.9 }],
  },
  {
    event: 'secret_found',
    minIntensity: 0.0,
    effects: [{ type: 'squash_stretch', scale: 1.0 }, { type: 'particles', amount: 14, color: '#84F24A' }, { type: 'camera_shake', scale: 0.6 }, { type: 'hit_stop', durationMs: 60 }],
  },
  {
    event: 'resource_changed',
    minIntensity: 0.15,
    effects: [{ type: 'squash_stretch', scale: 0.4 }, { type: 'ui_motion', scale: 0.3 }],
  },
  {
    event: 'state_changed',
    minIntensity: 0.15,
    effects: [{ type: 'squash_stretch', scale: 0.8 }, { type: 'particles', amount: 8, color: '#84F24A' }, { type: 'ui_motion', scale: 0.5 }],
  },
  {
    event: 'memory_spent',
    minIntensity: 0.0,
    effects: [{ type: 'ui_motion', scale: 0.9 }, { type: 'squash_stretch', scale: 0.25 }],
  },
  {
    event: 'echo_ping',
    minIntensity: 0.0,
    effects: [{ type: 'environmental', scale: 1.0 }, { type: 'particles', amount: 10, color: '#84F24A' }, { type: 'hit_stop', durationMs: 60 }],
  },
  {
    event: 'memory_empty',
    minIntensity: 0.0,
    effects: [{ type: 'slow_motion', durationMs: 500 }, { type: 'hit_stop', durationMs: 180 }, { type: 'camera_zoom', scale: 0.6 }, { type: 'particles', amount: 20, color: '#84F24A' }, { type: 'environmental', scale: 1.0 }],
  },
  {
    event: 'soul_delivered',
    minIntensity: 0.0,
    effects: [{ type: 'camera_zoom', scale: 0.8 }, { type: 'particles', amount: 18, color: '#84F24A' }, { type: 'ui_motion', scale: 1.0 }, { type: 'environmental', scale: 0.7 }],
  },
];

export const JUICE_SETTINGS = {
  maxParticles: 120,
  shakeCap: 0.012,
  flashMaxPerSecond: 1,
  shakeMaxMs: 300,
  accentColor: '#84F24A',
  dangerColor: '#C6463C',
};

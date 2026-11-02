/* eslint-disable */
// 默认运行时音频配置（模板自带，保证任何项目开箱可跑）。
// 项目执行 `python scripts/audio_director.py --project . --emit-ts` 后，本文件会被
// 从 docs/05-audio/audio-dna.json 重新生成 —— 那时它就是真相源，不要手改。

export interface StemCfg {
  id: string;
  key: string;
  defaultGain: number;
  duckUnderSfx: boolean;
}

export interface AudioStateCfg {
  id: string;
  zh: string;
  transitionMs: number;
  gains: Record<string, number>;
}

export const AUDIO_STEMS: StemCfg[] = [
  { id: 'melody', key: 'stem_melody', defaultGain: 0.5, duckUnderSfx: true },
  { id: 'rhythm', key: 'stem_rhythm', defaultGain: 0.4, duckUnderSfx: false },
  { id: 'bass', key: 'stem_bass', defaultGain: 0.45, duckUnderSfx: false },
  { id: 'percussion', key: 'stem_percussion', defaultGain: 0.35, duckUnderSfx: false },
  { id: 'atmosphere', key: 'stem_atmosphere', defaultGain: 0.4, duckUnderSfx: true },
];

export const AUDIO_STATES: AudioStateCfg[] = [
  {
    id: 'exploration',
    zh: '探索',
    transitionMs: 1200,
    gains: { melody: 0.35, rhythm: 0, bass: 0.2, percussion: 0, atmosphere: 0.5 },
  },
  {
    id: 'danger',
    zh: '危险',
    transitionMs: 900,
    gains: { melody: 0.25, rhythm: 0.35, bass: 0.7, percussion: 0.1, atmosphere: 0.4 },
  },
  {
    id: 'critical',
    zh: '濒危',
    transitionMs: 400,
    gains: { melody: 0.2, rhythm: 0.9, bass: 0.85, percussion: 0.5, atmosphere: 0.15 },
  },
  {
    id: 'victory',
    zh: '胜利',
    transitionMs: 400,
    gains: { melody: 0.85, rhythm: 0.4, bass: 0.5, percussion: 0.55, atmosphere: 0.3 },
  },
];

export const AUDIO_INITIAL_STATE = 'exploration';

export const AUDIO_BUS_GAINS = { master: 0.85, music: 0.55, sfx: 0.9, ui: 0.7, ambience: 0.5 };

export const AUDIO_SFX_RULES = {
  variants: 3,
  pitchJitter: 1.5,
  gainJitterDb: 2.5,
  minIntervalMs: 60,
  sameCooldownMs: 90,
  maxConcurrent: 12,
  maxPerSound: 3,
  distance: { enabled: true, refDistance: 400, rolloff: 1.2, maxDistance: 1600 },
};

export const AUDIO_GAMEPLAY_HOOKS: unknown[] = [];

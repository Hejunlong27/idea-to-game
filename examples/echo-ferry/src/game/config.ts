/**
 * 《回声摆渡》全部可调数值。
 * 色值来自 docs/02-art/visual-dna.json（由 art_director.py 生成），不要手改色值。
 */

export const LAYOUT = {
  width: 720,
  height: 1280,
  orientation: 'portrait' as 'portrait' | 'landscape',
};

export const GRID = {
  cols: 7,
  rows: 9,
  cell: 88,
  originX: 52,
  originY: 214,
};

export const COLORS = {
  bg: 0x08121c,
  water: 0x0e1b2a,
  waterLine: 0x1b3a4b,
  waterHi: 0x2e5d6b,
  shore: 0xe8dcc0,
  accent: 0xf2c14a,
  accent2: 0x7fd8cd,
  danger: 0xc6463c,
  text: '#F2EBDD',
  textDim: '#8FA3B0',
  ink: 0x050b12,
};

/** 回声与记忆的核心参数（levels.json 可按关覆盖） */
export const ECHO = {
  memoryMax: 5,
  memoryRegenMs: 12000,
  revealMs: 1200,
  ghostLifeMs: 9000,
  exposeRadius: 8,
  revealRadius: 4,
  rippleMs: 900,
};

export const RULES = {
  hullMax: 3,
  invulnMs: 1400,
  duckMs: 600,
};

export const JUICE = {
  pingRippleMs: 900,
  moveTweenMs: 90,
  deliverFlashMs: 420,
};

export const ASSETS = {
  useAtlas: false,
  atlasKey: 'game',
  atlasPng: 'assets/atlas/atlas.png',
  atlasJson: 'assets/atlas/atlas.json',
};

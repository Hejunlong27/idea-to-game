import Phaser from 'phaser';
import { COLORS, GAME } from './config';

/**
 * 美术层 —— 所有纹理的唯一入口。
 *
 * ## 为什么要单独一层
 *
 * 玩法代码里直接 `scene.add.image(x, y, 'some_key')` 会让「纹理从哪来」散落在各处，
 * 一旦换美术（程序化 → AI 图 → 图集）就要改遍全项目。这一层把来源收敛到一个地方：
 *
 *   玩法代码只认 `TEXTURES.xxx` 这些固定键，不关心背后是 AI 图还是矢量绘制。
 *
 * ## 混合美术（推荐做法）
 *
 * | 素材类型 | 来源 | 理由 |
 * |---|---|---|
 * | 角色 / 道具 / 背景 | AI 生图 | 质感（纸纹、笔触、光照）程序化画不出来 |
 * | 地块 / 水纹 / 粒子 / UI | 程序化 | 必须无缝平铺、像素对齐、零体积 |
 *
 * 关键约定：**同名纹理只生成一次**。
 * `BootScene` 先把 `assets/img/<stem>.png` 加载到 `TEXTURES` 里对应的键，
 * 这里每个块都先判 `scene.textures.exists(key)` —— 已存在就跳过。
 *
 * 于是：删掉某张 AI 图 → 自动回退到程序化版本 → **玩法代码零改动**。
 *
 * ## 新项目怎么用
 *
 * 1. 在 `TEXTURES` 里加键
 * 2. 在 `buildTextures()` 里加一段 `makeTexture(...)`
 * 3. 在 `BootScene` 的 `IMG_KEYS` 里把 `assets/img/<stem>.png` 映射到这个键
 */

/** 游戏内固定纹理键。玩法代码只用这些，不要出现裸字符串。 */
export const TEXTURES = {
  /** 占位靶子（模板自带玩法） */
  target: 'ph_target',
  targetHit: 'ph_target_hit',
} as const;

/**
 * 确定性伪随机。
 *
 * 不用 `Math.random()`：那会让每次构建产出的纹理都不一样，
 * 截图回归测试就没法比像素了。同一个 seed 永远得到同一张纹理。
 */
export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/**
 * 画一张纹理。`draw` 只负责画，尺寸、清屏、销毁由这里统一管。
 *
 * @returns 是否真的生成了（键已存在时返回 false —— 说明 AI 图已占位）
 */
export function makeTexture(
  scene: Phaser.Scene,
  key: string,
  w: number,
  h: number,
  draw: (g: Phaser.GameObjects.Graphics, w: number, h: number) => void,
): boolean {
  if (scene.textures.exists(key)) return false;
  const g = scene.make.graphics({ x: 0, y: 0 }, false);
  g.clear();
  draw(g, w, h);
  g.generateTexture(key, w, h);
  g.destroy();
  return true;
}

/** 生成全部程序化纹理。AI 图已加载的键会被自动跳过。 */
export function buildTextures(scene: Phaser.Scene): void {
  const r = GAME.targetRadius;

  makeTexture(scene, TEXTURES.target, r * 2, r * 2, (g) => {
    g.fillStyle(COLORS.accent, 1);
    g.fillCircle(r, r, r);
    g.lineStyle(6, 0xffffff, 0.35);
    g.strokeCircle(r, r, r);
  });

  makeTexture(scene, TEXTURES.targetHit, r * 2, r * 2, (g) => {
    g.fillStyle(COLORS.good, 1);
    g.fillCircle(r, r, r);
    g.lineStyle(6, 0xffffff, 0.5);
    g.strokeCircle(r, r, r);
  });

  // 新项目的纹理加在这里。例：
  //   makeTexture(scene, TEXTURES.player, 96, 96, (g) => {
  //     g.fillStyle(COLORS.accent, 1);
  //     g.fillCircle(48, 48, 40);
  //   });
}

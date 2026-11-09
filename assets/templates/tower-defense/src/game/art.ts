import Phaser from 'phaser';
import { COLORS, GRID } from './config';

/**
 * 美术层 —— 所有纹理的唯一入口。
 *
 * 玩法代码只认 `TEXTURES.xxx` 这些固定键，不关心背后是 AI 图还是矢量绘制。
 * 换美术（程序化 → AI 图 → 图集）只改本文件与 BootScene 的映射，玩法零改动。
 *
 * 塔防品类建议的混合美术分工：
 * | 素材 | 来源 | 理由 |
 * |---|---|---|
 * | 塔 / 敌人 / 基地 | AI 生图 | 需要辨识度与质感 |
 * | 地面 / 路径 / 选中框 / 弹道 | 程序化 | 必须像素对齐、可无缝拼接、零体积 |
 *
 * 同名纹理只生成一次：BootScene 先把 `assets/img/<stem>.png` 加载到对应键，
 * 这里每块都先判 `textures.exists()`，已存在就跳过 —— 删图自动回退，玩法零改动。
 */

/** 游戏内固定纹理键。玩法代码只用这些，不要出现裸字符串。 */
export const TEXTURES = {
  ground: 'td_ground',
  groundAlt: 'td_ground_alt',
  road: 'td_road',
  tower: 'td_tower',
  enemy: 'td_enemy',
  base: 'td_base',
  shot: 'td_shot',
  ring: 'td_ring',
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
  const s = GRID.cell;

  // 可建造地面：两种深浅交替，让网格可读但不抢眼
  makeTexture(scene, TEXTURES.ground, s, s, (g, w, h) => {
    g.fillStyle(COLORS.ground, 1);
    g.fillRect(0, 0, w, h);
    g.lineStyle(1, 0x000000, 0.25);
    g.strokeRect(0.5, 0.5, w - 1, h - 1);
  });

  makeTexture(scene, TEXTURES.groundAlt, s, s, (g, w, h) => {
    g.fillStyle(COLORS.groundAlt, 1);
    g.fillRect(0, 0, w, h);
    g.lineStyle(1, 0x000000, 0.25);
    g.strokeRect(0.5, 0.5, w - 1, h - 1);
  });

  // 路径：纯色无缝铺贴（**不能画格子边框**，否则路径看起来是一格格方块而不是一条路）
  makeTexture(scene, TEXTURES.road, s, s, (g, w, h) => {
    g.fillStyle(COLORS.road, 1);
    g.fillRect(0, 0, w, h);
    // 路面颗粒（确定性随机，保证截图可复现）
    const r = rng(0x7d3);
    g.fillStyle(0x000000, 0.16);
    for (let i = 0; i < 14; i++) {
      g.fillCircle(r() * w, r() * h, 1 + r() * 2);
    }
    g.fillStyle(0xffffff, 0.04);
    for (let i = 0; i < 8; i++) {
      g.fillCircle(r() * w, r() * h, 1 + r() * 1.5);
    }
  });

  /**
   * 塔：深色基座 + 可着色塔身 + 中心光点。
   * 白色部分会被运行时 setTint 染色（一张纹理服务三种塔），
   * 深色基座不染，保证任何颜色下都有轮廓、不会糊进背景。
   */
  makeTexture(scene, TEXTURES.tower, s, s, (g, w, h) => {
    const cx = w / 2;
    const cy = h / 2;
    // 基座（不被 tint 影响）
    g.fillStyle(0x0e131c, 0.92);
    g.fillRoundedRect(12, 12, w - 24, h - 24, 14);
    g.lineStyle(2, 0x000000, 0.5);
    g.strokeRoundedRect(12, 12, w - 24, h - 24, 14);
    // 塔身（会被染色）
    g.fillStyle(0xffffff, 1);
    g.fillCircle(cx, cy, 17);
    g.fillStyle(0xffffff, 0.35);
    g.fillCircle(cx, cy, 24);
    // 中心光点
    g.fillStyle(0xffffff, 1);
    g.fillCircle(cx, cy, 6);
  });

  // 敌人：白色圆 + 高光，颜色与大小由运行时按类型决定
  makeTexture(scene, TEXTURES.enemy, 48, 48, (g, w, h) => {
    const c = w / 2;
    g.fillStyle(0xffffff, 1);
    g.fillCircle(c, c, c - 2);
    g.fillStyle(0x000000, 0.28);
    g.fillCircle(c, c, c - 7);
    g.fillStyle(0xffffff, 0.6);
    g.fillCircle(c - 5, c - 6, 5);
  });

  // 基地：六边形轮廓 + 内核
  makeTexture(scene, TEXTURES.base, s, s, (g, w, h) => {
    const cx = w / 2;
    const cy = h / 2;
    const R = w / 2 - 6;
    const pts: Phaser.Geom.Point[] = [];
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i - Math.PI / 2;
      pts.push(new Phaser.Geom.Point(cx + Math.cos(a) * R, cy + Math.sin(a) * R));
    }
    g.fillStyle(0x14303f, 1);
    g.fillPoints(pts, true);
    g.lineStyle(3, COLORS.good, 0.9);
    g.strokePoints(pts, true);
    g.fillStyle(COLORS.good, 0.9);
    g.fillCircle(cx, cy, 9);
  });

  // 弹道点
  makeTexture(scene, TEXTURES.shot, 12, 12, (g, w, h) => {
    g.fillStyle(0xffe9a8, 1);
    g.fillCircle(w / 2, h / 2, w / 2 - 1);
  });

  // 射程指示环（建塔预览用）
  makeTexture(scene, TEXTURES.ring, 32, 32, (g, w, h) => {
    g.lineStyle(3, COLORS.accent, 0.8);
    g.strokeCircle(w / 2, h / 2, w / 2 - 2);
  });
}

import Phaser from 'phaser';
import { COLORS, GRID } from './config';

/**
 * 混合美术：AI 生图（角色/道具/背景）+ 程序化（地块/水纹/光效）。
 *
 * 为什么混：
 *   - AI 图擅长「质感」——角色的纸纹、水彩边缘、光照，程序化画不出来
 *   - 程序化擅长「绝对一致 + 零体积」——地块要无缝重复，UI 要像素对齐，AI 做不好
 *   实测：全 AI 图约 4.5MB，全程序化 0KB，混合后 224KB。
 *
 * 关键约定：**同名纹理只生成一次**。BootScene 若已加载 `t_boat`（来自 assets/img/boat.png），
 * 这里就跳过程序化生成 —— 换图/回退都不用改玩法代码。
 */

const TEX = {
  water: 't_water',
  shore: 't_shore',
  boat: 't_boat',
  boatLit: 't_boat_lit',
  soul: 't_soul',
  wraith: 't_wraith',
  rock: 't_rock',
  ripple: 't_ripple',
  dot: 't_dot',
  bg: 't_bg',
  bell: 't_bell',
} as const;

export const TEXTURES = TEX;

/** 确定性伪随机（不用 Math.random，保证每次构建出的纹理完全一致） */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

export function buildTextures(scene: Phaser.Scene) {
  const c = GRID.cell;
  const g = scene.make.graphics({ x: 0, y: 0 }, false);
  const has = (k: string) => scene.textures.exists(k);

  // ---- 水面（始终程序化：必须无缝平铺）
  if (!has(TEX.water)) {
    g.clear();
    g.fillStyle(COLORS.water, 1);
    g.fillRect(0, 0, c, c);
    g.lineStyle(1, COLORS.waterLine, 0.9);
    for (let i = 0; i < 3; i++) {
      const y = 16 + i * 26;
      g.beginPath();
      g.moveTo(4, y);
      g.lineTo(c * 0.35, y - 4);
      g.lineTo(c * 0.7, y + 3);
      g.lineTo(c - 4, y - 2);
      g.strokePath();
    }
    const r = rng(7);
    g.lineStyle(1, 0xffffff, 0.05);
    for (let i = 0; i < 14; i++) {
      const x = r() * c;
      const y = r() * c;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x + r() * 6 - 3, y + r() * 6 - 3);
      g.strokePath();
    }
    g.generateTexture(TEX.water, c, c);
  }

  // ---- 岸边（程序化：要与水面同尺寸无缝）
  if (!has(TEX.shore)) {
    g.clear();
    g.fillStyle(COLORS.shore, 1);
    g.fillRect(0, 0, c, c);
    g.fillStyle(0x000000, 0.1);
    for (let i = 0; i < 6; i++) g.fillRect(0, i * 16 + 6, c, 2);
    g.fillStyle(0x1b3a4b, 0.55);
    g.fillRect(0, 0, 6, c);
    g.generateTexture(TEX.shore, c, c);
  }

  // ---- 船（优先 AI 图；没有就画一个）
  if (!has(TEX.boat)) {
    const bw = 76;
    const bh = 64;
    const hull = [
      new Phaser.Geom.Point(6, 30), new Phaser.Geom.Point(20, 14),
      new Phaser.Geom.Point(bw - 22, 14), new Phaser.Geom.Point(bw - 6, 32),
      new Phaser.Geom.Point(bw - 22, 52), new Phaser.Geom.Point(20, 52),
    ];
    g.clear();
    g.fillStyle(COLORS.ink, 1);
    g.fillPoints(hull, true);
    g.lineStyle(2, COLORS.waterHi, 0.9);
    g.strokePoints(hull, true);
    g.fillStyle(COLORS.accent, 1);
    g.fillCircle(bw - 14, 32, 5);
    g.generateTexture(TEX.boat, bw, bh);
  }

  // ---- 船头灯柔光（始终程序化：AI 图不带发光层）
  if (!has(TEX.boatLit)) {
    g.clear();
    g.fillStyle(COLORS.accent, 0.16);
    g.fillCircle(38, 32, 34);
    g.fillStyle(COLORS.accent, 0.22);
    g.fillCircle(38, 32, 24);
    g.generateTexture(TEX.boatLit, 76, 64);
  }

  // ---- 灵魂（优先 AI 图）
  if (!has(TEX.soul)) {
    g.clear();
    g.fillStyle(COLORS.accent2, 0.9);
    g.fillCircle(28, 34, 16);
    g.fillTriangle(28, 4, 16, 32, 40, 32);
    g.fillStyle(0xffffff, 0.55);
    g.fillCircle(23, 30, 5);
    g.generateTexture(TEX.soul, 56, 56);
  }

  // ---- 幽影（优先 AI 图）
  if (!has(TEX.wraith)) {
    g.clear();
    const rr = rng(31);
    const pts: Phaser.Geom.Point[] = [];
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2;
      const rad = 18 + rr() * 8;
      pts.push(new Phaser.Geom.Point(32 + Math.cos(a) * rad, 34 + Math.sin(a) * rad * 0.92));
    }
    g.fillStyle(COLORS.ink, 1);
    g.fillPoints(pts, true);
    g.lineStyle(1.5, COLORS.danger, 0.75);
    g.strokePoints(pts, true);
    g.fillStyle(COLORS.danger, 1);
    g.fillCircle(26, 30, 2.6);
    g.fillCircle(38, 30, 2.6);
    g.generateTexture(TEX.wraith, 64, 68);
  }

  // ---- 礁石（优先 AI 图）
  if (!has(TEX.rock)) {
    const pts = [
      new Phaser.Geom.Point(10, 58), new Phaser.Geom.Point(4, 34),
      new Phaser.Geom.Point(22, 10), new Phaser.Geom.Point(52, 14),
      new Phaser.Geom.Point(66, 40), new Phaser.Geom.Point(54, 60),
    ];
    g.clear();
    g.fillStyle(0x11202c, 1);
    g.fillPoints(pts, true);
    g.lineStyle(2, COLORS.waterLine, 1);
    g.strokePoints(pts, true);
    g.generateTexture(TEX.rock, 72, 72);
  }

  // ---- 水纹（始终程序化：要精确同心圆）
  if (!has(TEX.ripple)) {
    g.clear();
    g.lineStyle(3, COLORS.accent2, 0.85);
    g.strokeCircle(96, 96, 80);
    g.lineStyle(1.5, COLORS.accent2, 0.45);
    g.strokeCircle(96, 96, 60);
    g.generateTexture(TEX.ripple, 192, 192);
  }

  // ---- 粒子点（始终程序化）
  if (!has(TEX.dot)) {
    g.clear();
    g.fillStyle(0xffffff, 1);
    g.fillCircle(5, 5, 5);
    g.generateTexture(TEX.dot, 10, 10);
  }

  g.destroy();
}

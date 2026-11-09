import Phaser from 'phaser';

/**
 * 美术层 —— 模拟器品类的纹理需求极少。
 *
 * 这类游戏的画面 90% 是文字与面板，用 Phaser 的 Rectangle / Graphics 直接画
 * 比生成纹理更清晰（矢量随分辨率缩放不糊），也更省体积。
 *
 * 只有真正需要「质感」的东西才走纹理：
 *   角色立绘、背景插画、道具图标 —— 这些接 AI 生图，通过 BootScene 的 IMG_KEYS 映射。
 *
 * 因此本文件默认只提供 `makeTexture` 工具，接图后按需补 TEXTURES。
 */

export const TEXTURES = {
  // 例：portrait: 'sim_portrait',
} as const;

/** 确定性伪随机（纹理生成用，保证截图可复现） */
export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

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

/** 生成全部程序化纹理。模拟器默认无纹理需求，接 AI 图后在此补。 */
export function buildTextures(_scene: Phaser.Scene): void {
  // 面板、属性条、按钮全部用 Rectangle / Graphics 直绘，不生成纹理。
}

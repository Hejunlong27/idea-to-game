import Phaser from 'phaser';
import { ASSETS, COLORS, GAME } from '../config';

/**
 * 启动场景：生成占位纹理、初始化存档、进入菜单。
 * 生图与切图完成后（ASSETS.useAtlas = true）在这里改为加载图集。
 */
export class BootScene extends Phaser.Scene {
  constructor() {
    super('Boot');
  }

  preload() {
    if (ASSETS.useAtlas) {
      this.load.atlas(ASSETS.atlasKey, ASSETS.atlasPng, ASSETS.atlasJson);
    }
  }

  create() {
    // 用几何图形生成占位纹理，保证 P2 之前无需任何美术资源即可运行
    const r = GAME.targetRadius;
    this.makeCircleTexture('ph_target', r, COLORS.accent);
    this.makeCircleTexture('ph_target_hit', r, COLORS.good);

    const boot = document.getElementById('boot');
    if (boot) boot.style.display = 'none';

    this.scene.start('Menu');
  }

  private makeCircleTexture(key: string, radius: number, color: number) {
    const g = this.add.graphics();
    g.fillStyle(color, 1);
    g.fillCircle(radius, radius, radius);
    g.lineStyle(6, 0xffffff, 0.35);
    g.strokeCircle(radius, radius, radius);
    g.generateTexture(key, radius * 2, radius * 2);
    g.destroy();
  }
}

import Phaser from 'phaser';
import { ASSETS } from '../config';
import { buildTextures } from '../art';
import { registerFrameAnims } from '../anim';

/**
 * 启动场景：生成占位纹理、初始化存档、进入菜单。
 *
 * 纹理来源全部收敛到 `art.ts` 的 `buildTextures()`。
 * 生图与切图完成后（ASSETS.useAtlas = true）在 preload 里加载图集，
 * 或把 `assets/img/<stem>.png` 映射到固定纹理键（见 `IMG_KEYS` 约定）——
 * 无论哪种，玩法代码都不用改。
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
    // 程序化纹理：与已加载的 AI 图同名则跳过（混合美术的关键）
    buildTextures(this);

    // 图集里的帧动画（帧名 <key>_0..N）—— 没有帧时静默跳过
    if (ASSETS.useAtlas) registerFrameAnims(this);

    const boot = document.getElementById('boot');
    if (boot) boot.style.display = 'none';

    // ⚠️ index.html 的启动看门狗靠这个标记判断「游戏是否真的起来了」。
    //    不要删：删了之后任何启动失败都会静默停在 Loading，无从诊断。
    (window as unknown as { __bootDone?: boolean }).__bootDone = true;

    this.scene.start('Menu');
  }
}

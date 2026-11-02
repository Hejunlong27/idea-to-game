import Phaser from 'phaser';
import { buildTextures } from '../art';
import { ASSETS } from '../config';

/**
 * 启动场景：加载 AI 素材 + 生成程序化纹理 + 加载音频。
 *
 * 音频与图片都用 `import.meta.glob` 批量收集（Vite 会产出独立文件并改写为相对路径），
 * 键名取文件名（不含扩展名），与 docs/05-audio/sfx-plan.json 的 id 一一对应。
 *
 * 图片按 `IMG_KEYS` 映射到**游戏内固定纹理键**（t_boat / t_soul …）。
 * 映射到同一个键之后，art.ts 会跳过对应的程序化生成 ——
 * 于是「换 AI 图 / 回退程序化」都不用改玩法代码。
 */
const AUDIO_URLS = import.meta.glob('../../../assets/audio/**/*.mp3', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>;

const IMG_URLS = import.meta.glob('../../../assets/img/*.{png,jpg}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>;

/** 文件名 → 游戏内纹理键。没有映射的文件不会加载。 */
const IMG_KEYS: Record<string, string> = {
  boat: 't_boat',
  wraith: 't_wraith',
  soul: 't_soul',
  rock: 't_rock',
  bell: 't_bell',
  bg: 't_bg',
};

export class BootScene extends Phaser.Scene {
  constructor() {
    super('Boot');
  }

  preload() {
    for (const [path, url] of Object.entries(AUDIO_URLS)) {
      const key = path.split('/').pop()!.replace(/\.mp3$/, '');
      this.load.audio(key, url);
    }
    for (const [path, url] of Object.entries(IMG_URLS)) {
      const stem = path.split('/').pop()!.replace(/\.(png|jpg)$/, '');
      const key = IMG_KEYS[stem];
      if (key) this.load.image(key, url);
    }
    if (ASSETS.useAtlas) {
      this.load.atlas(ASSETS.atlasKey, ASSETS.atlasPng, ASSETS.atlasJson);
    }
  }

  create() {
    // 程序化纹理：与已加载的 AI 图同名则跳过（混合美术的关键）
    buildTextures(this);

    const boot = document.getElementById('boot');
    if (boot) boot.style.display = 'none';

    // ⚠️ index.html 的启动看门狗靠这个标记判断「游戏是否真的起来了」。不要删。
    (window as unknown as { __bootDone?: boolean }).__bootDone = true;

    this.scene.start('Menu');
  }
}

import Phaser from 'phaser';
import { ANIM, ANIM_FPS, ASSETS } from './config';

/**
 * 帧动画工具。
 *
 * 帧命名约定（与 `gen_assets.py` 的 `kind: frames` 输出一致）：
 *   `<key>_0`、`<key>_1` … `<key>_N-1`
 * 即一张 2×2 网格图切出来的 4 帧，key 为 `slime_idle` 时得到
 * `slime_idle_0 … slime_idle_3`，注册后的动画名为 `slime_idle_loop`。
 *
 * 为什么用图集帧而不是多张独立 PNG：CrazyGames 限制总文件数 ≤1500，
 * 一套 8 帧动画就是 8 个文件；打成图集后只增 1 张图。
 */

export type AnimSpec = Record<string, number>;

function collectFrames(scene: Phaser.Scene, key: string, count: number): string[] {
  const tex = scene.textures.get(ASSETS.atlasKey);
  const names: string[] = [];
  for (let i = 0; i < count; i++) {
    const frame = `${key}_${i}`;
    // 图集里缺帧就整套跳过，避免注册出半截动画（比报错更安全）
    if (!tex.has(frame)) return [];
    names.push(frame);
  }
  return names;
}

/** 按 `ANIM` 配置批量注册动画。图集里没有的 key 静默跳过。 */
export function registerFrameAnims(scene: Phaser.Scene, specs: AnimSpec = ANIM, fps = ANIM_FPS): string[] {
  if (!ASSETS.useAtlas) return [];
  const registered: string[] = [];
  for (const [key, count] of Object.entries(specs)) {
    const names = collectFrames(scene, key, count);
    if (!names.length) continue;
    const animKey = `${key}_loop`;
    if (scene.anims.exists(animKey)) continue;
    scene.anims.create({
      key: animKey,
      frames: names.map((frame) => ({ key: ASSETS.atlasKey, frame })),
      frameRate: fps,
      repeat: -1,
    });
    registered.push(animKey);
  }
  return registered;
}

/**
 * 播放帧动画。动画不存在时返回 false（不抛错）——
 * 素材还没到位时游戏必须照常能跑，这是本项目的硬规则。
 */
export function playFrames(sprite: Phaser.GameObjects.Sprite, key: string): boolean {
  const animKey = `${key}_loop`;
  if (!sprite.scene.anims.exists(animKey)) return false;
  sprite.play(animKey);
  return true;
}

/** 一次性动画（不循环），播完回到指定帧。 */
export function playOnce(sprite: Phaser.GameObjects.Sprite, key: string, onDone?: () => void): boolean {
  const animKey = `${key}_once`;
  if (!sprite.scene.anims.exists(animKey)) {
    const base = `${key}_loop`;
    if (!sprite.scene.anims.exists(base)) return false;
    const src = sprite.scene.anims.get(base);
    sprite.scene.anims.create({
      key: animKey,
      frames: src.frames.map((f) => ({ key: f.textureKey, frame: f.textureFrame })),
      frameRate: src.frameRate,
      repeat: 0,
    });
  }
  sprite.once(Phaser.Animations.Events.ANIMATION_COMPLETE, () => onDone?.());
  sprite.play(animKey);
  return true;
}

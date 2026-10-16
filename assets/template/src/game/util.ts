import type Phaser from 'phaser';
import type { PlatformBridge, SaveData } from '../types';
import { emptySave } from '../types';

/** 从 registry 取出平台桥接实例。src/game/ 不直接依赖 src/platform/。 */
export function bridge(scene: Phaser.Scene): PlatformBridge {
  return scene.registry.get('platform') as PlatformBridge;
}

/** 读档，失败或无存档时返回空存档。 */
export async function readSave(scene: Phaser.Scene): Promise<SaveData> {
  try {
    const data = await bridge(scene).load();
    return data ? { ...emptySave(), ...data } : emptySave();
  } catch {
    return emptySave();
  }
}

/** 存档，失败静默忽略。 */
export async function writeSave(scene: Phaser.Scene, data: SaveData): Promise<void> {
  try {
    await bridge(scene).save(data);
  } catch {
    /* 静默降级 */
  }
}

/** 计算缩放，使设计分辨率适配任意屏幕（保持比例，留黑边）。 */
export function fitScale(gameWidth: number, gameHeight: number, designW: number, designH: number) {
  return Math.min(gameWidth / designW, gameHeight / designH);
}

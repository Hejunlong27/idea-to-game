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

/**
 * 在 create() 返回后读档。场景关闭时丢弃 UI 回调，避免异步任务回写已销毁对象。
 * Phaser 的生命周期要求 create() 同步返回，不能在 create() 内 await。
 */
export function readSaveWhenReady(
  scene: Phaser.Scene,
  apply: (save: SaveData) => void,
): void {
  let active = true;
  const cancel = () => {
    active = false;
  };
  scene.events.once('shutdown', cancel);
  void readSave(scene).then((save) => {
    if (!active) return;
    scene.events.off('shutdown', cancel);
    apply(save);
  });
}

/**
 * 在 create() 返回后执行读改写。先捕获平台实例，所以离开场景后仍会完成落盘。
 * 用于纯持久化任务；需要更新 UI 的读档应使用 readSaveWhenReady()。
 */
export function updateSave(
  scene: Phaser.Scene,
  update: (save: SaveData) => SaveData,
): void {
  const platform = bridge(scene);
  void platform
    .load()
    .then((data) => {
      const save = data ? { ...emptySave(), ...data } : emptySave();
      return platform.save(update(save));
    })
    .catch(() => {
      /* 静默降级 */
    });
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

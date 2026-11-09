import Phaser from 'phaser';
import { LAYOUT } from './config';
import { BootScene } from './scenes/BootScene';
import { MenuScene } from './scenes/MenuScene';
import { PlayScene } from './scenes/PlayScene';
import { GameOverScene } from './scenes/GameOverScene';

/** 场景清单。新增场景在此注册。 */
export const SCENES: (typeof Phaser.Scene)[] = [BootScene, MenuScene, PlayScene, GameOverScene];

/** Phaser 游戏配置。 */
export function gameConfig(): Phaser.Types.Core.GameConfig {
  return {
    type: Phaser.AUTO,
    parent: 'game',
    backgroundColor: '#10121a',
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_BOTH,
      width: LAYOUT.width,
      height: LAYOUT.height,
    },
    render: {
      antialias: true,
      powerPreference: 'high-performance',
    },
    input: {
      activePointers: 3,
    },
    scene: SCENES as unknown as Phaser.Types.Core.GameConfig['scene'],
  };
}

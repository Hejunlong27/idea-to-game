import Phaser from 'phaser';
import { COLORS, LAYOUT } from '../config';
import { readSave } from '../util';

/** 菜单场景：显示最高分与开始入口。首屏到可玩必须 <3 秒。 */
export class MenuScene extends Phaser.Scene {
  constructor() {
    super('Menu');
  }

  async create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);

    const save = await readSave(this);

    this.add
      .text(W / 2, H * 0.3, 'IDEA TO GAME', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '52px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.3 + 56, '占位玩法 · 点击靶子', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '26px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.52, `最高分 ${save.best}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '34px',
        color: COLORS.text,
      })
      .setOrigin(0.5);

    const btn = this.add
      .rectangle(W / 2, H * 0.68, 420, 110, COLORS.accent, 1)
      .setStrokeStyle(3, 0xffffff, 0.25);
    const btnText = this.add
      .text(W / 2, H * 0.68, '开始', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '40px',
        color: '#0b1020',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    btn.setInteractive({ useHandCursor: true });
    const start = () => this.scene.start('Play');
    btn.on('pointerdown', start);
    btnText.setInteractive({ useHandCursor: true }).on('pointerdown', start);

    this.tweens.add({
      targets: [btn, btnText],
      scaleX: 1.04,
      scaleY: 1.04,
      duration: 900,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }
}

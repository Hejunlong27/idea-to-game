import Phaser from 'phaser';
import { COLORS, LAYOUT } from '../config';
import { bridge, readSave, writeSave } from '../util';

/** 结束场景：展示成绩、存档、重开。失败后 2 秒内必须能重开。 */
export class GameOverScene extends Phaser.Scene {
  private score = 0;
  private best = 0;
  private played = 0;
  private busy = false;

  constructor() {
    super('GameOver');
  }

  init(data: { score?: number }) {
    this.score = data?.score ?? 0;
  }

  async create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);
    this.busy = false;

    const save = await readSave(this);
    this.best = Math.max(save.best, this.score);
    this.played = Number(save.played ?? 0) + 1;

    await writeSave(this, { ...save, best: this.best, played: this.played });

    this.add
      .text(W / 2, H * 0.3, '结束', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '64px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.43, `本局 ${this.score}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '48px',
        color: COLORS.text,
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.52, `最高分 ${this.best}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '32px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    const btn = this.add
      .rectangle(W / 2, H * 0.68, 420, 110, COLORS.accent, 1)
      .setStrokeStyle(3, 0xffffff, 0.25)
      .setInteractive({ useHandCursor: true });
    const btnText = this.add
      .text(W / 2, H * 0.68, '再来一局', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '40px',
        color: '#0b1020',
        fontStyle: 'bold',
      })
      .setOrigin(0.5)
      .setInteractive({ useHandCursor: true });

    const restart = () => this.restart();
    btn.on('pointerdown', restart);
    btnText.on('pointerdown', restart);
  }

  /** 每两局插一次插屏广告；广告失败或拦截器场景下直接重开。 */
  private async restart() {
    if (this.busy) return;
    this.busy = true;

    if (this.played % 2 === 0) {
      try {
        await bridge(this).showMidroll();
      } catch {
        /* 静默降级 */
      }
    }
    this.scene.start('Play');
  }
}

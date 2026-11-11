import Phaser from 'phaser';
import { COLORS, LAYOUT } from '../config';
import { updateSave } from '../util';
import LEVELS from '../levels.json';

interface OverData {
  win: boolean;
  delivered: number;
  total: number;
  level: number;
}

/** 结束界面。失败必须告诉玩家「下次该改什么」，否则失败没有学习价值。 */
export class GameOverScene extends Phaser.Scene {
  private over!: OverData;

  constructor() {
    super('GameOver');
  }

  init(data: OverData) {
    this.over = data ?? { win: false, delivered: 0, total: 1, level: 0 };
  }

  create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);
    const d = this.over;
    const isLast = d.level >= LEVELS.levels.length - 1;

    this.add
      .text(W / 2, H * 0.26, d.win ? '靠岸了' : '沉下去了', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '64px',
        color: d.win ? COLORS.text : COLORS.textDim,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.26 + 68, d.win ? `送到 ${d.delivered} / ${d.total} 个灵魂` : `只送到 ${d.delivered} / ${d.total} 个`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '26px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    // 失败的教学：明确告诉玩家下次改什么（E7）
    const tip = d.win
      ? isLast
        ? '海面安静了。你记住了这条路。'
        : '下一片海里，影子会开始动得更快。'
      : '你敲得太勤了。残影会过期 —— 试着用上一次的回声多走两步，再决定要不要敲。';
    this.add
      .text(W / 2, H * 0.44, tip, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.textDim,
        align: 'center',
        wordWrap: { width: W - 120 },
        lineSpacing: 10,
      })
      .setOrigin(0.5);

    const makeBtn = (y: number, label: string, primary: boolean, onClick: () => void) => {
      const btn = this.add
        .rectangle(W / 2, y, 380, 96, primary ? COLORS.accent : 0x1b3a4b, primary ? 0.16 : 0.35)
        .setStrokeStyle(2, primary ? COLORS.accent : COLORS.waterHi, 0.9);
      const t = this.add
        .text(W / 2, y, label, {
          fontFamily: 'system-ui, sans-serif',
          fontSize: '32px',
          color: COLORS.text,
          fontStyle: 'bold',
        })
        .setOrigin(0.5);
      btn.setInteractive({ useHandCursor: true });
      btn.on('pointerdown', onClick);
      t.setInteractive({ useHandCursor: true }).on('pointerdown', onClick);
    };

    if (d.win && !isLast) {
      makeBtn(H * 0.62, '下一片海', true, () => this.scene.start('Play', { level: d.level + 1 }));
      makeBtn(H * 0.74, '重玩这一关', false, () => this.scene.start('Play', { level: d.level }));
    } else {
      makeBtn(H * 0.62, d.win ? '再划一次' : '再试一次', true, () =>
        this.scene.start('Play', { level: d.win ? 0 : d.level }));
    }

    const back = this.add
      .text(W / 2, H * 0.86, '回到岸边（菜单）', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);
    back.setInteractive({ useHandCursor: true }).on('pointerdown', () => this.scene.start('Menu'));

    this.input.keyboard?.once('keydown-SPACE', () => {
      if (d.win && !isLast) this.scene.start('Play', { level: d.level + 1 });
      else this.scene.start('Play', { level: d.win ? 0 : d.level });
    });

    // 纯持久化任务：先捕获平台实例，所以玩家立即重开也不会丢成绩。
    updateSave(this, (save) => ({
      ...save,
      best: Math.max(Number(save.best) || 0, d.delivered + d.level * 3),
    }));
  }
}

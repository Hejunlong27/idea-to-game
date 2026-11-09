import Phaser from 'phaser';
import { COLORS, LAYOUT, LEVELS, type LevelRecord } from '../config';
import { readSave } from '../util';

/**
 * 菜单场景：关卡选择 + 进度。首屏到可玩必须 <3 秒。
 *
 * 关卡解锁规则：第 1 关总是可玩；之后每关需要「上一关已通关」（stars > 0）。
 * 解锁状态不单独存字段，由 levels 推导 —— 少一个字段就少一处不一致。
 */
export class MenuScene extends Phaser.Scene {
  constructor() {
    super('Menu');
  }

  async create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);

    const save = await readSave(this);
    // 存到 registry：PlayScene 的引导提示要读 tutorialDone
    this.registry.set('save', save);

    const levels = (save.levels as Record<string, LevelRecord>) ?? {};
    const totalStars = Object.values(levels).reduce((a, r) => a + (r.stars ?? 0), 0);
    const maxStars = LEVELS.length * 3;

    this.add
      .text(W / 2, H * 0.16, '塔 防', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '64px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);
    this.add
      .text(W / 2, H * 0.24, '守住基地，一只也别放过', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    this.add
      .text(W / 2, H * 0.31, `★ ${totalStars} / ${maxStars}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '30px',
        color: totalStars > 0 ? '#f0c674' : COLORS.textDim,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    // ---- 关卡按钮
    LEVELS.forEach((lv, i) => {
      const cleared = (levels[String(lv.id)]?.stars ?? 0) > 0;
      const unlocked = i === 0 || (levels[String(LEVELS[i - 1].id)]?.stars ?? 0) > 0;
      const y = H * 0.44 + i * 116;
      const stars = levels[String(lv.id)]?.stars ?? 0;

      const bg = this.add
        .rectangle(W / 2, y, 480, 96, unlocked ? COLORS.panel : 0x141821)
        .setStrokeStyle(2, unlocked ? COLORS.panelEdge : 0x222834);
      this.add
        .text(W / 2, y - 14, unlocked ? lv.name : '未解锁', {
          fontFamily: 'system-ui, sans-serif',
          fontSize: '26px',
          color: unlocked ? COLORS.text : '#4a5364',
          fontStyle: 'bold',
        })
        .setOrigin(0.5);
      this.add
        .text(
          W / 2,
          y + 22,
          unlocked ? '★'.repeat(stars) + '☆'.repeat(3 - stars) : '先通关上一关',
          {
            fontFamily: 'system-ui, sans-serif',
            fontSize: '20px',
            color: stars > 0 ? '#f0c674' : unlocked ? COLORS.textDim : '#3a4250',
          },
        )
        .setOrigin(0.5);

      if (unlocked) {
        bg.setInteractive({ useHandCursor: true });
        bg.on('pointerdown', () => this.scene.start('Play', { level: i }));
      }
    });

    this.add
      .text(W / 2, H - 80, '点关卡开始 · 空格进第一关', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '18px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);

    // 桌面端键盘 + 测试脚本入口：直接进第一个已解锁但未通关的关
    const firstOpen = LEVELS.findIndex((lv) => (levels[String(lv.id)]?.stars ?? 0) === 0);
    const startLevel = firstOpen >= 0 ? firstOpen : 0;
    const start = () => this.scene.start('Play', { level: startLevel });
    this.input.keyboard?.once('keydown-SPACE', start);
    this.input.keyboard?.once('keydown-ENTER', start);
  }
}

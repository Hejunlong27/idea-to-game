import Phaser from 'phaser';
import { COLORS, LAYOUT, LEVELS, type LevelRecord } from '../config';
import { bridge, readSave, writeSave } from '../util';

/**
 * 结束场景：展示星级与成绩、写存档、下一关或重开。
 *
 * 存档结构（SaveData 的扩展字段）：
 *   best        历史最高分
 *   levels      { "<levelId>": { stars, best } }  每关最好成绩
 *   tutorialDone 是否已完成新手引导
 *
 * 星级只升不降（Math.max），避免「这局打得差反而把记录刷低」。
 * 关卡流程：胜利且还有下一关 → 「下一关」；失败重开本关，不跳关。
 */
export class GameOverScene extends Phaser.Scene {
  private score = 0;
  private stars = 0;
  private win = false;
  /** -1 表示没有下一关 */
  private nextLevel = -1;
  private level = 0;
  private levelId = 1;
  private busy = false;

  constructor() {
    super('GameOver');
  }

  init(data: {
    score?: number;
    stars?: number;
    win?: boolean;
    nextLevel?: number;
    level?: number;
    levelId?: number;
  }) {
    this.score = data?.score ?? 0;
    this.stars = data?.stars ?? 0;
    this.win = data?.win ?? false;
    this.nextLevel = data?.nextLevel ?? -1;
    this.level = data?.level ?? 0;
    this.levelId = data?.levelId ?? this.level + 1;
  }

  async create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);
    this.busy = false;

    const save = await readSave(this);
    const levels = { ...((save.levels as Record<string, LevelRecord>) ?? {}) };
    const key = String(this.levelId);
    const prev = levels[key] ?? { stars: 0, best: 0 };
    const merged: LevelRecord = {
      stars: Math.max(prev.stars, this.stars),
      best: Math.max(prev.best, this.score),
    };
    levels[key] = merged;

    const totalStars = Object.values(levels).reduce((a, r) => a + (r.stars ?? 0), 0);
    const nextSave = {
      ...save,
      version: 1,
      best: Math.max(Number(save.best ?? 0), this.score),
      levels,
      totalStars,
      plays: Number(save.plays ?? 0) + 1,
    };
    await writeSave(this, nextSave);
    this.registry.set('save', nextSave);

    // ---- 标题
    this.add
      .text(W / 2, H * 0.2, this.win ? '通关' : '失守', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '62px',
        color: this.win ? '#46d17f' : '#ff8f8f',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    // ---- 星级（只有通关才有星）
    const starText = '★'.repeat(merged.stars) + '☆'.repeat(3 - merged.stars);
    this.add
      .text(W / 2, H * 0.3, starText, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '52px',
        color: merged.stars > 0 ? '#f0c674' : '#3a4250',
        fontStyle: 'bold',
      })
      .setOrigin(0.5);

    // ---- 本局 / 记录
    this.add
      .text(W / 2, H * 0.4, `本局 ${this.score}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '34px',
        color: COLORS.text,
      })
      .setOrigin(0.5);
    this.add
      .text(W / 2, H * 0.46, `本关最佳 ${merged.best}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '24px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5);
    this.add
      .text(W / 2, H * 0.51, `累计 ${totalStars} / ${LEVELS.length * 3} 星`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: '#f0c674',
      })
      .setOrigin(0.5);

    // ---- 按钮
    const hasNext = this.nextLevel >= 0;
    const label = hasNext ? '下一关' : this.win ? '再玩一次' : '重试本关';
    const target = hasNext ? this.nextLevel : this.level;

    const btn = this.add
      .rectangle(W / 2, H * 0.66, 420, 110, hasNext ? COLORS.good : COLORS.accent, 1)
      .setStrokeStyle(3, 0xffffff, 0.25)
      .setInteractive({ useHandCursor: true });
    const btnText = this.add
      .text(W / 2, H * 0.66, label, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '38px',
        color: '#0b1020',
        fontStyle: 'bold',
      })
      .setOrigin(0.5)
      .setInteractive({ useHandCursor: true });

    const go = () => this.go(target);
    btn.on('pointerdown', go);
    btnText.on('pointerdown', go);
    // 桌面端键盘 + 测试脚本入口
    this.input.keyboard?.once('keydown-SPACE', go);
    this.input.keyboard?.once('keydown-ENTER', go);

    // ---- 回菜单（玩家想换关或退出时不用等广告）
    const menu = this.add
      .text(W / 2, H * 0.78, '返回菜单', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5)
      .setInteractive({ useHandCursor: true });
    menu.on('pointerdown', () => this.scene.start('Menu'));
  }

  /** 每两局插一次插屏广告；广告失败或拦截器场景下直接继续。 */
  private async go(level: number) {
    if (this.busy) return;
    this.busy = true;

    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    const plays = Number(save.plays ?? 0);
    if (plays > 0 && plays % 2 === 0) {
      try {
        await bridge(this).showMidroll();
      } catch {
        /* 静默降级 */
      }
    }
    this.scene.start('Play', { level });
  }
}

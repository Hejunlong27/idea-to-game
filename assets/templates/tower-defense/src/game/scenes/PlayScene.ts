import Phaser from 'phaser';
import {
  COLORS,
  ENEMY_TYPES,
  GRID,
  LAYOUT,
  LEVELS,
  SELL_REFUND,
  STARS,
  TD,
  TOWER_TYPES,
  UPGRADE,
  type EnemyType,
  type LevelDef,
  type TowerType,
} from '../config';
import { TEXTURES } from '../art';
import { EventBus, GAME_EVENTS } from '../events';
import { AudioDirector } from '../audio';
import { JuiceDirector } from '../juice';
import { bridge, writeSave } from '../util';
import { detachTestApi, installTestApi, type TestAction, type TestAdapter } from '../test-api';
import { buildPathCells, cellAt, cellCenter, isBuildable, pathDirAt, pathPointAt, totalPathDist } from '../td';
import { Telemetry } from '../telemetry';
import { Fx } from '../fx';

const SKILL_CHARGE_MAX = 100;
const SKILL_CHARGE_PER_KILL = 20;
const LIGHTNING_DAMAGE = 30;
const LIGHTNING_RADIUS = 1.25;
const FROST_DURATION_MS = 2000;
const FROST_FACTOR = 0.35;

interface Enemy {
  id: number;
  typeId: string;
  hp: number;
  maxHp: number;
  /** 已走格数（玩法量纲，不是像素） */
  dist: number;
  /** 减速到期时间与倍率 */
  slowUntil: number;
  slowFactor: number;
  spr: Phaser.GameObjects.Image;
  bar: Phaser.GameObjects.Rectangle;
  barBg: Phaser.GameObjects.Rectangle;
}

interface Tower {
  id: number;
  typeId: string;
  level: number;
  c: number;
  r: number;
  /** 攻击冷却剩余毫秒 */
  cd: number;
  cx: number;
  cy: number;
  spr: Phaser.GameObjects.Image;
  lvText: Phaser.GameObjects.Text;
}

interface ShotFx {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  bornAt: number;
  color: number;
}

/**
 * 塔防主玩法。
 *
 * 核心循环：
 *   攒钱 → 选塔型 → 在可建造格放塔 → 敌人沿固定路径推进 → 塔自动攻击射程内走得最远的敌人
 *   → 击杀得金币 → 漏怪扣生命 → 清空所有波次即胜利，生命归零即失败。
 *
 * 三种塔的分工（见 config.ts 的注释）：箭塔铺量、炮塔清群、冰塔拖时间。
 * 三种敌人逼玩家搭配：甲兽有 4 点护甲，箭塔单发 8 只造成 4 点，必须上炮塔或堆等级。
 *
 * 分层约定：
 *   网格 / 路径 / 坐标换算 → `td.ts`（纯函数，参数化，无全局关卡）
 *   数值与关卡           → `config.ts`
 *   本文件                → 渲染、输入、事件、调度
 */
export class PlayScene extends Phaser.Scene {
  // ---- 关卡
  private levelIdx = 0;
  private level!: LevelDef;
  private pathCells = new Set<string>();
  private pathTotal = 0;
  private base: [number, number] = [0, 0];

  // ---- 资源
  private gold = 0;
  private lives = 0;
  private kills = 0;

  // ---- 波次
  private waveIndex = 0;
  /** 本波展开后的敌人类型序列（只展开一次，用游标推进） */
  private queue: string[] = [];
  /** 本波已生成到第几个（游标）。不能靠 queue.shift 判断本波是否结束 ——
   *  queue 空了会被当成「还没展开」而重新填满，导致同一波无限重复。 */
  private waveSpawned = 0;
  private spawnTimer = 0;
  private waveGapTimer = 0;

  // ---- 实体
  private enemies: Enemy[] = [];
  private towers: Tower[] = [];
  private nextEnemyId = 1;
  private nextTowerId = 1;

  // ---- 交互
  private buildTypeId = TOWER_TYPES[0].id;
  private selected: Tower | null = null;

  /**
   * 数值倍率（平衡搜索用）。默认 1，通过 window.__VARIANT 覆盖。
   *
   * 为什么不直接改变量：TOWER_TYPES / ENEMY_TYPES 是模块常量，
   * 改了会污染同页面的后续运行。倍率是实例级的，restart 就复原。
   */
  private towerCostMul = 1;
  private enemyHpMul = 1;

  private ended = false;
  private won = false;
  /** 新手引导提示（只在第一次玩时出现，建完第一座塔就消失） */
  private tutorialHint: Phaser.GameObjects.Text | null = null;
  /** 测试专用：暂停自动刷怪 */
  private wavesPaused = false;

  // ---- UI
  private hudGold!: Phaser.GameObjects.Text;
  private hudLives!: Phaser.GameObjects.Text;
  private hudWave!: Phaser.GameObjects.Text;
  private hudHint!: Phaser.GameObjects.Text;
  private skillChargeText!: Phaser.GameObjects.Text;
  private skillChargeBar!: Phaser.GameObjects.Rectangle;
  private lightningButton!: Phaser.GameObjects.Rectangle;
  private lightningLabel!: Phaser.GameObjects.Text;
  private frostButton!: Phaser.GameObjects.Rectangle;
  private frostLabel!: Phaser.GameObjects.Text;
  private skillCharge = 0;
  private skillTargeting = false;
  private skillCasts = 0;
  private bottom!: Phaser.GameObjects.Container;
  private lastHud = '';

  /** 飘字偏移用的确定性伪随机种子（不用 Math.random，保证截图可复现） */
  private nextFloatSeed = 7;
  /** 每个敌人最近一次伤害飘字，用于短时间内的累加合并 */
  private floatAccum = new Map<number, { total: number; at: number; text: Phaser.GameObjects.Text }>();
  private fxG!: Phaser.GameObjects.Graphics;
  private shots: ShotFx[] = [];

  /** 真人试玩遥测（?playtest=1 才生效） */
  private telemetry!: Telemetry;
  /** 程序化特效（爽感的核心） */
  private fx!: Fx;
  /** 连杀计数：1.5 秒内连续击杀累加 */
  private comboCount = 0;
  private lastKillAt = -9999;
  /** 是否已建过第一座塔（用于记录「进关到首次建塔」的延迟） */
  private builtOnce = false;
  /** 上一次的波次索引，用于检测「第 N 波清完」 */
  private lastWaveIndex = 0;
  private floatingTexts: Phaser.GameObjects.Text[] = [];

  private bus!: EventBus;
  private audio!: AudioDirector;
  private juice!: JuiceDirector;

  constructor() {
    super('Play');
  }

  init(data: { level?: number }) {
    this.levelIdx = Math.max(0, Math.min(LEVELS.length - 1, data?.level ?? 0));
  }

  create() {
    // 变体覆盖：原型对比时由 compare.mjs 通过 window.__VARIANT 注入
    // 只覆盖「关卡级」参数（波次/起始资源/首波延迟），不改全局数值表
    const base = LEVELS[this.levelIdx];
    this.level = { ...base };
    const ov = (window as unknown as { __VARIANT?: Record<string, unknown> }).__VARIANT;
    if (ov) {
      if (Array.isArray(ov.waves)) this.level.waves = ov.waves as typeof base.waves;
      if (typeof ov.startGold === 'number') this.level.startGold = ov.startGold;
      if (typeof ov.startLives === 'number') this.level.startLives = ov.startLives;
      if (typeof ov.firstWaveDelayMs === 'number') this.level.firstWaveDelayMs = ov.firstWaveDelayMs;
      if (typeof ov.towerCostMul === 'number') this.towerCostMul = ov.towerCostMul;
      if (typeof ov.enemyHpMul === 'number') this.enemyHpMul = ov.enemyHpMul;
    }

    this.base = this.level.path[this.level.path.length - 1];
    this.pathCells = buildPathCells(this.level.path);
    this.pathTotal = totalPathDist(this.level.path);

    this.cameras.main.setBackgroundColor(COLORS.bg);

    this.bus = new EventBus(() => this.time.now, this.time.now);
    this.audio = new AudioDirector(this, this.bus);
    this.juice = new JuiceDirector(this, this.bus);
    this.registry.set('audio', this.audio);
    this.audio.start('exploration');
    this.juice.attach();

    // 重置状态（场景会被 restart）
    this.gold = this.level.startGold;
    this.lives = this.level.startLives;
    this.kills = 0;
    this.waveIndex = 0;
    this.queue = [];
    this.waveSpawned = 0;
    this.spawnTimer = this.level.firstWaveDelayMs;
    this.waveGapTimer = TD.waveGapMs;
    this.enemies = [];
    this.towers = [];
    this.shots = [];
    this.nextEnemyId = 1;
    this.nextTowerId = 1;
    this.buildTypeId = TOWER_TYPES[0].id;
    this.selected = null;
    this.ended = false;
    this.won = false;
    this.wavesPaused = false;
    this.lastHud = '';

    this.fx = new Fx(this);
    this.comboCount = 0;
    this.lastKillAt = -9999;
    this.skillCharge = 0;
    this.skillTargeting = false;
    this.skillCasts = 0;
    this.telemetry = new Telemetry('tower-defense');
    this.builtOnce = false;
    this.lastWaveIndex = 0;

    this.buildBoard();
    this.buildEntry();
    this.buildBase();
    this.buildHud();
    this.bindInput();

    this.fxG = this.add.graphics().setDepth(18);

    this.exposeDebugHooks();
    this.installTestHooks();
    this.maybeShowTutorial();
    this.telemetry.start();

    this.bus.emit(GAME_EVENTS.GAME_START, { intensity: 0.5 });
    this.bus.emit(GAME_EVENTS.LEVEL_STARTED, {
      intensity: 0.45,
      context: { level: this.levelIdx + 1, name: this.level.name },
    });

    try {
      bridge(this).gameplayStart();
    } catch {
      /* 静默降级 */
    }

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.cleanup());
  }

  // ---------------------------------------------------------------- 建场
  private buildBoard() {
    for (let r = 0; r < GRID.rows; r++) {
      for (let c = 0; c < GRID.cols; c++) {
        const { x, y } = cellCenter(c, r);
        const isRoad = this.pathCells.has(`${c},${r}`);
        const key = isRoad
          ? TEXTURES.road
          : (c + r) % 2 === 0
            ? TEXTURES.ground
            : TEXTURES.groundAlt;
        this.add.image(x, y, key).setDepth(0);
      }
    }
  }

  /** 入侵口标记：不标的话玩家不知道敌人从哪来，第一波必被偷家 */
  private buildEntry() {
    const [c0, r0] = this.level.path[0];
    const { x, y } = cellCenter(c0, r0);
    const g = this.add.graphics().setDepth(3);
    g.fillStyle(COLORS.bad, 0.9);
    g.fillTriangle(
      x - 12,
      y - GRID.cell * 0.66,
      x + 12,
      y - GRID.cell * 0.66,
      x,
      y - GRID.cell * 0.44,
    );
    this.add
      .text(x, y - GRID.cell * 0.86, '入侵', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '15px',
        color: '#ff8f8f',
      })
      .setOrigin(0.5)
      .setDepth(3);
  }

  private buildBase() {
    const { x, y } = cellCenter(this.base[0], this.base[1]);
    this.add.image(x, y, TEXTURES.base).setDepth(2);
  }

  private buildHud() {
    const { width: W } = LAYOUT;
    this.add
      .text(W / 2, 40, this.level.name, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '24px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5, 0)
      .setDepth(20);

    this.hudGold = this.add
      .text(28, 96, '', { fontFamily: 'system-ui, sans-serif', fontSize: '23px', color: COLORS.text })
      .setDepth(20);

    this.hudLives = this.add
      .text(W / 2, 96, '', { fontFamily: 'system-ui, sans-serif', fontSize: '23px', color: COLORS.text })
      .setOrigin(0.5, 0)
      .setDepth(20);

    this.hudWave = this.add
      .text(W - 28, 96, '', { fontFamily: 'system-ui, sans-serif', fontSize: '23px', color: COLORS.text })
      .setOrigin(1, 0)
      .setDepth(20);

    this.hudHint = this.add
      .text(W / 2, 150, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '17px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5, 0)
      .setDepth(20);

    this.bottom = this.add.container(0, 0).setDepth(25);
    this.renderBottom();
    this.buildTacticalSkills();
    this.refreshHud();
  }

  private buildTacticalSkills() {
    const { width: W } = LAYOUT;
    const y = 1204;
    const buttonW = 280;
    const buttonH = 60;

    this.skillChargeText = this.add
      .text(W / 2, 1132, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '15px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5)
      .setDepth(28);

    this.add.rectangle(W / 2, 1154, 420, 8, COLORS.panelEdge).setDepth(28);
    this.skillChargeBar = this.add
      .rectangle(W / 2 - 210, 1154, 1, 8, COLORS.good)
      .setOrigin(0, 0.5)
      .setDepth(29);

    this.lightningButton = this.add
      .rectangle(190, y, buttonW, buttonH, COLORS.panel)
      .setStrokeStyle(2, COLORS.panelEdge)
      .setInteractive({ useHandCursor: true })
      .setDepth(28);
    this.lightningLabel = this.add
      .text(190, y, '雷击\n选点伤害', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '16px',
        color: COLORS.textDim,
        fontStyle: 'bold',
        align: 'center',
      })
      .setOrigin(0.5)
      .setDepth(29);
    this.lightningButton.on('pointerdown', () => this.beginLightningTargeting());

    this.frostButton = this.add
      .rectangle(W - 190, y, buttonW, buttonH, COLORS.panel)
      .setStrokeStyle(2, COLORS.panelEdge)
      .setInteractive({ useHandCursor: true })
      .setDepth(28);
    this.frostLabel = this.add
      .text(W - 190, y, '寒潮\n全场减速 2 秒', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '16px',
        color: COLORS.textDim,
        fontStyle: 'bold',
        align: 'center',
      })
      .setOrigin(0.5)
      .setDepth(29);
    this.frostButton.on('pointerdown', () => this.castFrost());
    this.refreshSkillHud();
  }

  private refreshSkillHud() {
    if (!this.skillChargeText || !this.skillChargeBar) return;
    const ready = this.skillCharge >= SKILL_CHARGE_MAX;
    this.skillChargeText.setText(`灵能 ${this.skillCharge}/${SKILL_CHARGE_MAX} · 击杀蓄能`);
    this.skillChargeBar.setSize(Math.max(1, 420 * this.skillCharge / SKILL_CHARGE_MAX), 8);
    this.skillChargeBar.setFillStyle(ready ? COLORS.good : COLORS.accent);
    this.lightningButton?.setFillStyle(this.skillTargeting ? 0x26364b : ready ? 0x24384f : COLORS.panel);
    this.lightningButton?.setStrokeStyle(2, this.skillTargeting ? COLORS.accent : ready ? COLORS.accent : COLORS.panelEdge);
    this.lightningLabel?.setText(this.skillTargeting ? '选择道路格\n点选敌群释放' : '雷击\n点选范围造成伤害');
    this.lightningLabel?.setColor(ready ? COLORS.text : COLORS.textDim);
    this.frostButton?.setFillStyle(ready ? 0x24384f : COLORS.panel);
    this.frostButton?.setStrokeStyle(2, ready ? COLORS.accent : COLORS.panelEdge);
    this.frostLabel?.setColor(ready ? COLORS.text : COLORS.textDim);
  }

  private beginLightningTargeting() {
    if (this.skillCharge < SKILL_CHARGE_MAX) {
      this.flashHint('击杀敌人蓄积灵能');
      return;
    }
    this.skillTargeting = !this.skillTargeting;
    this.hudHint.setText(this.skillTargeting ? '选择道路格上的敌群释放雷击 · Esc 取消' : '');
    this.refreshSkillHud();
  }

  private castLightning(c: number, r: number) {
    if (!this.skillTargeting || !this.pathCells.has(`${c},${r}`)) return false;
    const point = cellCenter(c, r);
    const radius = GRID.cell * LIGHTNING_RADIUS;
    const targets = this.enemies.filter((e) => Math.hypot(e.spr.x - point.x, e.spr.y - point.y) <= radius);
    if (targets.length === 0) {
      this.hudHint.setText('范围内没有敌人，再选一个道路格');
      return false;
    }

    this.skillTargeting = false;
    this.skillCharge -= SKILL_CHARGE_MAX;
    this.skillCasts += 1;
    this.hudHint.setText('');
    this.fx.burst(point.x, point.y, 0x9b6bd6, 14);
    this.cameras.main.shake(100, 0.0035);
    this.audio.play('gameplay_cast', { priority: 'high' });
    this.telemetry.record('ability_cast', { ability: 'lightning', c, r, targets: targets.length });
    for (const enemy of targets) this.hitEnemy(enemy, LIGHTNING_DAMAGE, false);
    this.refreshSkillHud();
    this.refreshHud();
    return true;
  }

  private castFrost() {
    if (this.skillCharge < SKILL_CHARGE_MAX) {
      this.flashHint('击杀敌人蓄积灵能');
      return;
    }
    if (this.enemies.length === 0) {
      this.flashHint('场上没有敌人，保留灵能');
      return;
    }

    this.skillCharge -= SKILL_CHARGE_MAX;
    this.skillCasts += 1;
    for (const enemy of this.enemies) {
      this.applySlow(enemy, FROST_FACTOR, FROST_DURATION_MS);
      this.fx.spark(enemy.spr.x, enemy.spr.y, 0x8fd6e8);
    }
    this.audio.play('gameplay_cast', { priority: 'high' });
    this.telemetry.record('ability_cast', { ability: 'frost', targets: this.enemies.length });
    this.flashHint('寒潮生效：所有敌人减速 2 秒');
    this.refreshSkillHud();
    this.refreshHud();
  }

  private cancelSkillTargeting() {
    if (!this.skillTargeting) return;
    this.skillTargeting = false;
    this.hudHint.setText('');
    this.refreshSkillHud();
  }

  /** 底部栏：建造模式显示三种塔，选中塔时显示升级/出售 */
  private renderBottom() {
    this.bottom.removeAll(true);
    const W = LAYOUT.width;
    const y = 1016;

    if (this.selected) {
      const t = this.selected;
      const type = this.typeOf(t.typeId);
      const upCost = this.upgradeCost(t);
      const sellGold = Math.round(this.investedIn(t) * SELL_REFUND);
      const maxed = t.level >= UPGRADE.maxLevel;

      this.bottom.add(
        this.add
          .rectangle(24, y, W - 48, 104, COLORS.panel)
          .setOrigin(0, 0)
          .setStrokeStyle(2, COLORS.panelEdge),
      );
      this.bottom.add(
        this.txt(44, y + 12, `${type.name} Lv.${t.level}`, 20, COLORS.text, true),
      );
      this.bottom.add(
        this.txt(44, y + 44, `伤害 ${this.damageOf(t)}　射程 ${this.rangeOf(t).toFixed(1)}`, 15, COLORS.textDim),
      );

      this.bottom.add(
        this.bottomButton(
          W / 2 - 8,
          y + 22,
          176,
          60,
          maxed ? '已满级' : `升级 ${upCost}`,
          maxed || this.gold < upCost,
          () => this.upgradeTower(t),
        ),
      );
      this.bottom.add(
        this.bottomButton(
          W - 40,
          y + 22,
          150,
          60,
          `出售 +${sellGold}`,
          false,
          () => this.sellTower(t),
          true,
        ),
      );
      return;
    }

    const bw = (W - 48 - 2 * 12) / 3;
    TOWER_TYPES.forEach((tp, i) => {
      const bx = 24 + i * (bw + 12);
      const active = tp.id === this.buildTypeId;
      const afford = this.gold >= tp.cost;
      const bg = this.add
        .rectangle(bx, y, bw, 104, active ? 0x24384f : COLORS.panel)
        .setOrigin(0, 0)
        .setStrokeStyle(2, active ? COLORS.accent : COLORS.panelEdge)
        .setInteractive({ useHandCursor: true });
      bg.on('pointerdown', () => {
        this.buildTypeId = tp.id;
        this.selected = null;
        this.renderBottom();
      });
      this.bottom.add(bg);
      this.bottom.add(
        this.add.rectangle(bx + 22, y + 30, 18, 18, tp.color).setOrigin(0, 0).setDepth(26),
      );
      this.bottom.add(this.txt(bx + 50, y + 20, tp.name, 19, COLORS.text, true));
      this.bottom.add(
        this.txt(bx + 50, y + 50, `${tp.cost} 金`, 15, afford ? COLORS.gold : COLORS.bad),
      );
      this.bottom.add(this.txt(bx + 14, y + 74, tp.desc, 12, COLORS.textDim));
    });
  }

  private bottomButton(
    rightX: number,
    y: number,
    w: number,
    h: number,
    label: string,
    disabled: boolean,
    onTap: () => void,
    danger = false,
  ) {
    const bg = this.add
      .rectangle(rightX - w, y, w, h, danger ? 0x3a2020 : 0x22303f)
      .setOrigin(0, 0)
      .setStrokeStyle(2, danger ? 0x7a3a3a : COLORS.panelEdge);
    if (!disabled) {
      bg.setInteractive({ useHandCursor: true });
      bg.on('pointerdown', onTap);
    }
    this.bottom.add(bg);
    this.bottom.add(
      this.txt(rightX - w / 2, y + h / 2 - 11, label, 16, disabled ? '#5b6f66' : COLORS.text, true, 0.5),
    );
    return bg;
  }

  /** 颜色既可能是 '#rrggbb' 字符串，也可能是 0xrrggbb 数值 —— 统一转成字符串 */
  private static hex(color: string | number): string {
    return typeof color === 'number' ? `#${color.toString(16).padStart(6, '0')}` : color;
  }

  private txt(
    x: number,
    y: number,
    text: string,
    size: number,
    color: string | number,
    bold = false,
    originX = 0,
  ): Phaser.GameObjects.Text {
    return this.add
      .text(x, y, text, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: `${size}px`,
        color: PlayScene.hex(color),
        fontStyle: bold ? 'bold' : 'normal',
      })
      .setOrigin(originX, 0);
  }

  private bindInput() {
    // FIT 缩放下 pointer.x 不等于设计坐标，必须手动换算
    this.input.on('pointerdown', (p: Phaser.Input.Pointer) => {
      const ev = p.event as MouseEvent | undefined;
      if (!ev) return;
      const rect = this.game.canvas.getBoundingClientRect();
      const gx = (ev.clientX - rect.left) * (LAYOUT.width / rect.width);
      const gy = (ev.clientY - rect.top) * (LAYOUT.height / rect.height);
      const cell = cellAt(gx, gy);
      this.telemetry.record('click', {
        x: Math.round(gx), y: Math.round(gy),
        cell: cell ? `${cell.c},${cell.r}` : null,
        gold: this.gold,
        wave: this.waveIndex + 1,
      });
      if (this.skillTargeting) {
        if (cell && this.pathCells.has(`${cell.c},${cell.r}`)) {
          this.castLightning(cell.c, cell.r);
        } else if (cell) {
          this.hudHint.setText('雷击只能指定道路格');
        }
        return;
      }
      if (!cell) return;

      const hit = this.towers.find((t) => t.c === cell.c && t.r === cell.r);
      if (hit) {
        this.selected = hit;
        this.renderBottom();
        return;
      }
      this.selected = null;
      this.renderBottom();
      this.buildTower(cell.c, cell.r, this.buildTypeId);
    });
    this.input.keyboard?.on('keydown-Q', () => this.beginLightningTargeting());
    this.input.keyboard?.on('keydown-E', () => this.castFrost());
    this.input.keyboard?.on('keydown-ESC', () => this.cancelSkillTargeting());
  }

  // ---------------------------------------------------------------- 塔
  private typeOf(id: string): TowerType {
    return TOWER_TYPES.find((t) => t.id === id) ?? TOWER_TYPES[0];
  }

  private damageOf(t: Tower): number {
    return Math.round(this.typeOf(t.typeId).damage * Math.pow(UPGRADE.damageMul, t.level - 1));
  }

  private rangeOf(t: Tower): number {
    return this.typeOf(t.typeId).range + UPGRADE.rangeAdd * (t.level - 1);
  }

  private upgradeCost(t: Tower): number {
    return Math.round(this.typeOf(t.typeId).cost * UPGRADE.costMul * t.level);
  }

  /** 累计投入（建造 + 所有升级），用于计算出售返还 */
  private investedIn(t: Tower): number {
    const base = this.typeOf(t.typeId).cost;
    let total = base;
    for (let lv = 1; lv < t.level; lv++) total += Math.round(base * UPGRADE.costMul * lv);
    return total;
  }

  private buildTower(c: number, r: number, typeId: string): boolean {
    if (this.ended) return false;
    const type = this.typeOf(typeId);
    if (!isBuildable(this.pathCells, this.base, c, r)) {
      this.flashHint('这里不能建塔');
      return false;
    }
    if (this.towers.some((t) => t.c === c && t.r === r)) return false;
    const cost = Math.round(type.cost * this.towerCostMul);
    if (this.gold < cost) {
      this.flashHint('金币不够');
      return false;
    }

    this.gold -= cost;
    const { x, y } = cellCenter(c, r);
    const spr = this.add.image(x, y, TEXTURES.tower).setDepth(5).setTint(type.color);
    spr.setScale(0.4);
    this.tweens.add({ targets: spr, scale: 1, duration: 160, ease: 'Back.easeOut' });

    const lvText = this.add
      .text(x + GRID.cell * 0.3, y + GRID.cell * 0.22, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '14px',
        color: '#ffffff',
        fontStyle: 'bold',
      })
      .setOrigin(0.5)
      .setDepth(9);

    const t: Tower = {
      id: this.nextTowerId++,
      typeId,
      level: 1,
      c,
      r,
      cd: 0,
      cx: x,
      cy: y,
      spr,
      lvText,
    };
    this.towers.push(t);

    this.telemetry.record('build', { c, r, typeId, cost, gold: this.gold, wave: this.waveIndex + 1 });
    if (!this.builtOnce) {
      this.builtOnce = true;
      // 进关到第一座塔的延迟：引导有没有用的最直接指标
      this.telemetry.record('first_build', { c, r, typeId });
    }
    this.markTutorialDone();
    this.audio.play('gameplay_cast', { priority: 'normal' });
    this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
      intensity: 0.4,
      context: { build: true, c, r, typeId, gold: this.gold, x, y },
    });
    this.refreshHud();
    return true;
  }

  private upgradeTower(t: Tower): void {
    if (this.ended) return;
    if (t.level >= UPGRADE.maxLevel) {
      this.flashHint('已满级');
      return;
    }
    const cost = this.upgradeCost(t);
    if (this.gold < cost) {
      this.flashHint('金币不够升级');
      return;
    }
    this.gold -= cost;
    t.level += 1;
    t.spr.setScale(1.14);
    this.tweens.add({ targets: t.spr, scale: 1, duration: 180, ease: 'Back.easeOut' });
    this.fx.upgrade(t.cx, t.cy, this.typeOf(t.typeId).color);
    this.telemetry.record('upgrade', { c: t.c, r: t.r, level: t.level, cost, gold: this.gold });
    this.audio.play('feedback_levelup', { priority: 'high' });
    this.floatText(t.cx, t.cy - 26, `Lv.${t.level}`, '#7fe3a8');
    this.bus.emit(GAME_EVENTS.ITEM_COLLECTED, {
      intensity: 0.5,
      context: { upgrade: true, level: t.level, x: t.cx, y: t.cy },
    });
    this.refreshHud();
    this.renderBottom();
  }

  private sellTower(t: Tower): void {
    if (this.ended) return;
    const refund = Math.round(this.investedIn(t) * SELL_REFUND);
    this.gold += refund;
    this.towers = this.towers.filter((x) => x !== t);
    t.spr.destroy();
    t.lvText.destroy();
    this.telemetry.record('sell', { c: t.c, r: t.r, refund, gold: this.gold });
    this.selected = null;
    this.floatText(t.cx, t.cy - 20, `+${refund}`, '#f0c674');
    this.audio.play('gameplay_block', { priority: 'low' });
    this.refreshHud();
    this.renderBottom();
  }

  // ---------------------------------------------------------------- 敌人
  private spawnEnemy(typeId: string): Enemy | null {
    if (this.ended) return null;
    const type: EnemyType = ENEMY_TYPES[typeId] ?? ENEMY_TYPES.grunt;
    const p = pathPointAt(this.level.path, 0);
    const scale = type.radius / 24;
    const spr = this.add.image(p.x, p.y, TEXTURES.enemy).setDepth(6).setTint(type.color).setScale(scale);
    const barBg = this.add.rectangle(p.x, p.y - 30, 40, 5, 0x000000, 0.55).setDepth(7);
    const bar = this.add.rectangle(p.x, p.y - 30, 40, 5, COLORS.bad, 1).setDepth(8);

    const hp = Math.round(type.hp * this.enemyHpMul);
    const e: Enemy = {
      id: this.nextEnemyId++,
      typeId: type.id,
      hp,
      maxHp: hp,
      dist: 0,
      slowUntil: 0,
      slowFactor: 1,
      spr,
      bar,
      barBg,
    };
    this.enemies.push(e);
    this.bus.emit(GAME_EVENTS.ENEMY_SPAWN, {
      intensity: 0.3,
      context: { id: e.id, typeId: type.id, hp: e.hp, x: p.x, y: p.y },
    }, 80);
    return e;
  }

  /** 伤害结算：护甲先减，最低仍造成 1 点（否则高护甲会让塔完全无效） */
  private hitEnemy(e: Enemy, raw: number, grantSkillCharge = true): void {
    const type = ENEMY_TYPES[e.typeId] ?? ENEMY_TYPES.grunt;
    const dmg = Math.max(1, Math.round(raw) - type.armor);
    e.hp -= dmg;
    this.floatDamage(e, dmg);
    if (e.hp <= 0) this.killEnemy(e, grantSkillCharge);
  }

  /**
   * 伤害飘字，同一敌人短时间内**累加合并**。
   *
   * 不合并的话，炮塔溅射 + 多塔同时开火会在同一位置刷出一堆数字叠在一起，
   * 玩家完全读不出来（截图里就是「10 10 10 4 4」糊成一团）。
   */
  private floatDamage(e: Enemy, dmg: number): void {
    const now = this.time.now;
    const rec = this.floatAccum.get(e.id);
    if (rec && now - rec.at < 360 && rec.text.active) {
      rec.total += dmg;
      rec.at = now;
      rec.text.setText(`${rec.total}`);
      return;
    }
    let record: { total: number; at: number; text: Phaser.GameObjects.Text } | null = null;
    const text = this.floatText(e.spr.x, e.spr.y - 26, `${dmg}`, '#ffffff', 420, () => {
      if (record && this.floatAccum.get(e.id) === record) this.floatAccum.delete(e.id);
    });
    if (text) {
      record = { total: dmg, at: now, text };
      this.floatAccum.set(e.id, record);
    }
  }

  private killEnemy(e: Enemy, grantSkillCharge = true): void {
    const i = this.enemies.indexOf(e);
    if (i < 0) return;
    this.enemies.splice(i, 1);
    this.kills += 1;
    const reward = (ENEMY_TYPES[e.typeId] ?? ENEMY_TYPES.grunt).reward;
    this.gold += reward;
    if (grantSkillCharge) {
      const wasReady = this.skillCharge >= SKILL_CHARGE_MAX;
      this.skillCharge = Math.min(SKILL_CHARGE_MAX, this.skillCharge + SKILL_CHARGE_PER_KILL);
      this.refreshSkillHud();
      if (!wasReady && this.skillCharge >= SKILL_CHARGE_MAX) {
        this.flashHint('灵能已满：可使用雷击或寒潮');
      }
    }

    // 击杀反馈四连：爆裂 + 震屏 + 连杀 + 金币飞行
    const type = ENEMY_TYPES[e.typeId] ?? ENEMY_TYPES.grunt;
    const kx = e.spr.x;
    const ky = e.spr.y;
    // 按敌人重量分级：甲兽更重，顿帧和震屏都更强
    const heavy = type.id === 'armored';
    this.fx.burst(kx, ky, type.color, heavy ? 14 : 10);
    this.cameras.main.shake(heavy ? 90 : 60, heavy ? 0.004 : 0.0022);

    const nowKill = this.time.now;
    this.comboCount = nowKill - this.lastKillAt < 1500 ? this.comboCount + 1 : 1;
    this.lastKillAt = nowKill;
    if (this.comboCount >= 2) this.fx.combo(this.comboCount);

    // 金币飞向 HUD：让「击杀=有钱」变成可见的动作，而不是数字默默跳
    this.fx.coinFly(kx, ky, 44, 108);

    this.tweens.add({
      targets: [e.spr, e.bar, e.barBg],
      alpha: 0,
      scale: (e.spr.scaleX ?? 1) * 1.5,
      duration: 160,
      onComplete: () => {
        e.spr.destroy();
        e.bar.destroy();
        e.barBg.destroy();
      },
    });

    this.bus.emit(GAME_EVENTS.ENEMY_DEFEATED, {
      intensity: 0.45,
      context: { id: e.id, gold: this.gold, kills: this.kills, x: e.spr.x, y: e.spr.y },
    });
    this.audio.play('feedback_score', { priority: 'low' });
    this.refreshHud();
  }

  private leakEnemy(e: Enemy): void {
    const i = this.enemies.indexOf(e);
    if (i < 0) return;
    this.enemies.splice(i, 1);
    e.spr.destroy();
    e.bar.destroy();
    e.barBg.destroy();

    this.lives -= 1;
    this.fx.flash(0xff3b30, 0.3, 180);
    this.telemetry.record('leak', { lives: this.lives, wave: this.waveIndex + 1, typeId: e.typeId });
    this.cameras.main.shake(120, 0.006);
    this.bus.emit(GAME_EVENTS.PLAYER_HIT, {
      intensity: 0.7,
      context: { lives: this.lives, reason: 'leak' },
    });
    this.audio.play('feedback_hurt', { priority: 'high' });
    this.refreshHud();
  }

  /** 某个可建格在给定射程内覆盖多少个路径格 —— 衡量这个位置值不值得建 */
  private coverOf(c: number, r: number, range: number): number {
    const { x, y } = cellCenter(c, r);
    const rp = range * GRID.cell;
    let n = 0;
    for (const key of this.pathCells) {
      const [pc, pr] = key.split(',').map(Number);
      const cp = cellCenter(pc, pr);
      if (Math.hypot(cp.x - x, cp.y - y) <= rp) n += 1;
    }
    return n;
  }

  /**
   * 星级：看漏怪，不看分数。
   * 分数可以靠多建塔刷，漏怪不能——它直接反映「你守住了没有」。
   */
  private starsOf(): number {
    if (!this.won) return 0;
    const leaks = this.level.startLives - this.lives;
    if (leaks <= STARS.threeStarMaxLeaks) return 3;
    if (leaks <= STARS.twoStarMaxLeaks) return 2;
    return 1;
  }

  /** 第一次玩时给一句提示；建完第一座塔就标记完成，之后不再出现 */
  private maybeShowTutorial() {
    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    if (save.tutorialDone) return;
    this.tutorialHint = this.add
      .text(LAYOUT.width / 2, GRID.originY - 54, '点空地建塔，挡住路上的敌人', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '20px',
        color: '#ffd166',
        fontStyle: 'bold',
      })
      .setOrigin(0.5)
      .setDepth(28);
    this.tweens.add({
      targets: this.tutorialHint,
      alpha: 0.35,
      duration: 700,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }

  private markTutorialDone() {
    if (!this.tutorialHint) return;
    this.tutorialHint.destroy();
    this.tutorialHint = null;
    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    // fire-and-forget：存档失败不该阻断玩法
    void writeSave(this, { ...save, version: 1, best: Number(save.best ?? 0), tutorialDone: true });
    this.registry.set('save', { ...save, tutorialDone: true });
  }

  // ---------------------------------------------------------------- 塔开火
  /**
   * 选射程内走得最远的敌人（经典塔防策略）。
   * 溅射对周围敌人造成 60% 伤害；冰塔额外挂减速。
   */
  private fire(t: Tower): void {
    const type = this.typeOf(t.typeId);
    const rangePx = this.rangeOf(t) * GRID.cell;
    let target: Enemy | null = null;
    let bestDist = -1;
    for (const e of this.enemies) {
      const d = Math.hypot(e.spr.x - t.cx, e.spr.y - t.cy);
      if (d <= rangePx && e.dist > bestDist) {
        bestDist = e.dist;
        target = e;
      }
    }
    if (!target) return;

    const dmg = this.damageOf(t);
    this.shots.push({
      x1: t.cx,
      y1: t.cy,
      x2: target.spr.x,
      y2: target.spr.y,
      bornAt: this.time.now,
      color: type.color,
    });
    if (this.shots.length > 16) this.shots.shift();

    this.fx.muzzle(t.cx, t.cy, type.color);
    this.fx.spark(target.spr.x, target.spr.y, type.color);
    this.audio.play('gameplay_hit', { priority: 'low' });
    this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
      intensity: 0.25,
      source: 'tower',
      target: 'enemy',
      context: { c: t.c, r: t.r, typeId: t.typeId, x: t.cx, y: t.cy },
    }, 60);

    // 溅射：先算目标，再波及周围（避免主目标死亡后引用失效）
    if (type.splash) {
      const splashPx = type.splash * GRID.cell;
      const around = this.enemies.filter(
        (o) => o !== target && Math.hypot(o.spr.x - target!.spr.x, o.spr.y - target!.spr.y) <= splashPx,
      );
      this.hitEnemy(target, dmg);
      for (const o of around) this.hitEnemy(o, dmg * 0.6);
    } else {
      this.hitEnemy(target, dmg);
    }

    if (type.slowFactor) {
      // 目标可能已被打死，重新取一次
      const still = this.enemies.find((o) => o.id === target!.id);
      if (still) {
        this.applySlow(still, type.slowFactor, type.slowMs ?? 1500);
      }
    }
  }

  // ---------------------------------------------------------------- HUD
  private refreshHud(): void {
    this.refreshSkillHud();
    const waveLabel =
      this.waveIndex >= this.level.waves.length
        ? '最后一波'
        : `第 ${this.waveIndex + 1}/${this.level.waves.length} 波`;
    const key = `${this.gold}|${this.lives}|${waveLabel}`;
    if (key === this.lastHud) return; // 每帧无条件 setText 是帧率杀手
    this.lastHud = key;
    this.hudGold.setText(`金币 ${this.gold}`);
    this.hudLives.setText(`生命 ${this.lives}`);
    this.hudWave.setText(waveLabel);
  }

  private floatText(
    x: number,
    y: number,
    msg: string,
    color: string,
    durationMs = 420,
    onDestroy?: () => void,
  ): Phaser.GameObjects.Text | null {
    if (!this.scene.isActive()) return null;
    this.floatingTexts = this.floatingTexts.filter((text) => text.active);
    while (this.floatingTexts.length >= 8) {
      const oldest = this.floatingTexts.shift();
      if (oldest?.active) {
        this.tweens.killTweensOf(oldest);
        oldest.destroy();
      }
    }
    // 同格多敌人同时受伤时，飘字会完全重叠成一坨 —— 加一点确定性偏移错开
    const jx = ((this.nextFloatSeed = (this.nextFloatSeed * 1103515245 + 12345) & 0x7fffffff) % 17) - 8;
    const jy = (this.nextFloatSeed % 11) - 5;
    const t = this.add
      .text(x + jx, y + jy, msg, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '18px',
        color,
        fontStyle: 'bold',
      })
      .setOrigin(0.5)
      .setDepth(40);
    this.floatingTexts.push(t);
    let fallback: Phaser.Time.TimerEvent | null = null;
    t.once('destroy', () => {
      fallback?.remove(false);
      this.floatingTexts = this.floatingTexts.filter((text) => text !== t);
      onDestroy?.();
    });
    fallback = this.time.delayedCall(durationMs + 300, () => {
      this.tweens.killTweensOf(t);
      if (t.active) t.destroy();
    });
    this.tweens.add({
      targets: t,
      y: y + jy - 34,
      alpha: 0,
      duration: durationMs,
      ease: 'Quad.easeOut',
      onComplete: () => t.destroy(),
    });
    return t;
  }

  private flashHint(msg: string): void {
    this.hudHint.setText(msg);
    this.time.delayedCall(900, () => {
      if (!this.ended) this.hudHint.setText('');
    });
  }

  private applySlow(enemy: Enemy, factor: number, durationMs: number) {
    const now = this.time.now;
    const alreadySlowed = now < enemy.slowUntil;
    enemy.slowFactor = alreadySlowed ? Math.min(enemy.slowFactor, factor) : factor;
    enemy.slowUntil = Math.max(enemy.slowUntil, now + durationMs);
  }

  private finish(win: boolean): void {
    if (this.ended) return;
    this.ended = true;
    this.won = win;
    this.telemetry.finish(win ? 'won' : 'lost');

    if (win) {
      this.audio.setState('victory');
      this.audio.play('feedback_win', { priority: 'high' });
      this.cameras.main.shake(200, 0.008);
      this.bus.emit(GAME_EVENTS.LEVEL_COMPLETED, {
        intensity: 1,
        context: { kills: this.kills, lives: this.lives },
      });
    } else {
      this.audio.setState('defeat');
      this.bus.emit(GAME_EVENTS.PLAYER_DEATH, {
        intensity: 1,
        context: { kills: this.kills, wave: this.waveIndex + 1 },
      });
      this.audio.play('feedback_defeat', { priority: 'high' });
    }

    try {
      bridge(this).gameplayStop();
    } catch {
      /* 静默降级 */
    }

    this.time.delayedCall(900, () => {
      const next = win && this.levelIdx + 1 < LEVELS.length ? this.levelIdx + 1 : -1;
      this.scene.start('GameOver', {
        score: this.kills * 10 + (win ? 100 : 0),
        win,
        stars: this.starsOf(),
        nextLevel: next,
        level: this.levelIdx,
        levelId: this.level.id,
      });
    });
  }

  // ---------------------------------------------------------------- 主循环
  update(_time: number, delta: number) {
    this.audio?.update(delta);
    this.juice?.update(delta);
    if (this.ended) return;

    // ---- 波次调度
    if (!this.wavesPaused && this.waveIndex < this.level.waves.length) {
      // 本波只在第一次进入时展开，之后靠 waveSpawned 游标推进。
      // 用「queue 是否为空」判断本波结束是错的：空了会被当成未展开而重填 → 无限刷同一波。
      if (this.queue.length === 0) {
        this.queue = this.expandWave(this.level.waves[this.waveIndex]);
        this.waveSpawned = 0;
      }
      if (this.waveSpawned < this.queue.length) {
        this.spawnTimer -= delta;
        if (this.spawnTimer <= 0) {
          this.spawnEnemy(this.queue[this.waveSpawned]);
          this.waveSpawned += 1;
          this.spawnTimer = TD.spawnGapMs;
        }
      } else {
        this.waveGapTimer -= delta;
        if (this.waveGapTimer <= 0) {
          this.waveIndex += 1;
          this.queue = [];
          this.waveSpawned = 0;
          this.spawnTimer = this.level.firstWaveDelayMs;
          this.waveGapTimer = TD.waveGapMs;
        }
      }
    }

    // ---- 波次推进埋点
    if (this.waveIndex !== this.lastWaveIndex) {
      if (this.enemies.length === 0) {
        this.fx.waveClear(this.lastWaveIndex + 1);
        this.telemetry.record('wave_clear', { wave: this.lastWaveIndex + 1, lives: this.lives, gold: this.gold });
      }
      this.lastWaveIndex = this.waveIndex;
    }

    // ---- 敌人推进
    const now = this.time.now;
    const baseStep = delta / 1000;

    // 排队约束（软碰撞）：同速敌人会完全重合，玩家数不清有几个、也看不清血条。
    // 按 dist 从远到近压一遍，保证相邻敌人至少隔 MIN_GAP 格。
    // 这不是纯视觉 hack —— 一堆敌人同时到达基地本身就不合理。
    const MIN_GAP = 0.5;
    const ordered = [...this.enemies].sort((a, b) => b.dist - a.dist);
    for (let i = 1; i < ordered.length; i++) {
      const prev = ordered[i - 1];
      const cur = ordered[i];
      if (prev.dist - cur.dist < MIN_GAP) cur.dist = Math.max(0, prev.dist - MIN_GAP);
    }

    for (const e of [...this.enemies]) {
      const type = ENEMY_TYPES[e.typeId] ?? ENEMY_TYPES.grunt;
      const slow = now < e.slowUntil ? e.slowFactor : 1;
      if (now >= e.slowUntil) e.slowFactor = 1;
      e.dist += type.speed * slow * baseStep;

      const p = pathPointAt(this.level.path, e.dist);
      // 同一位置的敌人按朝向垂直错开，否则完全重合、玩家数不清有几个。
      // lane 用 id 取模，保证同一个敌人始终在同一条道上（不会左右乱跳）。
      const dir = pathDirAt(this.level.path, e.dist);
      // 排队约束已经把敌人拉开，这里只做 ±6px 微调，让「并排」看起来更自然
      const lane = ((e.id % 3) - 1) * 6;
      const ox = -dir.y * lane;
      const oy = dir.x * lane;
      e.spr.setPosition(p.x + ox, p.y + oy);
      e.barBg.setPosition(p.x + ox, p.y + oy - 30);
      e.bar.setPosition(p.x + ox, p.y + oy - 30);
      e.bar.width = 40 * Math.max(0, e.hp / e.maxHp);

      if (e.dist >= this.pathTotal) this.leakEnemy(e);
    }

    // ---- 塔开火
    for (const t of this.towers) {
      t.cd -= delta;
      if (t.cd > 0) continue;
      this.fire(t);
      t.cd = this.typeOf(t.typeId).cooldownMs;
    }

    // ---- 弹道特效
    this.shots = this.shots.filter((s) => now - s.bornAt < 160);
    this.fxG.clear();
    for (const s of this.shots) {
      const k = 1 - (now - s.bornAt) / 160;
      this.fxG.lineStyle(3, s.color, 0.85 * k);
      this.fxG.lineBetween(s.x1, s.y1, s.x2, s.y2);
    }

    // ---- 塔等级标记
    for (const t of this.towers) t.lvText.setText(t.level > 1 ? `${t.level}` : '');

    this.refreshHud();

    if (this.lives <= 0) {
      this.finish(false);
      return;
    }
    if (this.waveIndex >= this.level.waves.length && this.enemies.length === 0 && this.waveSpawned >= this.queue.length) {
      this.finish(true);
    }
  }

  /** 把 { grunt: 3, swift: 2 } 展开成按类型交替的生成序列 */
  private expandWave(wave: Record<string, number>): string[] {
    const lists = Object.entries(wave).map(([id, n]) => Array.from({ length: n }, () => id));
    const out: string[] = [];
    const maxLen = Math.max(0, ...lists.map((l) => l.length));
    for (let i = 0; i < maxLen; i++) {
      for (const l of lists) if (i < l.length) out.push(l[i]);
    }
    return out;
  }

  // ------------------------------------------------------------ 只读快照
  private exposeDebugHooks() {
    const w = window as unknown as Record<string, unknown>;
    Object.defineProperty(w, '__gameState', {
      configurable: true,
      get: () => ({
        phase: this.ended ? (this.won ? 'won' : 'lost') : 'play',
        level: this.levelIdx + 1,
        gold: this.gold,
        lives: this.lives,
        startLives: this.level.startLives,
        wave: this.waveIndex + 1,
        waveTotal: this.level.waves.length,
        enemies: this.enemies.length,
        towers: this.towers.length,
        kills: this.kills,
        skillCharge: this.skillCharge,
        skillCasts: this.skillCasts,
        audio: this.audio.snapshot(),
        juice: { quality: this.juice.qualityLevel, reducedMotion: this.juice.reducedMotion },
      }),
    });
    Object.defineProperty(w, '__gameEvents', {
      configurable: true,
      get: () => this.bus.snapshot(),
    });
    /**
     * 试玩 Agent。**支持多种「玩家水平」**，这是平衡分析的基础：
     *
     *   同一个人玩同一个配置只有一种结果，测不出「新手能不能过」。
     *   要让两个不同水平的策略跑同一关，才能回答
     *   「难度是不是只有高手才玩得下去」。
     *
     * 两个策略的差异是真实的，不是作弊：
     *   novice  按阅读顺序建塔、不评估覆盖、钱不够多就攒着 —— 像第一次玩的人
     *   expert  逐个候选格算「射程内覆盖多少路径格」，选覆盖最多的 —— 像算过的人
     */
    w.__bot = {
      act: (strategy = 'expert') => {
        if (this.ended) return { action: 'none' };
        const type = TOWER_TYPES[0];
        if (this.gold < type.cost) return { action: 'none' };

        const cands: Array<{ c: number; r: number; cover: number }> = [];
        for (let r = 0; r < GRID.rows; r++) {
          for (let c = 0; c < GRID.cols; c++) {
            if (!isBuildable(this.pathCells, this.base, c, r)) continue;
            if (this.towers.some((t) => t.c === c && t.r === r)) continue;
            cands.push({ c, r, cover: this.coverOf(c, r, type.range) });
          }
        }
        if (!cands.length) return { action: 'none' };

        let pick = cands[0];
        if (strategy === 'novice') {
          // 新手：钱不够两座塔就攒着，位置按阅读顺序（左上优先）
          if (this.gold < type.cost * 1.15) return { action: 'none' };
        } else {
          // 老手：覆盖路径最多的格
          cands.sort((a, b) => b.cover - a.cover);
          pick = cands[0];
        }

        const p = cellCenter(pick.c, pick.r);
        return { action: `click:${Math.round(p.x)}:${Math.round(p.y)}` };
      },
    };
  }

  // ------------------------------------------------------------ 测试接口
  private installTestHooks() {
    const adapter: TestAdapter = {
      capabilities: () => ['tap', 'spawn', 'wait', 'reset', 'set'],

      getState: () => ({
        phase: this.ended ? (this.won ? 'won' : 'lost') : 'play',
        level: this.levelIdx + 1,
        levelName: this.level.name,
        gold: this.gold,
        lives: this.lives,
        startLives: this.level.startLives,
        wave: this.waveIndex + 1,
        waveTotal: this.level.waves.length,
        queued: Math.max(0, this.queue.length - this.waveSpawned),
        enemyCount: this.enemies.length,
        enemies: this.enemies.map((e) => ({
          id: e.id,
          typeId: e.typeId,
          hp: e.hp,
          maxHp: e.maxHp,
          armor: (ENEMY_TYPES[e.typeId] ?? ENEMY_TYPES.grunt).armor,
          dist: Math.round(e.dist * 100) / 100,
          slowed: this.time.now < e.slowUntil,
        })),
        towerCount: this.towers.length,
        skillCharge: this.skillCharge,
        skillCasts: this.skillCasts,
        tweenScale: this.tweens.timeScale,
        transientFxCount: this.children.list.filter((object) => {
          const depth = (object as Phaser.GameObjects.GameObject & { depth?: number }).depth;
          return depth !== undefined && [36, 37, 38, 39, 40, 41, 45, 46].includes(depth);
        }).length,
        towers: this.towers.map((t) => ({
          id: t.id,
          typeId: t.typeId,
          level: t.level,
          c: t.c,
          r: t.r,
          damage: this.damageOf(t),
        })),
        buildType: this.buildTypeId,
        selectedTowerId: this.selected?.id ?? null,
        kills: this.kills,
        pathTotal: this.pathTotal,
        levelCount: LEVELS.length,
        ended: this.ended,
      }),

      isOver: () => this.ended,

      // 游戏内时间：headless 下 rAF 慢会让墙钟等待不等价于游戏时间
      getClock: () => this.time.now,

      exec: (a: TestAction) => {
        switch (a.type) {
          case 'tap': {
            if (a.c !== undefined && a.r !== undefined) {
              const hit = this.towers.find((t) => t.c === a.c && t.r === a.r);
              if (hit) {
                this.selected = hit;
                this.renderBottom();
              } else {
                this.buildTower(a.c, a.r, this.buildTypeId);
              }
            }
            break;
          }
          case 'spawn':
            this.spawnEnemy('grunt');
            break;
          case 'reset':
            this.scene.restart({ level: a.level ?? this.levelIdx });
            break;
          case 'set':
            this.applyTestPatch(a.patch);
            break;
          case 'wait':
            break;
        }
      },
    };
    installTestApi(adapter);
  }

  /**
   * 直接改内部值，构造边界前置条件。
   *
   * 支持字段：
   *   gold / lives / kills        资源
   *   buildType                   当前建造的塔类型 id
   *   pauseWaves                  暂停自动刷怪
   *   enemyHp / enemyProgress     批量改场上敌人
   *   spawnType + spawnCount      立刻生成指定类型敌人
   *   clearEnemies                清空敌人
   *   waveIndex / queued          跳波次
   */
  private applyTestPatch(patch: Record<string, unknown>): void {
    const num = (k: string) => (typeof patch[k] === 'number' ? (patch[k] as number) : undefined);

    const gold = num('gold');
    const lives = num('lives');
    const kills = num('kills');
    const skillCharge = num('skillCharge');
    if (gold !== undefined) this.gold = gold;
    if (lives !== undefined) this.lives = lives;
    if (kills !== undefined) this.kills = kills;
    if (skillCharge !== undefined) {
      this.skillCharge = Math.max(0, Math.min(SKILL_CHARGE_MAX, Math.round(skillCharge)));
      this.refreshSkillHud();
    }

    if (typeof patch.buildType === 'string') {
      this.buildTypeId = patch.buildType;
      this.selected = null;
      this.renderBottom();
    }

    if (patch.pauseWaves === true) this.wavesPaused = true;
    if (patch.pauseWaves === false) this.wavesPaused = false;

    const enemyHp = num('enemyHp');
    if (enemyHp !== undefined) {
      for (const e of this.enemies) {
        e.hp = enemyHp;
        e.maxHp = Math.max(e.maxHp, enemyHp);
      }
    }

    const progress = num('enemyProgress');
    if (progress !== undefined) {
      for (const e of this.enemies) e.dist = this.pathTotal * progress;
    }

    if (typeof patch.spawnType === 'string') {
      const n = num('spawnCount') ?? 1;
      for (let i = 0; i < n; i++) this.spawnEnemy(patch.spawnType);
    }

    if (patch.clearEnemies === true) {
      for (const e of this.enemies) {
        e.spr.destroy();
        e.bar.destroy();
        e.barBg.destroy();
      }
      this.enemies = [];
    }

    const waveIndex = num('waveIndex');
    if (waveIndex !== undefined) {
      this.waveIndex = waveIndex;
      this.queue = [];
      this.spawnTimer = 0;
      this.waveGapTimer = 0;
    }
    const queued = num('queued');
    if (queued !== undefined) {
      this.queue = Array.from({ length: queued }, () => 'grunt');
      this.waveSpawned = 0;
    }

    // 升级当前选中的塔（测试用；正常玩法是点塔后在底部栏点升级）
    if (patch.upgradeSelected === true && this.selected) this.upgradeTower(this.selected);

    // 出售指定格的塔（测试用；正常玩法是点塔后在底部栏操作）
    const sellAt = patch.sellAt;
    if (Array.isArray(sellAt) && sellAt.length === 2) {
      const [c, r] = sellAt as [number, number];
      const t = this.towers.find((x) => x.c === c && x.r === r);
      if (t) this.sellTower(t);
    }

    this.refreshHud();
  }

  private cleanup() {
    const w = window as unknown as Record<string, unknown>;
    delete w.__gameState;
    delete w.__gameEvents;
    delete w.__bot;
    detachTestApi();
    this.juice?.destroy();
    this.fx?.destroy();
    this.fx?.destroy();
    this.audio?.destroy();
    this.bus?.clear();
  }
}

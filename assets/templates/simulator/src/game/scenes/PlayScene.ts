import Phaser from 'phaser';
import { COLORS, LAYOUT, SIM } from '../config';
import { EventBus, GAME_EVENTS } from '../events';
import { AudioDirector } from '../audio';
import { JuiceDirector } from '../juice';
import { bridge, writeSave } from '../util';
import { detachTestApi, installTestApi, type TestAction, type TestAdapter } from '../test-api';
import {
  ACTION_LIST,
  STAGE_LIST,
  applyAction,
  createState,
  grade,
  meetsRequire,
  resolveEvent,
  stageDef,
  type SimState,
} from '../sim';

/**
 * 模拟器主玩法（默认实例：修仙模拟器）。
 *
 * 与动作类玩法的根本差别：**没有 update 循环**。
 * 状态只在「玩家点了一个行动」或「选了一个事件选项」时变化，
 * 所以整屏按需重绘即可 —— 这也让测试完全确定性，不用等动画。
 *
 * 分层：
 *   规则与数值  → `sim.ts`（纯函数）
 *   内容        → `content/*.json`（行动 / 事件 / 境界）
 *   本文件      → 排版、输入、事件弹窗
 */
export class PlayScene extends Phaser.Scene {
  private state!: SimState;

  /** 每次状态变化整体重建，避免逐元素同步的漏改 */
  private dyn!: Phaser.GameObjects.Container;
  private evtLayer!: Phaser.GameObjects.Container;

  /** 结算只写一次存档（renderAll 会被多次调用） */
  private saved = false;
  /** 新手引导提示 */
  private tutorialHint: Phaser.GameObjects.Text | null = null;

  private bus!: EventBus;
  private audio!: AudioDirector;
  private juice!: JuiceDirector;

  constructor() {
    super('Play');
  }

  create() {
    this.cameras.main.setBackgroundColor(COLORS.bg);

    this.bus = new EventBus(() => this.time.now, this.time.now);
    this.audio = new AudioDirector(this, this.bus);
    this.juice = new JuiceDirector(this, this.bus);
    this.registry.set('audio', this.audio);
    this.audio.start('exploration');
    this.juice.attach();

    this.state = createState(1);

    // 变体覆盖：原型对比时由 compare.mjs 注入（初始属性 / 事件概率）
    const ov = (window as unknown as { __VARIANT?: Record<string, unknown> }).__VARIANT;
    if (ov) {
      if (ov.stats && typeof ov.stats === 'object') {
        this.state.stats = { ...this.state.stats, ...(ov.stats as Record<string, number>) };
      }
      if (typeof ov.eventChance === 'number') this.state.eventChance = ov.eventChance;
      if (typeof ov.seed === 'number') this.state.seed = ov.seed;
    }

    this.dyn = this.add.container(0, 0).setDepth(10);
    this.evtLayer = this.add.container(0, 0).setDepth(50);

    this.saved = false;
    this.renderAll();
    this.maybeShowTutorial();
    this.exposeDebugHooks();
    this.installTestHooks();

    this.bus.emit(GAME_EVENTS.GAME_START, { intensity: 0.5 });
    this.bus.emit(GAME_EVENTS.LEVEL_STARTED, { intensity: 0.4, context: { level: 1 } });

    try {
      bridge(this).gameplayStart();
    } catch {
      /* 静默降级 */
    }

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.cleanup());
  }

  // ---------------------------------------------------------------- 排版
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
    opts: { bold?: boolean; origin?: [number, number]; wrap?: number } = {},
  ): Phaser.GameObjects.Text {
    const t = this.add.text(x, y, text, {
      fontFamily: 'system-ui, sans-serif',
      fontSize: `${size}px`,
      color: PlayScene.hex(color),
      fontStyle: opts.bold ? 'bold' : 'normal',
      wordWrap: opts.wrap ? { width: opts.wrap } : undefined,
      lineSpacing: 6,
    });
    if (opts.origin) t.setOrigin(opts.origin[0], opts.origin[1]);
    return t;
  }

  /** 一条属性条：底槽 + 填充 + 标签 + 数值 */
  private bar(y: number, label: string, value: number, max: number, color: number) {
    const W = LAYOUT.width;
    const x0 = 150;
    const bw = W - x0 - 110;
    const h = 26;

    this.dyn.add(this.txt(40, y - 6, label, 20, COLORS.textDim));
    this.dyn.add(
      this.add.rectangle(x0, y + h / 2, bw, h, COLORS.panel).setOrigin(0, 0.5).setStrokeStyle(1, COLORS.panelEdge),
    );
    const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
    if (ratio > 0) {
      this.dyn.add(
        this.add.rectangle(x0 + 2, y + h / 2, Math.max(2, (bw - 4) * ratio), h - 4, color).setOrigin(0, 0.5),
      );
    }
    this.dyn.add(this.txt(W - 40, y - 6, `${value}`, 20, COLORS.text, { origin: [1, 0] }));
  }

  private renderAll() {
    this.dyn.removeAll(true);
    const W = LAYOUT.width;
    const s = this.state;
    const st = stageDef(s.stage);

    // ---- 顶部
    this.dyn.add(this.txt(W / 2, 40, '修 行', 30, COLORS.gold, { bold: true, origin: [0.5, 0] }));
    this.dyn.add(this.txt(W / 2, 92, st.name, 42, COLORS.text, { bold: true, origin: [0.5, 0] }));
    this.dyn.add(
      this.txt(W / 2, 148, `${s.stats.age} / ${s.stats.lifespan} 岁　·　第 ${s.turn + 1} 回合`, 19, COLORS.textDim, {
        origin: [0.5, 0],
      }),
    );

    // ---- 属性条
    const qiNext = STAGE_LIST[Math.min(STAGE_LIST.length - 1, s.stage + 1)].qiMin;
    const qiMax = Math.max(qiNext, s.stats.qi, 10);
    this.bar(210, '修为', s.stats.qi, qiMax, COLORS.qi);
    this.bar(266, '灵石', s.stats.stones, Math.max(100, s.stats.stones), COLORS.stones);
    this.bar(322, '心境', s.stats.mood, SIM.moodMax, COLORS.mood);

    // ---- 日志
    this.dyn.add(this.txt(40, 380, '近日', 19, COLORS.textDim));
    const logLines = s.log.slice(0, 5);
    logLines.forEach((line, i) => {
      this.dyn.add(this.txt(40, 412 + i * 30, `· ${line}`, 17, i === 0 ? COLORS.text : COLORS.textDim, { wrap: W - 80 }));
    });

    // ---- 行动按钮
    const btnY = 600;
    const btnH = 92;
    const gap = 14;
    ACTION_LIST.forEach((a, i) => {
      const enabled = !s.ended && !s.pending && meetsRequire(s.stats, a.require);
      this.dyn.add(this.actionButton(a.id, a.name, a.desc, 40, btnY + i * (btnH + gap), W - 80, btnH, enabled));
    });

    // ---- 底部提示
    this.dyn.add(
      this.txt(W / 2, LAYOUT.height - 54, s.ended ? '这一世结束了' : '选一个行动，度过这一年', 18, COLORS.textDim, {
        origin: [0.5, 0],
      }),
    );

    // ---- 覆盖层
    if (s.pending) this.renderEvent();
    else this.evtLayer.removeAll(true);

    if (s.ended) {
      this.persistResult();
      this.renderEnding();
    }
  }

  private actionButton(id: string, name: string, desc: string, x: number, y: number, w: number, h: number, enabled: boolean) {
    const c = this.add.container(x, y);
    const bg = this.add
      .rectangle(0, 0, w, h, COLORS.panel)
      .setOrigin(0, 0)
      .setStrokeStyle(2, enabled ? COLORS.panelEdge : 0x1b2b26);
    c.add(bg);
    c.add(this.txt(24, 16, name, 23, enabled ? COLORS.text : '#5b6f66', { bold: true }));
    c.add(this.txt(24, 52, desc, 15, enabled ? COLORS.textDim : '#44554e'));
    if (enabled) {
      bg.setInteractive({ useHandCursor: true });
      bg.on('pointerdown', () => this.doAction(id));
      bg.on('pointerover', () => bg.setFillStyle(0x1b3129));
      bg.on('pointerout', () => bg.setFillStyle(COLORS.panel));
    }
    return c;
  }

  // ---------------------------------------------------------------- 事件弹窗
  private renderEvent() {
    this.evtLayer.removeAll(true);
    const W = LAYOUT.width;
    const H = LAYOUT.height;
    const ev = this.state.pending!;

    const mask = this.add.rectangle(0, 0, W, H, 0x000000, 0.78).setOrigin(0, 0);
    mask.setInteractive(); // 吃掉点击，防止穿透到下面的按钮
    this.evtLayer.add(mask);

    const pw = W - 80;
    // 高度按内容收：标题 + 最多两行正文 + 两个选项，不留大片空白
    const ph = 430;
    const px = 40;
    const py = (H - ph) / 2 - 40;
    this.evtLayer.add(
      this.add.rectangle(px, py, pw, ph, COLORS.panel).setOrigin(0, 0).setStrokeStyle(2, COLORS.gold),
    );
    this.evtLayer.add(this.txt(W / 2, py + 28, ev.title, 28, COLORS.gold, { bold: true, origin: [0.5, 0] }));
    this.evtLayer.add(this.txt(px + 32, py + 84, ev.text, 19, COLORS.text, { wrap: pw - 64 }));

    const optY = py + 170;
    ev.options.forEach((opt, i) => {
      const oy = optY + i * 100;
      const bg = this.add
        .rectangle(px + 32, oy, pw - 64, 88, 0x1b3129)
        .setOrigin(0, 0)
        .setStrokeStyle(2, COLORS.panelEdge)
        .setInteractive({ useHandCursor: true });
      bg.on('pointerdown', () => this.chooseOption(i));
      bg.on('pointerover', () => bg.setFillStyle(0x24443a));
      bg.on('pointerout', () => bg.setFillStyle(0x1b3129));
      this.evtLayer.add(bg);
      this.evtLayer.add(this.txt(px + 52, oy + 14, opt.text, 18, COLORS.text, { wrap: pw - 104 }));
    });
  }

  /** 把本局结果写进存档：最高境界 + 结局收集。只写一次。 */
  private persistResult() {
    if (this.saved) return;
    this.saved = true;
    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    const endings = new Set<string>((save.endings as string[]) ?? []);
    endings.add(grade(this.state));
    const next = {
      ...save,
      version: 1,
      best: Math.max(Number(save.best ?? 0), this.state.stage),
      bestStage: Math.max(Number(save.bestStage ?? 0), this.state.stage),
      endings: [...endings],
      plays: Number(save.plays ?? 0) + 1,
      tutorialDone: true,
    };
    // fire-and-forget：存档失败不该阻断结算界面
    void writeSave(this, next);
    this.registry.set('save', next);
  }

  /** 第一次玩时给一句提示；做出第一个行动就消失 */
  private maybeShowTutorial() {
    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    if (save.tutorialDone) return;
    this.tutorialHint = this.txt(LAYOUT.width / 2, LAYOUT.height - 96, '选一个行动，度过这一年', 20, '#ffd166', {
      bold: true,
      origin: [0.5, 0],
    });
    this.tutorialHint.setDepth(60);
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
    void writeSave(this, { ...save, version: 1, best: Number(save.best ?? 0), tutorialDone: true });
    this.registry.set('save', { ...save, tutorialDone: true });
  }

  private renderEnding() {
    const W = LAYOUT.width;
    const H = LAYOUT.height;
    const s = this.state;

    this.evtLayer.add(this.add.rectangle(0, 0, W, H, 0x000000, 0.82).setOrigin(0, 0).setInteractive());
    const pw = W - 100;
    const ph = 340;
    const px = 50;
    const py = (H - ph) / 2 - 40;
    this.evtLayer.add(
      this.add.rectangle(px, py, pw, ph, COLORS.panel).setOrigin(0, 0).setStrokeStyle(2, COLORS.panelEdge),
    );
    this.evtLayer.add(this.txt(W / 2, py + 40, '道途终了', 30, COLORS.gold, { bold: true, origin: [0.5, 0] }));
    this.evtLayer.add(
      this.txt(W / 2, py + 104, `${s.stats.age} 岁　·　${stageDef(s.stage).name}`, 22, COLORS.text, {
        origin: [0.5, 0],
      }),
    );
    this.evtLayer.add(this.txt(W / 2, py + 152, grade(s), 34, COLORS.accent, { bold: true, origin: [0.5, 0] }));

    // 结局收集进度：这是重玩动机的核心
    const save = (this.registry.get('save') as Record<string, unknown>) ?? {};
    const endings = (save.endings as string[]) ?? [];
    const total = STAGE_LIST.length;
    this.evtLayer.add(
      this.txt(W / 2, py + 206, `结局收集 ${endings.length} / ${total}`, 20, COLORS.gold, {
        origin: [0.5, 0],
      }),
    );

    const bg = this.add
      .rectangle(W / 2, py + 246, 300, 72, COLORS.panelEdge)
      .setInteractive({ useHandCursor: true });
    bg.on('pointerdown', () => this.scene.restart());
    this.evtLayer.add(bg);
    this.evtLayer.add(this.txt(W / 2, py + 240, '再修一世', 24, COLORS.text, { bold: true, origin: [0.5, 0] }));
  }

  // ---------------------------------------------------------------- 操作
  private doAction(id: string) {
    if (this.state.ended || this.state.pending) return;
    const before = this.state;
    const res = applyAction(this.state, id);
    if (!res.applied) {
      this.hint(res.lines[0] ?? '无法执行');
      return;
    }
    this.state = res.state;
    this.markTutorialDone();
    this.audio.play('gameplay_move', { priority: 'low' });
    // 带上坐标：juice 的粒子默认落在屏幕正中（会压住第一个按钮），
    // 指到属性区上方才是「数值变化」的正确视觉位置
    this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
      intensity: 0.35,
      context: { action: id, turn: this.state.turn, x: LAYOUT.width / 2, y: 185 },
    });

    if (res.state.stage > before.stage) {
      this.audio.play('feedback_levelup', { priority: 'high' });
      this.bus.emit(GAME_EVENTS.ITEM_COLLECTED, { intensity: 0.7, context: { breakthrough: true } });
    }
    this.renderAll();
  }

  private chooseOption(index: number) {
    if (!this.state.pending) return;
    const res = resolveEvent(this.state, index);
    this.state = res.state;
    this.audio.play('feedback_score', { priority: 'normal' });
    this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
      intensity: 0.4,
      context: { event: true, x: LAYOUT.width / 2, y: 185 },
    });
    this.renderAll();
  }

  private hint(msg: string) {
    const t = this.txt(LAYOUT.width / 2, LAYOUT.height - 96, msg, 18, COLORS.danger, { origin: [0.5, 0] });
    t.setDepth(60);
    this.time.delayedCall(900, () => t.destroy());
  }

  // ------------------------------------------------------------ 只读快照
  private exposeDebugHooks() {
    const w = window as unknown as Record<string, unknown>;
    Object.defineProperty(w, '__gameState', {
      configurable: true,
      get: () => ({
        phase: this.state.ended ? 'over' : this.state.pending ? 'event' : 'play',
        turn: this.state.turn,
        age: this.state.stats.age,
        lifespan: this.state.stats.lifespan,
        qi: this.state.stats.qi,
        stones: this.state.stats.stones,
        mood: this.state.stats.mood,
        stage: this.state.stage,
        stageName: stageDef(this.state.stage).name,
        pending: this.state.pending?.id ?? null,
        ended: this.state.ended,
      }),
    });
    Object.defineProperty(w, '__gameEvents', {
      configurable: true,
      get: () => this.bus.snapshot(),
    });
    // 试玩 Agent 的策略：有事件先处理，否则优先炼丹（修为最高效），钱不够就打坐
    w.__bot = {
      act: () => {
        if (this.state.ended) return { action: 'none' };
        if (this.state.pending) return { action: 'choose:0' };
        if (this.state.stats.stones >= 10) return { action: 'act:alchemy' };
        return { action: 'act:meditate' };
      },
    };
  }

  // ------------------------------------------------------------ 测试接口
  /**
   * 模拟器是回合制，`exec` 完全同步生效，**不需要任何 wait**。
   * 这是模拟器品类测试比动作类稳的根本原因：没有帧、没有 tween、没有物理。
   */
  private installTestHooks() {
    const adapter: TestAdapter = {
      capabilities: () => ['act', 'choose', 'wait', 'reset', 'set'],

      getState: () => ({
        phase: this.state.ended ? 'over' : this.state.pending ? 'event' : 'play',
        turn: this.state.turn,
        age: this.state.stats.age,
        lifespan: this.state.stats.lifespan,
        qi: this.state.stats.qi,
        stones: this.state.stats.stones,
        mood: this.state.stats.mood,
        stage: this.state.stage,
        stageName: stageDef(this.state.stage).name,
        pending: this.state.pending?.id ?? null,
        pendingOptions: this.state.pending?.options.length ?? 0,
        logCount: this.state.log.length,
        actionCount: ACTION_LIST.length,
        stageCount: STAGE_LIST.length,
        ended: this.state.ended,
        endReason: this.state.endReason,
        grade: grade(this.state),
      }),

      isOver: () => this.state.ended,

      exec: (a: TestAction) => {
        switch (a.type) {
          case 'act':
            this.doAction(a.id);
            break;
          case 'choose':
            this.chooseOption(a.index);
            break;
          case 'reset':
            this.scene.restart({});
            break;
          case 'set':
            this.applyTestPatch(a.patch);
            break;
          case 'wait':
            // 回合制无需等待；runner 遇到 wait 会调 settle，这里什么都不用做
            break;
        }
      },
    };
    installTestApi(adapter);
  }

  /**
   * 直接改内部状态，构造边界前置条件。
   *
   * 支持字段：
   *   stats       属性增量式覆盖（{ qi: 150 } 直接把修为设为 150）
   *   stage       境界索引（直接设，不触发突破判定）
   *   eventChance 覆盖事件概率（0 = 关闭随机事件，测试必用）
   *   forcedEvent 本回合强制触发指定事件 id
   *   clearPending 清掉待选事件
   */
  private applyTestPatch(patch: Record<string, unknown>) {
    if (patch.stats && typeof patch.stats === 'object') {
      this.state.stats = { ...this.state.stats, ...(patch.stats as Record<string, number>) };
    }
    if (typeof patch.stage === 'number') this.state.stage = patch.stage;
    if (typeof patch.eventChance === 'number') this.state.eventChance = patch.eventChance;
    if (typeof patch.forcedEvent === 'string') this.state.forcedEvent = patch.forcedEvent;
    if (patch.clearPending === true) this.state.pending = null;
    if (typeof patch.seed === 'number') this.state.seed = patch.seed;
    this.renderAll();
  }

  private cleanup() {
    const w = window as unknown as Record<string, unknown>;
    delete w.__gameState;
    delete w.__gameEvents;
    delete w.__bot;
    detachTestApi();
    this.juice?.destroy();
    this.audio?.destroy();
    this.bus?.clear();
  }
}

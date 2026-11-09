import Phaser from 'phaser';
import { COLORS, DIFFICULTY, GAME, LAYOUT } from '../config';
import { bridge } from '../util';
import { EventBus, GAME_EVENTS } from '../events';
import { AudioDirector } from '../audio';
import { JuiceDirector } from '../juice';
import { detachTestApi, installTestApi, type TestAction, type TestAdapter } from '../test-api';

type Target = Phaser.GameObjects.Image & { bornAt: number; lifetime: number; hit: boolean };

/**
 * 主玩法场景（占位玩法：点击靶子）。执行 modules/04-core-loop.md 时按 GDD 替换。
 *
 * v3 的接线示范（每个新项目都应照此结构）：
 *   1. 建 EventBus，玩法只 emit 事件，不直接调镜头/音频
 *   2. AudioDirector 订阅事件并驱动自适应音乐
 *   3. JuiceDirector 订阅事件并按严重度分级表现
 *   4. 暴露 window.__gameState / __gameEvents / __bot 供 QA 与试玩读取
 *   5. shutdown 时**必须**清理（bus.clear / audio.destroy / juice.destroy），否则跨场景泄漏
 */
export class PlayScene extends Phaser.Scene {
  private score = 0;
  private combo = 0;
  private targets: Target[] = [];
  private startedAt = 0;
  private spawnAcc = 0;
  private scoreText!: Phaser.GameObjects.Text;
  private timeText!: Phaser.GameObjects.Text;
  private ended = false;

  private bus!: EventBus;
  private audio!: AudioDirector;
  private juice!: JuiceDirector;
  private lastTimeLabel = '';

  constructor() {
    super('Play');
  }

  create() {
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);
    this.score = 0;
    this.combo = 0;
    this.targets = [];
    this.ended = false;
    this.lastTimeLabel = '';

    // ---- 事件 / 音频 / 表现 三件套
    this.bus = new EventBus(() => this.time.now, this.time.now);
    this.audio = new AudioDirector(this, this.bus);
    this.juice = new JuiceDirector(this, this.bus);
    this.registry.set('audio', this.audio);
    this.juice.setTargetResolver(() => this.targets[0] ?? null);
    this.audio.start('exploration');
    this.juice.attach();

    this.scoreText = this.add.text(32, 32, '0', {
      fontFamily: 'system-ui, sans-serif',
      fontSize: '64px',
      color: COLORS.text,
      fontStyle: 'bold',
    });

    this.timeText = this.add
      .text(W - 32, 44, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '40px',
        color: COLORS.textDim,
      })
      .setOrigin(1, 0);

    this.startedAt = this.time.now;

    // ---- 供 QA / 试玩读取的只读快照
    this.exposeDebugHooks();
    // ---- 供 scenario runner 驱动的可写测试接口（仅 DEV）
    this.installTestHooks();

    this.bus.emit(GAME_EVENTS.GAME_START, { intensity: 0.5 });
    this.bus.emit(GAME_EVENTS.LEVEL_STARTED, { intensity: 0.4, context: { level: 1 } });

    // 平台生命周期：进入可玩状态
    try {
      bridge(this).gameplayStart();
    } catch {
      /* 静默降级 */
    }

    // 场景关闭时清理，防止监听器与音频对象泄漏
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.cleanup());
  }

  private exposeDebugHooks() {
    const w = window as unknown as Record<string, unknown>;
    Object.defineProperty(w, '__gameState', {
      configurable: true,
      get: () => ({
        phase: this.ended ? 'over' : 'play',
        score: this.score,
        combo: this.combo,
        remainMs: Math.max(0, GAME.roundMs - (this.time.now - this.startedAt)),
        targets: this.targets.length,
        audio: this.audio.snapshot(),
        juice: { quality: this.juice.qualityLevel, reducedMotion: this.juice.reducedMotion },
      }),
    });
    Object.defineProperty(w, '__gameEvents', {
      configurable: true,
      get: () => this.bus.snapshot(),
    });
    // 可选：给 Playtest Agent 用的操作策略。没有也能跑（会退回通用输入）
    w.__bot = {
      act: (_strategy: string, step: number) => {
        if (this.ended) return { action: 'none' };
        const t = this.targets.find((x) => !x.hit);
        if (t) return { action: `click:${Math.round(t.x)}:${Math.round(t.y)}` };
        return { action: step % 3 === 0 ? 'ping' : 'move' };
      },
    };
  }

  update(time: number, delta: number) {
    this.audio?.update(delta);
    this.juice?.update(delta);
    if (this.ended) return;

    const elapsed = time - this.startedAt;
    const remain = Math.max(0, GAME.roundMs - elapsed);
    // 只在文本真的变了才 setText（每帧无条件调用是帧率杀手）
    const label = `${(remain / 1000).toFixed(1)}s`;
    if (label !== this.lastTimeLabel) {
      this.timeText.setText(label);
      this.lastTimeLabel = label;
    }

    if (remain <= 0) {
      this.finish();
      return;
    }

    // 剩余时间驱动音乐状态：最后 25% 进 danger
    const ratio = remain / GAME.roundMs;
    if (ratio < 0.25) this.audio?.setState('danger');
    else if (ratio < 0.5) this.audio?.setState('exploration');

    const step = Math.floor(elapsed / DIFFICULTY.stepMs);
    const lifetime = Math.max(
      DIFFICULTY.minLifetimeMs,
      GAME.targetLifetimeMs * Math.pow(1 - DIFFICULTY.lifetimeDecay, step),
    );
    const interval = Math.max(
      DIFFICULTY.minSpawnMs,
      GAME.spawnIntervalMs * Math.pow(1 - DIFFICULTY.spawnDecay, step),
    );

    this.spawnAcc += delta;
    if (this.spawnAcc >= interval && this.targets.length < GAME.maxTargets) {
      this.spawnAcc = 0;
      this.spawnTarget(lifetime);
    }

    for (const t of [...this.targets]) {
      if (!t.hit && time - t.bornAt > t.lifetime) {
        this.expireTarget(t);
      }
    }
  }

  private spawnTarget(lifetime: number) {
    const { width: W, height: H } = LAYOUT;
    const r = GAME.targetRadius;
    const pad = r + 40;
    const x = Phaser.Math.Between(pad, W - pad);
    const y = Phaser.Math.Between(H * 0.28, H - pad);

    const key = 'ph_target';
    const t = this.add.image(x, y, key) as Target;
    t.setInteractive({ useHandCursor: true });
    t.bornAt = this.time.now;
    t.lifetime = lifetime;
    t.hit = false;
    t.setScale(0.6);
    t.setAlpha(0.98);

    this.tweens.add({ targets: t, scale: 1, duration: 160, ease: 'Back.easeOut' });
    t.on('pointerdown', () => this.hitTarget(t));
    this.targets.push(t);
    this.bus.emit(GAME_EVENTS.ENEMY_SPAWN, { intensity: 0.3, context: { x, y } }, 60);
  }

  private hitTarget(t: Target) {
    if (t.hit || this.ended) return;
    t.hit = true;
    this.combo += 1;
    const gained = GAME.scorePerHit + (this.combo - 1) * GAME.comboBonus;
    this.score += gained;
    this.scoreText.setText(String(this.score));

    t.disableInteractive();
    t.setTexture('ph_target_hit');
    this.tweens.add({
      targets: t,
      scale: GAME.hitScalePunch,
      alpha: 0,
      duration: 160,
      ease: 'Quad.easeOut',
      onComplete: () => this.removeTarget(t),
    });

    // 事件驱动：表现与音效由订阅者决定，玩法代码不再直接调 shake
    this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
      source: 'player', target: 'target', intensity: 0.45,
      context: { x: t.x, y: t.y, combo: this.combo },
    });
    this.bus.emit(GAME_EVENTS.ITEM_COLLECTED, {
      source: 'player', intensity: this.combo >= 5 ? 0.6 : 0.35,
      context: { x: t.x, y: t.y, score: this.score, gained },
    });
    if (this.combo >= 5) {
      this.bus.emit(GAME_EVENTS.SECRET_FOUND, { intensity: 0.55, context: { combo: this.combo } }, 500);
    }
  }

  private expireTarget(t: Target) {
    this.combo = 0;
    t.disableInteractive();
    this.tweens.add({
      targets: t,
      alpha: 0,
      scale: 0.8,
      duration: 160,
      onComplete: () => this.removeTarget(t),
    });
    this.bus.emit(GAME_EVENTS.PLAYER_HIT, {
      source: 'enemy', target: 'player', intensity: 0.5,
      context: { x: t.x, y: t.y, reason: 'expired' },
    });
  }

  private removeTarget(t: Target) {
    const i = this.targets.indexOf(t);
    if (i >= 0) this.targets.splice(i, 1);
    t.destroy();
  }

  private finish() {
    if (this.ended) return;
    this.ended = true;
    for (const t of [...this.targets]) this.removeTarget(t);

    this.bus.emit(GAME_EVENTS.LEVEL_COMPLETED, { intensity: 0.9, context: { score: this.score } });

    try {
      bridge(this).gameplayStop();
    } catch {
      /* 静默降级 */
    }

    // 让胜利 stinger 与音乐状态有时间播出来，再切场景
    this.time.delayedCall(650, () => this.scene.start('GameOver', { score: this.score }));
  }

  // ------------------------------------------------------------ 测试接口
  /**
   * 注册 Game Test API（仅 DEV 生效，生产构建被 DCE 掉）。
   *
   * 模板的玩法是「限时打靶」，靶子随机生成 —— 测试无法预知坐标。
   * 所以这里提供 `tap`（不带坐标 = 点第一个未命中的靶）和 `spawn`（强制生成），
   * 让用例可以「先造一个靶、再打掉它」，而不依赖随机时序。
   *
   * 换成别的玩法时，改这个 adapter 即可，runner 与用例格式不用动。
   */
  private installTestHooks() {
    const adapter: TestAdapter = {
      capabilities: () => ['tap', 'spawn', 'wait', 'reset', 'set'],

      getState: () => ({
        phase: this.ended ? 'over' : 'play',
        score: this.score,
        combo: this.combo,
        remainMs: Math.max(0, GAME.roundMs - (this.time.now - this.startedAt)),
        targetCount: this.targets.length,
        targets: this.targets.map((t) => ({ x: Math.round(t.x), y: Math.round(t.y), hit: t.hit })),
        ended: this.ended,
      }),

      isOver: () => this.ended,

      exec: (a: TestAction) => {
        switch (a.type) {
          case 'tap':
            this.testTap(a.x, a.y);
            break;
          case 'spawn':
            this.spawnTarget(GAME.targetLifetimeMs);
            break;
          case 'reset':
            this.scene.restart({});
            break;
          case 'set':
            this.applyTestPatch(a.patch);
            break;
          case 'wait':
            // 同步接口无法等待；runner 侧遇到 wait 会调用 settle()
            break;
        }
      },
    };
    installTestApi(adapter);
  }

  /** 命中判定：给了坐标按距离找，没给就点第一个未命中的靶。 */
  private testTap(x?: number, y?: number) {
    if (this.ended) return;
    const live = this.targets.filter((t) => !t.hit);
    if (!live.length) return;
    if (x === undefined || y === undefined) {
      this.hitTarget(live[0]);
      return;
    }
    const r = GAME.targetRadius;
    const hit = live.find((t) => Math.hypot(t.x - x, t.y - y) <= r);
    if (hit) this.hitTarget(hit);
  }

  /** 直接改内部值，用来构造「连击已 x 次」这类前置条件。 */
  private applyTestPatch(patch: Record<string, unknown>) {
    if (typeof patch.score === 'number') {
      this.score = patch.score;
      this.scoreText.setText(String(this.score));
    }
    if (typeof patch.combo === 'number') this.combo = patch.combo;
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

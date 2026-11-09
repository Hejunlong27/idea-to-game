import Phaser from 'phaser';
import { COLORS, ECHO, GRID, JUICE, LAYOUT, RULES } from '../config';
import { TEXTURES } from '../art';
import { EventBus, GAME_EVENTS } from '../events';
import { AudioDirector } from '../audio';
import { JuiceDirector } from '../juice';
import { bridge } from '../util';
import { detachTestApi, installTestApi, type TestAction, type TestAdapter } from '../test-api';
import LEVELS from '../levels.json';

type Pt = { c: number; r: number };
type Kind = 'soul' | 'wraith' | 'rock';

interface Ent {
  kind: Kind;
  c: number;
  r: number;
  spr: Phaser.GameObjects.Image;
  alive: boolean;
}

interface Ghost {
  kind: Kind;
  c: number;
  r: number;
  bornAt: number;
  spr: Phaser.GameObjects.Image;
}

const DOCK: Pt = { c: 6, r: 4 };

/**
 * AI 素材按 1.6 倍尺寸出（高分屏不糊），进游戏要缩回格子大小。
 * 程序化纹理不需要缩放（本来就按格子尺寸画），所以这里按 kind 给固定比例。
 */
const SPRITE_SCALE: Record<Kind, number> = { soul: 0.62, wraith: 0.64, rock: 0.9 };
const BOAT_SCALE = 0.72;

/**
 * 《回声摆渡》主玩法。
 *
 * 核心机制（见 docs/01-brief/creative-dna.json）：
 *   敲钟 → 世界亮 1.2 秒 → 亮过的位置留下**会腐烂的残影** → 残影是「当时」的位置，
 *   而黑暗里的东西会移动 → 你打的是幻影。敲钟同时会暴露自己。
 *
 * 事件驱动：玩法只 emit 事件；表现由 juice.ts 按严重度分级，音频由 audio.ts 驱动状态机。
 */
export class PlayScene extends Phaser.Scene {
  private levelIdx = 0;
  private cfg!: (typeof LEVELS.levels)[number];

  private hull = RULES.hullMax;
  private memory = ECHO.memoryMax;
  private memoryRegenMs = 0;
  private carried = 0;
  private delivered = 0;
  private totalSouls = 1;

  private player: Pt = { c: 1, r: 7 };
  private boat!: Phaser.GameObjects.Image;
  private ents: Ent[] = [];
  private ghosts: Ghost[] = [];
  private tiles: Phaser.GameObjects.Image[] = [];

  private revealUntil = 0;
  private invulnUntil = 0;
  private wraithAcc = 0;
  private ended = false;
  private stopped = false;
  private startedAt = 0;

  private hudTop!: Phaser.GameObjects.Text;
  private hudHint!: Phaser.GameObjects.Text;
  private memPips: Phaser.GameObjects.Arc[] = [];
  private hullPips: Phaser.GameObjects.Arc[] = [];
  private pingBtn!: Phaser.GameObjects.Container;
  private pingLabel!: Phaser.GameObjects.Text;
  private lastMemText = '';

  /** bot 用：撞过的格子（撞一次就记住）与看见过的灵魂位置 */
  private botBlocked = new Set<string>();
  private botKnownSouls = new Set<string>();

  private bus!: EventBus;
  private audio!: AudioDirector;
  private juice!: JuiceDirector;

  constructor() {
    super('Play');
  }

  init(data: { level?: number }) {
    this.levelIdx = Math.max(0, Math.min(LEVELS.levels.length - 1, data?.level ?? 0));
  }

  create() {
    this.cfg = LEVELS.levels[this.levelIdx];
    const { width: W, height: H } = LAYOUT;
    this.cameras.main.setBackgroundColor(COLORS.bg);

    // ---- 三件套
    this.bus = new EventBus(() => this.time.now, this.time.now);
    this.audio = new AudioDirector(this, this.bus);
    this.juice = new JuiceDirector(this, this.bus);
    this.registry.set('audio', this.audio);
    this.audio.start('exploration');
    this.juice.attach();

    // ---- 重置状态
    this.hull = RULES.hullMax;
    this.memory = this.cfg.memoryMax ?? ECHO.memoryMax;
    this.memoryRegenMs = this.cfg.memoryRegenMs ?? ECHO.memoryRegenMs;
    this.carried = 0;
    this.delivered = 0;
    this.totalSouls = this.cfg.souls;
    this.ents = [];
    this.ghosts = [];
    this.tiles = [];
    this.revealUntil = 0;
    this.invulnUntil = 0;
    this.wraithAcc = 0;
    this.ended = false;
    this.stopped = false;
    this.botBlocked.clear();
    this.botKnownSouls.clear();
    this.lastMemText = '';
    this.startedAt = this.time.now;

    this.buildBoard();
    this.buildEntities();
    this.buildPlayer();
    this.buildHud();
    this.bindInput();
    this.exposeDebugHooks();
    this.installTestHooks();

    this.bus.emit(GAME_EVENTS.GAME_START, { intensity: 0.5 });
    this.bus.emit(GAME_EVENTS.LEVEL_STARTED, {
      intensity: 0.45,
      context: { level: this.levelIdx + 1, name: this.cfg.name },
    });

    try {
      bridge(this).gameplayStart();
    } catch {
      /* 静默降级 */
    }

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => this.cleanup());
  }

  // ---------------------------------------------------------------- 建场
  private cx(c: number) {
    return GRID.originX + c * GRID.cell + GRID.cell / 2;
  }

  private cy(r: number) {
    return GRID.originY + r * GRID.cell + GRID.cell / 2;
  }

  private buildBoard() {
    for (let r = 0; r < GRID.rows; r++) {
      for (let c = 0; c < GRID.cols; c++) {
        const isDock = c === DOCK.c && r === DOCK.r;
        const img = this.add
          .image(this.cx(c), this.cy(r), isDock ? TEXTURES.shore : TEXTURES.water)
          .setDepth(0)
          .setAlpha(isDock ? 1 : 0.92);
        this.tiles.push(img);
      }
    }
    // 岸边：木桩 + 一盏灯（程序化，与 AI 角色形成质感对比但不抢）
    const dx = this.cx(DOCK.c);
    const dy = this.cy(DOCK.r);
    this.add.rectangle(dx, dy - 30, 5, 26, 0x3a2f22, 1).setDepth(3);
    this.add.circle(dx, dy - 44, 9, COLORS.accent, 0.28).setDepth(3);
    this.add.circle(dx, dy - 44, 4.5, COLORS.accent, 1).setDepth(4);
    this.tweens.add({
      targets: this.add.circle(dx, dy - 44, 9, COLORS.accent, 0.28).setDepth(3),
      alpha: 0.08,
      duration: 1500,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }

  private buildEntities() {
    const put = (kind: Kind, c: number, r: number) => {
      const key =
        kind === 'soul' ? TEXTURES.soul : kind === 'wraith' ? TEXTURES.wraith : TEXTURES.rock;
      const spr = this.add
        .image(this.cx(c), this.cy(r), key)
        .setDepth(kind === 'rock' ? 3 : 4)
        .setScale(SPRITE_SCALE[kind])
        .setAlpha(0);
      const e: Ent = { kind, c, r, spr, alive: true };
      this.ents.push(e);
      return e;
    };

    for (const [c, r] of this.cfg.rockPos ?? []) {
      if (c === DOCK.c && r === DOCK.r) continue;
      put('rock', c, r);
    }
    for (const [c, r] of this.cfg.wraithPos ?? []) put('wraith', c, r);
    for (const [c, r] of this.cfg.soulPos ?? []) put('soul', c, r);
  }

  private buildPlayer() {
    const [c, r] = this.cfg.start;
    this.player = { c, r };
    this.boat = this.add
      .image(this.cx(c), this.cy(r), TEXTURES.boat)
      .setDepth(10)
      .setAlpha(1)
      .setScale(BOAT_SCALE);
    // 船头灯的呼吸（secondary motion）。基准是 BOAT_SCALE，不能用 1.03 —— 那会把船放大一倍
    this.tweens.add({
      targets: this.boat,
      scaleX: BOAT_SCALE * 1.03,
      scaleY: BOAT_SCALE * 0.97,
      duration: 1400,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
  }

  private buildHud() {
    const { width: W } = LAYOUT;
    const lv = this.levelIdx + 1;
    this.add
      .text(28, 42, `${lv} · ${this.cfg.name}`, {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '30px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setDepth(20);

    this.hudTop = this.add
      .text(W - 28, 44, '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.textDim,
      })
      .setOrigin(1, 0)
      .setDepth(20);

    // 记忆格 + 船体放同一行（竖向空间留给网格）
    this.add
      .text(28, 96, '记忆', { fontFamily: 'system-ui, sans-serif', fontSize: '18px', color: COLORS.textDim })
      .setDepth(20);
    this.memPips = [];
    const memSlots = this.cfg.memoryMax ?? ECHO.memoryMax;
    for (let i = 0; i < memSlots; i++) {
      const p = this.add.circle(88 + i * 28, 105, 9, COLORS.accent, 1).setDepth(20);
      this.memPips.push(p);
    }

    this.add
      .text(300, 96, '船体', { fontFamily: 'system-ui, sans-serif', fontSize: '18px', color: COLORS.textDim })
      .setDepth(20);
    this.hullPips = [];
    for (let i = 0; i < RULES.hullMax; i++) {
      const p = this.add.circle(360 + i * 28, 105, 9, COLORS.danger, 1).setDepth(20);
      this.hullPips.push(p);
    }

    this.hudHint = this.add
      .text(28, 142, this.cfg.hint ?? '', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '18px',
        color: COLORS.textDim,
        wordWrap: { width: LAYOUT.width - 56 },
      })
      .setDepth(20);

    // 敲钟按钮
    const bx = LAYOUT.width / 2;
    const by = LAYOUT.height - 96;
    const ring = this.add.circle(0, 0, 62, COLORS.accent, 0.12).setStrokeStyle(2, COLORS.accent, 0.9);
    const parts: Phaser.GameObjects.GameObject[] = [ring];
    // AI 生成的钟（混合美术：可交互物件用 AI 图，其余程序化）
    if (this.textures.exists(TEXTURES.bell)) {
      parts.push(this.add.image(0, -6, TEXTURES.bell).setScale(0.62));
    }
    this.pingLabel = this.add
      .text(0, 34, '敲钟', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '22px',
        color: COLORS.text,
        fontStyle: 'bold',
      })
      .setOrigin(0.5);
    parts.push(this.pingLabel);
    this.pingBtn = this.add.container(bx, by, parts).setDepth(30);
    this.pingBtn.setSize(124, 124);
    this.pingBtn.setInteractive(new Phaser.Geom.Circle(0, 0, 62), Phaser.Geom.Circle.Contains);
    this.pingBtn.on('pointerdown', () => this.ping());
    this.add
      .text(bx, by + 84, '空格 / 点这里', {
        fontFamily: 'system-ui, sans-serif',
        fontSize: '16px',
        color: COLORS.textDim,
      })
      .setOrigin(0.5)
      .setDepth(30);
  }

  private bindInput() {
    const kb = this.input.keyboard;
    if (!kb) return;
    kb.on('keydown-UP', () => this.step(0, -1));
    kb.on('keydown-W', () => this.step(0, -1));
    kb.on('keydown-DOWN', () => this.step(0, 1));
    kb.on('keydown-S', () => this.step(0, 1));
    kb.on('keydown-LEFT', () => this.step(-1, 0));
    kb.on('keydown-A', () => this.step(-1, 0));
    kb.on('keydown-RIGHT', () => this.step(1, 0));
    kb.on('keydown-D', () => this.step(1, 0));
    kb.on('keydown-SPACE', () => this.ping());

    // 触摸：点相邻格移动（FIT 缩放下 pointer.x 不等于设计坐标，必须手动换算）
    this.input.on('pointerdown', (p: Phaser.Input.Pointer) => {
      const ev = p.event as MouseEvent | undefined;
      if (!ev) return;
      const rect = this.game.canvas.getBoundingClientRect();
      const gx = (ev.clientX - rect.left) * (LAYOUT.width / rect.width);
      const gy = (ev.clientY - rect.top) * (LAYOUT.height / rect.height);
      const c = Math.floor((gx - GRID.originX) / GRID.cell);
      const r = Math.floor((gy - GRID.originY) / GRID.cell);
      if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) return;
      const dc = c - this.player.c;
      const dr = r - this.player.r;
      if (Math.abs(dc) + Math.abs(dr) !== 1) return;
      this.step(dc, dr);
    });
  }

  private exposeDebugHooks() {
    const w = window as unknown as Record<string, unknown>;
    Object.defineProperty(w, '__gameState', {
      configurable: true,
      get: () => ({
        phase: this.ended ? 'over' : 'play',
        level: this.levelIdx + 1,
        hull: this.hull,
        memory: this.memory,
        carried: this.carried,
        delivered: this.delivered,
        soulsTotal: this.totalSouls,
        player: { ...this.player },
        ghosts: this.ghosts.length,
        revealed: this.time.now < this.revealUntil,
        audio: this.audio.snapshot(),
        juice: { quality: this.juice.qualityLevel, reducedMotion: this.juice.reducedMotion },
      }),
    });
    Object.defineProperty(w, '__gameEvents', {
      configurable: true,
      get: () => this.bus.snapshot(),
    });
    // 供 Playtest Agent 使用：一个只用公开状态做决策的简单 AI
    w.__bot = {
      act: (strategy: string) => {
        if (this.ended) return { action: 'none' };
        const target = this.botTarget();
        if (!target) return { action: this.memory > 0 ? 'ping' : 'move' };
        const next = this.botNextStep(target);
        // 新手更依赖敲钟确认；策略玩家只在没路时才敲
        const wantsInfo = strategy === 'novice' || strategy === 'explorer';
        const noPath = !next;
        if (this.memory > 0 && this.time.now >= this.revealUntil && (noPath || (wantsInfo && this.ghosts.length === 0))) {
          return { action: 'ping' };
        }
        if (!next) return { action: 'move' };
        const dc = next.c - this.player.c;
        const dr = next.r - this.player.r;
        if (dc > 0) return { action: 'key:ArrowRight' };
        if (dc < 0) return { action: 'key:ArrowLeft' };
        if (dr > 0) return { action: 'key:ArrowDown' };
        return { action: 'key:ArrowUp' };
      },
    };
  }

  // ------------------------------------------------------------ 测试接口
  /**
   * 注册 Game Test API（仅 DEV 生效，生产构建被 DCE 掉）。
   *
   * 与 `exposeDebugHooks` 的区别：那边是**只读**快照，给试玩 Agent 观察用；
   * 这边是**可写**驱动，能同步执行动作、精确构造边界场景。
   * 没有它，测试就只能靠敲键盘碰运气，永远碰不到「记忆满时送达」这类边界。
   */
  private installTestHooks() {
    const adapter: TestAdapter = {
      capabilities: () => ['move', 'ping', 'wait', 'reset', 'teleport', 'set'],

      getState: () => ({
        phase: this.ended ? 'over' : 'play',
        level: this.levelIdx + 1,
        levelName: this.cfg.name,
        hull: this.hull,
        hullMax: RULES.hullMax,
        memory: this.memory,
        memoryMax: this.cfg.memoryMax ?? ECHO.memoryMax,
        carried: this.carried,
        delivered: this.delivered,
        soulsTotal: this.totalSouls,
        soulsLeft: this.ents.filter((e) => e.kind === 'soul' && e.alive).length,
        player: { c: this.player.c, r: this.player.r },
        wraiths: this.ents
          .filter((e) => e.kind === 'wraith' && e.alive)
          .map((e) => ({ c: e.c, r: e.r })),
        rocks: this.ents.filter((e) => e.kind === 'rock' && e.alive).map((e) => ({ c: e.c, r: e.r })),
        ghosts: this.ghosts.length,
        revealed: this.time.now < this.revealUntil,
        ended: this.ended,
      }),

      isOver: () => this.ended,

      exec: (a: TestAction) => {
        switch (a.type) {
          case 'move':
            this.step(a.dc, a.dr);
            break;
          case 'ping':
            this.ping();
            break;
          case 'wait':
            // 同步接口无法等待；runner 侧遇到 wait 会调用 settle()
            break;
          case 'reset':
            this.scene.restart({ level: a.level ?? this.levelIdx });
            break;
          case 'teleport':
            this.teleport(a.c, a.r);
            break;
          case 'set':
            this.applyTestPatch(a.patch);
            break;
        }
      },
    };
    installTestApi(adapter);
  }

  /** 直接摆位置。测试用它精确构造场景，绕过寻路与 tween。 */
  private teleport(c: number, r: number) {
    if (c < 0 || r < 0 || c >= GRID.cols || r >= GRID.rows) return;
    this.player = { c, r };
    this.boat.setPosition(this.cx(c), this.cy(r));
    // 传送后立刻结算所在格：否则测试要额外走一步才能拿到货
    const here = this.entAt(c, r);
    if (here?.kind === 'soul') {
      here.alive = false;
      here.spr.destroy();
      this.carried = 1;
      this.bus.emit(GAME_EVENTS.ITEM_COLLECTED, {
        intensity: 0.5,
        context: { x: this.cx(c), y: this.cy(r), soul: true },
      });
    }
    this.refreshHud();
  }

  /** 直接改内部值，用来构造「记忆满 / 船体 1」这类前置条件。 */
  private applyTestPatch(patch: Record<string, unknown>) {
    const num = (k: string) => (typeof patch[k] === 'number' ? (patch[k] as number) : undefined);
    const hull = num('hull');
    const memory = num('memory');
    const carried = num('carried');
    const delivered = num('delivered');
    if (hull !== undefined) this.hull = hull;
    if (memory !== undefined) this.memory = memory;
    if (carried !== undefined) this.carried = carried;
    if (delivered !== undefined) this.delivered = delivered;
    this.refreshHud();
  }

  /** bot 的目标：有货回岸边，没货去最近一个「记得的」灵魂位置 */
  private botTarget(): Pt | null {
    if (this.carried > 0) return DOCK;
    const alive = this.ents.filter((e) => e.kind === 'soul' && e.alive);
    if (!alive.length) return null;
    const known = alive.filter((e) => this.botKnownSouls.has(`${e.c},${e.r}`));
    const pool = known.length ? known : alive;
    let best = pool[0];
    let bd = 99;
    for (const s of pool) {
      const d = Math.abs(s.c - this.player.c) + Math.abs(s.r - this.player.r);
      if (d < bd) {
        bd = d;
        best = s;
      }
    }
    return { c: best.c, r: best.r };
  }

  /** BFS 求下一步（避开撞过的格子与已知礁石）。找不到路就返回 null。 */
  private botNextStep(target: Pt): Pt | null {
    const start = this.player;
    if (start.c === target.c && start.r === target.r) return null;
    const key = (c: number, r: number) => `${c},${r}`;
    const q: Array<{ c: number; r: number; first: Pt | null }> = [
      { c: start.c, r: start.r, first: null },
    ];
    const seen = new Set<string>([key(start.c, start.r)]);
    const dirs: Array<[number, number]> = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    while (q.length) {
      const cur = q.shift()!;
      for (const [dc, dr] of dirs) {
        const nc = cur.c + dc;
        const nr = cur.r + dr;
        if (nc < 0 || nr < 0 || nc >= GRID.cols || nr >= GRID.rows) continue;
        const k = key(nc, nr);
        if (seen.has(k) || this.botBlocked.has(k)) continue;
        const first = cur.first ?? { c: nc, r: nr };
        if (nc === target.c && nr === target.r) return first;
        seen.add(k);
        q.push({ c: nc, r: nr, first });
      }
    }
    return null;
  }

  // ---------------------------------------------------------------- 玩法
  private entAt(c: number, r: number): Ent | undefined {
    return this.ents.find((e) => e.alive && e.c === c && e.r === r);
  }

  private step(dc: number, dr: number) {
    if (this.ended) return;
    const nc = this.player.c + dc;
    const nr = this.player.r + dr;
    if (nc < 0 || nr < 0 || nc >= GRID.cols || nr >= GRID.rows) return;

    const here = this.entAt(nc, nr);
    if (here?.kind === 'rock') {
      this.botBlocked.add(`${nc},${nr}`);
      this.audio.play('gameplay_block', { priority: 'low' });
      this.bus.emit(GAME_EVENTS.PLAYER_ACTION, {
        intensity: 0.2, context: { blocked: true, x: this.cx(nc), y: this.cy(nr) },
      }, 120);
      return;
    }
    if (here?.kind === 'wraith') {
      this.hurt('walked_into');
      return;
    }

    this.player = { c: nc, r: nr };
    this.tweens.add({
      targets: this.boat,
      x: this.cx(nc),
      y: this.cy(nr),
      duration: JUICE.moveTweenMs,
      ease: 'Quad.easeOut',
    });
    this.audio.play('gameplay_move', { priority: 'low' });

    if (here?.kind === 'soul') {
      here.alive = false;
      here.spr.destroy();
      this.carried = 1;
      this.bus.emit(GAME_EVENTS.ITEM_COLLECTED, {
        intensity: 0.5,
        context: { x: this.cx(nc), y: this.cy(nr), soul: true },
      });
    }

    if (nc === DOCK.c && nr === DOCK.r && this.carried > 0) {
      this.deliver();
    }
  }

  private deliver() {
    this.carried = 0;
    this.delivered += 1;
    // 送达的回馈：多一格记忆（世界记得你做过什么）
    // 必须封顶：记忆稀缺是本作的核心张力，突破上限会让玩家无限续杯
    this.memory = Math.min(this.cfg.memoryMax ?? ECHO.memoryMax, this.memory + 1);
    this.audio.play('feedback_levelup', { priority: 'high' });
    this.bus.emit('soul_delivered', {
      intensity: 0.8,
      context: { delivered: this.delivered, total: this.totalSouls, x: this.cx(DOCK.c), y: this.cy(DOCK.r) },
    });
    if (this.delivered >= this.totalSouls) {
      this.finish(true);
    }
  }

  private hurt(reason: string) {
    if (this.time.now < this.invulnUntil || this.ended) return;
    this.invulnUntil = this.time.now + RULES.invulnMs;
    this.hull -= 1;
    // 抓住你的那个幽影被甩到边缘：否则它会贴脸连击，失败变成连锁反应
    const catcher = this.ents.find(
      (e) => e.kind === 'wraith' && e.alive && e.c === this.player.c && e.r === this.player.r,
    );
    if (catcher) {
      const spots: Pt[] = [];
      for (let c = 0; c < GRID.cols; c++) {
        spots.push({ c, r: 0 }, { c, r: GRID.rows - 1 });
      }
      for (let r = 1; r < GRID.rows - 1; r++) {
        spots.push({ c: 0, r }, { c: GRID.cols - 1, r });
      }
      const far = spots
        .filter((p) => Math.abs(p.c - this.player.c) + Math.abs(p.r - this.player.r) >= 5)
        .filter((p) => !this.entAt(p.c, p.r));
      const pick = far[(this.hull * 7 + this.delivered * 3) % Math.max(1, far.length)] ?? spots[0];
      catcher.c = pick.c;
      catcher.r = pick.r;
      catcher.spr.setPosition(this.cx(pick.c), this.cy(pick.r));
    }
    this.audio.play('feedback_hurt', { priority: 'high' });
    this.bus.emit(GAME_EVENTS.PLAYER_HIT, {
      intensity: 0.75,
      context: { reason, x: this.cx(this.player.c), y: this.cy(this.player.r), hull: this.hull },
    });
    this.audio.setState(this.hull <= 1 ? 'critical' : 'danger');
    this.cameras.main.flash(160, 198, 70, 60, false);
    if (this.hull <= 0) this.finish(false);
  }

  /** 敲钟：本作的核心动作。信息与风险是同一枚硬币。 */
  private ping() {
    if (this.ended) return;
    if (this.memory <= 0) {
      this.audio.play('gameplay_block', { priority: 'low' });
      this.hudHint.setText('没有记忆了 —— 只能靠听');
      return;
    }
    this.memory -= 1;
    this.revealUntil = this.time.now + (this.cfg.revealMs ?? ECHO.revealMs);

    this.audio.play('gameplay_cast', { priority: 'high' });
    this.bus.emit('echo_ping', {
      intensity: 0.6,
      source: 'player',
      context: { x: this.cx(this.player.c), y: this.cy(this.player.r), memory: this.memory },
    });

    // 水纹扩散
    const ripple = this.add
      .image(this.cx(this.player.c), this.cy(this.player.r), TEXTURES.ripple)
      .setDepth(6)
      .setAlpha(0.9)
      .setScale(0.12);
    this.tweens.add({
      targets: ripple,
      scale: 0.78,
      alpha: 0,
      duration: JUICE.pingRippleMs,
      ease: 'Quad.easeOut',
      onComplete: () => ripple.destroy(),
    });

    // 揭示 + 留残影
    const R = ECHO.revealRadius;
    for (const e of this.ents) {
      if (!e.alive) continue;
      const d = Math.max(Math.abs(e.c - this.player.c), Math.abs(e.r - this.player.r));
      if (d <= R) {
        e.spr.setAlpha(e.kind === 'rock' ? 0.85 : 1);
        if (e.kind === 'rock') this.botBlocked.add(`${e.c},${e.r}`);
        if (e.kind === 'soul') this.botKnownSouls.add(`${e.c},${e.r}`);
        this.pushGhost(e);
      }
    }

    // 暴露：半径内的东西朝你走一步（这一步是「敲钟的代价」）
    let exposed = 0;
    for (const e of this.ents) {
      if (e.kind !== 'wraith' || !e.alive) continue;
      const d = Math.max(Math.abs(e.c - this.player.c), Math.abs(e.r - this.player.r));
      if (d <= ECHO.exposeRadius) {
        this.moveWraithToward(e);
        exposed += 1;
      }
    }
    if (exposed > 0) {
      this.bus.emit(GAME_EVENTS.ENEMY_SPAWN, {
        intensity: 0.35, context: { exposed, silent: true },
      }, 200);
    }

    if (this.memory <= 0) {
      // 标志性时刻：整片海同时熄灭
      this.bus.emit('memory_empty', {
        intensity: 0.95,
        context: { ghosts: this.ghosts.length, x: this.cx(this.player.c), y: this.cy(this.player.r) },
      });
      this.audio.play('feedback_boss', { priority: 'high' });
      this.audio.setState('critical');
      for (const g of this.ghosts) {
        this.tweens.add({ targets: g.spr, alpha: 0, duration: 600, onComplete: () => g.spr.destroy() });
      }
      this.ghosts = [];
      for (const e of this.ents) e.spr.setAlpha(0);
      this.hudHint.setText('记忆用尽了。听。');
    }
    this.refreshHud();
  }

  private pushGhost(e: Ent) {
    const spr = this.add
      .image(this.cx(e.c), this.cy(e.r), e.spr.texture.key)
      .setDepth(2)
      .setScale(SPRITE_SCALE[e.kind])
      .setAlpha(e.kind === 'rock' ? 0.3 : 0.55)
      .setTint(e.kind === 'soul' ? COLORS.accent2 : e.kind === 'wraith' ? COLORS.danger : 0x88aabb);
    const g: Ghost = {
      kind: e.kind,
      c: e.c,
      r: e.r,
      bornAt: this.time.now,
      spr,
    };
    this.ghosts.push(g);
    if (this.ghosts.length > 24) {
      const old = this.ghosts.shift();
      old?.spr.destroy();
    }
  }

  private moveWraithToward(e: Ent) {
    const dc = Math.sign(this.player.c - e.c);
    const dr = Math.sign(this.player.r - e.r);
    const cands: Array<[number, number]> = [];
    if (Math.abs(this.player.c - e.c) >= Math.abs(this.player.r - e.r)) {
      cands.push([dc, 0], [0, dr]);
    } else {
      cands.push([0, dr], [dc, 0]);
    }
    for (const [dx, dy] of cands) {
      if (dx === 0 && dy === 0) continue;
      const nc = e.c + dx;
      const nr = e.r + dy;
      if (nc < 0 || nr < 0 || nc >= GRID.cols || nr >= GRID.rows) continue;
      const occ = this.entAt(nc, nr);
      if (occ && occ !== e) continue;
      e.c = nc;
      e.r = nr;
      this.tweens.add({
        targets: e.spr,
        x: this.cx(nc),
        y: this.cy(nr),
        duration: 180,
        ease: 'Quad.easeOut',
      });
      if (nc === this.player.c && nr === this.player.r) this.hurt('caught');
      return;
    }
  }

  private refreshHud() {
    const memText = `记忆 ${this.memory}`;
    if (memText !== this.lastMemText) {
      this.lastMemText = memText;
      this.hudTop.setText(`送达 ${this.delivered}/${this.totalSouls}`);
      this.pingLabel.setText(this.memory > 0 ? '敲钟' : '无光');
    }
    // 槽位一直画着，只改亮度：已用掉的变暗。隐藏会让玩家以为 UI 坏了。
    for (let i = 0; i < this.memPips.length; i++) {
      this.memPips[i].setFillStyle(i < this.memory ? COLORS.accent : 0x2a3140, 1);
    }
    for (let i = 0; i < this.hullPips.length; i++) {
      this.hullPips[i].setFillStyle(i < this.hull ? COLORS.danger : 0x2a3140, 1);
    }
  }

  private finish(win: boolean) {
    if (this.ended) return;
    this.ended = true;

    if (win) {
      this.audio.setState('victory');
      this.audio.play('feedback_win', { priority: 'high' });
      this.bus.emit(GAME_EVENTS.LEVEL_COMPLETED, {
        intensity: 1, context: { final: true, delivered: this.delivered },
      });
    } else {
      this.audio.setState('defeat');
      this.bus.emit(GAME_EVENTS.PLAYER_DEATH, {
        intensity: 1, context: { hull: 0, delivered: this.delivered },
      });
      this.audio.play('feedback_defeat', { priority: 'high' });
    }

    // 平台生命周期只上报一次：SDK 对 1 秒内的重复调用会 throttle 并打 console.error
    if (!this.stopped) {
      this.stopped = true;
      try {
        bridge(this).gameplayStop();
      } catch {
        /* 静默降级 */
      }
    }

    this.time.delayedCall(900, () => {
      this.scene.start('GameOver', {
        win,
        delivered: this.delivered,
        total: this.totalSouls,
        level: this.levelIdx,
      });
    });
  }

  update(_time: number, delta: number) {
    this.audio?.update(delta);
    this.juice?.update(delta);
    if (this.ended) return;

    // 记忆回复
    if (this.memoryRegenMs > 0) {
      this.memoryRegenMs -= delta;
      if (this.memoryRegenMs <= 0) {
        this.memoryRegenMs = this.cfg.memoryRegenMs ?? ECHO.memoryRegenMs;
        const cap = this.cfg.memoryMax ?? ECHO.memoryMax;
        if (this.memory < cap) {
          this.memory += 1;
          this.refreshHud();
        }
      }
    }

    // 幽影自行缓慢移动（不依赖敲钟 —— 所以残影一定会过期）
    this.wraithAcc += delta;
    if (this.wraithAcc >= (this.cfg.wraithStepMs ?? 2600)) {
      this.wraithAcc = 0;
      for (const e of this.ents) {
        if (e.kind === 'wraith' && e.alive) this.moveWraithToward(e);
      }
    }

    // 残影褪色
    const life = this.cfg.ghostLifeMs ?? ECHO.ghostLifeMs;
    const now = this.time.now;
    for (const g of this.ghosts) {
      const age = now - g.bornAt;
      const k = Math.max(0, 1 - age / life);
      g.spr.setAlpha(k * (g.kind === 'rock' ? 0.3 : 0.55));
    }

    // 揭示结束 → 全部重新沉入黑暗
    if (now >= this.revealUntil) {
      for (const e of this.ents) {
        if (e.alive && e.spr.alpha > 0) e.spr.setAlpha(0);
      }
    }

    // 状态机：危险 / 濒危
    let near = 99;
    for (const e of this.ents) {
      if (e.kind !== 'wraith' || !e.alive) continue;
      near = Math.min(near, Math.abs(e.c - this.player.c) + Math.abs(e.r - this.player.r));
    }
    if (this.memory <= 1 || this.hull <= 1) this.audio.setState('critical');
    else if (near <= 3) this.audio.setState('danger');
    else this.audio.setState('exploration');

    this.refreshHud();
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
    for (const g of this.ghosts) g.spr.destroy();
    this.ghosts = [];
  }
}

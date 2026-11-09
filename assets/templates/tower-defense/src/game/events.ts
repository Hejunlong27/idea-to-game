/**
 * 统一游戏事件系统（Game Event Bus）。
 *
 * 为什么需要它 —— 没有它的时候，同一个「玩家受伤」会由玩法代码分别调用
 * 镜头震动、粒子、音效、UI 更新四遍，四处各写一遍且强度不一致；
 * 想做「表现强度按事件严重度分级」时无从下手。
 *
 * 有了它之后：玩法只 `bus.emit('player_hit', {...})`，
 * 动画（juice.ts）、音频（audio.ts）、UI、埋点、自动化测试**各自订阅**同一件事。
 *
 * 硬规则（见 references/game-event-schema.md）：
 *   1. 事件只描述「发生了什么」，不描述「应该怎么表现」—— 表现层订阅，不反向修改逻辑
 *   2. 事件系统**不消耗随机数**，保证游戏逻辑的确定性
 *   3. 场景 shutdown 必须 `bus.clear()`，否则监听器会跨场景泄漏
 *   4. 关键事件有类型化常量，避免拼错字符串导致「事件发了但没人收到」
 */

/** 统一事件结构。字段名与 references/game-event-schema.md 一致。 */
export interface GameEvent {
  /** 事件名，取自 GAME_EVENTS 或项目自定义 */
  event: string;
  /** 相对游戏开始的毫秒数（不是 Date.now()，保证可复现） */
  timestamp: number;
  /** 发起者：'player' | 'enemy' | 'system' | 'ui' */
  source: string;
  /** 承受者，无则空串 */
  target: string;
  /** 严重度 0..1，表现层据此分级（0.2 微反馈 / 0.5 轻 / 0.75 中 / 0.9 重） */
  intensity: number;
  /** 附加数据：坐标、数值、状态等。只读语义，表现层不得改写 */
  context: Record<string, unknown>;
}

export type EventHandler = (e: GameEvent) => void;

interface Sub {
  fn: EventHandler;
  priority: number;
  once: boolean;
}

/** 标准事件名。项目可以扩展，但核心这些不要改名（审核与自动化测试依赖它们）。 */
export const GAME_EVENTS = {
  GAME_START: 'game_start',
  GAME_PAUSED: 'game_paused',
  GAME_RESUMED: 'game_resumed',
  GAME_OVER: 'game_over',
  PLAYER_MOVE: 'player_move',
  PLAYER_HIT: 'player_hit',
  PLAYER_DEATH: 'player_death',
  PLAYER_ACTION: 'player_action',
  ENEMY_SPAWN: 'enemy_spawn',
  ENEMY_DEFEATED: 'enemy_defeated',
  ITEM_COLLECTED: 'item_collected',
  LEVEL_STARTED: 'level_started',
  LEVEL_COMPLETED: 'level_completed',
  BOSS_APPEARED: 'boss_appeared',
  BOSS_DEFEATED: 'boss_defeated',
  STORY_REVEAL: 'story_reveal',
  SECRET_FOUND: 'secret_found',
  RESOURCE_CHANGED: 'resource_changed',
  STATE_CHANGED: 'state_changed',
} as const;

/** 默认严重度。emit 未显式给 intensity 时用它，保证同类事件强度一致。 */
const DEFAULT_INTENSITY: Record<string, number> = {
  game_start: 0.5,
  game_over: 0.9,
  player_move: 0.1,
  player_action: 0.35,
  player_hit: 0.7,
  player_death: 1.0,
  enemy_spawn: 0.3,
  enemy_defeated: 0.6,
  item_collected: 0.25,
  level_started: 0.5,
  level_completed: 0.9,
  boss_appeared: 0.85,
  boss_defeated: 1.0,
  story_reveal: 0.6,
  secret_found: 0.55,
  resource_changed: 0.2,
  state_changed: 0.3,
};

export interface EmitOptions {
  source?: string;
  target?: string;
  intensity?: number;
  context?: Record<string, unknown>;
}

export class EventBus {
  private subs = new Map<string, Sub[]>();
  private anySubs: Sub[] = [];
  /** 去重窗口：同一事件在 windowMs 内只发一次（防止每帧触发的循环事件刷屏） */
  private lastFired = new Map<string, number>();
  /** 环形日志，供 QA / 试玩报告读取。容量固定，避免长局内存增长。 */
  private log: GameEvent[] = [];
  private readonly logCap = 400;
  private clock: () => number;
  private startAt = 0;
  private paused = false;
  private seq = 0;

  constructor(now: () => number = () => 0, startAt = 0) {
    this.clock = now;
    this.startAt = startAt;
  }

  /** 场景重启时重置时间原点（不清理订阅，用于同一场景重开） */
  resetClock(startAt: number) {
    this.startAt = startAt;
    this.lastFired.clear();
    this.log = [];
    this.seq = 0;
  }

  on(event: string, fn: EventHandler, priority = 0): () => void {
    const arr = this.subs.get(event) ?? [];
    arr.push({ fn, priority, once: false });
    arr.sort((a, b) => b.priority - a.priority);
    this.subs.set(event, arr);
    return () => this.off(event, fn);
  }

  once(event: string, fn: EventHandler, priority = 0): () => void {
    const arr = this.subs.get(event) ?? [];
    arr.push({ fn, priority, once: true });
    arr.sort((a, b) => b.priority - a.priority);
    this.subs.set(event, arr);
    return () => this.off(event, fn);
  }

  onAny(fn: EventHandler, priority = 0): () => void {
    this.anySubs.push({ fn, priority, once: false });
    this.anySubs.sort((a, b) => b.priority - a.priority);
    return () => {
      const i = this.anySubs.findIndex((s) => s.fn === fn);
      if (i >= 0) this.anySubs.splice(i, 1);
    };
  }

  off(event: string, fn: EventHandler) {
    const arr = this.subs.get(event);
    if (!arr) return;
    const i = arr.findIndex((s) => s.fn === fn);
    if (i >= 0) arr.splice(i, 1);
    if (!arr.length) this.subs.delete(event);
  }

  /**
   * 发事件。返回是否真的派发（被去重或暂停时返回 false）。
   * dedupeMs > 0 时，同名事件在该窗口内只派发一次。
   */
  emit(event: string, opts: EmitOptions = {}, dedupeMs = 0): boolean {
    if (this.paused && event !== GAME_EVENTS.GAME_RESUMED && event !== GAME_EVENTS.GAME_PAUSED) {
      return false;
    }
    const ts = Math.round(this.clock() - this.startAt);
    if (dedupeMs > 0) {
      const last = this.lastFired.get(event);
      if (last !== undefined && ts - last < dedupeMs) return false;
      this.lastFired.set(event, ts);
    }
    const ev: GameEvent = {
      event,
      timestamp: ts,
      source: opts.source ?? 'system',
      target: opts.target ?? '',
      intensity: clamp01(opts.intensity ?? DEFAULT_INTENSITY[event] ?? 0.5),
      context: opts.context ?? {},
    };
    this.seq += 1;

    const handlers = [...(this.subs.get(event) ?? [])];
    for (const s of handlers) {
      if (s.once) this.off(event, s.fn);
      safeCall(s.fn, ev);
    }
    for (const s of [...this.anySubs]) safeCall(s.fn, ev);

    this.log.push(ev);
    if (this.log.length > this.logCap) this.log.splice(0, this.log.length - this.logCap);
    return true;
  }

  pause() {
    this.paused = true;
    this.emit(GAME_EVENTS.GAME_PAUSED, { intensity: 0.3 });
  }

  resume() {
    this.paused = false;
    this.emit(GAME_EVENTS.GAME_RESUMED, { intensity: 0.3 });
  }

  /** 场景 shutdown 必须调用：清空全部订阅与日志，防止跨场景泄漏 */
  clear() {
    this.subs.clear();
    this.anySubs = [];
    this.lastFired.clear();
    this.log = [];
    this.paused = false;
  }

  /** 只读快照（供 QA / 试玩报告 / 调试面板） */
  snapshot(): readonly GameEvent[] {
    return this.log;
  }

  count(event?: string): number {
    return event ? this.log.filter((e) => e.event === event).length : this.log.length;
  }

  get eventCount(): number {
    return this.seq;
  }
}

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function safeCall(fn: EventHandler, ev: GameEvent) {
  try {
    fn(ev);
  } catch (err) {
    // 表现层抛错绝不能打断玩法循环（Phaser 里会整局冻结，且报错极难定位）
    console.warn('[events] 处理器异常，已忽略', ev.event, err);
  }
}

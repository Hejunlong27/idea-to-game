import Phaser from 'phaser';
import { GAME_EVENTS, type EventBus, type GameEvent } from './events';
import {
  JUICE_RULES,
  JUICE_SETTINGS,
  type EffectSpec,
  type JuiceRule,
} from './juice-config';

/**
 * Game Juice 引擎：把「事件」翻译成「表现」。
 *
 * 为什么需要它 —— v2 把 `camera.shake()` 直接写在 `PlayScene.hitTarget()` 里，
 * 换玩法就要重写一遍手感，而且所有事件用同一组 shake 参数（玩家分不清轻重）。
 *
 * 本模块的三条硬规则：
 *   1. **表现强度按事件严重度分级**，不是所有事件都全屏闪 + 大震动
 *   2. **动画不得影响游戏逻辑的确定性** —— hit stop / slow motion 只缩放 tween 时间，
 *      不碰 update() 里的逻辑步长
 *   3. **无障碍**：`prefers-reduced-motion` 时关闭震动/闪屏/缩放/慢动作，保留形变与粒子
 *
 * 所有效果都可配置（juice-config.ts 由 juice_forge.py 从 juice-plan.json 生成），
 * 并按设备性能降级（低端设备粒子减半、关闭视差）。
 */

export type Quality = 'high' | 'medium' | 'low';

interface ActiveEffect {
  kind: string;
  until: number;
}

export class JuiceDirector {
  private scene: Phaser.Scene;
  private bus: EventBus | null;
  private rules: JuiceRule[];
  private unsubs: Array<() => void> = [];
  private now = 0;
  private flashRect?: Phaser.GameObjects.Rectangle;
  private particleTex = 'juice_dot';
  private lastFlashAt = -1e9;
  private quality: Quality = 'high';
  private reduceMotion = false;
  /** Timed effects share one scale owner so overlapping callbacks cannot restore zero. */
  private tweenScaleRestore = 1;
  private hitStopUntil = 0;
  private slowMotionUntil = 0;
  private slowMotionScale = 0.35;
  private active: ActiveEffect[] = [];
  private counters = new Map<string, number>();
  private resolvedTarget: unknown = null;
  /** 供测试断言：实际触发过的效果序列 */
  readonly fired: string[] = [];

  constructor(scene: Phaser.Scene, bus: EventBus | null = null, quality: Quality = 'high') {
    this.scene = scene;
    this.bus = bus;
    this.rules = JUICE_RULES;
    this.quality = quality;
    this.reduceMotion = detectReduceMotion();
    this.tweenScaleRestore = scene.tweens.timeScale;
    this.ensureParticleTexture();
    this.ensureFlashLayer();
  }

  /** 允许游戏把「当前事件对应的对象」交给表现层（例如受击的那个敌人） */
  setTargetResolver(fn: () => unknown) {
    this.resolvedTargetResolver = fn;
  }
  private resolvedTargetResolver: (() => unknown) | null = null;

  attach() {
    if (!this.bus) return;
    this.unsubs.push(this.bus.onAny((e) => this.handle(e)));
  }

  private ensureParticleTexture() {
    if (this.scene.textures.exists(this.particleTex)) return;
    const g = this.scene.make.graphics({ x: 0, y: 0 }, false);
    g.fillStyle(0xffffff, 1);
    g.fillCircle(8, 8, 8);
    g.generateTexture(this.particleTex, 16, 16);
    g.destroy();
  }

  private ensureFlashLayer() {
    const cam = this.scene.cameras.main;
    this.flashRect = this.scene.add
      .rectangle(0, 0, cam.width, cam.height, 0xffffff, 0)
      .setOrigin(0, 0)
      .setScrollFactor(0)
      .setDepth(9999);
    this.flashRect.setActive(false);
  }

  private handle(e: GameEvent) {
    const rule = this.rules.find(
      (r) => r.event === e.event && e.intensity >= (r.minIntensity ?? 0),
    );
    if (!rule) return;
    for (const fx of rule.effects) this.apply(fx, e);
  }

  /** 外部也可以直接触发（用于不走事件系统的场景内联反馈） */
  trigger(event: string, intensity = 0.5, context: Record<string, unknown> = {}) {
    const e: GameEvent = {
      event,
      timestamp: Math.round(this.now),
      source: 'juice',
      target: '',
      intensity,
      context,
    };
    this.handle(e);
  }

  update(dt: number) {
    this.now += dt;
    this.active = this.active.filter((a) => a.until > this.now);
  }

  private pick<T>(key: string, arr: T[]): T {
    const n = (this.counters.get(key) ?? 0) + 1;
    this.counters.set(key, n);
    return arr[n % arr.length];
  }

  private scale(fx: EffectSpec, e: GameEvent): number {
    const s = fx.scale ?? 1;
    return Math.max(0, Math.min(1.5, s * (0.5 + e.intensity)));
  }

  private apply(fx: EffectSpec, e: GameEvent) {
    const k = this.scale(fx, e);
    this.fired.push(`${e.event}:${fx.type}`);
    switch (fx.type) {
      case 'squash_stretch':
        this.squash(k);
        break;
      case 'anticipation':
        this.anticipate(k, fx.durationMs ?? 60);
        break;
      case 'follow_through':
        this.followThrough(k);
        break;
      case 'secondary_motion':
        // 由场景自行维护（装饰元素持续微动），这里只记录
        break;
      case 'parallax':
        if (!this.reduceMotion && this.quality !== 'low') this.parallax(k);
        break;
      case 'particles':
        this.burst(e, fx, k);
        break;
      case 'environmental':
        break;
      case 'ui_motion':
        this.uiPulse(k);
        break;
      case 'camera_shake':
        if (!this.reduceMotion) this.shake(k);
        break;
      case 'camera_zoom':
        if (!this.reduceMotion) this.zoom(k);
        break;
      case 'hit_stop':
        this.hitStop(fx.durationMs ?? 70, k);
        break;
      case 'slow_motion':
        if (!this.reduceMotion) this.slowMotion(fx.durationMs ?? 400, k);
        break;
      case 'screen_flash':
        if (!this.reduceMotion) this.flash(fx.color ?? JUICE_SETTINGS.accentColor, k);
        break;
      case 'transition':
        this.transition(k);
        break;
      default:
        break;
    }
  }

  // ---------------------------------------------------------------- 效果实现
  private get target(): Phaser.GameObjects.GameObject | null {
    const t = this.resolvedTargetResolver ? this.resolvedTargetResolver() : this.resolvedTarget;
    return (t as Phaser.GameObjects.GameObject) ?? null;
  }

  private squash(k: number) {
    const obj = this.target as unknown as { scaleX: number; scaleY: number } | null;
    if (!obj) return;
    const baseX = obj.scaleX;
    const baseY = obj.scaleY;
    const amt = 0.18 * k;
    this.scene.tweens.add({
      targets: obj,
      scaleX: baseX * (1 + amt),
      scaleY: baseY * (1 - amt * 0.7),
      duration: 70,
      yoyo: true,
      ease: 'Quad.easeOut',
      onComplete: () => {
        obj.scaleX = baseX;
        obj.scaleY = baseY;
      },
    });
  }

  private anticipate(k: number, ms: number) {
    const obj = this.target as unknown as { x: number; y: number } | null;
    if (!obj) return;
    const dx = -6 * k;
    const x0 = obj.x;
    this.scene.tweens.add({
      targets: obj,
      x: x0 + dx,
      duration: ms,
      yoyo: true,
      ease: 'Quad.easeOut',
      onComplete: () => {
        obj.x = x0;
      },
    });
  }

  private followThrough(k: number) {
    const obj = this.target as unknown as { angle: number } | null;
    if (!obj) return;
    const a0 = obj.angle;
    this.scene.tweens.add({
      targets: obj,
      angle: a0 + 8 * k,
      duration: 140,
      delay: 40,
      yoyo: true,
      ease: 'Elastic.easeOut',
      onComplete: () => {
        obj.angle = a0;
      },
    });
  }

  private parallax(k: number) {
    const cam = this.scene.cameras.main;
    const dx = (k - 0.5) * 6;
    this.scene.tweens.add({ targets: cam, scrollX: cam.scrollX + dx, duration: 220, yoyo: true });
  }

  private burst(e: GameEvent, fx: EffectSpec, k: number) {
    const cam = this.scene.cameras.main;
    const ctx = e.context as { x?: number; y?: number };
    const x = typeof ctx.x === 'number' ? ctx.x : cam.width / 2;
    const y = typeof ctx.y === 'number' ? ctx.y : cam.height / 2;
    const base = fx.amount ?? 10;
    const qMul = this.quality === 'high' ? 1 : this.quality === 'medium' ? 0.6 : 0.3;
    const count = Math.max(2, Math.round(base * qMul * (0.6 + k)));
    const cap = Math.round(JUICE_SETTINGS.maxParticles * qMul);
    const color = hexToInt(fx.color ?? JUICE_SETTINGS.accentColor);
    const emitter = this.scene.add.particles(x, y, this.particleTex, {
      speed: { min: 40, max: 40 + 160 * k },
      angle: { min: 0, max: 360 },
      lifespan: { min: 220, max: 220 + 320 * k },
      scale: { start: 0.5 + 0.4 * k, end: 0 },
      alpha: { start: 0.9, end: 0 },
      quantity: Math.min(count, cap),
      tint: color,
      emitting: false,
      blendMode: 'ADD',
    });
    emitter.setDepth(900);
    emitter.explode(Math.min(count, cap));
    this.scene.time.delayedCall(700, () => {
      try {
        emitter.destroy();
      } catch {
        /* ignore */
      }
    });
  }

  private uiPulse(k: number) {
    const obj = this.target as unknown as { scaleX: number; scaleY: number } | null;
    if (!obj) return;
    const base = obj.scaleX;
    this.scene.tweens.add({
      targets: obj,
      scaleX: base * (1 + 0.1 * k),
      scaleY: base * (1 + 0.1 * k),
      duration: 90,
      yoyo: true,
      ease: 'Quad.easeOut',
    });
  }

  private shake(k: number) {
    const dur = Math.min(JUICE_SETTINGS.shakeMaxMs, 60 + 140 * k);
    const intensity = Math.min(JUICE_SETTINGS.shakeCap, 0.002 + 0.009 * k);
    this.scene.cameras.main.shake(dur, intensity);
  }

  private zoom(k: number) {
    const cam = this.scene.cameras.main;
    const z0 = cam.zoom;
    this.scene.tweens.add({
      targets: cam,
      zoom: z0 * (1 + 0.04 * k),
      duration: 140,
      yoyo: true,
      ease: 'Quad.easeOut',
      onComplete: () => {
        cam.zoom = z0;
      },
    });
  }

  /** 只冻结表现（tween），不动逻辑步长 —— 这样玩法判定与回放不受影响 */
  private hitStop(ms: number, k: number) {
    const dur = Math.max(20, Math.min(140, ms * (0.6 + k)));
    const now = this.scene.time.now;
    this.hitStopUntil = Math.max(this.hitStopUntil, now + dur);
    this.active.push({ kind: 'hit_stop', until: this.now + dur });
    this.applyTimedTweenScale();
    this.scheduleTimedTweenScaleRestore(this.hitStopUntil);
  }

  private slowMotion(ms: number, k: number) {
    const dur = Math.max(120, Math.min(700, ms * (0.7 + k)));
    const now = this.scene.time.now;
    this.slowMotionUntil = Math.max(this.slowMotionUntil, now + dur);
    this.active.push({ kind: 'slow_motion', until: this.now + dur });
    this.applyTimedTweenScale();
    this.scheduleTimedTweenScaleRestore(this.slowMotionUntil);
  }

  private applyTimedTweenScale() {
    const now = this.scene.time.now;
    if (now < this.hitStopUntil) {
      this.scene.tweens.timeScale = 0;
    } else if (now < this.slowMotionUntil) {
      this.scene.tweens.timeScale = this.slowMotionScale;
    } else {
      this.scene.tweens.timeScale = this.tweenScaleRestore;
    }
  }

  private scheduleTimedTweenScaleRestore(until: number) {
    const delay = Math.max(0, until - this.scene.time.now);
    this.scene.time.delayedCall(delay, () => this.applyTimedTweenScale());
  }

  private flash(color: string, k: number) {
    // 光敏性防护：每秒最多 1 次，硬上限不可配置
    if (this.now - this.lastFlashAt < 1000 / JUICE_SETTINGS.flashMaxPerSecond) return;
    this.lastFlashAt = this.now;
    if (!this.flashRect) return;
    this.flashRect.setFillStyle(hexToInt(color), 1);
    this.flashRect.setAlpha(Math.min(0.5, 0.12 + 0.35 * k));
    this.flashRect.setActive(true);
    this.scene.tweens.add({
      targets: this.flashRect,
      alpha: 0,
      duration: 180,
      ease: 'Quad.easeOut',
      onComplete: () => this.flashRect?.setActive(false),
    });
  }

  private transition(k: number) {
    if (this.reduceMotion) return;
    const cam = this.scene.cameras.main;
    cam.fadeOut(Math.round(120 + 180 * k), 8, 18, 28);
    cam.once('camerafadeoutcomplete', () => cam.fadeIn(160));
  }

  setQuality(q: Quality) {
    this.quality = q;
  }

  get qualityLevel(): Quality {
    return this.quality;
  }

  get reducedMotion(): boolean {
    return this.reduceMotion;
  }

  debugLines(): string[] {
    return [
      `juice: quality=${this.quality} reduceMotion=${this.reduceMotion}`,
      `effects fired: ${this.fired.length}`,
      `active: ${this.active.map((a) => a.kind).join(',') || '-'}`,
    ];
  }

  destroy() {
    for (const u of this.unsubs) {
      try {
        u();
      } catch {
        /* ignore */
      }
    }
    this.unsubs = [];
    try {
      this.flashRect?.destroy();
    } catch {
      /* ignore */
    }
    this.hitStopUntil = 0;
    this.slowMotionUntil = 0;
    this.scene.tweens.timeScale = this.tweenScaleRestore;
  }
}

function detectReduceMotion(): boolean {
  try {
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false;
  } catch {
    return false;
  }
}

function hexToInt(hex: string): number {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return Number.isFinite(n) ? n : 0xffffff;
}

export { GAME_EVENTS };

import Phaser from 'phaser';
import {
  AUDIO_BUS_GAINS,
  AUDIO_INITIAL_STATE,
  AUDIO_SFX_RULES,
  AUDIO_STATES,
  AUDIO_STEMS,
  type AudioStateCfg,
  type StemCfg,
} from './audio-config';
import { GAME_EVENTS, type EventBus, type GameEvent } from './events';

/**
 * 自适应音频运行时。
 *
 * v2 的问题：音频只有「文件」，没有「系统」—— 四个层只是四个文件夹，
 * 分层的意义在运行时不存在。本模块补上运行时：
 *
 *   1. **stem 分层**：所有状态共用同一组 stem，切换状态只改各轨音量
 *      （这样切换点听不出接缝，这是 stem 方案的全部好处）
 *   2. **状态机**：`setState('danger')` 后按 transitionMs 线性过渡
 *   3. **动态音效**：变体（音高/音量抖动）、去重、冷却、并发上限、优先级
 *   4. **距离衰减**：`playAt(key, x, y, listener)` 按距离算音量与声像
 *   5. **ducking**：关键音效播放时自动压低旋律与氛围，让反馈浮出来
 *   6. **调试模式**：`debugLines()` 返回当前状态 / 激活轨 / 最近事件 / 并发数
 *
 * 降级：任何资源缺失或 API 不可用时静默跳过，**绝不抛错打断玩法**。
 */

export interface PlayOptions {
  volume?: number;
  /** 半音偏移，用于同类音效变体 */
  detune?: number;
  bus?: 'sfx' | 'ui' | 'ambience';
  /** 高优先级音效会触发 ducking，且永不被并发上限挤掉 */
  priority?: 'low' | 'normal' | 'high';
}

interface ActiveVoice {
  sound: Phaser.Sound.BaseSound;
  key: string;
  startedAt: number;
  priority: 'low' | 'normal' | 'high';
}

export class AudioDirector {
  private scene: Phaser.Scene;
  private bus: EventBus | null;
  private stems: StemCfg[];
  private states: AudioStateCfg[];
  private current: Record<string, number> = {};
  private target: Record<string, number> = {};
  private stateId = '';
  private transitionMs = 800;
  private elapsed = 0;
  private stemSounds = new Map<string, Phaser.Sound.BaseSound>();
  private active: ActiveVoice[] = [];
  private lastPlayed = new Map<string, number>();
  private lastAnyPlay = 0;
  private duckUntil = 0;
  private duckAmount = 0;
  private muted = false;
  private busGains: Record<string, number> = { ...AUDIO_BUS_GAINS };
  private now = 0;
  private unsubs: Array<() => void> = [];
  private lastEvent = '';
  private recentEvents: string[] = [];
  private started = false;

  constructor(scene: Phaser.Scene, bus: EventBus | null = null) {
    this.scene = scene;
    this.bus = bus;
    this.stems = AUDIO_STEMS;
    this.states = AUDIO_STATES;
    for (const s of this.stems) {
      this.current[s.id] = 0;
      this.target[s.id] = s.defaultGain;
    }
  }

  /** 启动：把所有 stem 同时播起来（音量为 0），之后只调音量，不重新播放 */
  start(initialState = AUDIO_INITIAL_STATE) {
    if (this.started) return;
    this.started = true;
    for (const s of this.stems) {
      const snd = this.addLoop(s.key);
      if (snd) this.stemSounds.set(s.id, snd);
    }
    this.setState(initialState, true);
    if (this.bus) {
      // 事件 → 音频的默认联动（项目可以覆盖：再次 on 同名事件即可叠加）
      this.unsubs.push(this.bus.on(GAME_EVENTS.PLAYER_HIT, (e) => {
        this.play('feedback_hurt', { priority: 'high', volume: 0.5 + e.intensity * 0.4 });
      }));
      this.unsubs.push(this.bus.on(GAME_EVENTS.ITEM_COLLECTED, () => {
        this.play('feedback_score', { priority: 'normal' });
      }));
      this.unsubs.push(this.bus.on(GAME_EVENTS.LEVEL_COMPLETED, () => {
        this.setState('victory');
        this.play('feedback_win', { priority: 'high' });
      }));
      this.unsubs.push(this.bus.onAny((e) => {
        this.lastEvent = e.event;
        this.recentEvents.push(`${e.timestamp}ms ${e.event}`);
        if (this.recentEvents.length > 8) this.recentEvents.shift();
      }));
    }
  }

  private addLoop(key: string): Phaser.Sound.BaseSound | null {
    try {
      if (!this.scene.cache.audio.exists(key)) return null;
      const snd = this.scene.sound.add(key, { loop: true, volume: 0 });
      snd.play();
      return snd;
    } catch {
      return null;
    }
  }

  /** 切换音乐状态。只改各 stem 的目标音量，不换曲，所以没有接缝。 */
  setState(id: string, force = false) {
    if (!force && id === this.stateId) return;
    const st = this.states.find((s) => s.id === id);
    if (!st) return;
    this.stateId = id;
    this.transitionMs = Math.max(0, st.transitionMs);
    this.elapsed = 0;
    for (const s of this.stems) {
      this.target[s.id] = st.gains[s.id] ?? 0;
    }
  }

  get state(): string {
    return this.stateId;
  }

  /** 每帧调用。dt 单位毫秒。 */
  update(dt: number) {
    this.now += dt;
    const k = this.transitionMs <= 0 ? 1 : Math.min(1, dt / Math.max(1, this.transitionMs * 0.35));
    const ducking = this.now < this.duckUntil;
    for (const s of this.stems) {
      let goal = this.target[s.id] ?? 0;
      if (ducking && s.duckUnderSfx) goal *= 1 - this.duckAmount;
      const cur = this.current[s.id] ?? 0;
      const next = cur + (goal - cur) * k;
      this.current[s.id] = Math.abs(next - goal) < 0.002 ? goal : next;
      const snd = this.stemSounds.get(s.id);
      if (snd) {
        const v = this.muted ? 0 : this.current[s.id] * (this.busGains.music ?? 1) * (this.busGains.master ?? 1);
        this.setVolume(snd, v);
      }
    }
    // 回收已播完的音效
    this.active = this.active.filter((a) => {
      try {
        return a.sound.isPlaying;
      } catch {
        return false;
      }
    });
  }

  private setVolume(snd: Phaser.Sound.BaseSound, v: number) {
    try {
      (snd as unknown as { volume: number }).volume = Math.max(0, Math.min(1, v));
    } catch {
      /* 静默降级 */
    }
  }

  /**
   * 播放音效。返回是否真的播了（被冷却/并发上限拦下时返回 false，便于测试断言）。
   */
  play(key: string, opts: PlayOptions = {}): boolean {
    const priority = opts.priority ?? 'normal';
    // 1. 全局最小间隔：防止同一帧内一堆事件同时发声
    if (priority !== 'high' && this.now - this.lastAnyPlay < AUDIO_SFX_RULES.minIntervalMs) {
      return false;
    }
    // 2. 同名冷却：避免连续触发变成机关枪
    const last = this.lastPlayed.get(key);
    const cd = priority === 'high' ? AUDIO_SFX_RULES.sameCooldownMs * 0.5 : AUDIO_SFX_RULES.sameCooldownMs;
    if (last !== undefined && this.now - last < cd) return false;
    // 3. 并发上限
    const sameCount = this.active.filter((a) => a.key === key).length;
    if (sameCount >= AUDIO_SFX_RULES.maxPerSound) return false;
    if (this.active.length >= AUDIO_SFX_RULES.maxConcurrent) {
      const idx = this.active.findIndex((a) => a.priority === 'low');
      if (idx < 0) return false;
      try {
        this.active[idx].sound.stop();
      } catch {
        /* ignore */
      }
      this.active.splice(idx, 1);
    }
    if (!this.scene.cache.audio.exists(key)) return false;

    // 4. 变体：音高与音量抖动（确定性伪随机，不用 Math.random 以免影响逻辑复现）
    const v = this.variant(key);
    const detune = (v * 2 - 1) * AUDIO_SFX_RULES.pitchJitter;
    const gainDb = (this.variant(key + 'g') * 2 - 1) * AUDIO_SFX_RULES.gainJitterDb;
    const busGain = this.busGains[opts.bus ?? 'sfx'] ?? 1;
    const vol = (opts.volume ?? 1) * Math.pow(10, gainDb / 20) * busGain * (this.busGains.master ?? 1);

    try {
      const snd = this.scene.sound.add(key, { volume: this.muted ? 0 : Math.min(1, vol) });
      if (opts.detune !== undefined || detune !== 0) {
        const rate = Math.pow(2, ((opts.detune ?? 0) + detune) / 12);
        try {
          (snd as unknown as { setRate?: (r: number) => void }).setRate?.(rate);
        } catch {
          /* 通道不支持 rate 时忽略 */
        }
      }
      snd.play();
      this.active.push({ sound: snd, key, startedAt: this.now, priority });
      this.lastPlayed.set(key, this.now);
      this.lastAnyPlay = this.now;
      // 5. 关键音效触发 ducking：让反馈从音乐里浮出来
      if (priority === 'high') {
        this.duckUntil = this.now + 600;
        this.duckAmount = 0.45;
      }
      return true;
    } catch {
      return false;
    }
  }

  /** 确定性伪随机（0..1）：同一 key + 同一调用次数得到同一结果 */
  private counters = new Map<string, number>();
  private variant(key: string): number {
    const n = (this.counters.get(key) ?? 0) + 1;
    this.counters.set(key, n);
    let h = 2166136261;
    const s = `${key}#${n}`;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return ((h >>> 0) % 10000) / 10000;
  }

  /** 按距离衰减播放（用于世界空间音效） */
  playAt(key: string, x: number, y: number, listenerX: number, listenerY: number, opts: PlayOptions = {}): boolean {
    const d = AUDIO_SFX_RULES.distance;
    if (!d.enabled) return this.play(key, opts);
    const dist = Math.hypot(x - listenerX, y - listenerY);
    if (dist > d.maxDistance) return false;
    const att = d.refDistance / (d.refDistance + d.rolloff * Math.max(0, dist - d.refDistance * 0.25));
    return this.play(key, { ...opts, volume: (opts.volume ?? 1) * Math.max(0.05, Math.min(1, att)) });
  }

  setMuted(m: boolean) {
    this.muted = m;
    if (m) {
      for (const snd of this.stemSounds.values()) this.setVolume(snd, 0);
    }
  }

  get isMuted() {
    return this.muted;
  }

  setBusGain(bus: string, v: number) {
    this.busGains[bus] = Math.max(0, Math.min(1, v));
  }

  /** 调试面板内容：当前状态 / 各轨音量 / 最近事件 / 并发数 */
  debugLines(): string[] {
    const stems = this.stems
      .map((s) => `${s.id.slice(0, 4)} ${(this.current[s.id] ?? 0).toFixed(2)}`)
      .join('  ');
    return [
      `music: ${this.stateId}  (${this.states.find((s) => s.id === this.stateId)?.zh ?? '-'})`,
      `stems: ${stems}`,
      `voices: ${this.active.length}/${AUDIO_SFX_RULES.maxConcurrent}  duck: ${this.now < this.duckUntil ? 'on' : 'off'}`,
      `last: ${this.lastEvent || '-'}`,
      `muted: ${this.muted}`,
    ];
  }

  /** 供自动化测试读取的只读快照 */
  snapshot() {
    return {
      state: this.stateId,
      gains: { ...this.current },
      voices: this.active.length,
      muted: this.muted,
      events: this.recentEvents.slice(),
    };
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
    for (const snd of this.stemSounds.values()) {
      try {
        snd.stop();
        snd.destroy();
      } catch {
        /* ignore */
      }
    }
    this.stemSounds.clear();
    for (const a of this.active) {
      try {
        a.sound.stop();
      } catch {
        /* ignore */
      }
    }
    this.active = [];
  }
}

/** 便于场景使用的简写：从 registry 取（与 platform bridge 同一模式） */
export function audioOf(scene: Phaser.Scene): AudioDirector | null {
  return (scene.registry.get('audio') as AudioDirector) ?? null;
}

export type { GameEvent };

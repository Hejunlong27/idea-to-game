/**
 * Telemetry —— 真人试玩的操作记录。
 *
 * ## 它和 bot 试玩的分工
 *
 *   `scripts/playtest.mjs`  用策略机器人跑，回答「能不能过」
 *   本模块                   记录真人操作，回答「**人会不会玩**」
 *
 * bot 永远知道该干什么，所以它测不出「新手进来不知道该点哪」。
 * 真人试玩的核心价值是暴露这类问题，前提是**把操作记下来**。
 *
 * ## 开关
 *
 * URL 带 `?playtest=1` 才记录。正常游玩零开销、零上报。
 *
 * ## 记录什么（以及为什么）
 *
 * | 事件 | 用来回答 |
 * |---|---|
 * | `scene_start` | 进关时刻，作为所有延迟的基准 |
 * | `first_build` | 从进关到第一座塔的秒数 → **引导有没有用** |
 * | `click` | 点击位置与间隔 → 点在哪、犹豫多久 |
 * | `build` / `upgrade` / `sell` | 决策序列 → 玩家的策略倾向 |
 * | `wave_clear` | 每波耗时 → 节奏曲线 |
 * | `leak` | 漏怪时刻 → 从第几波开始崩 |
 * | `game_over` | 结局与总时长 → 劝退点 |
 * | `idle_gap` | 超过 5 秒无操作 → **卡住/困惑的信号** |
 *
 * ## 导出
 *
 * 结束时自动下载 `playtest-<时间戳>.json`。也可以在控制台调
 * `window.__telemetry.dump()` 手动取。
 *
 * 为什么用下载而不是上报服务：真人试玩通常只有几次，起一个后端不值得。
 * 下载下来的 JSON 交给 `scripts/playtest_report.mjs` 分析。
 */

export interface TelemetryEvent {
  /** 相对进关的毫秒数 */
  t: number;
  type: string;
  data?: Record<string, unknown>;
}

export interface TelemetryDump {
  version: 1;
  startedAt: string;
  durationMs: number;
  game: string;
  events: TelemetryEvent[];
  summary: {
    clicks: number;
    builds: number;
    firstBuildSec: number | null;
    longestIdleSec: number;
    leaks: number;
    waveReached: number;
    outcome: string;
  };
}

const IDLE_THRESHOLD_MS = 5000;

export class Telemetry {
  private events: TelemetryEvent[] = [];
  private t0 = 0;
  private startedAt = '';
  private lastActionAt = 0;
  private longestIdleMs = 0;
  private enabled = false;
  private gameName = '';
  private finished = false;

  constructor(gameName: string) {
    this.gameName = gameName;
    this.enabled = Telemetry.isPlaytestMode();
    if (this.enabled) this.installGlobal();
  }

  static isPlaytestMode(): boolean {
    try {
      return new URLSearchParams(window.location.search).has('playtest');
    } catch {
      return false;
    }
  }

  get active(): boolean {
    return this.enabled;
  }

  /** 进关时调用，重置计时 */
  start(): void {
    if (!this.enabled) return;
    this.t0 = performance.now();
    this.startedAt = new Date().toISOString();
    this.lastActionAt = this.t0;
    this.events = [];
    this.longestIdleMs = 0;
    this.finished = false;
    this.record('scene_start');
  }

  record(type: string, data?: Record<string, unknown>): void {
    if (!this.enabled || this.finished) return;
    const now = performance.now();

    // 空闲检测：上一次操作到现在超过阈值，补一条记录
    // 这是「卡住」最直接的信号——玩家盯着屏幕不动，通常是在找该点哪
    if (type !== 'idle_gap' && this.lastActionAt > 0) {
      const gap = now - this.lastActionAt;
      if (gap > IDLE_THRESHOLD_MS && gap > this.longestIdleMs) {
        this.longestIdleMs = gap;
        this.events.push({ t: Math.round(this.lastActionAt - this.t0), type: 'idle_gap', data: { ms: Math.round(gap) } });
      }
    }
    this.lastActionAt = now;
    this.events.push({ t: Math.round(now - this.t0), type, data });
  }

  dump(): TelemetryDump {
    const counts = (t: string) => this.events.filter((e) => e.type === t).length;
    const firstBuild = this.events.find((e) => e.type === 'first_build');
    const lastWave = [...this.events].reverse().find((e) => e.type === 'wave_clear');
    const over = [...this.events].reverse().find((e) => e.type === 'game_over');

    return {
      version: 1,
      startedAt: this.startedAt,
      durationMs: Math.round(performance.now() - this.t0),
      game: this.gameName,
      events: this.events,
      summary: {
        clicks: counts('click'),
        builds: counts('build'),
        firstBuildSec: firstBuild ? Math.round(firstBuild.t / 100) / 10 : null,
        longestIdleSec: Math.round(this.longestIdleMs / 100) / 10,
        leaks: counts('leak'),
        waveReached: Number((lastWave?.data?.wave as number) ?? 0),
        outcome: String(over?.data?.outcome ?? 'incomplete'),
      },
    };
  }

  /** 结束时调用：落盘一次，之后不再记录 */
  finish(outcome: string): void {
    if (!this.enabled || this.finished) return;
    this.record('game_over', { outcome });
    this.finished = true;
    this.download();
  }

  private download(): void {
    try {
      const dump = this.dump();
      const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `playtest-${Date.now()}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      console.info('[telemetry] 已导出试玩数据', dump.summary);
    } catch (e) {
      console.warn('[telemetry] 导出失败', e);
    }
  }

  private installGlobal(): void {
    const w = window as unknown as Record<string, unknown>;
    w.__telemetry = {
      dump: () => this.dump(),
      record: (t: string, d?: Record<string, unknown>) => this.record(t, d),
      active: true,
    };
  }
}

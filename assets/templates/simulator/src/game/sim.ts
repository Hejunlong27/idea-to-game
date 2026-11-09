import ACTIONS from './content/actions.json';
import EVENTS from './content/events.json';
import STAGES from './content/stages.json';
import { SIM } from './config';

/**
 * 模拟器纯逻辑层 —— 不 import Phaser，不碰渲染。
 *
 * 为什么模拟器品类必须把逻辑抽出来：
 *   这类游戏的价值在「数值与选择的因果关系」，而不是画面。
 *   一旦逻辑和 UI 缠在一起，「这个选项到底扣了多少」就只能靠眼睛看，
 *   既测不了也调不了平衡。
 *
 * 三条硬规则：
 *   1. **确定性**：随机数由 (seed, turn, salt) 哈希得出，不调 Math.random。
 *      同 seed 同操作序列必然得到同一结果 —— 否则测试无法复现，平衡也无法回滚。
 *   2. **不可变**：每个函数返回新 state，不改入参。回放/存档/撤销都依赖这一点。
 *   3. **数据驱动**：行动 / 事件 / 境界全在 content/*.json。换主题不改本文件。
 */

export interface Effect {
  stat: string;
  delta: number;
}

export interface Requirement {
  stat: string;
  min?: number;
  max?: number;
}

export interface ActionDef {
  id: string;
  name: string;
  desc: string;
  effects: Effect[];
  require?: Requirement[];
  risk?: { chance: number; effects: Effect[] };
}

export interface EventOption {
  text: string;
  effects: Effect[];
}

export interface EventDef {
  id: string;
  title: string;
  text: string;
  weight: number;
  require?: Requirement[];
  options: EventOption[];
}

export interface StageDef {
  id: string;
  name: string;
  qiMin: number;
  lifespanBonus: number;
}

export const ACTION_LIST = ACTIONS.actions as ActionDef[];
export const EVENT_LIST = EVENTS.events as EventDef[];
export const STAGE_LIST = STAGES.stages as StageDef[];

/** 属性表。用 Record 而不是固定接口：炒股/家族换一套属性名也能跑。 */
export type Stats = Record<string, number>;

export interface SimState {
  seed: number;
  turn: number;
  stats: Stats;
  /** 当前境界索引 */
  stage: number;
  ended: boolean;
  endReason: string;
  /** 最近若干条日志，新在前 */
  log: string[];
  /** 待玩家选择的事件。非 null 时不允许执行行动 */
  pending: EventDef | null;
  /** 覆盖 config 的事件触发概率（测试用；undefined 表示走 SIM.eventChance） */
  eventChance?: number;
  /** 本回合强制触发的事件 id（测试/剧情用，触发后自动清空） */
  forcedEvent?: string;
}

/**
 * 确定性随机：同 (seed, turn, salt) 永远同值。
 *
 * 不用 `Math.random()` 也不维护 PRNG 内部状态 —— 那样「第 7 回合的结果」
 * 依赖之前调了几次随机，回放和测试都会变得不可控。
 */
export function hashRand(seed: number, turn: number, salt: number): number {
  let h = (seed ^ Math.imul(turn, 0x9e3779b1) ^ Math.imul(salt, 0x85ebca6b)) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x7feb352d) >>> 0;
  h = Math.imul(h ^ (h >>> 15), 0x846ca68b) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function createState(seed = 1): SimState {
  return {
    seed,
    turn: 0,
    stats: { ...SIM.startStats },
    stage: 0,
    ended: false,
    endReason: '',
    log: ['你踏上了修行路。'],
    pending: null,
  };
}

/** 属性下限/上限。灵石与修为不能为负，心境锁在 0–100。 */
function clampStats(stats: Stats): Stats {
  const out = { ...stats };
  for (const k of Object.keys(out)) {
    if (k === 'mood') out[k] = Math.max(0, Math.min(100, out[k]));
    else out[k] = Math.max(0, out[k]);
  }
  return out;
}

function applyEffects(stats: Stats, effects: Effect[]): Stats {
  const next = { ...stats };
  for (const e of effects) {
    next[e.stat] = (next[e.stat] ?? 0) + e.delta;
  }
  return clampStats(next);
}

export function meetsRequire(stats: Stats, req?: Requirement[]): boolean {
  if (!req || req.length === 0) return true;
  for (const r of req) {
    const v = stats[r.stat] ?? 0;
    if (r.min !== undefined && v < r.min) return false;
    if (r.max !== undefined && v > r.max) return false;
  }
  return true;
}

export function stageDef(stage: number): StageDef {
  return STAGE_LIST[Math.max(0, Math.min(STAGE_LIST.length - 1, stage))];
}

/**
 * 境界突破：达到门槛即升，不消耗修为。
 * 用 while 而不是 if —— 一次加很多修为时可能连跳两级。
 */
function tryBreakthrough(state: SimState, log: string[]): SimState {
  let stage = state.stage;
  let lifespan = state.stats.lifespan;
  let changed = false;
  while (stage + 1 < STAGE_LIST.length && state.stats.qi >= STAGE_LIST[stage + 1].qiMin) {
    stage += 1;
    lifespan += STAGE_LIST[stage].lifespanBonus;
    log.push(`突破至${STAGE_LIST[stage].name}，寿元 +${STAGE_LIST[stage].lifespanBonus}。`);
    changed = true;
  }
  if (!changed) return state;
  return {
    ...state,
    stage,
    stats: { ...state.stats, lifespan },
  };
}

function checkEnd(state: SimState, log: string[]): SimState {
  if (state.ended) return state;
  if (state.stats.age >= state.stats.lifespan) {
    log.push(`寿元耗尽，止步于${stageDef(state.stage).name}。`);
    return { ...state, ended: true, endReason: 'lifespan' };
  }
  return state;
}

function pushLog(state: SimState, lines: string[]): string[] {
  const merged = [...lines.reverse(), ...state.log];
  return merged.slice(0, SIM.maxLog);
}

/** 按权重抽一个符合条件的事件。没有可用事件时返回 null。 */
export function pickEvent(state: SimState): EventDef | null {
  const pool = EVENT_LIST.filter((e) => meetsRequire(state.stats, e.require));
  if (!pool.length) return null;
  const total = pool.reduce((a, e) => a + e.weight, 0);
  let r = hashRand(state.seed, state.turn, 0x51ed) * total;
  for (const e of pool) {
    r -= e.weight;
    if (r <= 0) return e;
  }
  return pool[pool.length - 1];
}

export interface StepResult {
  state: SimState;
  /** 本次结算产生的日志（供 UI 高亮） */
  lines: string[];
  /** 行动是否真的执行了（require 不满足时为 false） */
  applied: boolean;
}

/**
 * 执行一个回合。
 *
 * 顺序很重要：**先结算行动 → 再涨年龄 → 再判突破 → 再判结束 → 最后抽事件**。
 * 如果先涨年龄再结算，玩家会在「寿元已尽」的那一回合还能行动一次。
 */
export function applyAction(state: SimState, actionId: string): StepResult {
  if (state.ended) return { state, lines: [], applied: false };
  if (state.pending) return { state, lines: ['先处理眼前的事。'], applied: false };

  const action = ACTION_LIST.find((a) => a.id === actionId);
  if (!action) return { state, lines: [`未知行动 ${actionId}`], applied: false };
  if (!meetsRequire(state.stats, action.require)) {
    return { state, lines: [`${action.name}：条件不足。`], applied: false };
  }

  const lines: string[] = [];
  let stats = applyEffects(state.stats, action.effects);
  lines.push(`${action.name}：${describeDelta(state.stats, stats)}`);

  // 风险判定：命中则追加负面效果
  if (action.risk && hashRand(state.seed, state.turn, 0x7a1) < action.risk.chance) {
    stats = applyEffects(stats, action.risk.effects);
    lines.push(`意外：${describeDelta(state.stats, stats)}`);
  }

  stats = { ...stats, age: stats.age + 1 };

  // 注意：这里先不写 log，等 breakthrough / checkEnd 往 lines 里补完再统一 push，
  // 否则同一条行动日志会被写两遍（曾因此让日志区出现重复条目）。
  let next: SimState = { ...state, stats, turn: state.turn + 1 };
  next = tryBreakthrough(next, lines);
  next = checkEnd(next, lines);

  // 结束的回合不再抽事件：否则玩家在「已寿终」的面板上还要点一次选项
  const chance = next.eventChance ?? SIM.eventChance;
  const forced = next.forcedEvent ? EVENT_LIST.find((e) => e.id === next.forcedEvent) : undefined;
  if (!next.ended && (forced || hashRand(next.seed, next.turn, 0x9c1) < chance)) {
    const ev = forced ?? pickEvent(next);
    if (ev) next = { ...next, pending: ev, forcedEvent: undefined };
  }

  return { state: { ...next, log: pushLog(state, lines) }, lines, applied: true };
}

/** 处理待选事件。optionIndex 越界时取第 0 项（UI 不该传错，但不能崩）。 */
export function resolveEvent(state: SimState, optionIndex: number): StepResult {
  if (!state.pending) return { state, lines: [], applied: false };
  const ev = state.pending;
  const opt = ev.options[optionIndex] ?? ev.options[0];
  const lines: string[] = [`${ev.title}：${opt.text}`];

  let stats = applyEffects(state.stats, opt.effects);
  lines.push(describeDelta(state.stats, stats));

  let next: SimState = { ...state, stats, pending: null };
  next = tryBreakthrough(next, lines);
  next = checkEnd(next, lines);
  next = { ...next, log: pushLog(next, lines) };
  return { state: next, lines, applied: true };
}

/** 生成「修为 +8、心境 -2」这样的可读描述。只列出真正变化的属性。 */
export function describeDelta(before: Stats, after: Stats): string {
  const names: Record<string, string> = {
    qi: '修为',
    stones: '灵石',
    mood: '心境',
    age: '年龄',
    lifespan: '寿元',
  };
  const parts: string[] = [];
  for (const k of Object.keys(after)) {
    if (k === 'age' || k === 'lifespan') continue;
    const d = after[k] - (before[k] ?? 0);
    if (d !== 0) parts.push(`${names[k] ?? k} ${d > 0 ? '+' : ''}${d}`);
  }
  return parts.length ? parts.join('，') : '无变化';
}

/** 结算评级：按最终境界给一句话。 */
export function grade(state: SimState): string {
  const s = stageDef(state.stage);
  const order = STAGE_LIST.findIndex((x) => x.id === s.id);
  if (order >= 4) return '化神登仙';
  if (order === 3) return '元婴不朽';
  if (order === 2) return '金丹圆满';
  if (order === 1) return '筑基有成';
  return '炼气一生';
}

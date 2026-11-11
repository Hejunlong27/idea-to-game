/**
 * Game Test API —— 让测试能「直接驱动」游戏，而不是隔着键盘猜。
 *
 * 为什么需要它：
 *   旧的 `playtest.mjs` 只能 press 键盘 + 每 120ms 读一次只读快照。
 *   这有两个致命限制：
 *     1. 无法构造确定场景（「记忆满时送达」这种边界根本碰不到）；
 *     2. 无法断言因果（按下键 ≠ 船移动了，中间有 tween 与碰撞）。
 *
 * 本模块提供 `window.__test`，把玩法函数直接暴露给测试：
 *   getState()      深快照（含内部计数，不只是 HUD 能看到的）
 *   actions()       本游戏支持哪些动作（runner 据此跳过不适用的用例）
 *   exec(action)    **同步**执行一个动作，返回后逻辑状态已更新
 *   settle(ms)      等 tween / 计时器稳定
 *   reset()         重启当前关卡
 *   teleport(c,r)   直接摆位置，用来精确构造边界场景
 *   setState(patch) 直接改内部值，用来构造「记忆满 / 船体 1」这类前置条件
 *
 * 安全边界：
 *   整块安装逻辑包在 `import.meta.env.DEV` 里。Vite 生产构建会把它 DCE 掉，
 *   发行包里不存在 `__test`，不会把调试能力暴露给玩家。
 *
 * 接入方式（PlayScene.create() 末尾）：
 *   import { installTestApi } from '../test-api';
 *   installTestApi({ getState: () => ({...}), exec: (a) => {...}, ... });
 *
 * 契约见 references/game-test-schema.md。
 */

/** 测试可执行的动作。所有游戏至少要支持 move / wait / reset。 */
export type TestAction =
  | { type: 'move'; dc: number; dr: number }
  | { type: 'ping' }
  /** 点按。省略 x/y 表示「点第一个可交互目标」——随机生成的实体也能被确定性命中。 */
  | { type: 'tap'; x?: number; y?: number }
  /** 强制生成一个实体，用来构造「场上一定有目标」的前置条件。 */
  | { type: 'spawn' }
  | { type: 'wait'; ms: number }
  | { type: 'reset'; level?: number }
  | { type: 'teleport'; c: number; r: number }
  | { type: 'set'; patch: Record<string, unknown> };

/** 每个游戏实现这一个接口，test-api 负责挂到 window 上。 */
export interface TestAdapter {
  /** 深快照。必须包含逻辑状态（不是渲染状态），且可直接 JSON 序列化。 */
  getState(): Record<string, unknown>;

  /** 本适配器实现了哪些动作。runner 用它判断用例是否适用。 */
  capabilities(): string[];

  /** 执行动作。**必须同步生效**——返回时状态已可断言。 */
  exec(action: TestAction): void;

  /** 是否已结束（死亡 / 胜利 / 关卡完成）。 */
  isOver(): boolean;
}

export interface TestApiHandle {
  version: string;
  ready: boolean;
  getState(): Record<string, unknown>;
  actions(): string[];
  exec(action: TestAction): void;
  execAll(actions: TestAction[]): void;
  settle(ms: number): Promise<void>;
  reset(level?: number): void;
  isOver(): boolean;
}

const VERSION = '1.0.0';

/** 当前活跃的适配器。场景重启会重新注册，永远用最新那个。 */
let current: TestAdapter | null = null;

/** 场景 SHUTDOWN 时调用，避免拿到已销毁场景的适配器。 */
export function detachTestApi(adapter?: TestAdapter): void {
  if (!adapter || current === adapter) current = null;
}

/**
 * 注册适配器。多次调用以最后一次为准（场景重启）。
 * 返回是否真的装上了（生产构建下返回 false）。
 */
export function installTestApi(adapter: TestAdapter): boolean {
  current = adapter;
  if (!import.meta.env.DEV) return false;

  const w = window as unknown as Record<string, unknown>;
  if (w.__test) return true; // 已经装过，只更新 adapter

  const settle = (ms: number) =>
    new Promise<void>((resolve) => {
      const t0 = performance.now();
      // rAF 驱动，保证 tween / 计时器真的推进过；
      // 再加 setTimeout 兜底，防止后台标签页被节流到 1fps 时永久挂住。
      const timer = setTimeout(resolve, ms + 120);
      const tick = () => {
        if (performance.now() - t0 >= ms) {
          clearTimeout(timer);
          resolve();
        } else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

  const api: TestApiHandle = {
    version: VERSION,
    get ready() {
      return current !== null;
    },
    getState: () => {
      if (!current) throw new Error('__test: 没有活跃的场景适配器');
      return current.getState();
    },
    actions: () => (current ? current.capabilities() : []),
    exec: (action) => {
      if (!current) throw new Error('__test: 没有活跃的场景适配器');
      if (!current.capabilities().includes(action.type)) {
        throw new Error(`__test: 本游戏不支持动作 ${action.type}`);
      }
      current.exec(action);
    },
    execAll: (actions) => {
      if (!current) throw new Error('__test: 没有活跃的场景适配器');
      for (const a of actions) api.exec(a);
    },
    settle,
    reset: (level) => {
      const adapter = current;
      if (!adapter) throw new Error('__test: 没有活跃的场景适配器');
      if (!adapter.capabilities().includes('reset')) {
        throw new Error('__test: 本游戏不支持动作 reset');
      }
      current = null;
      try {
        adapter.exec({ type: 'reset', level });
      } catch (error) {
        current = adapter;
        throw error;
      }
    },
    isOver: () => (current ? current.isOver() : true),
  };

  Object.defineProperty(w, '__test', { configurable: true, get: () => api });
  return true;
}

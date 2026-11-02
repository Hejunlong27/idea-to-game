# 08b · Game Juice（游戏表现引擎）

**目标**：建立「事件 → 表现」的统一通道，让表现强度与事件重要程度匹配。
**这是实现说明**，设计方法见 `05b-animation-forge.md`。

## 三个文件

| 文件 | 职责 | 谁生成 |
|---|---|---|
| `src/game/events.ts` | 统一事件总线（类型化、优先级、去重、清理、只读快照） | 模板自带，不改 |
| `src/game/juice.ts` | 订阅事件 → 执行 14 类效果；强度分级；性能降级；无障碍 | 模板自带，不改 |
| `src/game/juice-config.ts` | 规则表（事件 → 效果组合 + 强度） | **`juice_forge.py --emit-ts` 生成** |

## 事件总线的六条设计约束

1. **只描述发生了什么**，不描述「应该怎么表现」—— 表现层订阅，不反向修改逻辑
2. **不消耗随机数**：`timestamp` 来自场景时钟，不用 `Date.now()`，保证回放可复现
3. **去重**：`emit(name, opts, dedupeMs)` 同名事件在窗口内只发一次（防每帧触发的循环事件刷屏）
4. **优先级**：处理器按 `priority` 降序执行；`high` 表现先跑
5. **异常隔离**：单个处理器抛错只 `console.warn`，**绝不打断玩法循环**
   （Phaser 里一旦 rAF 循环被打断，整局冻结且报错极难定位）
6. **清理**：`clear()` 清空订阅与日志；场景 SHUTDOWN 必须调用

## 事件结构

```ts
{
  event: 'player_hit',
  timestamp: 1284,        // 相对游戏开始，ms
  source: 'enemy',
  target: 'player',
  intensity: 0.75,        // 0..1，表现层据此分级
  context: { x: 320, y: 480, reason: 'caught' }
}
```

## 强度分级

`JuiceDirector.scale(fx, e) = fx.scale × (0.5 + e.intensity)`

即：规则里写 `scale: 1.0`，实际强度在 `0.5×` 到 `1.5×` 之间随事件严重度浮动。
所以**同一条规则在不同严重度下表现不同**，不需要为每个强度写一条规则。

## 性能降级

| 质量档 | 粒子 | 视差 | 说明 |
|---|---|---|---|
| high | 100% | 开 | 桌面 |
| medium | 60% | 开 | 中端移动 |
| low | 30% | 关 | 低端 |

`juice.setQuality('low')` 可在运行时切换（例如检测到持续掉帧）。

## 无障碍

- `prefers-reduced-motion: reduce` → 关闭 `camera_shake` / `screen_flash` / `camera_zoom` /
  `slow_motion` / `parallax` / `transition`；**保留** `squash_stretch` 与粒子（减半）
- 闪屏硬上限 1 次/秒（光敏性癫痫），震动 ≤300ms（晕动），**不可配置放宽**
- 这些不是「选项」，是审核会拦的硬指标

## 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 在玩法代码里直接 `camera.shake()` | 换玩法要重写手感，强度无法分级 | 只 `bus.emit(...)` |
| 每帧 `emit('player_move')` 不设 dedupe | 事件日志爆炸，表现变成噪声 | 传 `dedupeMs`（如 60） |
| `hit_stop` 用 `scene.time.timeScale = 0` | 逻辑也被冻结，玩法判定错乱 | 只改 `tweens.timeScale` |
| SHUTDOWN 不 `destroy()` | 监听器泄漏，重进场景表现翻倍 | `juice.destroy()` |
| 处理器里抛异常不捕获 | rAF 循环被打断，整局冻结 | 总线已 try/catch，别绕过总线 |

## 自检

- [ ] `new JuiceDirector(...)` + `juice.update(delta)` 在场景里
- [ ] `SHUTDOWN` 里有 `juice.destroy()` / `audio.destroy()` / `bus.clear()`
- [ ] `prefers-reduced-motion` 分支存在
- [ ] 没有 `time.timeScale` 改写
- [ ] 同屏粒子数有上限

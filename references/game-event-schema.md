# 统一游戏事件契约（Game Event Schema）

> 实现：`assets/template/src/game/events.ts`　消费：`audio.ts` / `juice.ts` / QA / 试玩 / 埋点

## 1. 事件结构

```json
{
  "event": "player_hit",
  "timestamp": 1284,
  "source": "enemy",
  "target": "player",
  "intensity": 0.75,
  "context": { "x": 320, "y": 480, "reason": "caught" }
}
```

| 字段 | 类型 | 约束 |
|---|---|---|
| `event` | string | 取自下表或项目扩展；**不得在表现层改写** |
| `timestamp` | number | **相对游戏开始**的毫秒数（不是 `Date.now()`）—— 保证可复现 |
| `source` | string | `player` / `enemy` / `system` / `ui` |
| `target` | string | 承受者，无则 `""` |
| `intensity` | number | 0–1，表现层据此分级（0.2 微 / 0.5 轻 / 0.75 中 / 0.9 重） |
| `context` | object | 附加数据，**只读语义**，表现层不得改写 |

## 2. 标准事件与默认严重度

| 事件 | 默认 intensity | 语义 |
|---|---|---|
| `game_start` | 0.5 | 进入可玩状态 |
| `game_paused` / `game_resumed` | 0.3 | 暂停/恢复 |
| `game_over` | 0.9 | 一局结束 |
| `player_move` | 0.1 | 移动（最频繁，表现必须最轻） |
| `player_action` | 0.35 | 主行为 |
| `player_hit` | 0.7 | 玩家受损 |
| `player_death` | 1.0 | 玩家死亡 |
| `enemy_spawn` | 0.3 | 敌人生成 |
| `enemy_defeated` | 0.6 | 敌人被击败 |
| `item_collected` | 0.25 | 收集 |
| `level_started` | 0.5 | 关卡开始 |
| `level_completed` | 0.9 | 关卡完成 |
| `boss_appeared` | 0.85 | Boss 登场 |
| `boss_defeated` | 1.0 | Boss 击败 |
| `story_reveal` | 0.6 | 叙事揭示 |
| `secret_found` | 0.55 | 发现秘密 |
| `resource_changed` | 0.2 | 资源变化 |
| `state_changed` | 0.3 | 状态机切换 |

项目可扩展（如本作的 `echo_ping` / `memory_spent` / `memory_empty` / `soul_delivered`），
扩展事件必须在 `juice-plan.json` 里有对应规则，否则不会产生表现。

## 3. 六条硬规则

1. **事件只描述发生了什么**，不描述「应该怎么表现」。表现层订阅，**不得反向修改玩法逻辑**。
2. **不消耗随机数**：`timestamp` 来自场景时钟，表现层的变体抖动用确定性伪随机（FNV 哈希）。
   否则同一份输入两次运行结果不同，回放与测试都失去意义。
3. **去重**：`emit(name, opts, dedupeMs)`。每帧触发的循环事件必须传窗口（建议 60ms）。
4. **优先级**：处理器按 `priority` 降序执行；`high` 表现先跑，音频的 `high` 音效永不被并发上限挤掉。
5. **异常隔离**：单个处理器抛错只 `console.warn`。**绝不能打断 rAF 循环** ——
   Phaser 里一旦循环被打断，整局冻结且报错极难定位。
6. **清理**：`clear()` 清空订阅与日志。场景 `SHUTDOWN` 必须调用，否则监听器跨场景泄漏（表现会翻倍）。

## 4. 一个事件驱动五个系统

```
bus.emit('player_hit', { intensity: 0.75 })
   ├─ juice.ts   → squash_stretch + camera_shake(0.6) + particles(红) + hit_stop
   ├─ audio.ts   → feedback_hurt（high 优先级，触发 ducking 压低旋律）
   ├─ UI         → 血条数字跳动
   ├─ 埋点       → 记录受伤位置与原因
   └─ 自动化测试 → 断言「受伤 3 次后游戏结束」
```

## 5. 测试与调试需要暴露的全局

| 全局 | 类型 | 用途 |
|---|---|---|
| `window.__bootDone` | boolean | 启动看门狗判断「游戏真的起来了」 |
| `window.__gameState` | getter → object | 只读状态快照（QA/试玩采样） |
| `window.__gameEvents` | getter → array | 环形日志（最多 400 条） |
| `window.__bot` | `{ act(strategy) }` | 可选：游戏自带的试玩策略 |

**这些必须在场景 `SHUTDOWN` 时 `delete`**，否则重进场景会读到旧数据。

## 6. 反模式

| 反模式 | 后果 |
|---|---|
| 在玩法代码里直接 `camera.shake()` | 换玩法要重写手感，强度无法分级 |
| 用 `Date.now()` 做 timestamp | 无法复现，回放/测试失效 |
| 表现层里改 `gameState` | 逻辑与表现耦合，行为不可预测 |
| 每帧 emit 不设 dedupe | 日志爆炸，表现变成噪声 |
| SHUTDOWN 不清理 | 监听器泄漏，重进场景表现翻倍 |

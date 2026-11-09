# Game Test Schema —— 测试接口、用例格式与自动修复契约

本文件是**下游 Agent 的硬契约**。写测试、改玩法、做自动修复前必须读。

分三层：

| 层 | 文件 | 职责 |
|---|---|---|
| 运行时接口 | `src/game/test-api.ts` | 游戏暴露 `window.__test`，让测试能驱动 |
| 用例格式 | `tests/scenarios/*.json` | 声明式动作 + 断言 |
| 修复契约 | `docs/10-iteration/ISS-*.json` | 改动范围 + 验证清单 |

---

## 1. 为什么需要可写测试接口

模板原本只有 `window.__gameState`（只读快照）。它够让试玩 Agent 观察，但有两个做不到：

1. **构造不了确定场景。** 「记忆满时送达」这种边界，靠敲键盘碰不到。
2. **断言不了因果。** 按下方向键 ≠ 船移动了，中间有 tween、碰撞、状态机。

`window.__test` 解决这两点：动作**同步生效**，返回即可断言。

**安全边界**：整块安装逻辑包在 `import.meta.env.DEV` 里，Vite 生产构建会 DCE 掉。发行包里不存在 `__test`。

---

## 2. TestAction 契约

```ts
type TestAction =
  | { type: 'move'; dc: number; dr: number }   // 网格移动（增量）
  | { type: 'ping' }                            // 游戏的核心主动作（按玩法命名）
  | { type: 'tap'; x?: number; y?: number; c?: number; r?: number }
  | { type: 'spawn' }                           // 强制生成一个实体（构造前置条件）
  | { type: 'wait'; ms: number }                // 等待（由 runner 转成 settle）
  | { type: 'reset'; level?: number }           // 重启场景
  | { type: 'teleport'; c: number; r: number }  // 直接摆位置（网格类游戏）
  | { type: 'set'; patch: Record<string, unknown> } // 直接改内部值
```

`tap` 有三种寻址方式：`{c,r}` 按格子（**网格类游戏推荐**，换分辨率不失效）、`{x,y}` 按像素、都不给则点第一个可交互目标（随机生成的实体也能确定性命中）。

**游戏不必全支持。** 在 adapter 的 `capabilities()` 里列出真正实现了的，runner 据此判断用例适用性；调用未声明的动作会抛错（早失败好过静默无效）。

**新增动作类型的门槛**：只有当「现有动作无法表达该玩法的最小交互」时才加。加之前先看 `tap` / `set` / `teleport` 能不能组合出来。

---

## 3. adapter 要求

```ts
installTestApi({
  capabilities: () => ['move', 'ping', 'wait', 'reset', 'teleport', 'set'],
  getState: () => ({ /* 深快照，必须可 JSON 序列化 */ }),
  isOver: () => boolean,
  exec: (action) => { /* 同步生效 */ },
});
```

### getState 的硬要求

- **必须是逻辑状态，不是渲染状态。** 报 `player.c`（格子坐标），不要报 `boat.x`（像素）。
- **必须包含上限值。** 有 `memory` 就要有 `memoryMax`。否则断言只能写死常量，换个关卡就失效。
- **必须包含 `phase`。** `'play' | 'over'`，用于判断结束。
- **禁止放函数、DOM 节点、Phaser 对象。** runner 会 JSON 序列化。

### exec 的硬要求

- **同步。** 不要 `async`，不要等 tween。逻辑状态必须当场更新。
- **幂等安全。** `set` 重复执行结果一致。
- **不做校验以外的副作用。** 不要在 `exec` 里写存档、发平台事件。

### getClock：让 wait 等「游戏时间」而不是墙钟

有实时循环的玩法**必须实现** `getClock: () => this.time.now`。

原因：headless 浏览器里 rAF 可能只有 20–30fps，Phaser 会把单帧 delta 钳在上限内，
于是墙钟过了 1200ms、游戏内只过了 500ms。用例写 `wait 1200` 会等不够，
表现为随机失败——**曾经把它误判成「修复引入回归」**。

实现了 `getClock` 后，runner 会循环 settle 直到游戏内时间真的走够。回合制玩法不需要（没有帧循环）。

---

## 4. 用例格式

```json
{
  "id": "02-memory-cap",
  "name": "记忆上限：送达奖励不得突破 memoryMax",
  "level": 1,
  "note": "为什么这条用例存在（写给人看）",
  "setup":  [{ "type": "set", "patch": { "memory": 5 } }],
  "steps":  [
    { "type": "teleport", "c": 5, "r": 2 },
    { "type": "move", "dc": 1, "dr": 0 }
  ],
  "assertions": [
    { "path": "delivered", "op": "eq", "value": 1 },
    { "path": "memory", "op": "lte", "valuePath": "memoryMax" }
  ]
}
```

- `setup` 构造前置条件，`steps` 是玩家/系统动作，两者都用 TestAction。
- `level` 是 1-based 关卡序号，runner 会先 `reset` 到该关卡。
- `id` 全局唯一，自动修复用它定位目标用例。

### 断言操作符

`eq` `ne` `gt` `gte` `lt` `lte` `truthy` `falsy`

`path` 支持点号取值：`player.c`、`targets.0.hit`。

### valuePath：断言「跟另一个字段比」

```json
{ "path": "memory", "op": "lte", "valuePath": "memoryMax" }
```

**这是最重要的一条约定。** 写死 `memory <= 5` 只能测一个关卡；写 `memory <= memoryMax` 每关都成立，而且能抓住「忘 clamp」这类 bug。

---

## 5. 写用例的取舍

**该写的**（按优先级）：

1. 核心循环能否走完（收集 → 交付 → 结束）
2. 资源边界（上限、归零、负数）
3. 碰撞/阻挡/伤害的**因果**（撞了才掉血，不是「血量有变化」）
4. 重置是否干净
5. 边界坐标不出界

**不该写的**：

- 写死像素坐标、写死随机数结果（换个屏幕就崩）
- 「有加分」这种弱断言（要断言**加了多少**）
- 依赖时序的断言（先 `wait` 再断言要留足余量，但别用它测逻辑）
- 视觉美观度（那是视觉评价的活，不是断言能表达的）

**一条用例只验证一件事。** 一个用例里堆 8 条断言，失败时你不知道坏在哪。

### 品类模板的必备用例（以塔防为例）

| 用例 | 断言什么 | 为什么必须有 |
|---|---|---|
| 建塔扣费 | `gold` 减 `towerCost`、`towerCount` +1 | 资源循环的地基 |
| 非法位置 | 路径格 / 重复格 → 不扣钱不产塔 | 玩家乱点不能白烧钱 |
| 资源边界 | `gold = cost - 1` → 建不了 | 最容易写成 `<=` 的地方 |
| 实体推进 | `dist` 增加且 `< pathTotal` | 验证「在动」而不是「瞬移」 |
| 击杀链路 | 实体消失 + 奖励到账 + 击杀数 +1 | 三段都要断 |
| 漏怪链路 | 生命 −1 且实体消失 | 失败压力的来源 |
| 失败判定 | 生命归零 → `phase=lost` | 否则游戏输不了 |
| 胜利判定 | 目标清空 → `phase=won` | 否则游戏赢不了 |
| 重置干净 | 所有资源回初始值 | 自动修复每次都从干净状态重跑 |

**共同点：每条都在断「因果」，不是断「有变化」。**「金币有变化」是弱断言，「金币从 100 变 50」才是。

### 别让自动刷怪污染用例

塔防 / 幸存者这类有自动波次的玩法，`reset` 后第一帧就会生成敌人，会打乱后续每个用例的实体计数。两条解法，**都要做**：

1. 玩法侧给首波一个准备延迟（塔防用 `firstWaveDelayMs = 1200`）—— 这同时是真实的体验改进，玩家进游戏不该被偷家。
2. 测试侧提供暂停开关（塔防用 `set { pauseWaves: true }`），让用例自己用 `spawn` 精确控制实体数量。

### 回合制品类（模拟器 / 卡牌 / 经营）

回合制玩法**没有帧循环**，`exec` 完全同步，所以用例**一条 `wait` 都不该有**。实测模拟器模板单条 170–370ms，全靠同步执行。

用 `act` 与 `choose` 而不是 `tap`：

```json
{ "setup":  [{ "type": "set", "patch": { "eventChance": 0 } }],
  "steps":  [{ "type": "act", "id": "meditate" }, { "type": "choose", "index": 0 }] }
```

三条必备约定：

1. **关掉随机事件**（`set { eventChance: 0 }`），否则弹窗会打断断言；需要测事件时用 `set { forcedEvent: 'event_id' }` 指定触发哪个。
2. **随机必须是确定性的**：不用 `Math.random()`，改用 `hashRand(seed, turn, salt)`。否则 `--repeat` 永远不稳定，平衡也无法回放。
3. **必测「待选事件时行动无效」**：弹窗开着还能点行动，等于一回合做两件事。这是回合制最常见的漏。

---

## 6. 跑测试

```bash
node scripts/scenario.mjs --serve                 # 自己起 vite，跑全部用例
node scripts/scenario.mjs --url http://127.0.0.1:5173
node scripts/scenario.mjs --only 02-memory-cap    # 只跑一条
node scripts/scenario.mjs --repeat 3              # 可复现性验证（三轮结果必须一致）
```

输出 `docs/07-qa/scenario-report.json`。失败时带 `state_on_failure` 完整状态快照，供 Issue Analyzer 定位。

退出码非 0 表示有失败。

### 进不去玩法场景怎么办

runner 会先等 `__bootDone`，然后按 `--boot-key`（默认 `Space`）尝试进入玩法场景。菜单不是空格启动的游戏，传 `--boot-key Enter` 或 `--boot-key <你的键>`。

---

## 7. 自动修复契约

### Issue 定义

```json
{
  "id": "ISS-001",
  "type": "gameplay_bugfix",
  "severity": "high",
  "detected_by": "02-memory-cap",
  "description": "一句话说清现象",
  "impact": "为什么这是问题（对玩法/玩家的影响）",
  "evidence": { "assertion": "memory lte memoryMax", "expected": 5, "actual": 6 },
  "root_cause": "定位到的代码位置与原因",
  "allowed_paths": ["src/game/"],
  "forbidden_paths": ["assets/", "docs/09-review/", "tests/scenarios/"],
  "validation": ["02-memory-cap", "01-core-loop"]
}
```

`forbidden_paths` 里必须包含 `tests/scenarios/`——**禁止改测试来让测试通过**。这是自动修复最容易走歪的地方。

### 流程

```bash
# 1. 测试发现失败后，先建 checkpoint（此时代码是坏的）
node scripts/iterate.mjs start  --issue docs/10-iteration/ISS-001.json

# 2. Agent 改代码（只改 allowed_paths 内）

# 3. 校验范围 + 跑目标用例 + 跑全量回归 + 算质量变化
node scripts/iterate.mjs verify --issue docs/10-iteration/ISS-001.json

# 4. 需要时回滚
node scripts/iterate.mjs rollback --issue docs/10-iteration/ISS-001.json
```

`verify` 的判定规则：

| 条件 | 结果 |
|---|---|
| 有改动命中 `forbidden_paths` 或越出 `allowed_paths` | REJECT |
| `validation` 里有用例未通过 | REJECT |
| 任何原本 PASS 的用例变 FAIL | REJECT（引入回归） |
| 以上都没有 | ACCEPT |

**ACCEPT 不等于「修好了」，只等于「这批用例证明没修坏」。** 用例覆盖不到的地方它管不了。

### 一次只修一个问题

`verify` 一次只认一个 issue。多个问题分开跑，否则质量变化算不清是谁带来的。

### 定位自动化：`diagnose.mjs`

「从失败报告找到代码行」这一步曾经是人做的，人是瓶颈。`diagnose` 用三条线索自动收敛：

1. 断言字段名（`enemies.0.hp` → 找 `hp` 的写入点）
2. 失败方向（实际偏大 → 找「增加」的赋值；偏小 → 找「减少」的）
3. 代码上下文（在 `update`/`hit` 等逻辑函数里加分，在 `create`/`init` 里减分）

还有**二跳定位**：命中 `e.hp -= dmg` 后，会回找 `const dmg = ...` 的定义行——
真正的 bug 往往在那一行，而不是赋值行。

```bash
node scripts/diagnose.mjs                    # 打印候选位置
node scripts/diagnose.mjs --write            # 生成 docs/10-iteration/ISS-AUTO-xxx.json
node scripts/diagnose.mjs --src src          # 指定源码根
```

生成的是**候选，不是结论**。它的价值是把搜索范围从整个仓库缩到 2–3 行。

### 原型对比：`compare.mjs`

选数值方案 / 机制变体不能靠「看着不错」。同一套用例 + 同一个 bot，只改变量，用数据比：

```bash
node scripts/compare.mjs                  # 跑 variants/ 下所有变体
node scripts/compare.mjs --only fast-pace
```

变体文件 `variants/*.json`：

```json
{ "id": "fast-pace", "name": "快节奏",
  "override": { "waves": [{ "grunt": 5 }, { "grunt": 4, "swift": 3 }], "startGold": 150 } }
```

`override` 通过 `window.__VARIANT` 在页面脚本执行前注入，游戏 `create()` 时读。

**必须区分两类用例**：

| 类型 | 标记 | 用途 |
|---|---|---|
| 机制类 | `"variantSafe": true` | 与具体数值/波数/关卡无关，变体下**必须全过** |
| 配置类 | `"variantSafe": false` | 断言了绝对金币、波数、某关数据，变体下失效属正常 |

`compare` 只拿机制类的通过率判断「机制有没有被改坏」，配置类只作参考。
不区分的话，任何改数值的变体都会被误判成「把游戏改坏了」。

**推荐逻辑**：机制全过 + bot 能通关 → 比通关耗时（越短越紧凑）。
报告里会明确写「bot 只代表一个会按规则出牌的玩家，不代表真实玩家手感」。

### 数值平衡搜索：`balance_search.mjs`

调数值不该靠「感觉差不多」。但也不能跑 100 局算胜率——**确定性游戏里那个胜率不存在**。

```bash
node scripts/balance_search.mjs              # 按 balance-search.json 跑
node scripts/balance_search.mjs --only towerCostMul=1.0
```

参数网格（笛卡尔积）× 两个策略（`novice` / `expert`），输出**二值结果 + 通关余量**。

`novice` 按阅读顺序建塔、不评估覆盖；`expert` 算「射程内覆盖多少路径格」。
差异是真实决策差异，**不是给新手加延迟或降属性作弊**——靠削弱来制造差距，测出来的就不是难度。

甜点判定：新手能过（余量 30–90%）+ 老手轻松 = `SWEET_SPOT`。

详见 `references/balance-tuning.md`。

### 交付前技术门禁：`ship_check.py`

一个项目「能不能发」不该靠翻四个脚本的输出来判断。`ship_check` 把它们串成一次检查：

```bash
python scripts/ship_check.py --project . --build --platforms crazygames,taptap --tests
```

检查链：**构建 → 体积/文件数 → 平台预检 → 音频参数 → 素材台账 → 玩法用例**，输出单一结论。

与 `gate_check.py` 的分工：前者管**流程**（阶段产物齐不齐），后者管**技术**（跑不跑得动、能不能提交）。

音频硬性规范（`AUDIO_RULES`）：44.1kHz / 单声道 / 音效 ≤1.5s / BGM 20–35s / 单文件 ≤500KB / 总量 ≤1536KB。

### 跨项目质量基准：`benchmark.mjs`

单项目用例只能回答「这次改坏了没」。要回答「新版本整体变好还是变差」需要基准：

```bash
node scripts/benchmark.mjs              # 汇总 benchmarks/projects.json 里所有项目的已有报告
node scripts/benchmark.mjs --run        # 真跑每个项目的测试（慢）
node scripts/benchmark.mjs --baseline   # 标记为基线
```

指标只取能自动算的：通过率、用例数、平均耗时、产物体积、迭代次数。
**玩家满意度要真人数据，不塞进来假装是数字。**

---

## 8. 与旧工具的关系

| 工具 | 定位 | 何时用 |
|---|---|---|
| `smoke.mjs` | 能不能启动、有没有报错 | 每次构建 |
| `qa.mjs` | 断言 + 帧率基线 + 移动端 | 每阶段门禁 |
| `playtest.mjs` | 探索型试玩，找异常与卡死 | R2 审核前 |
| `scenario.mjs` | 确定性用例，判行为对错 | 自动修复闭环 |
| `iterate.mjs` | 修复护栏与质量变化 | 修复时 |

`scenario.mjs` 不替代 `playtest.mjs`：前者验证「已知应该怎样」，后者发现「不知道哪里不对」。两个都要。

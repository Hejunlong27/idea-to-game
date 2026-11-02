# 08c · 玩家体验设计师（Experience Designer）

**目标**：定义**可验证**的玩家体验目标，而不是写一段「本作希望带给玩家沉浸的体验」。
**上游**：`creative-dna.experience` + `src/game/levels.json`。**下游**：`specialist_review` 的体验审核。

## 为什么需要这一步

v2 的 `richness_check` 只判「有没有内容」（机制数、对白数、音效数），不判「体验是否成立」：
前 10 秒能不能理解、有没有正反馈、难度是不是只靠数值、失败有没有教学价值、
有没有无意义的重复劳动。**这些一条都没被检查过。**

## 1. 情绪曲线

```bash
python scripts/experience_forge.py --project . --plan
```

七段基准（允许按品类调整，见 `assets/data/emotional-patterns/curves.json`）：

| 段 | 强度 | 这一段玩家在做什么 |
|---|---|---|
| curiosity | 0.35 | 看见一个未解释的异常 |
| learning | 0.45 | 做对一个动作并看到后果 |
| mastery | 0.60 | 同一动作在新情境下复用成功 |
| challenge | 0.80 | 旧解法失效，必须换策略 |
| surprise | 0.70 | 规则被改写，或代价以没预料的方式出现 |
| climax | **1.00** | 所有机制同时生效，做一次不可逆选择 |
| satisfaction | 0.50 | 结算代价 + 安静收尾 |

**硬要求：曲线必须有 climax，且强度峰值就在 climax。** 没有高潮的曲线留不下记忆点。

短局变体（≤3 分钟）应删掉 mastery 与 surprise，否则节奏拖沓。

## 2. 每关体验表（10 项）

| 字段 | 要求 |
|---|---|
| `emotion` | 本关目标情绪（一个词） |
| `learn` | 可检验：能做到 X |
| `new_mechanic` | 本关新引入的机制 id（**≤1 个**，且必须存在于 DNA） |
| `core_decision` | 必须写成「A好但B坏」（含取舍标记词） |
| `challenge` | 五轴之一：information / resource / operation / environment / cost |
| `feedback` | 玩家如何知道自己做对了（具体到感官） |
| `climax` | 本关的高潮时刻 |
| `reward` | 给的是能力/信息/情感，**不是分数** |
| `next_hook` | 让玩家想玩下一关的东西 |
| `duration_seconds` | 预计时长 |

## 3. 八条可验证判据（E1–E8）

```bash
python scripts/experience_forge.py --project . --verify
```

| id | 判据 | 怎么验（程序化） |
|---|---|---|
| E1 | 前 10 秒可理解 | `levels.json` 第 1 关有 hint，且源码有引导逻辑 |
| E2 | 前 30 秒有正反馈 | 试玩报告的 `first_positive_feedback_s` ≤30 |
| E3 | 学习曲线 | 每关新机制 ≤1，且 id 存在于 DNA |
| E4 | 难度非数值 | 挑战轴 ≥2 条非数值 |
| E5 | 存在意外 | 源码有 `story_reveal` / `memory_empty` 类事件 |
| E6 | 值得记住的瞬间 | `signature_moments` 绑定的事件**在源码里真实存在** |
| E7 | 失败有学习价值 | 有 `player_death` 事件 + 结束界面 + 慢动作 |
| E8 | 无意义重复 | 试玩操作重复率 <70% |

**关键立场：未验证就写 UNVERIFIED，不许写 PASS。**
`gate_check` 会把 UNVERIFIED 当「未通过」处理（warning 而非 pass）。

## 4. 不要机械套用时间标准

「前 10 秒」不是对每个游戏都成立：解谜的「理解」可能是 30 秒的观察，
叙事向的「正反馈」可能是 1 分钟后的一个揭示。
**判据是「有没有这件事」，不是「必须在第几秒」。**
脚本里给的阈值是超休闲品类的经验值，其他品类应调整并在蓝图里说明理由。

## 自检

- [ ] 曲线有 climax 且是强度峰值
- [ ] 每关都有取舍决策（含「还是/但/放弃/代价」等标记词）
- [ ] 每关新机制 ≤1 且存在于 DNA
- [ ] 挑战轴 ≥2 条非数值
- [ ] 至少一个标志时刻绑定了真实事件
- [ ] E1–E8 没有 FAIL，且 UNVERIFIED 已补验证

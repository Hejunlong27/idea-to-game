# 创意身份（Creative Identity）

> 判据文件。`creative_forge.py` 的评分与 `specialist_review` 的创意审核都以本文件为准。

## 1. 为什么需要「身份」而不只是「设定」

设定是**描述**（这个世界有雾、有灯塔、有灵魂）。身份是**约束**：

> 如果换掉任何一个元素，其他三个域（玩法/美术/音频）都得跟着改 —— 这才叫身份。

v2 的问题不是没有设定，是设定之间没有约束关系：美术可以随便换风格，音频可以随便换乐器，
玩法可以随便换机制，蓝图不会报错。

## 2. 一份合格的 Creative DNA 长什么样

| 区块 | 判定要点 |
|---|---|
| `identity.unique_hook` | ≤80 字、一句话、含一个**反常识的因果关系**（「每一声都会留下一张会腐烂的地图」） |
| `identity.signature_moment` | 含「发生条件 + 玩家动作 + ≥2 种感官」 |
| `gameplay.core_mechanic` | 6 条：一句话/非数值/互动≥2/改变策略/标志时刻/独特性论证 |
| `gameplay.progression_identity` | **质变**（地图越来越不可信），不是「更快更多」 |
| `narrative.narrative_mechanic_link` | 写清「哪条世界规则被写进了机制」 |
| `visual.style_identity` | **混血**（水墨 × 水彩绘本），不是单一流派名 |
| `audio.sound_signature` | 只属于这款游戏的声音（回声三连、音高随记忆下降的木质轻响） |
| `experience.player_memory` | 玩家关掉游戏后还记得什么 |

## 3. 新颖度：启发式相似度，不是原创性证明

**立场（任务书 §3.4）**：不能仅凭语言模型主观判断就宣称一个创意完全原创。

`creative_forge.similarity()` 做的是**结构指纹比对**：

```
指纹维度：spatial / time / info / resource / risk / win / fail / progression
相似度 = 5 维重合 × 0.6 + 3 维重合 × 0.25 + 关键词重合 × 0.15
```

| 相似度 | 风险 | 处置 |
|---|---|---|
| ≥0.85 | HIGH | **必须重设计核心机制** |
| 0.70–0.85 | MEDIUM | 需要一条结构性差异 |
| <0.70 | LOW | 通过 |

输出写成「与 `stealth` 原型结构重合 0.48（LOW），重合在 radial/realtime，差异在
info=hidden 与 risk=reversible 的组合方式」—— **不是**「原创度 95 分」。

**这个方法的局限（必须说清）**：
- 它只能识别**已知原型**的结构相似，识别不了「从没见过但很平庸」的创意
- 指纹是人工归纳的 8 维，粒度粗；两个指纹不同的方案仍可能实际很像
- 所以它是**筛子**，不是**判决**。最终由人（G1）拍板。

## 4. 7 维评分（100 分制）

| 维度 | 分 | 判据（可核对） |
|---|---|---|
| 新颖度 | 20 | `(1 - 最大相似度) × 16` + 有反转维度 4 |
| 核心机制独特性 | 20 | 6 条硬条件各 1/6 |
| 玩法可理解性 | 15 | 动词可识别 / 决策 2–4 / 品类明确 / 有一句话 |
| 机制互动深度 | 15 | 机制图边数 ×3.5 + 有环 2 |
| 玩法与叙事一致性 | 10 | 世界观关键词出现在机制/决策里的比例 |
| 可实现性 | 10 | 结构复杂度 ≤9 / 机制 ≤6 / 平台 / 视觉提案 |
| 玩家记忆点 | 10 | 标志场景长度 + 感官词数 |

结论：`ACCEPT`（≥70 且换皮风险非 HIGH）/ `REVISE`（≥55）/ `REJECT`（<55）。

## 5. 五个方案必须真的不同

判据不是「名字不同」，是**结构指纹**：

| 维度 | 取值 | 例 |
|---|---|---|
| spatial | none / lane / grid / radial / free | 网格布点 vs 自由空间 |
| time | turn / rhythm / realtime | 回合思考 vs 实时反应 |
| info | full / partial / hidden | 全可见 vs 只能靠声音 |
| resource | renewable / converted / finite | 可再生 vs 耗尽即止 |
| risk | reversible / irreversible | 可重试 vs 一步错到底 |

**要求：任意两个方案至少 3 项不同。** 只有 2 项不同 = 同一交互的换皮。

## 6. 引用的合规要求

每条 `references` 必须含：

```json
{
  "pattern_id": "listen_locate",
  "source": "assets/data/creative-patterns/interaction-verbs.json（原创整理）",
  "license": "CC0-1.0",
  "how_used": "取其信息隐藏 + 不可逆指纹；把「听」从感官变成唯一信息接口"
}
```

缺 `source` / `license` → 校验报 ERROR。`how_used` 必须写「怎么改的」，不能只写 `pattern_id` ——
否则就是把参考当模板用。

## 7. 自检清单

- [ ] `unique_hook` 一句话、≤80 字、有反常识因果
- [ ] `core_mechanic` 6 条全过，且 `non_numeric = true`
- [ ] `progression_identity` 是质变
- [ ] `narrative_mechanic_link` 写清了规则→机制的映射
- [ ] `style_identity` 是混血
- [ ] `sound_signature` ≥2 条且只属于本作
- [ ] `player_memory` 是一句能被复述的话
- [ ] 5 个方案结构距离 ≥3
- [ ] 相似度结论是启发式表述，没有写成「原创度 X 分」
- [ ] 每条引用有 source + license + how_used

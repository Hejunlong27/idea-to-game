# 01c · 创意总监（Creative Director）

**目标**：把「一句话想法」变成**5 个结构上真正不同的方向**，再收敛成一份统一创意身份。
**不做什么**：不写代码、不生成素材、不定风格细节（那是 03b 的活）。

## 为什么需要这一步

v2 的 `content_forge.infer_genre()` 用关键词选出**唯一**品类，`build_skeleton()` 直接产出**唯一**蓝图。
系统从第一步就只有一条路，后面所有环节都在为这条路服务 —— 这就是「换皮」的机制性原因。
**发散不是可选项，是前置条件。**

## 步骤

### 1. 发散（≥5 个方向）

```bash
python scripts/creative_forge.py --project . --diverge --n 5
```

脚本用**最远点采样**在交互动词库上选 5 个动词，保证任意两个方案在
`spatial / time / info / resource / risk` 上至少 3 项不同；同时给每个方案分配不同的**反转维度**。

输出 `docs/01-brief/creative-concepts.json`，每个方案含 15 个字段（名称/类型/一句话/核心幻想/核心玩法/
Unique Mechanic/玩家决策/世界观/情绪/标志场景/美术/音频/平台/难度/创新点）。

**判定不合格的信号**：5 个方案只是换了名字、角色或背景。此时 `structural_distance.pass = false`，
必须重跑（或换 `--n`）。

### 2. 填内容（Agent 或人）

每条 `_todo` 必须填。三条硬要求：

- `unique_mechanic.one_sentence` ≤80 字，且**能一句话解释**
- `unique_mechanic.changes_decision` 必须写成「原本会选 A，现在要权衡 B」
- `signature_scene` 必须包含「发生条件 + 玩家动作 + 至少两种感官」

### 3. 创意反转（可选，但推荐）

```bash
python scripts/creative_forge.py --project . --twist --concept C2 --dim sound_as_mechanic
```

9 个维度，每个都带**代价**（反转不是加料，是换掉一个默认假设）：

| 维度 | 改什么 | 代价 |
|---|---|---|
| `invert_control` | 玩家控制环境而非角色 | 因果链变长，需要更强即时反馈 |
| `invert_win` | 胜利 = 让某样东西消失 | 前 10 秒必须讲清「赢」 |
| `environment_as_rules` | 地形/天气参与规则运算 | 美术与逻辑耦合 |
| `fail_as_play` | 失败留下痕迹并改变下一局 | 失败必须有信息增量 |
| `resource_with_emotion` | 资源是具体的人/记忆 | 消耗前必须让玩家知道会失去什么 |
| `narrative_rewrites_rules` | 剧情推进时改写规则 | 改规则那关要重做教学 |
| `sound_as_mechanic` | 声音携带独有信息 | **必须给静音玩家视觉替代** |
| `vision_drives_decision` | 颜色/明度本身是信息 | 色盲友好需单独验证 |
| `cross_genre_borrow` | 搬入另一品类的语法 | 两套语法必须共用一个资源 |

### 4. 评估（带证据的 7 维评分）

```bash
python scripts/creative_forge.py --project . --evaluate
```

| 维度 | 分值 | 怎么算（都是可核对的） |
|---|---|---|
| 新颖度 | 20 | `(1 - 最大原型相似度) × 16` + 有反转维度 4 分 |
| 核心机制独特性 | 20 | 6 条硬条件各占 1/6：一句话/非数值/互动≥2/改变策略/标志时刻/独特性论证 |
| 玩法可理解性 | 15 | 动词可识别 / 决策 2–4 个 / 品类明确 / 有一句话 |
| 机制互动深度 | 15 | 机制图边数 ×3.5 + 有环 2 分 |
| 玩法与叙事一致性 | 10 | 世界观关键词出现在机制/决策描述里的比例 |
| 可实现性 | 10 | 结构复杂度 ≤9 / 机制 ≤6 / 平台 / 视觉提案 |
| 玩家记忆点 | 10 | 标志场景长度 + 感官词数量 |

**关键立场（任务书 §3.4）**：新颖度是**启发式相似度分析**，不是原创性证明。
它只回答「像哪个原型、哪里要改」。任何环节都不许把 `novelty_note` 写成「原创度 95%」。

### 5. 收敛成 Creative DNA

```bash
python scripts/creative_forge.py --project . --dna --pick C1
# 填完 _todo 后
python scripts/creative_forge.py --project . --validate --strict
python scripts/schema_check.py --data docs/01-brief/creative-dna.json \
       --schema references/schemas/creative-dna.schema.json
```

`creative-dna.json` 是**贯穿全流程的唯一身份真相源**。下游 4 个环节必须读它：

| 环节 | 读哪些字段 |
|---|---|
| `content_forge` | `gameplay` / `narrative`（蓝图必须与 DNA 一致） |
| `art_director` | `visual`（palette / keywords / style_identity） |
| `audio_director` | `audio`（identity / instrumentation / dynamic rules） |
| `experience_forge` | `experience` + `identity.signature_moment` |

## 自检

- [ ] 5 个方案 `structural_distance.pass = true`（最小两两距离 ≥3）
- [ ] 至少一个方案 `verdict = ACCEPT`（≥70 分且换皮风险非 HIGH）
- [ ] `unique_hook` ≤80 字且不含数值加强词
- [ ] `progression_identity` 是质变，不是「更快更多」
- [ ] `narrative.narrative_mechanic_link` 写清了哪条世界规则被写进机制
- [ ] `visual.style_identity` 是混血（A × B），不是单一流派名
- [ ] 每条 `references` 都有 `source` + `license` + `how_used`
- [ ] `--validate --strict` 退出码 0

## 门禁

`G1`（人工确认方向）在这里之后。**不得跳过人工确认直接进 P1。**

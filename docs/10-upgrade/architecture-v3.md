# v3.0 架构

## 一、总体形态

**单一技能包 + 主编排 + 专业职责模块 + 结构化文件契约 + 独立审核角色。**
没有拆成多个 Agent —— 环节之间靠文件契约与状态机串联，能力环节互不调用。

```
SKILL.md                      入口：规则 + 阶段表 + 降级表
├─ modules/*.md (22)          能力环节的执行说明书
├─ references/*.md (15)       判据与契约（标准、流程、schema 索引）
│   └─ schemas/*.json (5)     ★ v3：机器可校验的身份契约
├─ assets/
│   ├─ data/                  ★ v3：6 类创意模式库（全部带 source + license）
│   ├─ template/              Phaser 模板（v3 新增 events/audio/juice 三个运行时）
│   ├─ styles/  workflows/    画风预设 / ComfyUI 工作流
├─ scripts/*.py (24)          确定性工具
├─ tests/*.py (4)             ★ v3：49 个 pytest
└─ docs/10-upgrade/           本次升级的审计、架构、实现、测试、迁移、功能状态
```

## 二、五份身份契约（v3 的核心）

| 契约 | 文件 | 谁写 | 谁读 |
|---|---|---|---|
| **Creative DNA** | `docs/01-brief/creative-dna.json` | `creative_forge --dna` | 全部下游 |
| **Visual DNA** | `docs/02-art/visual-dna.json` | `art_director --dna` | `asset_forge`、`specialist_review` |
| **Audio DNA** | `docs/05-audio/audio-dna.json` | `audio_director --plan` | `audio_director --emit-ts` → `audio-config.ts` |
| **Juice Plan** | `docs/04-core-loop/juice-plan.json` | `juice_forge --plan` | `juice_forge --emit-ts` → `juice-config.ts` |
| **Experience Blueprint** | `docs/03-experience/experience-blueprint.json` | `experience_forge --plan` | `specialist_review`、`playtest` |

**这五份文件解决的是 v2 的结构性问题**：v2 的身份信息散落在 `content-blueprint.json`
的 world/story/art/audio 四个子树里，谁都可以单独改，没有交叉约束 ——
所以能拿 98 分，同时美术风格和叙事主题毫无关系。

## 三、数据流

```
idea + 平台(G0)
  │
  ├─► creative_forge --diverge ──► creative-concepts.json（5 个结构不同的方向）
  │      └─ --twist / --evaluate ──► 7 维评分 + 相似度分析 ──► creative-review.md
  │
  ├─► creative_forge --dna ──► creative-dna.json ★
  │                              │
  │   ┌──────────────────────────┴──────────────────────────┐
  │   ▼                          ▼                          ▼
  │ art_director            audio_director             experience_forge
  │  --propose 3 套           --plan 状态机              --plan 情绪曲线
  │  --dna ──► visual-dna ★   --emit stem 清单           --verify E1–E8
  │  --consistency            --qc 波形实测
  │   │                       --emit-ts ──► audio-config.ts
  │   ▼
  │ asset_forge --spec（真实读取 Visual DNA）──► prompts/ ──► gen_assets
  │
  ├─► juice_forge --plan ──► juice-plan ★ ──► --emit-ts ──► juice-config.ts
  │
  └─► 代码（events.ts / audio.ts / juice.ts / 玩法）
         │
         ├─► qa.mjs（断言 + 帧率基线 + 移动端）
         ├─► smoke.mjs（闭环）
         ├─► playtest.mjs（四策略真玩）──► playtest.json
         │
         └─► specialist_review（六项，带证据）──► verdict-specialist.json
                │
                └─► gate_check --stage ship（一票否决）
```

## 四、运行时三件套（模板新增）

| 文件 | 职责 | 关键设计 |
|---|---|---|
| `src/game/events.ts` | 统一事件总线 | 类型化事件、优先级、去重、异常隔离、环形日志、**不消耗随机数** |
| `src/game/audio.ts` | 自适应音频 | stem 分层、状态机、变体/冷却/并发、距离衰减、ducking、调试面板 |
| `src/game/juice.ts` | 表现引擎 | 14 类效果、按严重度分级、性能降级、`prefers-reduced-motion` |

**三者都是「配置驱动」**：`audio-config.ts` / `juice-config.ts` 由 Python 脚本从 DNA 生成。
改 DNA → 重跑脚本 → 运行时行为改变，**不需要改代码**。这是「DNA 真的接入流水线」的证据。

### 为什么事件总线是必需的

没有它的时候，同一个「玩家受伤」由玩法代码分别调用镜头震动、粒子、音效、UI 四遍，
四处各写一遍且强度不一致；想做「表现强度按严重度分级」时无从下手。

有了它之后：玩法只 `bus.emit('player_hit', {...})`，表现层、音频层、UI、埋点、自动化测试各自订阅。

## 五、状态机（24 阶段，向后兼容）

```
brief → creative → creative_dna → content → review_plan(R0) → review_richness(RC)
     → scaffold → art_bible → visual_dna → core_loop → review_graybox(R1)
     → art_forge → sprite_tools → audio_forge → audio_director
     → juice → experience → polish → perf_audit → qa → playtest
     → review_specialist → review_final(R2) → ship
```

- v1/v2 的 15 个键**全部保留**，只 append 8 个新键
- 旧项目 state.yaml 缺新键 → `stages.get(s, {}).get("status", "pending")` 天然返回 pending
- `STAGE_MODULES` 显式映射阶段 → 模块文件（修掉了「用序号推断文件名」的老 bug）

## 六、四道门禁

| 门禁 | 判据 | 位置 |
|---|---|---|
| G0 / G1 / G2 | 人工确认平台 / 方向 / 风格 | 平台表、创意评审后、视觉提案后 |
| R0 / RC / R1 / R2 | CrazyGames A–H + 四维丰富度 | 写代码前 / 写代码前 / 生图前 / 交付前 |
| **专项审核** | 创意·美术·动画·音频·体验·试玩 | R2 之前，**一票否决** |
| 工程回退 | 体积 / 帧率 / QA | 各阶段内，3 次上限 |

**审核官只审不写**：不改 `src/`、`assets/`、`docs/00–08`，只写 `docs/09-review/`。

## 七、与 v2 的差异一览

| 维度 | v2 | v3 |
|---|---|---|
| 创意 | 关键词推断唯一品类 | 5 个结构不同的方向 + 9 维反转 + 相似度分析 |
| 身份 | 蓝图四个子树各自为政 | 5 份 DNA 契约，下游强制读取 |
| 美术 | palette.json（颜色） | Visual DNA（轮廓/材质/光照/镜头/UI/比例/动画/FX） |
| 动画 | 写死 1 种 shake | 事件驱动的 14 类效果 + 强度分级 |
| 音频 | 只有文件，无播放层 | stem 分层 + 状态机 + 变体/冷却/距离 + 波形质检 |
| 体验 | 只数内容数量 | 情绪曲线 + 每关 10 项 + E1–E8 可验证判据 |
| 测试 | 0 个 Python 测试 | 49 个 pytest + qa/smoke/playtest 三个浏览器脚本 |
| 审核 | A–H 八维 | A–H + 六项专项（带真实像素与波形证据） |

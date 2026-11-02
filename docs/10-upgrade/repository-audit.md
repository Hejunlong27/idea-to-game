# IdeaToGame 仓库审计报告（v3.0 起点）

> 审计时间：2026-11-01
> 审计对象：`Hejunlong27/idea-to-game`（本地工作副本 `C:/Users/15274/.workbuddy-ai/skills/idea-to-game/`，HEAD `8691e14`）
> 审计方式：逐文件读取真实代码（`SKILL.md`、`README.md`、`modules/*.md` 14 份、`references/*.md` 12 份、
> `scripts/*.py` 20 个、`assets/template/` 全部 20 个文件、`assets/data/`、`assets/styles/`、`assets/workflows/`）。
> **本报告不依据 README 推断能力，所有结论都有代码位置支撑。**

---

## 1. 当前架构

### 1.1 形态

单一技能包（single skill package），不是多 Agent 编排。结构是：

```
SKILL.md                       # 唯一入口，规则 + 阶段表 + 降级表
modules/*.md (14)              # 能力环节的「执行说明书」（Markdown，给 Agent 读）
references/*.md (12)           # 判据与契约（标准、流程、文件格式、平台红线）
scripts/*.py (20)              # 确定性工具（Python 3.9+，仅依赖 PyYAML / Pillow / numpy）
assets/template/               # Phaser 3.90 + Vite 5 + TS 5 项目模板（含 5 个平台适配器）
assets/data/                   # 结构化词库（48 机制 / 8 叙事框架）
assets/styles/                 # 5 档画风预设（style_tokens + 配色板）
assets/workflows/              # ComfyUI API 格式工作流（Qwen-Image 2.1 turbo t2i/i2i）
docs/                          # 技能自身的演示 GIF
```

### 1.2 控制流

**没有运行时编排器。** 编排 = `SKILL.md` 的流程表 + `scripts/state.py` 的状态机 +
`scripts/gate_check.py` 的产物校验 + `scripts/review_gate.py` 的审核判定。
Agent 每次读一个 `modules/*.md`，执行，跑脚本，落盘，改状态。中断后从 `.gamedev/state.yaml` 续跑。

`STAGES`（`scripts/_common.py:17-34`）共 15 项：

```
brief → content → review_plan(R0) → review_richness(RC) → scaffold → art_bible
      → core_loop → review_graybox(R1) → art_forge → sprite_tools → audio_forge
      → polish → perf_audit → qa → review_final(R2) → ship
```

### 1.3 两道并行的质量标准

| 标准 | 判据文件 | 判定器 | 挡什么 |
|---|---|---|---|
| 能不能上架 | `references/crazygames-standard.md`（A–H 八维，REQ 60 + GUIDE 28） | `scripts/review_gate.py` | R0/R1/R2 三处硬闸，REQ 任一 FAIL → `REJECTED` |
| 值不值得上架 | `references/content-depth.md`（四维百分制） | `scripts/richness_check.py` | RC 一处硬闸，非 `RICH` 不得写代码 |

### 1.4 数据流（文件契约）

```
idea + 平台
  → docs/00-platforms/platform-plan.md
  → docs/01-brief/{gdd.md, scope.json, content-blueprint.json, story.md}
  → docs/09-review/{r0-plan-review.md, verdict-r0.json}
  → docs/09-review/richness.json
  → src/ + package.json（模板复制）
  → docs/02-art/{palette.json, art-bible.md, asset-spec.json, prompts/*}
  → src/game/levels.json
  → docs/09-review/verdict-r1.json
  → assets/raw → assets/processed → assets/atlas
  → docs/05-audio/{sfx,music,voice}-plan.json → assets/audio/{sfx,bgm,voice}
  → docs/05-polish/juice-log.md → docs/06-perf/report.md → docs/07-qa/report.html
  → docs/09-review/verdict-r2.json → dist/<platform>.zip
```

**契约是硬编码的**：`gate_check.py:20-62` 的 `REQUIRED_FILES` 字典就是契约本身，
`references/contracts.md` 是它的人读版本。两者需要同步维护。

---

## 2. 模块依赖关系

### 2.1 脚本层（真实 import 关系）

```
_common.py  ←── 所有脚本（STAGES / PLATFORMS / state 读写 / 体积与 URL 扫描）
   ▲
   ├── state.py           状态机读写（唯一真相源 .gamedev/state.yaml）
   ├── gate_check.py      阶段产物校验（REQUIRED_FILES + 11 个 check_* 函数）
   ├── init_project.py    建项目（复制 assets/template + 写 artgen.yaml + state.yaml）
   │      └── style_lib.py（--style 时被 import 进来 apply 预设）
   ├── content_forge.py   蓝图骨架 / 分析 / 校验（读 assets/data/*.json）
   ├── richness_check.py  四维打分（读 blueprint + palette + asset-spec + sfx/music/voice-plan + levels.json）
   ├── asset_forge.py     素材规格 → 提示词 → lint（读 blueprint + palette）
   ├── audio_forge.py     三份 plan（**import gen_audio.RECIPES** 校验配方名）
   │      └── gen_audio.py（numpy 合成 + ffmpeg 转码，被 audio_forge --synth 以 subprocess 调用）
   ├── gen_assets.py      生图通道（comfyui / runninghub / placeholder，1417 行，最大单体）
   ├── gen_prompts.py     ⚠ 另一条提示词生成路径（读 scope.json）
   ├── sprite_tools.py    抠图/裁边/统一画布
   ├── pack_atlas.py      图集打包
   ├── palette_extract.py 从参考图提色板 → palette.json
   ├── review_gate.py     A–H 判定（19 个 auto_* 探针 + 人工条目合并出 verdict）
   ├── measure_bundle.py  体积审计
   ├── precheck.py        过审自检（平台标记 / 外部 URL / 绝对路径）
   └── ship_pack.py       一键构建 + 审计 + 自检 + zip + 商店素材
```

### 2.2 模板层

```
src/main.ts ──► src/platform/index.ts ──► 5 个适配器 + mock（if 链，可被 Rollup 折叠）
    │                    ▲
    │              registry.set('platform', ...)
    ▼                    │
src/game/index.ts ──► scenes/{Boot,Menu,Play,GameOver}
                             │
                             └── util.ts bridge(scene) ──► 读 registry（**唯一合法通道**）
                             └── anim.ts（图集帧动画注册）
                             └── config.ts（全部数值）
```

**架构硬规则已落地且有校验**：`gate_check.py:191-198` 用正则扫描 `src/game/` 是否 import 了
`platform`，违规直接 FAIL。这条规则是有效的。

### 2.3 依赖倒置缺口

`asset_forge.py`、`content_forge.py`、`audio_forge.py` **各自从蓝图的不同子树取数**，
彼此不共享「身份」层：

| 脚本 | 读什么 | 写什么 |
|---|---|---|
| `content_forge` | idea + `assets/data/mechanic-vocab.json` | `content-blueprint.json`（world/story/mechanics/levels/art/audio） |
| `asset_forge` | blueprint.`art` + `palette.json` | `asset-spec.json` |
| `audio_forge` | blueprint.`audio` + blueprint.`story.dialogue` | `sfx/music/voice-plan.json` |

**没有一份文件是「玩法、叙事、美术、音频都必须遵守」的。** 蓝图是一个大桶，
`art` 与 `audio` 只是它的两个子树，谁都可以单独改，没有交叉约束。
这是「四块各做各的、最后拼起来不统一」的结构性原因。

---

## 3. 现有功能完成度

判定口径：**DONE** = 有脚本/代码且接入流水线且能被 gate 校验；
**PARTIAL** = 有代码但未接入或被 gate 绕过；**DOC_ONLY** = 只有文档；**ABSENT** = 不存在。

### 3.1 生产链路

| 能力 | 状态 | 证据 |
|---|---|---|
| 平台确认（G0） | DONE | `state.py set-platforms` + `gate_check.check_brief` 校验 `platform_confirmed` |
| 立项（GDD + scope） | DONE | `modules/01-brief.md` + `check_brief` 校验 6 字段 + MVP ≤6 |
| 内容蓝图（世界观/三幕/机制/关卡取舍） | DONE | `content_forge.py`（643 行）+ `check_content` + `--validate` |
| 机制咬合校验 | DONE | `content_forge.py:536-556` 校验 `interacts` 引用真实性 + 自引用 |
| 丰富度门禁（四维 + X1–X4 交叉校验） | DONE | `richness_check.py`（525 行），实测基线 14.5 / 98.0 |
| 项目脚手架（模板 + 5 适配器） | DONE | `init_project.py` + `assets/template/` |
| 画风预设（5 档） | DONE | `style_lib.py` + `assets/styles/*.json` |
| 色板提取 | DONE | `palette_extract.py`（参考图 → palette.json） |
| 素材规格（9 role + 七槽位提示词 + lint） | DONE | `asset_forge.py`（493 行） |
| 生图通道（ComfyUI / RunningHub / 占位 + 断点续跑 + 台账） | DONE | `gen_assets.py`（1417 行） |
| 抠图 / 裁边 / 图集 | DONE | `sprite_tools.py` + `pack_atlas.py` |
| 音频方案（三层 plan + 通道探测 + YuE2/TTS 调用清单） | DONE | `audio_forge.py`（473 行） |
| 音频生产（L1 合成 + ffmpeg 转码） | DONE | `gen_audio.py`（440 行，8 个配方） |
| 体积/帧率审计 | DONE | `measure_bundle.py` + `review_gate.auto_fps` |
| 自动化 QA（截图 + 状态断言） | **PARTIAL** | `modules/10-qa.md` 要求 `smoke.mjs` / `qa.mjs`，**模板 `assets/template/scripts/` 里没有这两个文件**（只有 build-standalone / serve / shots / test-standalone / zip-all）。每个项目都要重写一遍，且没有回灌模板 —— 这正是「同一个坑犯两次」的机制性原因 |
| 打包交付 | DONE | `ship_pack.py` + `precheck.py` |
| 审核门禁 R0/R1/R2 | DONE | `review_gate.py`（717 行，19 个自动探针）+ 按阶段分文件的 verdict |

### 3.2 创意 / 美术 / 动画 / 音频 / 体验（v3 的目标域）

| 能力 | 状态 | 证据与缺口 |
|---|---|---|
| 创意发散（多方案） | **ABSENT** | `content_forge.infer_genre()` 用关键词计分选**唯一**品类；`build_skeleton()` 直接产出一份蓝图。全链路没有「生成 5 个实质不同的方向再选」这一步。**这是「换皮」的根因**：系统从第一步就只有一条路 |
| 创意反转（Twist） | **ABSENT** | 蓝图有 `mechanics.twists` 字段，但它只是「第二个机制层」的槽位，没有任何反转维度（颠覆操作/胜利条件/失败即玩法/声音即机制…）的生成或校验 |
| Unique Mechanic 判定 | **PARTIAL** | `content_forge --validate` 校验「机制 ≥5 且互相咬合」，但**不校验独特性**。5 个常规机制互相咬合也能全过 |
| 原创性/相似度检查 | **ABSENT** | 无任何机制套路识别、无相似度分析。`review_gate` 只有合规与可玩性探针 |
| Creative DNA（统一身份） | **ABSENT** | 身份信息散落在 `content-blueprint.json` 的 world/story/art/audio 四个子树 + `palette.json`。**没有单一身份文件，也没有任何机制强制四个生产域读同一份身份** |
| 多风格探索（≥3 套提案） | **ABSENT** | `style_lib.py` 是 5 档**固定预设选择器**（`apply <key>`），正是任务书明确反对的形态。`palette_extract.py` 只能从一张参考图提色，不能提案 |
| Visual DNA | **ABSENT** | `palette.json` 只有 style_tokens / primary / accent / background / negative。**没有轮廓语言、材质、纹理、光照方向、阴影规则、镜头、景深、字体排版、角色比例、动画风格、特效风格** |
| 角色一致性（参考图 + seed + ref 链） | **PARTIAL** | `asset_forge.mk_item()` 有 `seed` 与 `ref` 字段，`cmd_prompts` 会给主角后续姿态挂 `ref=assets/raw/<base>.png`。但：① 只覆盖 `character` role；② 依赖 `use_hero_ref` 字段而该字段**从未被写入**（`mk_item` 不产出它），所以 ref 链实际**默认不生效**；③ 没有正面/侧面/背面参考图；④ 无法保证一致性的通道没有记录降级状态 |
| 场景视觉叙事 | **ABSENT** | `bg` role 只有「宽幅建立镜头」一个模板，无「环境随进度变化 / 灯光反映危险 / 颜色暗示机关」的结构化字段 |
| 美术审核（程序化） | **ABSENT** | `richness_check.score_art()` 只数「有没有」，不判「好不好」。没有色相分布检查、没有分辨率检查、没有透明通道检查、没有实际截图审查 |
| 帧动画注册 | DONE | `anim.ts`（78 行，图集帧 → `<key>_loop`） |
| Game Juice 系统 | **ABSENT** | 全模板只有 `PlayScene.ts` 里两处 ad-hoc `cameras.main.shake()` + 几个 tween。任务书要求的 14 类效果（squash&stretch / anticipation / follow through / secondary motion / parallax / particle / environmental / UI motion / camera shake / zoom / hit stop / slow motion / screen flash / transition）**只存在 shake 一种，且写死在玩法代码里** |
| 事件驱动表现 | **ABSENT** | `grep -rn "emit(|EventBus|dispatcher" assets/template/src/` → 0 命中。事件是各场景自己调平台桥（`bridge(this).gameplayStart()`），**没有任何统一事件通道** |
| 音频运行时 | **ABSENT** | `grep -rln "sound|audio|AudioContext" assets/template/src/` → 只有 `main.ts`（iOS resume + `pauseAll`）。**游戏侧没有任何音频管理器**：没有分层播放、没有音量总线、没有并发限制、没有变体、没有自适应音乐、没有 ducking、没有距离衰减。音频只有「文件」，没有「系统」 |
| Adaptive Music（stem 分轨） | **ABSENT** | `music-plan.json` 是「一首曲子一个 mood」，`MUSIC_STYLES` 6 个固定 mood。没有 stem、没有状态机、没有交叉淡化、没有分层音量 |
| 动态音效（变体/防重复/距离/滤波/声像/并发） | **ABSENT** | `sfx-plan` 只有 id/layer/cue/recipe/priority，**没有变体组、没有冷却、没有距离参数** |
| 情绪化声音设计 | **ABSENT** | 无「濒死心跳/低频增强/环境衰减」这类状态驱动规则 |
| 声音即玩法 | **ABSENT** | 无任何机制级音频钩子 |
| 音频质量审核（削波/静音/循环接缝/峰值/频率冲突） | **ABSENT** | `check_audio` 只查「目录非空 + 不是 wav + 总体积 ≤2MB」。**不做任何波形分析** |
| 音频调试模式 | **ABSENT** | 无 |
| 玩家体验目标 / 情绪曲线 | **ABSENT** | 蓝图只有 `audio.mood_arc`（音频情绪），**没有玩家情绪曲线、没有每关学习内容/新机制/核心决策/高潮/奖励/下一关期待** |
| 前 10 秒可理解性等体验判据 | **ABSENT** | 无 |
| Playtest Agent（实际操作游戏） | **ABSENT** | 只有 `shots.mjs`（截图）和 `test-standalone.mjs`（单文件版冒烟）。**没有操作模拟、没有事件记录、没有状态快照、没有卡死检测、没有试玩报告** |
| 统一 Game Event Schema | **ABSENT** | 无 |
| 专项审核（创意/美术/动画/音频/体验/试玩） | **ABSENT** | `review_gate.PHASE_DIMS` 只有 A–H 八维（可玩性/技术/合规），**没有一条判「视觉身份是否成立」「声音是否表达情绪」** |
| 创意/风格参考库 | **PARTIAL** | 有 `assets/data/mechanic-vocab.json`（48 机制）与 `story-frames.json`（8 框架）。**没有 visual-styles / audio-styles / gameplay-patterns / emotional-patterns / character / animation 库，且已有两个库没有 license/source 字段** |
| JSON Schema + 校验脚本 | **ABSENT** | 全部校验都是手写 `if` 判断，没有一份 schema 文件，没有通用校验器 |
| Python 自动化测试 | **ABSENT** | `ls tests` → 不存在。**零 pytest**。20 个脚本全靠人工跑一遍看输出 |

### 3.3 完成度汇总

| 域 | DONE | PARTIAL | ABSENT |
|---|---|---|---|
| 生产链路（v1/v2） | 18 | 1 | 0 |
| 创意 | 0 | 1 | 3 |
| 美术 | 0 | 1 | 5 |
| 动画/表现 | 1 | 0 | 2 |
| 音频 | 0 | 0 | 8 |
| 体验 | 0 | 0 | 2 |
| 事件系统 | 0 | 0 | 1 |
| 质量审核 | 2 | 0 | 2 |
| 工程基础（测试/schema） | 0 | 0 | 2 |

**结论：v2 把「产量与丰富度」做扎实了，但「创意身份 → 视觉身份 → 声音身份 → 体验身份」这条纵向链条完全不存在。**
现状是「一条流水线 + 若干可数指标」，不是「一个能做出有辨识度作品的 Studio」。

---

## 4. 主要技术债务

按修复成本 × 影响面排序。

### T1. 创意环节缺失，导致结构性换皮（最高优先级）
`content_forge.infer_genre()` 用 13 个品类的关键词表计分，取最高分作为唯一品类；
`build_skeleton()` 的机制来自 `match_mechanics()`（品类命中 +5、中文 2-gram 命中 +4）。
同一个 idea 永远得到同一个蓝图。**系统没有「发散」这一步，只有「收敛」**。
这不是提示词问题，是流程缺一个阶段。

### T2. 身份信息没有单一真相源
`content-blueprint.json` 同时承载世界观、机制、关卡、美术、音频五个域的字段。
`richness_check` 分别给四个维度打分，但**维度之间没有一致性校验**
（唯一的交叉校验 X1–X4 是「声明 vs 产物」，不是「美术 vs 叙事」）。
后果：可以拿 98 分，同时美术风格和叙事主题毫无关系。

### T3. 美术环节是「素材工厂」，不是「视觉设计系统」
`asset_forge.ROLES` 的 9 个模板全部是**出图参数**（view / extra / bg / trim / budget），
没有一个字段描述「这套视觉的语言」：轮廓怎么走、材质是什么、光从哪来、阴影硬还是软、
镜头是俯视还是平视、UI 的圆角和字重是多少、角色几头身。
`palette.json` 只有颜色。**颜色不是视觉身份。**

### T4. 角色一致性机制实际未生效
`asset_forge.py:300-304` 的条件里用了 `i.get("use_hero_ref")`，
但 `mk_item()`（第 221-240 行）**从不写这个字段**。因此 ref 链默认不挂，
只有手工编辑 `asset-spec.json` 加上 `use_hero_ref: true` 才会生效。
这是「代码写了但默认走不到」的典型——比没写更危险，因为它看起来是有的。

### T5. 音频只有文件没有系统
`audio_forge` 产出 plan，`gen_audio` 产出 mp3，然后……没有了。
模板里没有播放层。这意味着：分层的意义（ui/gameplay/feedback/ambience）在运行时不存在，
四个层只是四个文件夹。**自适应音乐、动态混音、并发控制、距离衰减全部无从谈起。**

### T6. 表现力写死在玩法代码里
`PlayScene.hitTarget()` 里直接 `this.cameras.main.shake(...)`。
换玩法就要重写一遍手感，且不同事件用同一个 shake 参数（任务书明确反对）。
没有「事件 → 表现」的映射表，表现强度无法按事件严重程度分级。

### T7. QA 能力未回灌模板
`modules/10-qa.md` 与 `references/delivery-standards.md` 都要求 `scripts/smoke.mjs` + `scripts/qa.mjs`，
但模板里没有。每个项目重写一遍，写法各不相同，gate 也无法统一校验。
（这与 MEMORY 里记录的「修复必须回灌模板」是同一条教训，已被验证犯过两次。）

### T8. 双提示词生成路径
`gen_prompts.py`（读 `scope.json`）与 `asset_forge.py --prompts`（读 `asset-spec.json`）
都往 `docs/02-art/prompts/` 写文件。两者对同一目录的写入格式不同（sidecar 字段不一致），
后跑的覆盖先跑的。`gate_check.check_art_bible` 只校验「含 style_tokens」，看不出差异。

### T9. 状态机与模块文件靠序号耦合
`state.py:167-168`：
```python
idx = STAGES.index(s) + 1
print(f"读模块：modules/{idx:02d}-*.md")
```
`STAGES` 里第 2 项是 `content`，会打印 `modules/02-*.md` —— 而 02 是 `scaffold`。
`STAGES` 一旦插项，提示就错。应该改成阶段 → 模块文件的显式映射表。

### T10. 零自动化测试
20 个 Python 脚本、1400 行的 `gen_assets.py`、717 行的 `review_gate.py`，没有任何测试。
改判据（例如调四维权重）只能靠手工跑一个真实项目看输出。这是 v3 每次改动的最大风险。

### T11. 契约硬编码在两处
`gate_check.REQUIRED_FILES`（代码）与 `references/contracts.md`（文档）是同一份契约的两个副本，
没有生成关系，只能靠人同步。

### T12. `check_audio` 的判据与 v2 判据冲突
`gate_check.check_audio` 对 `n_sfx < 16` 只给 WARN，而 `richness_check.U1` 对 `<16` 直接扣分并可能判 THIN。
同一件事两个口径，容易让 Agent 以为 gate 过了就没事。

---

## 5. 需要保留（不得改动语义）

| 项 | 原因 |
|---|---|
| 单一技能包形态 | 12+ 能力环节 + 审核官同包，靠文件契约串联。v3 继续用这个形态，**不拆多 Agent**（任务书 2.3 明确要求） |
| `state.yaml` 作为唯一真相源 | 续跑、迁移、审计全靠它。v3 只**追加**阶段键，不重命名、不删除 |
| `STAGES` 的 15 个既有键名 | 旧项目 state.yaml 里就是这些键。新增阶段只能 append，旧键必须保留（缺失时按 pending 处理，天然向后兼容） |
| 三处人工门禁 G0/G1/G2 | 平台/方向/风格必须人确认 |
| 三处审核门禁 R0/RC/R1/R2 + R3 回环 | 一票否决、只审不写、不设轮次上限、复审全量重跑 |
| `references/crazygames-standard.md` 作为唯一判据 | 标准不可放宽 |
| `references/content-depth.md` 四维权重 30/25/25/20 | 保留总分与 THIN 判定，v3 只在其上**追加**专项审核，不改权重 |
| `src/game/` 禁止 import `src/platform/` | 有 gate 校验，有效 |
| 全部数值集中在 `src/game/config.ts` | 调参入口唯一 |
| `levels.json` 作为 TS/Python 双端真相源 | 静态可解性校验依赖它 |
| 平台参数集中在 `_common.PLATFORMS` | 单一真相源 |
| `createPlatform()` 的 if 链写法 | switch 会导致 6 个适配器全进包（已实测） |
| 模板的启动看门狗 + 单文件版 | `file://` 静默失败的防线 |
| 音频 MP3 96k 单声道 + 禁 wav | 体积红线 |
| 生图通道可配置可降级 | 不允许因为没显卡卡死流程 |

---

## 6. 需要增强（改原模块，不新建重复模块）

| 模块 | 增强内容 |
|---|---|
| `content_forge.py` | ① 读 `creative-dna.json` 作为唯一身份输入；② `--scaffold` 生成的蓝图字段与 DNA 交叉引用（`dna_ref`）；③ `--validate` 增加「蓝图与 DNA 一致性」检查 |
| `asset_forge.py` | ① 读 `visual-dna.json` 的轮廓/材质/光照/镜头/比例字段拼进七槽位；② **修复 T4**：`mk_item` 直接写 `use_hero_ref`，默认给主角后续姿态挂 ref；③ 新增 `--consistency` 生成三视图参考计划并记录通道降级状态 |
| `richness_check.py` | ① 追加「身份一致性」交叉校验 X5（DNA ↔ 蓝图 ↔ palette ↔ 音频 plan）；② 保留四维权重与 THIN 判定不变 |
| `gate_check.py` | ① 新增阶段的 `REQUIRED_FILES` 与 checker；② 新增 `check_dna` / `check_visual_dna` / `check_experience` / `check_juice` / `check_specialist_review`；③ 统一 `check_audio` 与 U1 口径 |
| `state.py` | ① 修 T9：阶段 → 模块文件显式映射；② 新增阶段自动出现在 `show`（因为读 STAGES） |
| `init_project.py` | ① 建 v3 需要的 docs 子目录（`01-brief` 已有，新增 `03-experience` 等）；② 写 `creative.yaml` 默认配置 |
| `review_gate.py` | 不改变 A–H 判据，只把「专项审核结论」作为 R2 的附加阻断条件读取 |
| 模板 | 新增 `events.ts` / `juice.ts` / `audio.ts`；`PlayScene` 改为事件驱动；新增 `qa.mjs` / `smoke.mjs` / `playtest.mjs` |

---

## 7. 需要新增

### 7.1 脚本（8 个）

| 脚本 | 职责 | 产物 |
|---|---|---|
| `creative_forge.py` | 创意发散（5 方案）+ 创意反转（9 维度）+ Uniqueness 启发式 + 7 维评分 + DNA 生成与校验 | `creative-concepts.json`、`creative-dna.json`、`creative-review.md` |
| `art_director.py` | 三套风格提案 + 视觉语言混合 + Visual DNA + 角色一致性计划 | `style-proposals.json`、`visual-dna.json` |
| `audio_director.py` | 自适应音乐（stem）+ 动态音效规则 + 情绪声设计 + 音频 QC | `audio-dna.json`、`adaptive-music.json`、`audio-qc.json` |
| `juice_forge.py` | 事件 → 表现映射矩阵（14 类效果，按严重度分级） | `juice-plan.json` |
| `experience_forge.py` | 玩家情绪曲线 + 每关体验表 + 前 10/30 秒判据 | `experience-blueprint.json` |
| `specialist_review.py` | 六项专项审核（创意/美术/动画/音频/体验/试玩），**每项必须有证据** | `docs/09-review/specialist-*.json` + `verdict-specialist.json` |
| `schema_check.py` | 通用 JSON Schema（子集）校验器，零依赖 | 退出码 + 报告 |
| `playtest.py` | 试玩编排（起服务 → 跑 playtest.mjs → 汇总报告） | `docs/07-qa/playtest-report.html` |

### 7.2 Schema（5 份）

`references/schemas/`：`creative-dna.schema.json`、`visual-dna.schema.json`、
`game-event.schema.json`、`experience-blueprint.schema.json`、`juice-plan.schema.json`。

### 7.3 参考库（6 个目录）

`assets/data/creative-patterns/`、`visual-styles/`、`audio-styles/`、`gameplay-patterns/`、
`emotional-patterns/`、`character-patterns/`、`animation-patterns/`。
**每个模式必须带 `source` 与 `license` 字段**（任务书 §12.5），且只是「抽象原则」，不含受版权保护的素材。

### 7.4 模板运行时（3 个模块）

| 文件 | 职责 |
|---|---|
| `src/game/events.ts` | 统一事件总线：类型化事件、优先级、去重、清理、只读快照、确定性（不消耗随机数） |
| `src/game/juice.ts` | Game Juice 引擎：订阅事件 → 14 类效果；强度分级；性能降级；`prefers-reduced-motion` 无障碍 |
| `src/game/audio.ts` | 自适应音频：总线、stem 分层、状态机、变体组、冷却、并发上限、ducking、距离衰减、调试面板 |

### 7.5 测试

`tests/`：pytest 套件覆盖 schema、状态机、文件契约、DNA 校验、Visual DNA、音频规划、
创意评分确定性、事件 schema 一致性。模板侧 `scripts/qa.mjs`（断言 + 性能 + 移动端）、
`scripts/smoke.mjs`（闭环截图）、`scripts/playtest.mjs`（自动试玩）。

### 7.6 文档

`docs/10-upgrade/` 六份（本报告 + roadmap + architecture-v3 + implementation-report +
test-report + migration-guide + feature-status）；`modules/` 新增 7 份；
`references/` 新增 3 份（game-event-schema / audio-emotion-design / creative-identity）。

---

## 8. 推荐实施顺序

严格按依赖排序，每步都能独立验证。

| 序 | Phase | 内容 | 依赖 | 验证方式 |
|---|---|---|---|---|
| 1 | P0 | 本审计 + 架构设计 | — | 本文件 |
| 2 | P1 | `schema_check.py` + 5 份 schema | — | `pytest tests/test_schema.py` |
| 3 | P1 | 创意模式库（6 类，带 license） | — | schema 校验 |
| 4 | P1 | `creative_forge.py`（发散/反转/评分/DNA） | 2,3 | 同一 idea 生成 5 个可区分方案；确定性可复现 |
| 5 | P1 | 蓝图接入 DNA（`content_forge` 增强） | 4 | 蓝图与 DNA 交叉引用一致 |
| 6 | P2 | `art_director.py` + Visual DNA | 2,4 | 3 套提案可区分；DNA 字段齐全 |
| 7 | P2 | `asset_forge` 读 Visual DNA + 修 T4 | 6 | 提示词含视觉 DNA 词；ref 链默认生效 |
| 8 | P3 | `audio_director.py` | 2,4 | stem/状态/变体/QC 齐备 |
| 9 | P3 | 模板 `audio.ts` | 8 | 浏览器内可切状态、有调试面板 |
| 10 | P4 | `juice_forge.py` + 模板 `events.ts` / `juice.ts` | 2 | 事件驱动表现，14 类效果可配置 |
| 11 | P5 | `experience_forge.py` | 4 | 情绪曲线 + 每关体验表 |
| 12 | P5 | `playtest.py` + 模板 `playtest.mjs` | 10 | 能真跑游戏并出报告 |
| 13 | P6 | `specialist_review.py` + gate/state 集成 | 4,6,8,10,11,12 | 六项审核有证据；gate 能阻断 |
| 14 | P7 | Showcase Demo | 全部 | 可玩 + 自动化测试通过 |
| 15 | P8 | pytest 全套 + 文档 + 交付 | 全部 | 真实执行结果 |

**关键判断：先做 P1（创意 + DNA），因为它是所有后续环节的输入。**
如果先做美术或音频，它们只能继续从蓝图散字段取数，等于把 T2 的债再欠一遍。

---

## 9. 兼容性风险评估

| 风险 | 评估 | 缓解 |
|---|---|---|
| 新增 STAGES 破坏旧项目 | **低**。`load_state` 返回 dict，`stages.get(s, {}).get("status", "pending")` 对缺失键返回 pending | 只 append；`state.py show` 自动显示新阶段为 pending |
| 新增 REQUIRED_FILES 让旧项目 gate 失败 | **中**。旧项目没有 `creative-dna.json` | 新阶段单独成 key，不并入旧阶段；旧项目跳过新阶段时 `status=skipped` 即可通过 |
| `richness_check` 改判据导致旧项目从 RICH 掉档 | **高** | 四维权重与 X1–X4 **一律不动**；身份一致性作为**新的 X5**，且只在 DNA 存在时才检查 |
| 模板新增模块导致旧项目构建失败 | **低**。新增文件不被引用不影响构建 | `events.ts`/`juice.ts`/`audio.ts` 均为可选 import；`PlayScene` 的改动保持向后兼容 |
| `createPlatform` if 链被误改 | **中** | 保持原样，不动 |
| 音频新增运行时增加包体 | **低**。三个模块纯 TS，压缩后 < 8KB | 无外部依赖，全部用 Phaser 内置 WebAudio |

---

## 10. 审计结论

1. **v2 的生产链路是扎实的**：20 个脚本、15 个阶段、两道质量闸、有真实项目验证（4 个游戏）。
   这部分不能推倒，只能加。
2. **缺的不是能力数量，是纵向一致性**。玩法、叙事、美术、音频四个域各自有生成器和评分项，
   但没有共享的身份定义，也没有跨域一致性校验。这是「作品没有辨识度」的机制性原因。
3. **创意环节的缺失是根因**。系统从第一步就只有一个方向，后面所有环节都在为这一个方向服务。
   加 5 个发散方案 + 反转维度 + 独特性判定，成本最低、杠杆最高。
4. **动画与音频的缺口是「运行时」而非「素材」**。素材生成已有（生图 + 合成音频），
   但游戏里没有播放系统、没有事件通道，所以素材的价值发挥不出来。补齐运行时即可。
5. **零测试是最大工程风险**。v3 会改 10 个以上脚本，没有回归网就等于闭眼改。
   测试必须与功能同步落地，不能留到最后。

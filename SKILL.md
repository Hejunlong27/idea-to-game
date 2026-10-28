---
name: idea-to-game
description: "将一句游戏想法或一款同款游戏名，连同美术风格参考图，自动转化为一个完整可玩、可提交到 CrazyGames / Poki / GameDistribution / Playgama / TapTap 等平台的 HTML5 小游戏。覆盖平台确认、立项策划、项目脚手架、平台 SDK 适配、玩法实现、AI 生图、切图打包图集、配乐音效、手感打磨、性能与体积审计、自动化测试、多平台打包过审共 12 个环节，并内置一名按 CrazyGames 官方审核与质量标准（作为不可放宽的硬底线）独立把关的'质量与玩法审核官'角色，未达标必须持续修改并重新送审直至通过。收到第一个指令后必须先向用户确认目标平台（并告知支持的平台清单），交付包严格按用户选定的平台产出。This skill should be used when the user wants to make a small/browser/HTML5/casual/hyper-casual game, or says 做个游戏、做个小游戏、我要做一款游戏、照《XX》做一个、开发网页游戏、上线到 CrazyGames/Poki/TapTap、make a game like XX、build an HTML5 game。Also use when the user provides an idea plus a style reference image and expects a playable game as output, or asks whether a game meets CrazyGames quality standards."
agent_created: true
---

# IdeaToGame

## Overview

把一个游戏想法，端到端地变成一个能玩、能提交到平台的 HTML5 小游戏。

**输入**：一个 idea（一段想法描述，或一款同款游戏名）+ 一张美术风格参考图 + **目标平台**
**输出**：完整可玩的小游戏项目，含**用户选定平台**的可分包与过审自检清单

本技能是**单一技能包**：12 个能力环节 + 1 名审核官角色全部内置于本包，不依赖外部安装的其他技能。所有环节通过 `modules/` 下的模块说明驱动，通过 `scripts/` 下的脚本落地，通过文件契约在环节之间传递产物。

## ⚠️ 第二件事：审核官在场

本技能内置一名**质量与玩法审核官**（Reviewer），唯一判据是 `references/crazygames-standard.md`，在三处硬闸介入：

| 轮次 | 时机 | 挡什么 |
|---|---|---|
| **R0** | 立项后、写代码前 | 挡「玩法不成立就开工」 |
| **R1** | 灰盒可玩后、**生图之前** | 挡「玩法不成立就烧素材成本」 |
| **R2** | 性能与测试通过后、交付之前 | 挡「未达标就交付」 |

**三条铁律，不可协商**：

1. **只审不写** —— 审核官不得修改 `src/`、`assets/`、`docs/00`–`08`。只产出问题单与修改建议，修复退回对应环节执行（防止生产者自评自批）。
2. **标准固定** —— CrazyGames 标准是**底线**，不得因用户催促、改范围、换平台而放宽。REQ 条目任一 FAIL 一律阻塞，**永不豁免、永不降级**。
3. **一票否决** —— `review_final.verdict` 非 `PASS`/`PASS_WITH_DEVIATIONS` 时，`ship` 阶段被 `gate_check.py` 硬阻断，绕过不了。

**未达标必须持续修改并重新送审，直至通过 —— 不设轮次上限。** 每轮复审全量重跑（禁止只测修过的条目）；同一维度连续 2 轮同类问题必须更换修复策略。

详见 `modules/12-review.md`。

## ⚠️ 第一件事：确认目标平台

**收到用户的第一个指令后，不要立刻开工。先输出下面的平台表，问用户准备发到哪些平台，拿到回复后再进入立项。**

理由：平台选择同时决定**体积红线、SDK 接入方式、合规前置条件、商店素材规格、投递顺序** —— 定晚了就是返工。交付包也必须严格按用户选定的平台产出，不多不少。

| 平台 key | 名称 | 区域 | 形态 | 首包红线 | 额外前置条件 |
|---|---|---|---|---|---|
| `crazygames` | CrazyGames | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 无（Basic Launch 自助提交） |
| `poki` | Poki | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 提报制：需可玩链接 + 3 张实机截图 |
| `gamedistribution` | GameDistribution | 海外 | 分发聚合（3000+ 发布商） | ≤50MB | SDK 强制；审核最长 3 周；不收同款 |
| `playgama` | Playgama | 海外 | 分发网络（25+ 平台） | ≤50MB | 需自行接入 Bridge SDK |
| `taptap` | TapTap | 国内 | 网页游戏 H5 / Tap 小游戏 | **≤60MB**（优秀 ≤20MB） | **Tap 小游戏需前置备案**；广告位需在 Dirichlet 创建 |

**规则**：
- 支持多选，也支持后续追加
- **不得替用户默认选择**，不得用「先按全平台做」敷衍
- 用户回复模糊时确认具体范围
- 选了多个平台时，**体积预算取最严的一条**（如 `crazygames` + `taptap` → 按 20MB 做）

详细执行步骤见 `modules/00-platforms.md`。

## 触发场景

在以下任一情形使用本技能：

- 用户提出游戏想法并期望得到可玩的成品，例如「做个合成水果的小游戏」「做一个躲避障碍的网页游戏」
- 用户给出同款游戏名，例如「照《合成大西瓜》做一个」「仿一下 Flappy Bird」
- 用户提供风格参考图 + 玩法描述，要求产出游戏
- 用户要求把游戏发布到 CrazyGames / Poki / GameDistribution / Playgama / TapTap 等平台
- 用户要续做或改进本技能此前产出的游戏项目（项目内存在 `.gamedev/state.yaml`）

**不适用**：3D 重资产游戏、需要长剧情/重叙事的游戏、多人联网游戏（首版不支持，应明确告知用户）。

## 核心工作流

按 P-1 → P4 推进。**共三处需要人工确认**，其余全自动。

```
输入：idea + 风格参考图（+ 用户回复的目标平台）
  ↓
[P-1 平台确认] modules/00-platforms.md
              先告知支持平台 → 问用户发哪些 → 定体积预算（取最严）
  ↓
  ◆ 门禁 G0：用户回复平台清单（必做，绝对不可跳过）
  ↓
[P0 立项]   modules/01-brief.md         → docs/00-platforms/ + docs/01-brief/
  ↓
  ◆ 门禁 G1：向用户确认方向（必做）
  ↓
[R0 审核]   modules/12-review.md        → docs/09-review/r0-plan-review.md
            ★ 审可审性与合规初筛；结论 REJECTED / INCOMPLETE 不得往下走
  ↓
[P1 地基]   modules/02-scaffold.md  ∥  modules/03-art-bible.md
            （只生成目标平台需要的构建配置；模板自带全部适配器）
  ↓
  ◆ 门禁 G2：向用户确认风格（必做）
  ↓
[P2 玩法]   modules/04-core-loop.md     → 灰盒可玩（几何占位素材）
  ↓
[R1 审核]   modules/12-review.md        → docs/09-review/r1-graybox-review.md
            ★ 审 A 玩法 / B 核心循环 / C 操作引导
            ★★ 结论非通过 → 禁止进入生图（这是全流程成本控制的核心闸）
  ↓
[P2 生产]   05-art-forge → 06-sprite-tools  ∥  07-audio-forge
  ↓
[P3 打磨]   modules/08-polish.md → modules/09-perf-audit.md
            （逐平台审计；不达标自动回退压缩，最多 3 次）
  ↓
[P4 测试]   modules/10-qa.md            → docs/07-qa/report.html + 试玩链接
  ↓
[R2 终审]   modules/12-review.md        → docs/09-review/verdict-r2.json
            ★ A–H 八维度全量判定，REQ 必须全 PASS
            ★★ 一票否决：verdict 非通过则 ship 被硬阻断
  ↓
[P4 交付]   modules/11-ship.md
            （只构建并打包用户选定的平台）
  ↓
交付：L3 可过审包（选定平台 zip + 过审自检清单 + **明确的 CrazyGames 标准结论行**）
  ↓
[R3 回环]   平台实测反馈 → 回到 R2 全量复审（直至通过）
```

### 关键约束（必须遵守）

1. **先问平台再开工**：收到第一个指令后，第一个动作是输出支持平台表并询问用户目标平台。**未收到回复不得进入 P0。**
2. **审核官一票否决**：R0/R1/R2 任一结论为 `REJECTED` / `INCOMPLETE` 时不得进入下一阶段。**标准固定，不因催促、改范围、换平台而放宽**；未达标必须持续修改并重新送审，**不设轮次上限**。
3. **审核官只审不写**：不得修改 `src/`、`assets/`、`docs/00`–`08`，只产出问题单与建议，修复退回对应环节。
4. **每轮复审全量重跑**：禁止只测修过的条目。同一维度连续 2 轮同类问题必须更换修复策略。
5. **交付包与选定平台严格一致**：不多不少。`gate_check.py --stage ship` 会校验这一点。
6. **体积预算取最严**：多平台时按最严红线做，不是各算一份。
7. **灰盒先行**：`modules/04-core-loop.md` 必须先用几何占位素材把玩法跑通并自测可玩并通过 R1，之后才允许进入 `05-art-forge` 生图。玩法不成立就投入生图成本是本流程最大的浪费。
8. **文件契约传递**：阶段之间不依赖对话上下文，全部落盘到 `docs/` 与 `assets/`。中断后从 `.gamedev/state.yaml` 续跑。
9. **人工门禁必须停下**：G0、G1、G2 三处必须向用户确认，不得自行通过。
10. **可降级**：生图或配乐不可用时退化为程序化占位（纯色几何 + Web Audio 合成音），游戏必须仍能运行。
11. **不自动提交平台**：`modules/11-ship.md` 只产出 zip 与自检清单。实际提交（含 TapTap 前置备案、Poki 提报、taptap-cli 上传）永远由用户执行。
12. **SDK script URL 必须核对**：`vite.config.ts` 的 `SDK_SCRIPTS` 中预填了各平台 SDK 的 CDN 地址，提交前必须对照官方文档核对一次 —— 平台会更换 CDN。
13. **最终交付必须给出明确的 CrazyGames 标准结论**：三选一，措辞不得模糊。
    禁止「基本达标」「接近标准」「小问题不影响提交」「后续版本会改」。
14. **生图通道必须可配置、可降级**：不得把 ComfyUI / RunningHub 的地址、节点 id、模型名硬编码进脚本或代码；
    一律走 `.gamedev/artgen.yaml`。两个通道都不可用时必须降级为占位素材继续推进，**不允许因为"没显卡"卡死流程**。
15. **产物不能双击打开，必须给用户一条能走的路径**：构建产物是外部 ES module，浏览器在 `file://` 下会以 CORS（origin `null`）**拒绝执行且不报错**，页面永远停在 `Loading…`。
    因此模板内置了两道防线，**不得删除**：
    - `index.html` 的**启动看门狗**（file:// 直开 / 脚本异常 / 8 秒超时 → 页面给出可操作提示，而不是静默 Loading）
    - `npm run standalone` 出的**单文件 HTML**（JS 内联 + 资源全变 data URI，双击即玩）
    交付时**必须**在交付说明里给出这两条路径；`npm run test:standalone` 必须通过。

## 模块索引

每个环节的详细步骤、输入输出与自检项在 `modules/` 下。**按需读取，不要一次性全读**。

| 阶段 | 模块文件 | 职责 | 关键产物 |
|---|---|---|---|
| 编排 | `references/pipeline.md` | 阶段定义、门禁规则、回退策略、并行关系 | — |
| **P-1** | **`modules/00-platforms.md`** | **确认目标平台（G0）、定体积预算、写平台计划** | `docs/00-platforms/platform-plan.md` |
| P0 | `modules/01-brief.md` | idea → 一页 GDD + 范围边界 + 素材清单 | `docs/01-brief/` |
| **R0** | **`modules/12-review.md`** | **审核官介入①：规划预审（可审性 + 合规初筛）** | `docs/09-review/r0-plan-review.md` |
| P1 | `modules/02-scaffold.md` | 项目骨架 + 平台适配层 + 目标平台构建脚本 + **单文件版与启动看门狗** | `src/`、`package.json` |
| P1 | `modules/03-art-bible.md` | 参考图 → 色板 + 风格规范 + 提示词模板 | `docs/02-art/` |
| P2 | `modules/04-core-loop.md` | 灰盒玩法主循环实现 | `src/game/` |
| **R1** | **`modules/12-review.md`** | **审核官介入②：灰盒预审（A 玩法 / B 核心循环 / C 操作引导）—— 不通过禁止生图** | `docs/09-review/r1-graybox-review.md` |
| P2 | `modules/05-art-forge.md` | 按 Art Bible 生图（ComfyUI / RunningHub / 占位） | `assets/raw/` + `manifest.json` |
| P2 | `modules/06-sprite-tools.md` | 切图 / 抠图 / 裁剪 / 图集打包 | `assets/processed/`、`assets/atlas/` |
| P2 | `modules/07-audio-forge.md` | BGM + 音效 | `assets/audio/` |
| P3 | `modules/08-polish.md` | 手感 juice + UI 接线 + 难度曲线 + 存档 | 优化后的 `src/` |
| P3 | `modules/09-perf-audit.md` | 逐平台体积 / 帧率 / 内存审计 | `docs/06-perf/report.md` |
| P4 | `modules/10-qa.md` | 自动化走查 + **file:// 启动行为回归** + 试玩链接 | `docs/07-qa/report.html` |
| **R2** | **`modules/12-review.md`** | **审核官介入③：终审（A–H 八维度全量，REQ 必须全 PASS）—— 一票否决** | `docs/09-review/verdict-r2.json` |
| P4 | `modules/11-ship.md` | 按选定平台打包 + 过审自检 + **CrazyGames 标准结论** | `dist/<平台>.zip`、`docs/08-ship/` |

> `modules/12-review.md` 是**一个模块、三处介入**：审核官在 R0 / R1 / R2 分别执行不同的维度子集，判据统一为 `references/crazygames-standard.md`。文件编号 12 只是序号。

## 快速开始

### 1. 确认平台（先做）

输出上文「支持的平台」表 → 问用户 → 拿到回复。

### 2. 建立项目

```bash
python <skill>/scripts/init_project.py \
  --name merge-fruit \
  --idea "做一个合成水果的游戏" \
  --platforms crazygames,taptap \
  --style-ref /path/to/style.png \
  --style chibi-2d \
  --out /path/to/workspace
```

若项目已建但平台未定：

```bash
python <skill>/scripts/state.py set-platforms --project <project> --platforms crazygames,taptap
python <skill>/scripts/state.py set-platforms --project <project> --confirm
```

### 3. 按阶段推进

每个阶段：读对应 `modules/*.md` → 执行 → 用脚本校验 → 更新状态。

```bash
# 查看当前进度（含平台确认状态）
python <skill>/scripts/state.py show --project <project>

# 显示下一步该做什么
python <skill>/scripts/state.py next --project <project>

# 校验某阶段产物是否齐备（门禁检查）
python <skill>/scripts/gate_check.py --project <project> --stage brief

# 标记阶段完成
python <skill>/scripts/state.py set --project <project> --stage brief --status done
```

### 4. 审核官介入（三处，不可跳过）

```bash
# R0 规划预审（立项后、写代码前）
python <skill>/scripts/review_gate.py --project <project> --phase r0 --round 1

# R1 灰盒预审（core-loop 自测可玩后、生图之前）
python <skill>/scripts/review_gate.py --project <project> --phase r1 --round 1

# R2 终审（perf-audit + qa 之后、ship 之前）
python <skill>/scripts/review_gate.py --project <project> --phase r2 --round 1
```

首次运行会生成 `docs/09-review/manual-checks.json`（人工条目填写表）。
审核官逐条走查并填入 `result`（`pass`/`fail`/`na`）与 `evidence`，**再跑一次同一条命令**才会得出结论。

结论非通过时：按 `issues.json` 的 `owner` 退回对应生产环节修复 → 回填 `fix_note` → 以 `--round N+1` **全量重跑**。
**不设轮次上限，直至通过。**

`verdict-<phase>.json` 的取值与含义：

| verdict | 含义 | 能否进入 ship |
|---|---|---|
| `PASS` | 完全达标 | ✅ |
| `PASS_WITH_DEVIATIONS` | REQ 全过，GUIDE 有偏离（须列出） | ✅（但报告只能写"达到必需标准"） |
| `REJECTED` | **REQ 有 FAIL** | ❌ 硬阻断 |
| `INCOMPLETE` | 人工条目未填完 | ❌ |

### 5. 素材处理（生图通道：本地 ComfyUI / RunningHub 云端）

**先体检，再出图**。两个通道都不可用时自动降级为程序化占位素材，流程不中断。

```bash
# 体检：ComfyUI 是否可达、RunningHub 凭证是否齐全
python <skill>/scripts/gen_assets.py --probe

# 提示词骨架（从 scope.json 批量生成，自带 style_tokens）
python <skill>/scripts/gen_prompts.py

# 一张图出多个素材 / 一套动画帧（网格模式）
python <skill>/scripts/gen_prompts.py --sheet items --grid 3x3 --items apple,pear,banana
python <skill>/scripts/gen_prompts.py --frames slime_idle --grid 2x2 --count 4 \
  --subject "a cute round slime monster" --action "idle breathing"

# 预演（不花钱）：逐条打印素材名/尺寸/seed/最终提示词
python <skill>/scripts/gen_assets.py --dry-run

# 先出 2 张验风格，满意再全量
python <skill>/scripts/gen_assets.py --max 2
python <skill>/scripts/gen_assets.py

# 从风格参考图提取主色板
python <skill>/scripts/palette_extract.py --input style.png --out docs/02-art/palette.json

# 抠图（AI 出图不带 alpha，必做）+ 统一画布
python <skill>/scripts/sprite_tools.py --input assets/raw/ --remove-bg --bg-color "#FF00FF" --trim --pad-to 256x256 --out assets/processed/

# 打包为 Phaser 可用图集
python <skill>/scripts/pack_atlas.py --input assets/processed/ --out assets/atlas/atlas --padding 2
```

**provider 配置**在项目内的 `.gamedev/artgen.yaml`（`init_project.py` 已生成）：

| provider | 通道 | 说明 |
|---|---|---|
| `comfyui` | 本地 ComfyUI `/prompt` + `/history` + `/view` | 默认 **Qwen-Image 2.1 turbo**（文生图 + 图生图两套，`ref` 触发 i2i）；工作流用 **API 格式**；节点自动探测，探测不到写 `node_map` |
| `runninghub` | RunningHub `task/openapi/*` | 填 `workflow_id`；`api_key` 走 `RUNNINGHUB_API_KEY` 环境变量 |
| `placeholder` | 程序化占位 | 兜底，标记 `art_forge: degraded` |
| `auto` | 按序降级 | ComfyUI → RunningHub → 占位 |

细节见 `references/artgen-integration.md` 与 `assets/workflows/README.md`。

### 6. 审计与交付（逐平台）

```bash
# 一键：构建 → 体积审计 → 过审自检 → 打 zip → 商店素材 → 自检清单
python <skill>/scripts/ship_pack.py --build

# 或手工分步
python <skill>/scripts/measure_bundle.py --dir dist/taptap --platform taptap
python <skill>/scripts/precheck.py --dir dist/taptap --platform taptap

# 交付前校验（含审核结论 + 平台范围一致性）
python <skill>/scripts/gate_check.py --project <project> --stage ship
```

## 支持的平台构建目标

模板内置 5 个适配器，构建命令一一对应：

| 目标 | 构建命令 | 产物目录 |
|---|---|---|
| `crazygames` | `npm run build:cg` | `dist/crazygames/` |
| `poki` | `npm run build:poki` | `dist/poki/` |
| `gamedistribution` | `npm run build:gd` | `dist/gamedistribution/` |
| `playgama` | `npm run build:pg` | `dist/playgama/` |
| `taptap` | `npm run build:taptap` | `dist/taptap/` |

**只构建并交付用户选定的平台**，不要「顺手全构建」。

## 输出项目结构

```
<project>/
├─ .gamedev/state.yaml          # 状态机唯一真相源（含 delivery.platforms 与三段审核结论）
├─ docs/00-platforms/           # 平台计划（体积预算、投递顺序、前置条件）
├─ docs/01-brief … 08-ship/     # 各阶段产物与报告
├─ docs/09-review/              # ★ 审核官产物：清单/问题单/建议/结论/轮次记录/证据
├─ src/types.ts                 # 共享类型（PlatformBridge 接口定义）
├─ src/game/                    # 纯玩法逻辑，禁止 import src/platform/
├─ src/platform/                # 各平台适配器 + 工厂（taptap/crazygames/poki/playgama/gd/mock）
├─ .gamedev/artgen.yaml        # 生图通道配置（comfyui / runninghub / placeholder）
├─ assets/{raw,processed,atlas,audio,workflows}/
└─ dist/<用户选定平台>/
```

完整契约见 `references/contracts.md`。

## 交付标准

分三档，逐档验收。完整清单见 `references/delivery-standards.md`。

| 档位 | 判据概要 |
|---|---|
| **L1 可玩** | 完整闭环（开始→游玩→结束→重开）+ 计分 + 桌面端可操作；素材可用几何占位；**R1 审核已介入** |
| **L2 可交付** | 风格与参考图一致 + 音频 + 移动端触摸 + juice 手感 + 存档 + 零报错 + **满足最严平台的体积与帧率红线** |
| **L3 可过审** | **R2 终审通过（REQ 全 PASS）** + **选定平台**的 zip 齐备且与清单一致 + 过审自检全绿 + SDK 事件正确 + iOS 音频恢复 + 商店素材齐备 + **交付报告含明确的 CrazyGames 标准结论行** |

## 降级与容错

| 失败点 | 降级策略 |
|---|---|
| ComfyUI / RunningHub 均不可用 | `gen_assets.py` 自动降级为程序化占位素材，标记 `art_forge: degraded`，游戏仍可玩 |
| 单张素材生成失败 | 重试 3 次（指数退避）→ 仍失败用占位兜底并记入 `.artgen-report.json`，交付报告必须列出 |
| 工作流节点探测不到 | 在 `.gamedev/artgen.yaml` 的 `node_map` 显式指定 nodeId + fieldName，不要改脚本 |
| 配乐不可用 | 用 Web Audio 合成音效，跳过 BGM |
| 风格提取失败 | 退回默认色板并要求用户补充参考图，标记 `art_bible: fallback` |
| 首包超红线 | 自动：纹理压缩 → 降分辨率 → 音频降码率 → 砍非必要素材，最多 3 次 |
| 帧率不达标 | 自动降级：减少粒子/阴影/后处理，降低 DPR |
| 某阶段连续失败 3 次 | 停止并上报失败原因与建议，交人工决策 |
| 平台 SDK 加载失败 | 适配层捕获异常静默降级，游戏照常可玩 |
| TapTap 无 `tap` 全局对象 | 属预期（网页游戏形态），自动降级为本地行为 |
| **用户双击 `index.html` 说"卡在 Loading"** | 属预期（`file://` 拦掉外部 ES module）。**不要**去改游戏代码：让用户跑 `npm run serve:cg` 走 HTTP，或 `npm run standalone` 拿单文件版。若页面上没有提示文案，说明启动看门狗被删了，先补回来 |

## 资源索引

| 路径 | 用途 | 何时读 |
|---|---|---|
| `references/crazygames-standard.md` | **审核官的判据 —— CrazyGames 官方标准的完整条目表（A–H 八维度，REQ/GUIDE 分开）** | 每次审核；判定任何条目时 |
| `references/pipeline.md` | 阶段定义、门禁、回退、并行关系 | 启动流程时 |
| `references/contracts.md` | 各阶段文件契约、state.yaml schema、审核产物契约 | 需要确认产物格式时 |
| `references/delivery-standards.md` | L1/L2/L3 完整验收清单（含审核门禁） | 验收与交付时 |
| `references/platform-requirements.md` | 5 个平台的硬红线（已核实官方文档） | 平台确认、构建、审计、打包时 |
| `references/genre-playbook.md` | 超休闲品类拆解与选型建议 | P0 立项时 |
| **`assets/styles/`** | **画风预设库（5 档，已蒸馏成游戏资产向 style_tokens + 配色板 + 风险标注）** | P1 定风格时 |
| **`references/artgen-integration.md`** | **ComfyUI / RunningHub 接口细节、节点探测规则、故障排查** | 接生图通道、出图失败时 |
| `assets/workflows/` | ComfyUI API 格式工作流（Qwen-Image 2.1 turbo 文生图/图生图 + SDXL 兜底）+ 导出/node_map 说明 | P1/P2 配 provider 时 |
| `modules/00-…-11-*.md` | 各环节详细执行步骤 | 执行到该环节时 |
| **`modules/12-review.md`** | **审核官角色定义、三处介入、判定与结论、不达标处理流程** | 执行任何 R 轮审核时 |
| `scripts/*.py` | 确定性工具脚本，可直接执行 | 对应操作时 |
| **`scripts/review_gate.py`** | **审核执行与结论判定（自动 + 人工条目合并出 verdict）** | 每轮审核时 |
| **`scripts/gen_assets.py`** | **资产生成：ComfyUI / RunningHub / 占位，含台账与断点续跑** | P2 生图时 |
| `scripts/gen_prompts.py` | 从 scope.json 批量生成提示词（自带 style_tokens） | P1 收尾、P2 之前 |
| **`scripts/style_lib.py`** | **画风预设：list / show / apply（写入 palette.json）** | P1 定风格时 |
| **`scripts/ship_pack.py`** | **一键构建 + 审计 + 自检 + 打 zip + 商店素材 + 自检清单** | P4 交付时 |
| `assets/template/` | Phaser 3.90 + Vite + 5 平台适配层模板 | P1 建项目时复制 |

---
name: idea-to-game
description: "将一句游戏想法或一款同款游戏名，连同美术风格参考图，自动转化为一个完整可玩、可提交到 CrazyGames / Poki / GameDistribution 等平台的 HTML5 小游戏。覆盖立项策划、项目脚手架、平台 SDK 适配、玩法实现、AI 生图、切图打包图集、配乐音效、手感打磨、性能与体积审计、自动化测试、多平台打包过审共 11 个环节。This skill should be used when the user wants to make a small/browser/HTML5/casual/hyper-casual game, or says 做个游戏、做个小游戏、我要做一款游戏、照《XX》做一个、开发网页游戏、上线到 CrazyGames/Poki、make a game like XX、build an HTML5 game。Also use when the user provides an idea plus a style reference image and expects a playable game as output."
agent_created: true
---

# IdeaToGame

## Overview

把一个游戏想法，端到端地变成一个能玩、能提交到平台的 HTML5 小游戏。

**输入**：一个 idea（一段想法描述，或一款同款游戏名）+ 一张美术风格参考图
**输出**：完整可玩的小游戏项目，含 CrazyGames / Poki / Playgama 三平台可分发包与过审自检清单

本技能是**单一技能包**：11 个能力环节全部内置于本包，不依赖外部安装的其他技能。所有环节通过 `modules/` 下的模块说明驱动，通过 `scripts/` 下的脚本落地，通过文件契约在环节之间传递产物。

## 触发场景

在以下任一情形使用本技能：

- 用户提出游戏想法并期望得到可玩的成品，例如「做个合成水果的小游戏」「做一个躲避障碍的网页游戏」
- 用户给出同款游戏名，例如「照《合成大西瓜》做一个」「仿一下 Flappy Bird」
- 用户提供风格参考图 + 玩法描述，要求产出游戏
- 用户要求把游戏发布到 CrazyGames / Poki / GameDistribution / Playgama 等 Web 游戏平台
- 用户要续做或改进本技能此前产出的游戏项目（项目内存在 `.gamedev/state.yaml`）

**不适用**：3D 重资产游戏、需要长剧情/重叙事的游戏、多人联网游戏（首版不支持，应明确告知用户）。

## 核心工作流

按 P0 → P4 五个阶段推进。**只有两处需要人工确认**，其余全自动。

```
输入：idea + 风格参考图
  ↓
[P0 立项]   modules/01-brief.md         → docs/01-brief/gdd.md + scope.json
  ↓
  ◆ 门禁 G1：向用户确认方向（必做，不可跳过）
  ↓
[P1 地基]   modules/02-scaffold.md  ∥  modules/03-art-bible.md
  ↓
  ◆ 门禁 G2：向用户确认风格（必做，不可跳过）
  ↓
[P2 生产]   modules/04-core-loop.md ∥ 05-art-forge → 06-sprite-tools ∥ 07-audio-forge
            ★ 灰盒先跑通并自测可玩，再继续生图
  ↓
[P3 打磨]   modules/08-polish.md → modules/09-perf-audit.md
            （性能不达标自动回退压缩，最多 3 次）
  ↓
[P4 交付]   modules/10-qa.md → modules/11-ship.md
  ↓
交付：L3 可过审包（三平台 zip + 过审自检清单）
```

### 关键约束（必须遵守）

1. **灰盒先行**：`modules/04-core-loop.md` 必须先用几何占位素材把玩法跑通并自测可玩，之后才允许进入 `05-art-forge` 生图。玩法不成立就投入生图成本是本流程最大的浪费。
2. **文件契约传递**：阶段之间不依赖对话上下文，全部落盘到 `docs/` 与 `assets/`。中断后从 `.gamedev/state.yaml` 续跑。
3. **门禁必须人工**：G1、G2 两处必须停下来向用户确认，不得自行通过。
4. **可降级**：生图或配乐不可用时退化为程序化占位（纯色几何 + Web Audio 合成音），游戏必须仍能运行。
5. **不自动提交平台**：`modules/11-ship.md` 只产出 zip 与自检清单，实际提交动作永远由用户执行。
6. **首包 ≤ 20MB**：这是 CrazyGames 移动端首页的硬门槛，贯穿全流程的体积预算。
7. **SDK script URL 必须核对**：`vite.config.ts` 的 `SDK_SCRIPTS` 中预填了各平台 SDK 的 CDN 地址，提交前必须对照官方文档核对一次 —— 平台会更换 CDN。构建后可用 `grep` 确认 script 标签已注入 `dist/<platform>/index.html`。

## 模块索引

每个环节的详细步骤、输入输出与自检项在 `modules/` 下。**按需读取，不要一次性全读**。

| 阶段 | 模块文件 | 职责 | 关键产物 |
|---|---|---|---|
| 编排 | `references/pipeline.md` | 阶段定义、门禁规则、回退策略、并行关系 | — |
| P0 | `modules/01-brief.md` | idea → 一页 GDD + 范围边界 + 素材清单 | `docs/01-brief/` |
| P1 | `modules/02-scaffold.md` | 项目骨架 + 平台适配层 + 多平台构建脚本 | `src/`、`package.json` |
| P1 | `modules/03-art-bible.md` | 参考图 → 色板 + 风格规范 + 提示词模板 | `docs/02-art/` |
| P2 | `modules/04-core-loop.md` | 灰盒玩法主循环实现 | `src/game/` |
| P2 | `modules/05-art-forge.md` | 按 Art Bible 生图 | `assets/raw/` |
| P2 | `modules/06-sprite-tools.md` | 切图 / 抠图 / 裁剪 / 图集打包 | `assets/processed/`、`assets/atlas/` |
| P2 | `modules/07-audio-forge.md` | BGM + 音效 | `assets/audio/` |
| P3 | `modules/08-polish.md` | 手感 juice + UI 接线 + 难度曲线 + 存档 | 优化后的 `src/` |
| P3 | `modules/09-perf-audit.md` | 体积 / 帧率 / 内存审计 | `docs/06-perf/report.md` |
| P4 | `modules/10-qa.md` | 自动化走查 + 试玩链接 | `docs/07-qa/report.html` |
| P4 | `modules/11-ship.md` | 三平台打包 + 过审自检 | `dist/*.zip`、`docs/08-ship/` |

## 快速开始

### 1. 建立项目

```bash
python <skill>/scripts/init_project.py \
  --name merge-fruit \
  --idea "做一个合成水果的游戏" \
  --style-ref /path/to/style.png \
  --out /path/to/workspace
```

生成项目目录骨架、复制 Phaser + Vite 模板、初始化 `.gamedev/state.yaml`。

### 2. 按阶段推进

每个阶段：读对应 `modules/*.md` → 执行 → 用脚本校验 → 更新状态。

```bash
# 查看当前进度
python <skill>/scripts/state.py show --project <project>

# 校验某阶段产物是否齐备（门禁检查）
python <skill>/scripts/gate_check.py --project <project> --stage brief

# 标记阶段完成
python <skill>/scripts/state.py set --project <project> --stage brief --status done
```

### 3. 素材处理

```bash
# 从风格参考图提取主色板
python <skill>/scripts/palette_extract.py --input style.png --out docs/02-art/palette.json

# 切图 + 抠图（支持 2x3 / 3x2 等网格，或按 alpha 自动裁边）
python <skill>/scripts/sprite_tools.py --input assets/raw/sheet.png --grid 3x3 --trim --out assets/processed/

# 打包为 Phaser 可用图集
python <skill>/scripts/pack_atlas.py --input assets/processed/ --out assets/atlas/atlas --padding 2
```

### 4. 审计与交付

```bash
# 体积与文件数审计（对照 CrazyGames 红线）
python <skill>/scripts/measure_bundle.py --dir dist/crazygames

# 提交前过审自检
python <skill>/scripts/precheck.py --dir dist/crazygames --platform crazygames
```

## 输出项目结构

```
<project>/
├─ .gamedev/state.yaml          # 状态机唯一真相源
├─ docs/01-brief … 08-ship/     # 各阶段产物与报告
├─ src/types.ts                 # 共享类型（PlatformBridge 接口定义）
├─ src/game/                    # 纯玩法逻辑，禁止 import src/platform/
├─ src/platform/                # 各平台适配器 + 工厂（crazygames/poki/playgama/gd/mock）
├─ assets/{raw,processed,atlas,audio}/
└─ dist/{crazygames,poki,playgama}/
```

完整契约见 `references/contracts.md`。

## 交付标准

分三档，逐档验收。完整清单见 `references/delivery-standards.md`。

| 档位 | 判据概要 |
|---|---|
| **L1 可玩** | 完整闭环（开始→游玩→结束→重开）+ 计分 + 桌面端可操作；素材可用几何占位 |
| **L2 可交付** | 风格与参考图一致 + 音频 + 移动端触摸 + juice 手感 + 存档 + 零报错 + 首包 ≤20MB + 60fps |
| **L3 可过审** | 三平台 zip + 过审自检全绿 + SDK 事件正确 + iOS 音频恢复 + 商店素材齐备 |

## 降级与容错

| 失败点 | 降级策略 |
|---|---|
| 生图不可用 | 生成程序化占位素材，标记 `art_forge: degraded`，游戏仍可玩 |
| 配乐不可用 | 用 Web Audio 合成音效，跳过 BGM |
| 风格提取失败 | 退回默认色板并要求用户补充参考图，标记 `art_bible: fallback` |
| 首包超 20MB | 自动：纹理压缩 → 降分辨率 → 音频降码率 → 砍非必要素材，最多 3 次 |
| 帧率不达标 | 自动降级：减少粒子/阴影/后处理，降低 DPR |
| 某阶段连续失败 3 次 | 停止并上报失败原因与建议，交人工决策 |
| 平台 SDK 加载失败 | 适配层捕获异常静默降级，游戏照常可玩 |

## 资源索引

| 路径 | 用途 | 何时读 |
|---|---|---|
| `references/pipeline.md` | 阶段定义、门禁、回退、并行关系 | 启动流程时 |
| `references/contracts.md` | 各阶段文件契约与 state.yaml schema | 需要确认产物格式时 |
| `references/delivery-standards.md` | L1/L2/L3 完整验收清单 | 验收与交付时 |
| `references/platform-requirements.md` | CrazyGames / Poki / GameDistribution / Playgama 硬红线 | 构建、审计、打包时 |
| `references/genre-playbook.md` | 超休闲品类拆解与选型建议 | P0 立项时 |
| `modules/01-…-11-*.md` | 各环节详细执行步骤 | 执行到该环节时 |
| `scripts/*.py` | 确定性工具脚本，可直接执行 | 对应操作时 |
| `assets/template/` | Phaser 3.90 + Vite + 适配层项目模板 | P1 建项目时复制 |

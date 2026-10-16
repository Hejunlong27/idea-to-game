# 流程定义（pipeline）

本文件定义 IdeaToGame 的阶段、门禁、并行关系与回退策略。执行流程前读本文件。

## 阶段总表

| 阶段 | 模块 | 串行前置 | 可并行 | 产出 | 通过标准 |
|---|---|---|---|---|---|
| **P-1 平台确认** | `modules/00-platforms.md` | — | — | `state.yaml` 的 `delivery.platforms`、`docs/00-platforms/platform-plan.md` | **用户明确回复了目标平台清单**（来自技能内置的支持列表） |
| **G0 门禁** | — | P-1 | — | — | **收到用户平台回复后才允许进入 P0** |
| P0 立项 | `modules/01-brief.md` | G0 | — | `docs/01-brief/` | GDD 含核心循环/操作/胜负/计分/难度/范围边界；`scope.json` 明确 MVP 功能与素材清单 |
| **G1 门禁** | — | P0 | — | — | **用户明确确认方向** |
| P1 地基 | `modules/02-scaffold.md` | G1 | ∥ `03-art-bible` | `src/`、`package.json` | `npm run dev` 零报错；目标平台的构建脚本可执行；适配层就位 |
| P1 美术策略 | `modules/03-art-bible.md` | G1 | ∥ `02-scaffold` | `docs/02-art/` | 主色板 5–8 色 HEX + 线条/着色/质感/氛围词 + 每类素材 prompt 模板 |
| **G2 门禁** | — | P1 | — | — | **用户明确确认风格** |
| P2 玩法 | `modules/04-core-loop.md` | G2 | ∥ 05→06 ∥ 07 | `src/game/` | **灰盒可玩**：闭环跑通、计分生效、用几何占位素材 |
| P2 生图 | `modules/05-art-forge.md` | G2 | ∥ 04 ∥ 07 | `assets/raw/` | 每类素材 ≥1 可用候选；风格与参考图一致；透明背景 |
| P2 切图 | `modules/06-sprite-tools.md` | 05 | ∥ 04 ∥ 07 | `assets/processed/`、`assets/atlas/` | 切分正确、抠图干净、产出 Phaser 可用图集 JSON |
| P2 配乐 | `modules/07-audio-forge.md` | G2 | ∥ 04 ∥ 05→06 | `assets/audio/` | BGM 可无缝循环；SFX <1s；音频总体积 ≤2MB |
| P3 打磨 | `modules/08-polish.md` | P2 | — | 优化后 `src/` | juice 到位、UI 接线、难度曲线、存档可用 |
| P3 性能 | `modules/09-perf-audit.md` | 08 | — | `docs/06-perf/report.md` | **全部目标平台**的体积红线都达标；60fps；无内存泄漏 |
| P4 测试 | `modules/10-qa.md` | 09 | — | `docs/07-qa/report.html` | 自动化走查通过、canvas 点击可模拟、零控制台报错、移动端视口正常 |
| P4 交付 | `modules/11-ship.md` | 10 | — | `dist/<平台>.zip`、`docs/08-ship/` | 过审自检全绿、**产物平台与用户选定平台完全一致**、商店素材齐备 |

## 依赖图

```
01-brief ──┬──► 02-scaffold ──┐
           │                   ├──► 04-core-loop ──┐
           └──► 03-art-bible ──┘                    │
                     │                              ▼
                     ├──► 05-art-forge ──► 06-sprite-tools ──┐
                     │                                        ├──► 08-polish ──► 09-perf-audit ──► 10-qa ──► 11-ship
                     └──► 07-audio-forge ─────────────────────┘
```

**关键路径**：`00 → 01 → 02 → 04 → 08 → 09 → 10 → 11`
**并行支线**：`03` 在 G1 后即可启动；`05→06` 与 `07` 可与 `04` 同时进行。

## 门禁规则

共设三处门禁。三处都必须停下并向用户提问，**不得自行判定通过**。

| 门禁 | 位置 | 提问要点 | 为什么必须人工 |
|---|---|---|---|
| **G0** | **收到用户第一个指令后，立即**（`modules/00-platforms.md`） | **列出技能支持的平台，问用户准备发到哪些** | **交付包必须与用户选定的平台一致**。平台决定体积红线、SDK 接入、合规要求、商店素材规格 —— 定晚了会返工 |
| **G1** | `01-brief` 产出后 | 核心玩法是否认可？范围边界是否同意？有无要加/要砍的功能？ | 方向错了后面全白干，此处纠错成本最低 |
| **G2** | `03-art-bible` 产出后 | 色板与画风是否符合预期？是否需要换参考图重提？ | 风格定错，所有生图素材作废，返工成本最高 |

**G0 是第一个动作，不可跳过、不可替用户默认选择。** 用户未回复平台前不得开始 P0 立项。

门禁通过后，把结果写入 `state.yaml`：
- G0 → `delivery.platforms` + `delivery.platform_confirmed: true`
- G1 → `stages.brief.gate: G1_passed`
- G2 → `stages.art_bible.gate: G2_passed`

## 回退策略

| 触发条件 | 回退目标 | 最多重试 |
|---|---|---|
| `09-perf-audit` 首包 >20MB | 压缩素材（纹理压缩/降分辨率/音频降码率/砍非必要素材） | 3 |
| `09-perf-audit` 帧率不达标 | `08-polish` 降级渲染（减粒子/阴影/后处理，降 DPR） | 3 |
| `04-core-loop` 自测不可玩 | 就地修复，不进入 P2 素材环节 | 3 |
| `10-qa` 发现阻断性缺陷 | 回退到对应模块修复 | 3 |
| 任意阶段连续失败 3 次 | 停止，上报失败原因与建议 | — |

## 状态机

唯一真相源是项目根目录的 `.gamedev/state.yaml`。每次阶段状态变更都必须落盘。

状态取值：`pending` / `in_progress` / `done` / `failed` / `degraded` / `skipped`

`degraded` 表示该阶段以降级方式完成（例如用占位素材替代生图），必须在最终交付报告中显式标注。

## 执行纪律

1. 进入任一阶段前，先读该阶段的 `modules/*.md`。
2. 阶段完成后必须跑 `scripts/gate_check.py` 校验产物齐备性，再标记 `done`。
3. 不要跳过门禁，不要在一次回复里连跑多个阶段而不报告。
4. 每完成一个阶段，向用户简要报告：做了什么 / 结论 / 下一步需要什么。

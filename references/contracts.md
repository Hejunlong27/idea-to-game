# 文件契约（contracts）

阶段之间只通过本文件定义的产物通信。不要依赖对话上下文传递状态。

## 项目根目录布局

```
<project>/
├─ .gamedev/
│  ├─ state.yaml
│  ├─ artgen.yaml           # 生图通道配置（comfyui / runninghub / placeholder）
│  └─ logs/
├─ docs/
│  ├─ 00-platforms/ platform-plan.md
│  ├─ 01-brief/   gdd.md  scope.json
│  ├─ 02-art/     art-bible.md  palette.json  prompts/
│  ├─ 03-scaffold/ architecture.md
│  ├─ 04-core-loop/ notes.md
│  ├─ 05-polish/  juice-log.md
│  ├─ 06-perf/    report.md
│  ├─ 07-qa/      report.html  screenshots/
│  ├─ 08-ship/    submit-checklist.md  store-copy.md
│  └─ 09-review/  checklist.md  manual-checks.json  issues.json
│                 improvement-plan.md  rounds.md  verdict.json（最新副本）
│                 verdict-r0.json  verdict-r1.json  verdict-r2.json
│                 r0-plan-review.md  r1-graybox-review.md  r2-final-review.md
│                 evidence/
├─ src/
│  ├─ types.ts    共享类型（PlatformBridge 接口定义在此）
│  ├─ game/       纯玩法逻辑，禁止 import src/platform/
│  ├─ platform/   各平台适配器 + 工厂
│  └─ main.ts
├─ assets/
│  ├─ raw/        生图原始产物 + manifest.json（生成台账）
│  ├─ workflows/  ComfyUI API 格式工作流 + README
│  ├─ processed/  切图抠图后
│  ├─ atlas/      图集 png + json
│  └─ audio/{bgm,sfx}/
├─ dist/<选定平台>/
└─ package.json
```

## `.gamedev/state.yaml`

```yaml
project:
  name: "merge-fruit"
  idea: "做一个合成水果的游戏"
  style_ref: "assets/ref/style.png"
  genre: "merge"
  created: "2026-10-16T12:00:00+08:00"

stages:
  brief:        { status: done,        output: docs/01-brief/,  gate: G1_passed }
  review_plan:  { status: done,        verdict: PASS, round: 1, req_passed: "18/18", guide_passed: "9/10" }
  scaffold:     { status: done,        output: src/ }
  art_bible:    { status: done,        output: docs/02-art/,   gate: G2_passed }
  core_loop:    { status: done,        self_test: playable }
  review_graybox: { status: done,      verdict: PASS_WITH_DEVIATIONS, round: 2, req_passed: "15/15", guide_passed: "12/14" }
  art_forge:    { status: done,        progress: "sprites 12/12" }
  sprite_tools: { status: done,        output: assets/atlas/ }
  audio_forge:  { status: degraded,    note: "配乐不可用，已用合成音降级" }
  polish:       { status: done }
  perf_audit:   { status: done,        retries: 1 }
  qa:           { status: done,        output: docs/07-qa/report.html }
  review_final: { status: done,        verdict: PASS_WITH_DEVIATIONS, round: 3, req_passed: "59/59", guide_passed: "32/35" }
  ship:         { status: pending }

delivery:
  tier: L3_submittable
  # ★ 平台确认（门禁 G0）—— 交付包严格按此清单产出，不多不少
  platform_confirmed: true
  platforms: [crazygames, taptap]
  platform_notes:
    taptap: "需前置备案，排期在后；先发网页游戏形态拿反馈"
  # 全程体积预算 = 选定平台中最严的一条（此处 crazygames 移动端首页 20MB）
  size_budget_mb: 20
```

字段规则：
- `status`：`pending` / `in_progress` / `done` / `failed` / `degraded` / `skipped`
- `gate`：仅 `brief` 与 `art_bible` 阶段有，取值 `G1_passed` / `G2_passed`
- `retries`：仅 `perf_audit` 使用，回退计数
- `verdict`（仅审核阶段 `review_plan` / `review_graybox` / `review_final`）：`PASS` / `PASS_WITH_DEVIATIONS` / `REJECTED` / `INCOMPLETE`
- `round`：审核轮次（不设上限）
- `delivery.platforms`：**交付契约的核心字段**。合法值只有 `crazygames` / `poki` / `gamedistribution` / `playgama` / `taptap`
- `delivery.platform_confirmed`：用户是否已明确回复平台（G0 门禁）。`false` 时禁止进入 P0
- `delivery.size_budget_mb`：全程体积预算，取所有选定平台中**最严**的一条
- `degraded` 必须在最终交付报告中显式列出

## `docs/00-platforms/platform-plan.md`

至少包含：选定平台清单、各平台红线与**取最严后的全程预算**、需要用户自己完成的前置事项（实名认证 / 前置备案 / 广告位创建 / 提报）、投递顺序与排期、各平台商店素材要求。

## `docs/01-brief/scope.json`

```json
{
  "genre": "merge",
  "core_loop": "拖拽水果下落，同级碰撞合成更高级水果，超出边界即结束",
  "controls": ["drag", "touch"],
  "win_lose": "容器溢出即失败，分数决定排名",
  "scoring": "合成产生分数，等级越高分越高",
  "difficulty_curve": "水果等级随机池随时间扩大",
  "orientation": "portrait",
  "mvp_features": ["合成", "计分", "重开", "最高分存档"],
  "out_of_scope": ["排行榜", "内购", "多人"],
  "assets": {
    "sprites": ["fruit_1..8", "container", "guide_line"],
    "ui": ["btn_restart", "score_panel", "game_over_panel"],
    "sfx": ["merge", "drop", "gameover"],
    "bgm": ["main_loop"]
  }
}
```

`assets` 字段是 P2 生图与配乐的输入清单，必须与 `modules/05-art-forge.md`、`07-audio-forge.md` 对齐。

## `docs/02-art/palette.json`

```json
{
  "source_image": "assets/ref/style.png",
  "primary": ["#F2A65A", "#D9534F", "#5CB85C", "#4A90D9", "#F7E7CE"],
  "accent": ["#2E2E38"],
  "background": "#FFF8EE",
  "line_style": "thick_outline",
  "shading": "flat",
  "texture": "smooth",
  "mood": ["playful", "warm", "clean"],
  "style_tokens": "flat vector, thick dark outline, warm saturated palette, soft rounded shapes, no gradient"
}
```

`style_tokens` 是注入所有生图提示词的统一风格串，必须与 `art-bible.md` 中记录的一致。

## `.gamedev/artgen.yaml`

`scripts/gen_assets.py` 的唯一配置源（优先级：命令行 > 环境变量 > 本文件 > 内置默认）。

```yaml
provider: auto                 # auto | comfyui | runninghub | placeholder
size: { width: 1024, height: 1024 }
seed: 20261016
negative: "low quality, blurry, watermark, text, extra limbs, photorealistic"
remove_bg: "auto"              # 泛洪抠背景：auto=四边取样（推荐）/ #RRGGBB / 留空不抠
remove_bg_tolerance: 60        # 取样色容差
trim: false
fallback_placeholder: true     # 失败时用占位素材兜底（不得让流程卡死）
comfyui:
  host: http://127.0.0.1:8188
  workflow: assets/workflows/comfyui_txt2img.json
  checkpoint: sd_xl_base_1.0.safetensors
  timeout: 300
  node_map: {}                 # 留空自动探测；{prompt: {nodeId: "6", fieldName: "text"}}
runninghub:
  base_url: https://www.runninghub.cn
  api_key: ""                  # 建议用 RUNNINGHUB_API_KEY 环境变量
  workflow_id: ""
  timeout: 600
  poll: 3
  instance_type: ""
  node_map: {}
```

环境变量：`COMFYUI_HOST` / `RUNNINGHUB_API_KEY` / `RUNNINGHUB_BASE_URL` / `RUNNINGHUB_WORKFLOW_ID` / `I2G_ARTGEN_PROVIDER`。

**密钥不得提交进仓库** —— `api_key` 留空，用环境变量。

## `assets/raw/manifest.json`（生成台账）

```json
{
  "version": 1,
  "provider": "comfyui",
  "updated": "2026-10-28T18:00:00+08:00",
  "assets": {
    "apple": {
      "provider": "comfyui",
      "prompt": "a shiny red apple, front view, ...",
      "negative": "...",
      "seed": 20261016,
      "width": 1024, "height": 1024,
      "signature": "a1b2c3d4e5f6a7b8",
      "status": "ok",
      "bytes": 48211,
      "generated_at": "..."
    }
  }
}
```

- `signature = sha256(provider|prompt|negative|w|h|seed|ref|workflow)[:16]`
- 签名未变且文件存在 → 跳过（断点续跑、只重出改动的那张）
- `status`：`ok` / `degraded`（占位兜底）/ `failed`

`assets/raw/.artgen-report.json` 记录**本次运行**结果（含 `degraded` / `failed` 明细），交付报告必须引用它。

## `docs/02-art/prompts/<asset>.txt`

单行提示词，格式：

```
<subject>, <view/pose>, game asset, transparent background, centered, <style_tokens>
```

禁止在提示词里重新描述风格 —— 风格只由 `style_tokens` 提供，保证一致性。

同名 `.json` sidecar 可逐素材覆盖参数（可选）：

```json
{ "width": 512, "height": 512, "seed": 12345, "negative": "...", "ref": "assets/ref/hero.png" }
```

`docs/02-art/subjects.json` 存「素材名 → 主体描述」，供 `gen_prompts.py` 批量生成提示词：

```json
{ "apple": "a shiny red apple, front view", "ui_btn_restart": "round button with restart arrow icon" }
```

## `assets/atlas/atlas.json`

Phaser 标准纹理图集格式（TexturePacker JSON Hash）：

```json
{
  "frames": {
    "fruit_1": { "frame": {"x":0,"y":0,"w":64,"h":64}, "sourceSize": {"w":64,"h":64} }
  },
  "meta": { "image": "atlas.png", "size": {"w":512,"h":512}, "scale": "1" }
}
```

## 交付契约

| 路径 | 内容 |
|---|---|
| `dist/<平台>/` | 该平台可独立运行的构建产物 |
| `dist/<平台>.zip` | 提交用压缩包（内部相对路径，根目录直接是 index.html） |
| `docs/08-ship/submit-checklist.md` | 过审自检清单，逐条打勾并附实测值 |
| `docs/08-ship/store-copy.md` | 标题（≤60 字符）、简短描述（≤120）、详细描述（≤500）、截图清单 |
| `docs/08-ship/store/<平台>/` | `icon.png` / `cover.png` / `screenshot-1..3.png`（`ship_pack.py` 生成） |
| `docs/08-ship/precheck-<平台>.json` | 过审自检逐条结果（机器可读） |
| `docs/06-perf/measure-<平台>.json` | 体积/文件数审计原始数据 |

**交付包的平台范围必须与 `delivery.platforms` 完全一致**：
- 选定但缺产物 → 校验失败
- 未选却出现产物 → 校验失败

## 审核契约（`docs/09-review/`）

审核官与生产环节之间只通过以下文件交接。**口头说"改好了"不算，必须回填问题单。**

### `verdict-<phase>.json`（门禁依赖它；`verdict.json` 是最新副本）

```json
{
  "phase": "r2",
  "round": 3,
  "verdict": "PASS_WITH_DEVIATIONS",
  "standard": "crazygames",
  "standard_file": "references/crazygames-standard.md",
  "generated_at": "2026-10-17T22:00:00+08:00",
  "platforms": ["crazygames", "taptap"],
  "req_total": 59, "req_passed": 59,
  "guide_total": 35, "guide_passed": 32,
  "blockers": [],
  "deviations": [{ "item": "E6", "desc": "加载到可玩 ≤10 秒", "evidence": "实测 11.2s" }],
  "pending_manual": []
}
```

`verdict` 取值：`PASS` / `PASS_WITH_DEVIATIONS` / `REJECTED` / `INCOMPLETE`。
**只有 `PASS` 与 `PASS_WITH_DEVIATIONS` 允许进入 `ship`。**

### `issues.json`（问题单，交接凭证）

```json
[
  {
    "id": "ISSUE-001",
    "item": "G3",
    "dimension": "G",
    "severity": "blocker",
    "desc": "禁止在导航按钮上触发中插广告",
    "evidence": "MenuScene.ts:120 主菜单按钮 pointerdown 里调用了 showMidroll()",
    "owner": "08-polish + 02-scaffold",
    "suggestion": "把广告调用移到 GameOverScene 的重开流程；主菜单按钮不得触发广告",
    "status": "open",
    "fix_note": "",
    "round": 1,
    "found_at": "2026-10-17T21:40:00+08:00"
  }
]
```

- `severity`：`blocker`（REQ 条目，必须修）/ `major`（GUIDE 条目）
- `owner`：应退回哪个生产环节（**审核官不自己改**）
- `status`：`open` → `fixed`；环节修复后必须回填 `fix_note` 与修复证据
- 审核官复审时按 `(item, round)` 去重，不重复开单

### `manual-checks.json`（人工条目填写表）

由 `review_gate.py` 首次运行生成；审核官逐条填 `result`（`pass`/`fail`/`na`）与 `evidence`。
**存在未填条目时结论为 `INCOMPLETE`，不得放行。**

## 硬性约束（违反即视为契约破坏）

1. `src/game/` 内**禁止**出现任何平台 SDK 或 `src/platform/` 的引用；平台能力一律通过 `src/game/util.ts` 的 `bridge(scene)` 读取注入的实例。
2. 构建产物中**禁止**出现绝对路径引用（CrazyGames 等平台会直接拒审）。
3. `state.yaml` 必须与磁盘实际产物一致；不一致时以磁盘为准并修正状态。
4. **未完成 G0（`delivery.platform_confirmed: true`）不得进入任何后续阶段。**
5. 每个平台适配器必须保留 `name: 'i2g-platform:<key>'` 标识（构建产物中需可检索），`precheck.py` 依赖它判定适配层是否被正确注入。
6. **审核官不得修改 `src/`、`assets/`、`docs/00`–`08`**（职责分离）。它只写 `docs/09-review/`。
7. **`review_final.verdict` 非 `PASS` / `PASS_WITH_DEVIATIONS` 时，`ship` 阶段必须失败** —— 此约束由 `gate_check.py` 强制执行，不得绕过。
8. **`docs/09-review/` 只由审核官写入**；问题单的 `fix_note` 与 `status` 由被指派的环节回填。

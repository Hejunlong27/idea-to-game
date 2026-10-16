# 文件契约（contracts）

阶段之间只通过本文件定义的产物通信。不要依赖对话上下文传递状态。

## 项目根目录布局

```
<project>/
├─ .gamedev/
│  ├─ state.yaml
│  └─ logs/
├─ docs/
│  ├─ 01-brief/   gdd.md  scope.json
│  ├─ 02-art/     art-bible.md  palette.json  prompts/
│  ├─ 03-scaffold/ architecture.md
│  ├─ 04-core-loop/ notes.md
│  ├─ 05-polish/  juice-log.md
│  ├─ 06-perf/    report.md
│  ├─ 07-qa/      report.html  screenshots/
│  └─ 08-ship/    submit-checklist.md  store-copy.md
├─ src/
│  ├─ types.ts    共享类型（PlatformBridge 接口定义在此）
│  ├─ game/       纯玩法逻辑，禁止 import src/platform/
│  ├─ platform/   各平台适配器 + 工厂
│  └─ main.ts
├─ assets/
│  ├─ raw/        生图原始产物
│  ├─ processed/  切图抠图后
│  ├─ atlas/      图集 png + json
│  └─ audio/{bgm,sfx}/
├─ dist/{crazygames,poki,playgama}/
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
  scaffold:     { status: done,        output: src/ }
  art_bible:    { status: done,        output: docs/02-art/,   gate: G2_passed }
  core_loop:    { status: done,        self_test: playable }
  art_forge:    { status: done,        progress: "sprites 12/12" }
  sprite_tools: { status: done,        output: assets/atlas/ }
  audio_forge:  { status: degraded,    note: "配乐不可用，已用合成音降级" }
  polish:       { status: in_progress }
  perf_audit:   { status: pending,     retries: 0 }
  qa:           { status: pending }
  ship:         { status: pending }

delivery:
  tier: L2_shippable
  platforms: [crazygames, poki, playgama]
```

字段规则：
- `status`：`pending` / `in_progress` / `done` / `failed` / `degraded` / `skipped`
- `gate`：仅 `brief` 与 `art_bible` 阶段有，取值 `G1_passed` / `G2_passed`
- `retries`：仅 `perf_audit` 使用，回退计数
- `degraded` 必须在最终交付报告中显式列出

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

## `docs/02-art/prompts/<asset>.txt`

单行提示词，格式：

```
<subject>, <view/pose>, game asset, transparent background, centered, <style_tokens>
```

禁止在提示词里重新描述风格 —— 风格只由 `style_tokens` 提供，保证一致性。

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
| `dist/<platform>/` | 该平台可独立运行的构建产物 |
| `dist/<platform>.zip` | 提交用压缩包（内部相对路径，根目录直接是 index.html） |
| `docs/08-ship/submit-checklist.md` | 过审自检清单，逐条打勾并附实测值 |
| `docs/08-ship/store-copy.md` | 标题（≤60 字符）、简短描述（≤120）、详细描述（≤500）、截图清单 |

## 硬性约束（违反即视为契约破坏）

1. `src/game/` 内**禁止**出现任何平台 SDK 或 `src/platform/` 的引用；平台能力一律通过 `src/game/util.ts` 的 `bridge(scene)` 读取注入的实例。
2. 构建产物中**禁止**出现绝对路径引用（CrazyGames 会直接拒审）。
3. `state.yaml` 必须与磁盘实际产物一致；不一致时以磁盘为准并修正状态。

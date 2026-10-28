# 模块 03 · 美术风格规范（art bible）

**阶段**：P1 ｜ **前置**：G1 通过 ｜ **产出**：`docs/02-art/art-bible.md`、`palette.json`、`prompts/` ｜ **后置门禁**：G2 ｜ 可与 `02-scaffold` 并行

## 目标

从**一张风格参考图**中提取可复用的风格规范，产出统一的 `style_tokens`，供后续所有生图环节注入，**保证全套素材风格一致**。

这是整条链路风格一致性的唯一锚点。此环节做错，P2 所有素材作废。

## 步骤

### 1. 提取主色板

```bash
python <skill>/scripts/palette_extract.py --input <参考图> --out docs/02-art/palette.json --colors 8
```

产出主色板（5–8 色 HEX）+ 背景色 + 强调色。

### 2. 人工判读风格维度

对照参考图，逐项判定并记录到 `art-bible.md`：

| 维度 | 取值示例 |
|---|---|
| 线条风格 | 粗描边 / 细描边 / 无描边 |
| 着色方式 | 平涂 / 渐变 / 像素 / 厚涂 |
| 质感 | 光滑 / 粗糙 / 手绘 / 3D 渲染感 |
| 形状语言 | 圆润 / 硬朗 / 几何 |
| 明度关系 | 高对比 / 低对比 |
| 氛围词 | playful / warm / clean / moody / retro |

### 3. 生成 style_tokens

把上述维度压缩成**一行**可注入提示词的风格串，写入 `palette.json` 的 `style_tokens` 字段。

示例：

```
flat vector, thick dark outline, warm saturated palette, soft rounded shapes, high contrast, no gradient
```

### 4. 生成各素材提示词

**先跑脚本生成骨架，再精修主体描述**（手写 30 条提示词既慢又容易漏 `style_tokens`）：

```bash
python <skill>/scripts/gen_prompts.py            # 从 scope.json 批量生成
python <skill>/scripts/gen_prompts.py --dry-run  # 只看不写
```

脚本会为每个素材写 `docs/02-art/prompts/<asset>.txt` 与同名 `.json`（尺寸/negative），
并生成 `docs/02-art/subjects.json` 骨架 —— **主体描述必须精修**（`apple` → `a shiny red apple, front view`），
改完 `--force` 重跑即可。

提示词格式：

```
<subject>, <view/pose>, game asset, centered, <纯色背景指令>, <style_tokens>
```

**规则**：
- 提示词中**禁止**重新描述风格 —— 风格只由 `style_tokens` 提供
- 尺寸在 `art-bible.md` 中统一约定（如精灵 64×64、UI 图标 48×48）；生图尺寸由 `.json` sidecar 或 `artgen.yaml` 的 `size` 控制
- 同类素材的视角与构图保持一致（如全部正面平视、全部居中）
- 用本地 ComfyUI / RunningHub 出图时，加 `on a flat pure magenta background` 以便出图后泛洪抠图（见 `05-art-forge`）

### 5. 写 art-bible.md

汇总：色板（含 HEX 色块说明）、风格维度、`style_tokens`、素材尺寸规范、命名规范、每个素材的用途与尺寸表。

### 6. 门禁 G2（必须人工）

向用户展示色板与风格判读结果，明确询问：

1. 色板与画风是否符合预期？
2. 是否需要换参考图重新提取？
3. 素材尺寸与命名规范是否同意？

**得到明确确认后**才写入 `state.yaml` 的 `gate: G2_passed`。

## 自检

- [ ] `palette.json` 含 5–8 个主色 + 背景色 + `style_tokens`
- [ ] `style_tokens` 是一行，不含具体主体描述
- [ ] `prompts/` 覆盖 `scope.json` 中全部素材，且每行都含 `style_tokens`
- [ ] `art-bible.md` 有尺寸规范与命名规范
- [ ] 已获用户明确确认

## 降级

若参考图模糊、色板提取质量差：标记 `art_bible: fallback`，使用中性默认色板，并要求用户补充更清晰的参考图。**不得**在未确认风格的情况下进入 P2 生图。

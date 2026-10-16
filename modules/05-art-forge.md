# 模块 05 · 生图（art forge）

**阶段**：P2 ｜ **前置**：G2 通过 + `04-core-loop` 自测可玩 ｜ **产出**：`assets/raw/` ｜ 后接 `06-sprite-tools`

## 目标

按 `docs/02-art/palette.json` 的 `style_tokens` 与 `docs/02-art/prompts/` 生成全套素材，保证风格统一。

## 前置检查（不可跳过）

- [ ] `04-core-loop` 已标记 `self_test: playable` —— 玩法未验证不得进入本环节
- [ ] `docs/02-art/palette.json` 存在且含 `style_tokens`
- [ ] `docs/02-art/prompts/` 覆盖 `scope.json` 的全部素材

## 步骤

### 1. 逐项生图

对 `prompts/` 中每个文件，用图像生成能力（ImageGen）按提示词生成素材，输出到 `assets/raw/<asset>.png`。

**必须遵守**：
- 提示词**原样使用** `prompts/` 文件内容，不要临场改写风格描述
- 透明背景（PNG with alpha）
- 主体居中
- 同一批素材使用相同风格参数，必要时固定 seed

### 2. 一致性控制

| 问题 | 手段 |
|---|---|
| 多个精灵风格跳脱 | 全部复用同一 `style_tokens`；固定 seed |
| 同一角色多帧不一致 | 以首帧为参考图做 img2img |
| 色板偏离参考图 | 出图后用 `palette_extract.py` 比对，偏差大则重出 |
| 尺寸不统一 | 生成后统一缩放到 `art-bible.md` 约定的尺寸 |

### 3. 批量出图策略

对同类多件素材（如 8 个水果），可用**一张网格图**批量生成（如 3×3 布局），再由 `06-sprite-tools` 切分。这样风格一致性最好。

### 4. 候选筛选

每类素材至少保留 1 个可用候选。不合格的候选直接重出，不要把明显不合格的素材带入下一环节。

### 5. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage art_forge
```

## 自检

- [ ] `assets/raw/` 中每个文件对应 `scope.json` 的一个素材项，无遗漏
- [ ] 全部为透明背景 PNG
- [ ] 风格与参考图一致（色板可比对）
- [ ] 无肉眼可见的风格跳脱素材
- [ ] 素材尺寸已按 `art-bible.md` 统一

## 降级

生图能力不可用时：**不要阻塞流程**。生成程序化占位素材（按 `palette.json` 的主色填充的几何图形 + 文字标签），标记 `art_forge: degraded`，游戏仍必须可运行。在最终交付报告中显式列出该降级项。

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 在提示词里重写风格 | 风格漂移 | 只用 `style_tokens` |
| 逐个生图导致风格不一 | 素材不可用 | 改用网格批量出图 |
| 把不合格素材带入切图 | 返工到生图 | 当批筛掉重出 |
| 玩法未验证就大规模生图 | 玩法改了全废 | 先确认 `self_test: playable` |

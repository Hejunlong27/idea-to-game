# 模块 06 · 切图与图集（sprite tools）

**阶段**：P2 ｜ **前置**：`05-art-forge` 完成 ｜ **产出**：`assets/processed/`、`assets/atlas/`

## 目标

把生图原始产物处理成 Phaser 可直接使用的素材与图集。

**为什么必须打图集**：CrazyGames 限制总文件数 ≤1500，散落小图会迅速逼近上限。

## 步骤

### 0. 网格图已经切好了？

用 `gen_prompts.py --sheet/--frames` + `gen_assets.py` 生成的素材，**切分与抠图已经在生图环节做完了**，
产物直接落在 `assets/raw/`（每格一个 PNG，尺寸已统一）。这种情况下跳过本模块的 1–3 步，直接打图集。

只有「别人给的网格图 / 手工拼的 sheet」才需要下面手工切分。

### 1. 网格切分

若生图是网格图（如 3×3 布局）：

```bash
python <skill>/scripts/sprite_tools.py \
  --input assets/raw/sheet.png \
  --grid 3x3 \
  --trim \
  --out assets/processed/
```

- `--grid RxC`：按行列切分
- `--trim`：按 alpha 通道裁掉透明边距，让素材紧贴内容

### 2. 抠图

AI 出图**不带 alpha**（SDXL/SD1.5），必须抠。优先用泛洪抠图（从四边向内，主体内部同色区域不受影响）：

```bash
python <skill>/scripts/sprite_tools.py \
  --input assets/raw/ \
  --remove-bg --bg-color "#FF00FF" --bg-tolerance 40 \
  --trim --pad-to 256x256 \
  --out assets/processed/
```

- `--remove-bg`：四边泛洪抠背景色，**AI 出图首选**
- `--matte`：全局替换同色像素，只适合纯色底且主体无同色的情况（会误伤高光）
- `--pad-to WxH`：等比缩放进统一透明画布并居中 —— 让所有精灵尺寸一致，避免图集里大小不一

### 3. 统一尺寸

按 `docs/02-art/art-bible.md` 约定的尺寸缩放：

```bash
python <skill>/scripts/sprite_tools.py \
  --input assets/processed/ \
  --resize 64x64 \
  --out assets/processed/
```

`--resize` 会**拉伸**（强制 WxH）；要保持比例用 `--pad-to`。

### 4. 打包图集

```bash
python <skill>/scripts/pack_atlas.py \
  --input assets/processed/ \
  --out assets/atlas/atlas \
  --padding 2 \
  --max-size 2048
```

产出 `atlas.png` + `atlas.json`（Phaser TexturePacker JSON Hash 格式）。

### 5. 在代码中引用

```ts
this.load.atlas('game', 'assets/atlas/atlas.png', 'assets/atlas/atlas.json');
// 使用
this.add.image(x, y, 'game', 'fruit_1');
```

### 6. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage sprite_tools
```

## 自检

- [ ] 每个素材切分位置正确，无截断、无粘连
- [ ] 抠图边缘干净，无明显白边或残留背景
- [ ] 素材尺寸与 `art-bible.md` 一致
- [ ] `atlas.json` 中每个 `frames` 键名与代码引用一致
- [ ] 图集总尺寸 ≤2048（超出需分多张）
- [ ] `assets/processed/` 中无冗余文件

## 帧动画（多帧素材）

一套动画 = 一组命名连续的帧，打成图集后由模板的 `anim.ts` 注册：

| 约定 | 值 |
|---|---|
| 帧名 | `<key>_0` … `<key>_N-1`（如 `slime_idle_0..3`） |
| 生成方式 | `gen_prompts.py --frames slime_idle --grid 2x2 --count 4` → `gen_assets.py --only slime_idle` |
| 注册 | `config.ts` 的 `ANIM = { slime_idle: 4 }`，`BootScene` 自动注册为 `slime_idle_loop` |
| 播放 | `playFrames(sprite, 'slime_idle')`（`src/game/anim.ts`） |

**为什么用图集帧而不是多张 PNG**：CrazyGames 限制总文件数 ≤1500，一套 8 帧就是 8 个文件；
图集只增 1 张图。

**一致性要点**：

- 同一套帧必须出自**同一张网格图**（同一次推理）—— 跨图生成必然色差/比例漂移
- 每帧裁边后统一画布（`gen_assets.py` 已做），否则播放时会"抖动"
- 帧率 8–12 fps 足够；超休闲不需要 24 fps
- 帧数控制在 4–6 帧：再多对观感提升有限，对体积和生图成本是线性增加

## 命名规范

- 精灵：`<类别>_<序号>`，如 `fruit_1` … `fruit_8`
- 动画帧：`<动作key>_<帧序号>`，如 `slime_idle_0` … `slime_idle_3`
- UI：`ui_<用途>`，如 `ui_btn_restart`
- 图集内的键名必须与 `scope.json` 的 `assets` 清单可对应

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 不打图集，散落小图 | 文件数超标被拒审 | 必须打图集 |
| 切分偏移（素材不居中） | 素材被切坏 | 先 `--trim` 再切，或调整网格 |
| 图集键名与代码不一致 | 运行时报纹理缺失 | 切完立即核对 |
| 忘记抠图 | 出现白底方块 | 检查 alpha 通道 |

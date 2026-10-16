# 模块 06 · 切图与图集（sprite tools）

**阶段**：P2 ｜ **前置**：`05-art-forge` 完成 ｜ **产出**：`assets/processed/`、`assets/atlas/`

## 目标

把生图原始产物处理成 Phaser 可直接使用的素材与图集。

**为什么必须打图集**：CrazyGames 限制总文件数 ≤1500，散落小图会迅速逼近上限。

## 步骤

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

若素材不是透明背景，按 alpha 通道或边缘色做抠图：

```bash
python <skill>/scripts/sprite_tools.py \
  --input assets/raw/fruit.png \
  --matte \
  --bg-color "#FFFFFF" \
  --out assets/processed/
```

### 3. 统一尺寸

按 `docs/02-art/art-bible.md` 约定的尺寸缩放：

```bash
python <skill>/scripts/sprite_tools.py \
  --input assets/processed/ \
  --resize 64x64 \
  --out assets/processed/
```

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

## 命名规范

- 精灵：`<类别>_<序号>`，如 `fruit_1` … `fruit_8`
- UI：`ui_<用途>`，如 `ui_btn_restart`
- 图集内的键名必须与 `scope.json` 的 `assets` 清单可对应

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 不打图集，散落小图 | 文件数超标被拒审 | 必须打图集 |
| 切分偏移（素材不居中） | 素材被切坏 | 先 `--trim` 再切，或调整网格 |
| 图集键名与代码不一致 | 运行时报纹理缺失 | 切完立即核对 |
| 忘记抠图 | 出现白底方块 | 检查 alpha 通道 |

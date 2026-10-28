# 模块 05 · 生图（art forge）

**阶段**：P2 ｜ **前置**：G2 通过 + `04-core-loop` 自测可玩 + **R1 灰盒预审通过** ｜ **产出**：`assets/raw/` ｜ 后接 `06-sprite-tools`

## 目标

按 `docs/02-art/prompts/` 的提示词，用**本地 ComfyUI** 或 **RunningHub 工作流 API** 批量出图，保证风格统一、可断点续跑、失败可降级。

三种 provider，由 `.gamedev/artgen.yaml` 的 `provider` 决定：

| provider | 说明 | 何时用 |
|---|---|---|
| `comfyui` | 本地 ComfyUI（`/prompt` + `/history` + `/view`） | 本机有 GPU、要跑 LoRA/ControlNet/自建工作流 |
| `runninghub` | RunningHub 云端工作流 API（`task/openapi/*`） | 本机没显卡，或要用现成的云端工作流 |
| `placeholder` | 程序化占位（Pillow 画色块 + 名称） | 两者都不可用时的兜底，保证流程不卡死 |

`auto`（默认）= ComfyUI 可达 → RunningHub 凭证齐全 → 占位，按序降级。

## 前置检查（不可跳过）

- [ ] `04-core-loop` 已标记 `self_test: playable`，且 **R1 审核通过** —— 玩法未验证不得烧生图成本
- [ ] `docs/02-art/palette.json` 含 `style_tokens`
- [ ] `docs/02-art/prompts/` 覆盖 `scope.json` 的全部素材

## 步骤

### 1. 配 provider

```bash
# 体检：一次看清两条通道是否可用
python <skill>/scripts/gen_assets.py --probe
```

典型输出：

```
[PASS] ComfyUI: 可达 · ComfyUI 0.3.x · NVIDIA GeForce RTX 4070
[FAIL] RunningHub: 缺少 workflowId（在 RunningHub 工作流页面取数字 ID）
```

配置在 `.gamedev/artgen.yaml`（`init_project.py` 已生成）。默认用 **Qwen-Image 2.1 turbo** 的文生图 + 图生图工作流：

```yaml
comfyui:
  host: http://127.0.0.1:8188
  workflow: assets/workflows/qwen_image_21_turbo_t2i.json        # 文生图
  workflow_i2i: assets/workflows/qwen_image_21_turbo_i2i.json    # 图生图（sidecar 给 ref 时自动用）
  unet_name: ""      # 留空=用工作流里的值；换量化版本/换机器时在这里覆盖，别改 JSON
  clip_name: ""
  vae_name: ""
  size_mode: auto
  timeout: 600
```

`--probe` 会顺带核对工作流引用的模型本机有没有，缺了会列出本机可用清单。
工作流特殊结构（提示词在 PrimitiveString 上、尺寸走 ResolutionSelector、双图槽位）已在
`assets/workflows/README.md` 说明，脚本自动处理，**不需要手改 JSON**。

RunningHub 填 `workflow_id`，`api_key` 建议走环境变量：

```bash
export RUNNINGHUB_API_KEY=xxxx          # 不要写进仓库
python <skill>/scripts/gen_assets.py --probe
```

拿不到节点映射时先拉工作流结构：

```bash
python <skill>/scripts/gen_assets.py --dump-rh-workflow docs/02-art/rh-workflow.json
# 会打印探测到的 node_map，可直接粘进 artgen.yaml
```

### 2. 复核提示词（先看，再花钱）

```bash
python <skill>/scripts/gen_assets.py --dry-run
```

逐条打印「素材名 / 尺寸 / seed / 最终提示词」。**这一步是唯一低成本纠错点** —— 提示词写错，后面全是废图。

提示词缺失或没带 `style_tokens` 时先补：

```bash
python <skill>/scripts/gen_prompts.py            # 从 scope.json 批量生成，自带 style_tokens
python <skill>/scripts/gen_prompts.py --force    # 精修 subjects.json 后重写
```

### 3. 先出 2 张验风格（成本控制）

```bash
python <skill>/scripts/gen_assets.py --max 2
```

看图确认：风格是否符合 `art-bible.md`、主体是否居中、背景是否可抠。**不满意就改提示词，不要全量跑。**

### 4. 全量出图

```bash
python <skill>/scripts/gen_assets.py
```

- 已生成且提示词/参数未变的素材**自动跳过**（台账 `assets/raw/manifest.json`）
- 只重出某一类：`--only fruit`；强制重出：`--force`
- 单张失败自动重试 3 次（指数退避），仍失败则用占位素材兜底并标记 `degraded`

### 5. 抠图（SDXL 不出 alpha，必做）

三条路，选一条：

| 做法 | 配置 | 适用 |
|---|---|---|
| 出图后自动泛洪抠色 | `artgen.yaml` 的 `remove_bg: "auto"` + 提示词含 `on a flat pure magenta background` | **默认推荐**：auto 从图像四边取样，不要求模型画出精确色值 |
| 指定色值抠 | `remove_bg: "#FF00FF"` | 背景色稳定、想严格控制时 |
| 工作流里接抠图节点（rembg / BRIA / LayerDiffuse） | 自己导出的 API 工作流 + `remove_bg: ""` | 质量最好 |
| 交给 06 环节批量处理 | `sprite_tools.py --remove-bg --bg-color auto` | 想统一控制容差 |

> **为什么默认 `auto`**：模型不会精确画出你写的色值。实测 SD1.5 把 "pure magenta" 画成 `(248,15,187)`，
> 与 `#FF00FF` 的蓝通道差 68 —— 按固定色值抠会整张失败（alpha 全 255，看起来像"没抠"）。
> `auto` 取四边像素中位数作背景色，再配 `remove_bg_tolerance`（默认 60）才可靠。

### 6. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage art_forge
```

同时检查 `assets/raw/.artgen-report.json`：`degraded` 非空说明有素材是占位货，**必须写进最终交付报告**。

## 一致性控制

| 问题 | 手段 |
|---|---|
| 多个精灵风格跳脱 | 同一批固定 `seed` + 同一 `style_tokens`；改风格才改 seed |
| 同一角色多帧不一致 | 以首帧为参考图做 img2img：sidecar 里写 `ref`，脚本会自动切到 `workflow_i2i` |
| 色板偏离参考图 | 出图后用 `palette_extract.py` 比对主色，偏差大则重出 |
| 尺寸不统一 | 生成后 `sprite_tools.py --pad-to 256x256` 统一画布 |

逐素材覆盖参数（可选）：`docs/02-art/prompts/<asset>.json`

```json
{ "width": 512, "height": 512, "seed": 12345, "negative": "...", "ref": "assets/ref/hero.png" }
```

## 自检

- [ ] `assets/raw/` 每个文件对应 `scope.json` 的一个素材项，无遗漏
- [ ] 全部为透明背景 PNG（用看图工具确认 alpha，不是只有棋盘格背景）
- [ ] 风格与参考图一致（色板可比对）
- [ ] 无肉眼可见的风格跳脱素材
- [ ] `manifest.json` 记录了 provider / seed / prompt hash
- [ ] `degraded` 项已记录，准备写入交付报告

## 降级

| 失败点 | 处理 |
|---|---|
| ComfyUI 不可达（连接被拒） | 检查是否启动、端口是否 8188；`--probe` 会显示具体错误 |
| ComfyUI 返回 502 | 系统代理劫持了 127.0.0.1 —— 脚本已对本地地址绕过代理，若仍 502 检查 `http_proxy` 是否指向了本地端口 |
| 工作流节点探测不到 | 在 `artgen.yaml` 的 `comfyui.node_map` 显式写 `{prompt: {nodeId, fieldName}}` |
| RunningHub 凭证无效 | 确认 API Key 类型支持工作流 API；余额是否充足 |
| 两个通道都不可用 | `provider: placeholder` 出占位素材，游戏仍可跑，标记 `art_forge: degraded` |
| 出图全废但时间紧 | 不要硬扛 —— 降级为程序化几何素材（`assets/` 全用 Graphics 绘制），保证可交付 |

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 在提示词里重写风格 | 风格漂移 | 风格只由 `style_tokens` 提供 |
| 玩法未验证就大规模生图 | 玩法改了全废 | 先确认 `self_test: playable` + R1 通过 |
| 不做 dry-run 直接全量 | 提示词错了，白烧一轮 | 先 `--dry-run`，再 `--max 2` |
| 忘了抠图 | 素材带纯色底，进游戏像贴纸 | 见步骤 5 |
| 把 `degraded` 素材当成品交付 | 过审被拒 | 报告里显式列出 |

## 相关

- `references/artgen-integration.md` —— ComfyUI / RunningHub 接口细节、节点探测规则、故障排查
- `assets/workflows/README.md` —— 工作流导出与 node_map 配置

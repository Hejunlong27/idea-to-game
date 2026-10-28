# 工作流模板（workflows）

`gen_assets.py` 需要一个 **API 格式** 的工作流 JSON（不是 WebUI 的 UI 格式）。

## ComfyUI

### 用内置模板（最快）

`comfyui_txt2img.json` 是最小可用的 SDXL 文生图工作流。只需在 `.gamedev/artgen.yaml` 里把
`comfyui.checkpoint` 改成本机实际存在的模型文件名（在 ComfyUI 的 `models/checkpoints/` 下）：

```yaml
comfyui:
  host: http://127.0.0.1:8188
  workflow: assets/workflows/comfyui_txt2img.json
  checkpoint: sd_xl_base_1.0.safetensors
```

模型名不确定时：

```bash
curl -s http://127.0.0.1:8188/object_info/CheckpointLoaderSimple | python -c "import sys,json;print(json.load(sys.stdin)['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0])"
```

### 用自己调好的工作流（推荐）

1. 在 ComfyUI 里把工作流调到满意（含 LoRA、ControlNet、抠图节点都行）
2. 菜单 → **工作流 → 导出 (API)** → 存成 `<project>/assets/workflows/my.json`
3. 配置 `comfyui.workflow: assets/workflows/my.json`
4. 节点映射**自动探测**，规则见下；探测失败时用 `node_map` 显式指定

### 节点自动探测规则

| 目标 | 探测方式 |
|---|---|
| 正向提示词 | 采样器（`KSampler*`，且 inputs 同时含 positive/negative/latent_image）的 `positive` 指向的节点，取其 `text` / `value` 字段 |
| 反向提示词 | 同上，`negative` 指向的节点 |
| 种子 | 采样器自身的 `seed` 或 `noise_seed` |
| 宽高 | 采样器 `latent_image` 指向的节点，或任一 `Empty*` 类节点的 `width`/`height` |
| 模型 | `CheckpointLoaderSimple` 的 `ckpt_name`（仅当配置了 `comfyui.checkpoint`） |
| 参考图 | 若工作流里有 `LoadImage` 节点且素材 sidecar 里给了 `ref`，会先上传再填文件名 |

探测不到就在 `.gamedev/artgen.yaml` 写死：

```yaml
comfyui:
  node_map:
    prompt:   { nodeId: "6", fieldName: "text" }
    negative: { nodeId: "7", fieldName: "text" }
    seed:     { nodeId: "3", fieldName: "seed" }
    width:    { nodeId: "5", fieldName: "width" }
    height:   { nodeId: "5", fieldName: "height" }
```

## RunningHub

RunningHub 的工作流 ID 是工作流页面 URL 里的那串数字。节点映射来源优先级：

1. `runninghub.node_map` 显式配置
2. `runninghub.workflow_json` 指向的本地 API 格式 JSON（可用 `gen_assets.py --dump-rh-workflow` 拉取）
3. 自动调用 `/api/openapi/getJsonApiFormat` 拉取并探测

```yaml
runninghub:
  base_url: https://www.runninghub.cn      # 国际版用 https://www.runninghub.ai
  api_key: ""                              # 建议用环境变量 RUNNINGHUB_API_KEY
  workflow_id: "1900000000000000001"
  instance_type: ""                        # 需要 4090 48G 时填 plus
  timeout: 600
  poll: 3
```

## 透明背景

SDXL / SD1.5 输出**不带 alpha**。三种做法，按省事程度排序：

1. **提示词写纯色背景 + 自动抠**（默认推荐）
   - 提示词里加 `on a flat pure magenta background`
   - 配置 `remove_bg: "#FF00FF"` —— 出图后从四边泛洪把该色抠成透明，主体内部同色区域不受影响
2. **工作流里接抠图节点**（rembg / BRIA / LayerDiffuse），导出 API 格式即可，无需额外配置
3. **出图后单独跑 `sprite_tools.py --remove-bg`**，批量处理更可控

## 成本与一致性

- `seed` 固定 → 同一素材重跑结果稳定，改提示词才变
- `assets/raw/manifest.json` 记录每个素材的 prompt hash + seed + provider，**未变化自动跳过**
- 先 `--dry-run` 看提示词，再 `--max 2` 试两张确认风格，最后全量
- `--only fruit` 只重出某一类，不触发全量重跑

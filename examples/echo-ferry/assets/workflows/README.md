# 工作流模板（workflows）

`gen_assets.py` 需要一个 **API 格式** 的工作流 JSON（不是 WebUI 的 UI 格式：WebUI 菜单 → 工作流 → 导出 (API)）。

包内自带三份：

| 文件 | 用途 | 说明 |
|---|---|---|
| `qwen_image_21_turbo_t2i.json` | **文生图（默认）** | Qwen-Image 2.1 turbo，8 步 sigmas，中文提示词友好 |
| `qwen_image_21_turbo_i2i.json` | **图生图（默认）** | 同款模型的参考图版，走 `TextEncodeQwenImage21` 的双图槽位 |
| `comfyui_txt2img.json` | SDXL 通用兜底 | 标准 CheckpointLoader + KSampler，模型不匹配时用 |

## 默认：Qwen-Image 2.1 turbo

`.gamedev/artgen.yaml` 默认就指向这两份：

```yaml
comfyui:
  host: http://127.0.0.1:8188
  workflow: assets/workflows/qwen_image_21_turbo_t2i.json
  workflow_i2i: assets/workflows/qwen_image_21_turbo_i2i.json
  unet_name: ""
  clip_name: ""
  vae_name: ""
  size_mode: auto
  timeout: 600
  node_map: {}
```

### 这套工作流的三个特殊之处

1. **提示词不在编码节点上。**
   采样器 → `TextEncodeQwenImage21(471).prompt` → 再链接到 `PrimitiveStringMultiline(488).value`。
   脚本会自动**沿链接追一层**，最终写 `488.value`（不破坏图结构）。

2. **正负提示词共用一个编码节点。**
   `SamplerCustom` 的 positive 取 471 的第 0 个输出、negative 取第 1 个输出。
   脚本识别「同节点双输出」，正向写 `471.prompt`（追到 488）、反向写 `471.negative_prompt`（字面量）。

3. **输出尺寸由 `ResolutionSelector` 决定，不是 EmptyLatentImage。**
   `EmptyLatentImage.width/height` 是**链接**（指向节点 13）。脚本不会粗暴覆盖链接，
   而是把目标宽高换算成 `aspect_ratio` + `megapixels`（`size_mode: selector`）：

   | 目标 | 实际设置 |
   |---|---|
   | 1024×1024 | `1:1 (Square)` + 1.0 MP |
   | 1080×1920 | `9:16 (Portrait Widescreen)` + 2.1 MP |
   | 512×512 | `1:1 (Square)` + 0.3 MP |

   ⚠️ 这套工作流的实际像素是「比例档位 × 百万像素」算出来的，**不是精确 W×H**。
   要精确尺寸就在 `artgen.yaml` 设 `size_mode: latent`（会直接写 474 的宽高，切断与选择器的链接）。

### 模型名

工作流里写的是 `qwen_image_2.1_turbo_int8_convrot.safetensors` / `qwen3vl_8b_int8_convrot.safetensors` /
`qwen_image_2.1_vae_bf16.safetensors`。**换机器/换量化版本时不要改工作流 JSON**，在配置里覆盖：

```yaml
comfyui:
  unet_name: qwen_image_2.1_int8_convrot.safetensors   # 非 turbo 版
  clip_name: ""
  vae_name: ""
```

`gen_assets.py --probe` 会先核对工作流引用的模型在本机 `UNETLoader / CLIPLoader / VAELoader`
里是否存在，缺了直接报出本机可用清单 —— 共享工作流最常见的失败就是模型名对不上。

> 非 turbo 模型配 8 步 sigmas 能跑但质量差。换非 turbo 时把 `ManualSigmas` 的档位调多
> （例如 `1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.45, 0.3, 0.15, 0`），或直接用 turbo 模型。

### 图生图怎么触发

素材 sidecar 里给 `ref` 就会**自动切到 i2i 工作流**（不需要改配置）：

```json
// docs/02-art/prompts/gem_red.json
{ "width": 1024, "height": 1024, "ref": "assets/ref/gem_base.png" }
```

参考图会先 `POST /upload/image` 上传，然后写入**所有** `LoadImage` 节点（Qwen i2i 有两个图槽位
`images.image_1` / `images.image_2`，只填一个、另一个仍指向工作流里原本的文件名会导致校验失败）。

用途：同一角色的多帧/多表情保持一致 —— 以首帧为 `ref` 生成其余帧。

## 用自己调好的工作流

1. ComfyUI 里调到满意（含 LoRA、ControlNet、抠图节点都行）
2. 菜单 → **工作流 → 导出 (API)** → 存成 `<project>/assets/workflows/my.json`
3. 配置 `comfyui.workflow: assets/workflows/my.json`
4. 节点映射**自动探测**，规则见下；探测失败时用 `node_map` 显式指定

### 节点自动探测规则

| 目标 | 探测方式 |
|---|---|
| 采样器 | inputs 同时含 `positive` / `negative` / `latent_image` 的节点；找不到则取 `class_type` 含 `KSampler` 的 |
| 正向提示词 | 采样器 `positive` 指向的节点；字段按 `text` → `prompt` → `value` → `string` 优先；**若是链接则沿链接再追一层** |
| 反向提示词 | 同上；positive 与 negative 指向**同一节点**时，改用 `negative_prompt` 字段 |
| 种子 | 采样器自身的 `seed` 或 `noise_seed` |
| 宽高 | `latent_image` 指向的节点，或任一 `Empty*` 节点：字面量→直接写；链接到 `ResolutionSelector`→改比例+百万像素 |
| 模型 | `UNETLoader.unet_name` / `CLIPLoader.clip_name` / `VAELoader.vae_name` / `CheckpointLoaderSimple.ckpt_name` |
| 参考图 | 所有 `LoadImage.image`（给了 `ref` 才动） |

探测不到就在 `.gamedev/artgen.yaml` 写死（Qwen 这套工作流的等价写法）：

```yaml
comfyui:
  node_map:
    prompt:   { nodeId: "488", fieldName: "value" }
    negative: { nodeId: "471", fieldName: "negative_prompt" }
    seed:     { nodeId: "497", fieldName: "noise_seed" }
```

## RunningHub

RunningHub 的工作流 ID 是工作流页面 URL 里的那串数字。节点映射来源优先级：

1. `runninghub.node_map` 显式配置
2. `runninghub.workflow_json` 指向的本地 API 格式 JSON（`--dump-rh-workflow` 可生成）
3. 自动调用 `/api/openapi/getJsonApiFormat` 拉取并探测

```yaml
runninghub:
  base_url: https://www.runninghub.cn      # 国际版 https://www.runninghub.ai
  api_key: ""                              # 建议用环境变量 RUNNINGHUB_API_KEY
  workflow_id: "1900000000000000001"
  instance_type: ""                        # 需要 4090 48G 时填 plus
  timeout: 600
  poll: 3
```

## 透明背景

Qwen-Image / SDXL 输出都**不带 alpha**。三种做法，按省事程度排序：

1. **提示词写纯色背景 + 自动抠**（默认推荐）
   - 提示词里加 `on a flat pure magenta background`
   - 配置 `remove_bg: "auto"` —— 从四边取样背景色后泛洪抠成透明，主体内部同色区域不受影响
   - **别写死 `#FF00FF`**：模型画不出精确色值（实测 SD1.5 出 `(248,15,187)`），固定值会整张抠不掉
2. **工作流里接抠图节点**（rembg / BRIA / LayerDiffuse），导出 API 格式即可，无需额外配置
3. **出图后单独跑 `sprite_tools.py --remove-bg --bg-color auto`**

## 成本与一致性

- `seed` 固定 → 同一素材重跑结果稳定，改提示词才变
- `assets/raw/manifest.json` 记录每个素材的 prompt hash + seed + provider + workflow，**未变化自动跳过**
- 先 `--dry-run` 看提示词，再 `--max 2` 试两张确认风格，最后全量
- `--only fruit` 只重出某一类，不触发全量重跑

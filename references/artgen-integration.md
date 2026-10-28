# 生图接入（ComfyUI / RunningHub）

`scripts/gen_assets.py` 的实现依据。**改动本文件前先确认接口没有变更** —— 两个平台的 API 都在演进。

## 一、ComfyUI（本地）

### 接口

| 用途 | 请求 | 说明 |
|---|---|---|
| 提交任务 | `POST {host}/prompt` body `{prompt: <API格式工作流>, client_id}` | 返回 `{prompt_id}` |
| 查结果 | `GET {host}/history/{prompt_id}` | 未完成返回 `{}`；完成后 `outputs` 里是图片清单 |
| 下载图片 | `GET {host}/view?filename=&subfolder=&type=output` | 返回 PNG 二进制 |
| 上传参考图 | `POST {host}/upload/image`（multipart：`image` / `overwrite` / `type`） | 返回 `{name, subfolder}` |
| 体检 | `GET {host}/system_stats` | 返回 `system.comfyui_version`、`devices[]` |
| 查模型 | `GET {host}/object_info/CheckpointLoaderSimple` | `input.required.ckpt_name[0]` 是模型名数组 |

工作流必须是 **API 格式**（WebUI 菜单「工作流 → 导出 (API)」），结构是 `{"<节点id>": {class_type, inputs, _meta}}`。

### 节点自动探测规则（`detect_nodes`）

1. **采样器**：找 `inputs` 同时含 `positive` / `negative` / `latent_image` 的节点；找不到则退化为任一 `class_type` 含 `KSampler` 的节点
2. **正/反向提示词**：采样器 `positive` / `negative` 指向的节点；字段按 `text` → `prompt` → `value` → `string` 优先；
   **若该字段是链接，沿链接再追一层**（Qwen 的 `TextEncodeQwenImage21.prompt` → `PrimitiveStringMultiline.value` 就是这种）
3. **同节点双输出**：positive 与 negative 指向**同一个**编码节点时（Qwen 的 `SamplerCustom` 就是这样），
   正向取 `prompt`、反向取 `negative_prompt`，不能当成两个节点处理
4. **种子**：采样器自身的 `seed` 或 `noise_seed`
5. **宽高**：`latent_image` 指向的节点或任一 `Empty*` 节点 ——
   字面量 → 直接写；是链接且上游有 `aspect_ratio` + `megapixels`（`ResolutionSelector`）→ 换算成比例档位 + 百万像素
6. **模型**：`UNETLoader.unet_name` / `CLIPLoader.clip_name` / `VAELoader.vae_name` / `CheckpointLoaderSimple.ckpt_name`，
   可被 `comfyui.unet_name / clip_name / vae_name / checkpoint` 覆盖
7. **参考图**：给了 `ref` 时上传并写入**所有** `LoadImage.image`（多图槽位的工作流必须全填，否则另一个槽位指向本机不存在的文件）

### 尺寸：`size_mode`

| 值 | 行为 | 何时用 |
|---|---|---|
| `auto`（默认） | 有 `ResolutionSelector` 就改比例+百万像素，否则直接写宽高 | 通用 |
| `latent` | 强制直接写 `Empty*` 的宽高（会切断与选择器的链接） | 需要精确 W×H 时 |
| `selector` | 强制走选择器 | 明确知道工作流结构时 |

⚠️ 走 selector 时输出像素是「比例档位 × 百万像素」算出来的，**不保证等于请求的 W×H**（1024×1024 是准的，512 会落到 544 附近）。

### 模型存在性校验（`--probe`）

`probe()` 会读取工作流里引用的模型名，逐个查 `/object_info/{UNETLoader|CLIPLoader|VAELoader|CheckpointLoaderSimple}`，
缺失时直接报「工作流引用的模型本机缺失：xxx（本机可用：yyy…）」。**共享工作流的头号失败原因就是模型名对不上**，
不要靠 ComfyUI 的 400 报错去猜。

探测不到就在 `artgen.yaml` 的 `comfyui.node_map` 里显式写死。**不要改脚本去适配某个特定工作流** —— 不同工作流节点 id 完全不同，配置化才是可维护的。

### ⚠️ 两个必踩的坑

1. **系统代理会劫持 127.0.0.1。** 沙盒/公司网络里常设了 `http_proxy`，urllib 默认对 localhost 也走代理，结果 ComfyUI 明明在跑却返回 `502 Bad Gateway`。
   脚本对 ComfyUI 的所有请求都传 `no_proxy=True`（`ProxyHandler({})` 绕过）。**新增 ComfyUI 请求时必须带上这个参数。**
2. **`/history` 空对象 ≠ 失败。** 未完成时返回 `{}`，必须轮询到出现 `prompt_id` 键为止；同时要看 `status.status_str == "error"` 才算真失败，否则会一直等到超时。

## 二、RunningHub（云端工作流）

### 接口（v1，`/task/openapi/*`，请求体带 `apiKey`）

| 用途 | 请求 | 返回 |
|---|---|---|
| 提交任务 | `POST {base}/task/openapi/create` `{workflowId, apiKey, nodeInfoList, instanceType?}` | `{code:0, data:{taskId, netWssUrl}}` |
| 查状态/结果 | `POST {base}/task/openapi/outputs` `{taskId, apiKey}` | `code:0` + `data:[{fileUrl, fileType, nodeId, fieldName, taskCostTime}]`；未完成时 `msg` 为 `APIKEY_TASK_IS_QUEUED` / `APIKEY_TASK_IS_RUNNING` |
| 上传素材 | `POST {base}/task/openapi/upload`（multipart：`apiKey` / `file` / `fileType=image`） | 上传后的文件名 |
| 拉工作流结构 | `POST {base}/api/openapi/getJsonApiFormat` `{apiKey, workflowId}` | API 格式工作流 JSON |

- `base`：国内 `https://www.runninghub.cn`，国际 `https://www.runninghub.ai`
- `nodeInfoList` 每项 `{nodeId, fieldName, fieldValue}` —— 必须用**字符串** nodeId
- `instanceType: "plus"` 才走 4090 48G（默认实例）
- 平台另有 v2 接口（`POST /openapi/v2/{endpoint}`，`Authorization: Bearer <key>`，`POST /openapi/v2/query` 查结果）。本脚本用 v1，因为 v1 的 `nodeInfoList` 语义最直接；要用 v2 时按官方文档换 `RunningHub` 类里的 URL 与鉴权即可。

### 节点映射来源（优先级）

1. `runninghub.node_map` 显式配置
2. `runninghub.workflow_json` 指向的本地 API 格式 JSON（`--dump-rh-workflow` 可生成）
3. 自动调 `getJsonApiFormat` 拉取后按同一套 `detect_nodes` 规则探测

### 计费与并发

- 按任务计费，**失败任务也可能计费** → 先用 `--max 1` 验证提示词与工作流
- 并发受 API Key 权益限制，脚本串行执行（ComfyUI 队列本身也是串行，统一按串行设计）
- `timeout` 默认 600s；复杂工作流（视频/高清放大）要调大

## 三、统一行为

### 台账与断点续跑

`assets/raw/manifest.json`：

```json
{
  "version": 1,
  "provider": "comfyui",
  "assets": {
    "apple": {
      "provider": "comfyui", "seed": 20261016, "width": 1024, "height": 1024,
      "prompt": "...", "signature": "a1b2c3d4e5f6a7b8",
      "status": "ok", "bytes": 48211, "generated_at": "..."
    }
  }
}
```

`signature = sha256(provider|prompt|negative|width|height|seed|ref|workflow)` 的前 16 位。
**签名不变且文件存在 → 跳过**。这就是「改一条提示词只重出那一张」的实现方式。

### 失败处理

```
单张：重试 3 次（2s / 4s / 8s 退避）
  └─ 仍失败 → fallback_placeholder: true 时用占位素材顶上，记 degraded
             false 时记 failed，退出码 1
整体：任一 failed → state.art_forge = failed；只有 degraded → degraded；全 ok → done
```

### 透明背景

SDXL/SD1.5 输出不带 alpha。`remove_bg` 用**从四边泛洪**而不是全局色替换 ——
全局替换会把主体内部同色像素一起抠掉（例如红色苹果上的高光），泛洪只吃掉与边缘连通的背景。

**不要用固定色值抠**：模型画不出精确的 `#FF00FF`。实测 SD1.5 的 "pure magenta" 是 `(248,15,187)`，
蓝通道差 68，tol=40 时一个像素都抠不掉，结果"看起来没生效"。
所以默认 `remove_bg: "auto"` —— 取四边像素逐通道中位数当背景色，再配 `remove_bg_tolerance: 60`。

### 成本控制顺序（照做能省 80% 的废图）

1. `--dry-run` 看提示词
2. `--max 2` 验风格
3. `--only <类别>` 单类重出
4. 全量

## 四、排查表

| 症状 | 原因 | 处理 |
|---|---|---|
| ComfyUI `502 Bad Gateway` | 系统代理劫持 localhost | 脚本已绕代理；仍失败则检查 `host` 是否写成了外网地址 |
| ComfyUI `Connection refused` | 服务没起 / 端口不对 | 启动 ComfyUI，确认 `--port` |
| ComfyUI 一直超时 | 工作流里有未满足的节点（缺模型/缺自定义节点） | 先在 WebUI 里手动跑通同一工作流 |
| 出图全是黑图 | VAE 与模型不匹配 | 换 checkpoint 或显式接 VAE Decode |
| RunningHub `code != 0` | Key 类型不支持工作流 API / 余额不足 / workflowId 错 | 看 `msg`，到控制台核对 |
| RunningHub 任务一直 QUEUED | 排队或实例类型不匹配 | 调大 `timeout`，或设 `instance_type` |
| 节点探测不到 prompt | 工作流用了非标准编码节点（如 `PrimitiveString` 中转） | 在 `node_map` 里直接指向真正持有文本的节点 |
| 抠图后主体缺块 | 主体颜色与背景色太接近 | 换背景色（洋红 ↔ 绿），或降低 `bg-tolerance` |

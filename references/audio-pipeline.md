# 音频接入流水线

游戏音频分三层，按可用性逐级降级。**任何一层缺失都不能让游戏静音崩溃**。

| 层 | 来源 | 何时用 | 版权 |
|---|---|---|---|
| L1 程序化 | `gen_audio.py` 的 RECIPES | 永远可用，兜底 | 自有，无争议 |
| L2 音乐 | **YuE2-Studio 本机模型** | 要真 BGM 时 | 本地生成，无第三方素材 |
| L3 语音 | TTS 服务 | 需要旁白时 | 视服务而定 |

## 为什么优先用 YuE2 而不是素材库

素材库的 BGM 有授权范围问题（平台独占、商用限制、二次分发）。本机模型生成的音频**没有第三方权利主张**，这是它最大的价值，不是音质。

## YuE2 怎么接：直连引擎，不要碰 GUI

**结论：不要启动 `YuE2-Studio.exe`。** 它是 WebView2 外壳，从脚本启动的进程会在会话结束时被回收
（能起来，窗口和端口都正常，但几十秒后消失）。

真正的引擎是 `resources/yue2-cpp/yue-server.exe`，纯 CLI、自带 HTTP 服务，可以常驻：

```bash
cd "<YuE2>/resources/yue2-cpp"
./yue-server.exe \
  --model "<YuE2>/data/models/yue2-cpp/YuE2-3B-Q8_0.gguf" \
  --vae "<YuE2>/data/models/yue2-cpp/YuE2-Vae-F32.gguf" \
  --companion "<YuE2>/data/models/yue2-cpp/nar_lora_joint_v9.safetensors" \
  --adapters "<YuE2>/data/adapters" --device Vulkan1 --host 127.0.0.1 --port 8087
```

或让脚本代劳：`python music_gen.py --start-engine`（用 `DETACHED_PROCESS` 拉起，脚本退出后引擎继续活着）。

### 引擎的 HTTP 契约（实测）

| 端点 | 作用 |
|---|---|
| `GET /health` | `{"status":"ok"}`，就绪判断 |
| `GET /props` | 完整参数表与默认值 |
| `POST /synth` | 提交任务，返回 `{"id":"<jobId>"}` |
| `GET /job?id=<jobId>` | `{"status":"running"\|"done"}`，轮询用 |
| `GET /job?id=<jobId>&result=1` | **multipart 返回结果**，`audio/mpeg` 段就是成品 |
| `GET /logs` | SSE 进度流 |

`result=1` 是关键：`/job` 不带它只返回状态，产物不会落盘。multipart 里通常有三段
（`application/json` 元数据 / `audio/mpeg` 成品 / `application/octet-stream` 潜变量），只取第二段。

### 两个环境坑

1. **CUDA 后端当前不可用**：`--device CUDA0` 报 `not found. Available: Vulkan0 Vulkan1 CPU`，
   `cuda13/ggml-cuda.dll` 依赖不全。用 `Vulkan1`，25 秒音频约 100 秒（0.2x 实时），结果一样。
2. **适配器未下载完**：`data/adapters/yue2-instrumental/` 只有 `.part` 文件，
   传 `adapters` 会报 `unknown adapter`。`lyrics` 留空本身就是纯音乐，不挂适配器即可。

### 实测

| 曲目 | 生成耗时 | 成品 |
|---|---|---|
| 塔防 calm | 66s | 28.000s / 96kbps / 44.1kHz 单声道 / 329KB |
| 塔防 tense | 84s | 同上 |
| 模拟器 calm | 84s | 同上 |
| 模拟器 tense | 72s | 同上 |

## 规格文件

`docs/05-audio/bgm-plan.json`：

```json
{ "tracks": [
  { "id": "calm", "target": "assets/audio/bgm/stem_melody.mp3",
    "prompt": "calm strategic tower defense background music, ...",
    "lyrics": "", "durationSec": 30, "trimSec": 28 }
] }
```

**`lyrics` 必须留空。** 带歌词会生成人声，游戏 BGM 不需要，且人声在不同设备上极易刺耳。

## 两段 BGM 怎么映射到状态机

`audio.ts` 的 stem 状态机按 `audio-config.ts` 的音量表混音。不生成 5 条分轨也能做出动态：

| 曲目 | 落到哪条 stem | 状态机里的音量 |
|---|---|---|
| calm | `stem_melody` | exploration 0.35 / danger 0.25 / critical 0.2 |
| tense | `stem_rhythm` | exploration 0 / danger 0.35 / critical 0.9 |

于是切到 danger 时 calm 淡出、tense 淡入 —— **不需要改 audio.ts**。这是「用现有机制表达新需求」而不是加分支。

## 转码规范（硬要求）

YuE2 产物是 48kHz 立体声 FLAC，30 秒约 6MB。**必须转码**，否则单首曲子吃掉首包三分之一。

```
96k 单声道 MP3，取中段 28 秒
```

取中段的原因：开头常有渐入、结尾常有收束，中段最稳且能循环。

`yue2_gen.py` 已内置这段转码。

## 接入游戏（一次配好，之后不用管）

`BootScene.preload` 用 `import.meta.glob('../../../assets/audio/**/*.mp3')` 批量加载，
**键名取文件名**，与 `audio.play('<key>')` 一一对应。

```ts
const AUDIO_URLS = import.meta.glob('../../../assets/audio/**/*.mp3', {
  eager: true, query: '?url', import: 'default',
}) as Record<string, string>;
```

用 glob 而不是手写清单：加一个音效只要丢进目录，忘了登记也不会静默失效 —— 这是「素材与代码脱钩」最常见的坑（参见 `asset-registry.md` 的三级关联）。

## 音效计划

`docs/05-audio/sfx-plan.json` 定义「事件 id → 配方」，由 `gen_audio.py --spec` 合成：

```json
{ "items": [
  { "id": "gameplay_hit", "synth": { "recipe": "blip", "params": { "freq": 1200, "dur": 0.045 } } }
] }
```

配方名见 `gen_audio.py` 的 `RECIPES`：`blip` / `sweep_up` / `sweep_down` / `chime` / `arp` / `noise_burst` / `thud` / `pad_loop`，以及 `hit` / `miss` / `gold` / `bomb` / `ice` / `combo` / `levelup` / `fail`。

### 规则：音效一律程序化，不做 AI 生成

这不是「暂时如此」，是**长期规则**，理由是技术性的不是成本性的：

1. **起音时间（attack）必须精确到毫秒。** 玩家点下去的反馈如果晚 30ms 就会被感知为「不跟手」。
   生成音乐的输出长度不可控（YuE2 一次出 130 秒），裁切后起音点也不在你要的位置。
2. **音效需要「可参数化」。** 同一个 `blip` 改 `freq` 就是另一种 UI 音，改 `dur` 就是另一种手感。
   生成模型给不了这种粒度。
3. **体积。** 9 个程序化音效共 33KB；同等数量的生成音频至少 10 倍。
4. **音效是「符号」不是「音乐」。** 它只需要传达「命中了 / 失败了」，不需要氛围与变化。

所以分工是：**音效 = 程序化合成（确定、可控、极小）；BGM = YuE2 生成（氛围、变化、无版权风险）。**

## 体积预算

| 项 | 塔防实测 |
|---|---|
| 9 个 SFX | 33KB |
| 2 段 BGM（程序化兜底） | 445KB |
| 2 段 BGM（YuE2 转码后预计） | 约 680KB |
| 合计 | 0.7–1.2MB |

`asset_registry.py` 会按 `asset-spec.total_budget_kb`（默认 2000KB）检查超预算。

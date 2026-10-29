# 音频设计规范（Audio Design）

> 判据来源：`references/content-depth.md` §5（U1–U5）。
> 本文件规定**怎么设计、怎么产出、怎么接入本地工具**。

---

## 0. 为什么需要分层

v1 的问题不是"音效少"，是**所有声音都在同一个平面上**：
UI 点击、命中、得分、失败用的是同一类短促正弦音，音量相同，没有远近，没有悬念。

结果：玩家听觉疲劳极快，且无法从声音判断局势。

分层的目的：**让听觉成为第二条信息通道**。闭眼听，能知道打到第几阶段、还剩多少余量。

---

## 1. 四层结构与硬性规格

| layer | 触发 | 时长 | 起音 | 音量基准 | 混响 | 并发 | 示例 |
|---|---|---|---|---|---|---|---|
| `ui` | 按钮/菜单/切换 | 40–120ms | <20ms | −12dB | 干 | 1 | click / hover / back / confirm |
| `gameplay` | 玩法主行为 | 80–250ms | <30ms | −8dB | 微 | 3 | place / swing / jump / cast |
| `feedback` | 状态变化 | 150–600ms | <50ms | −6dB | 微 | 2 | score / combo_up / hurt / fail |
| `ambience` | 持续环境 | 循环 8–20s | 淡入 | −18dB | 大 | 1 | wind / hum / water / crowd |
| `music` | 背景乐 | 循环 30–60s | 淡入 | −14dB | 大 | 1 | calm / tense / victory |

**并发限制是性能红线**：同层超过并发上限时新声部**截断最旧的**，不要叠加（移动端 WebAudio 超过 8 个并发节点开始掉帧）。

**反馈层的方向性规则（不可违反）**：

| 语义 | 音高走向 | 音色 | 长度 |
|---|---|---|---|
| 好（得分/成功） | 上行 | 明亮（sine/tri 高次谐波） | 短 |
| 坏（受伤/失败） | 下行 | 暗（低通后的 noise/saw） | 稍长 |
| 中性（放置/切换） | 平稳 | 中频 | 极短 |

这条规则让玩家**不需要看 UI 也知道自己做得对不对**，是"手感"最便宜的一半。

---

## 2. 命名规范（`audio_forge.py` 按此生成，`gate_check` 按此校验）

```
assets/audio/sfx/<layer>_<event>[_<variant>].mp3
assets/audio/bgm/<mood>.mp3
assets/audio/voice/<speaker>_<cue>_<index>.mp3
```

示例：
```
sfx/ui_click.mp3
sfx/gameplay_place.mp3
sfx/feedback_score_up.mp3
sfx/feedback_hurt_low.mp3
bgm/calm.mp3  bgm/tense.mp3  bgm/victory.mp3
voice/keeper_lv1_start_0.mp3
```

- **只用小写 + 下划线**，无中文、无空格
- 一个事件多个变体用 `_a` `_b` `_c`（避免机械重复听觉疲劳）
- **禁止**：`sound1.mp3`、`新建音频.mp3`、`hit_final_v2.mp3`

---

## 3. 三层生产通道

### L1 程序化合成（默认，`gen_audio.py`）

适用：`ui` / `gameplay` / `feedback` 三层 + BGM 兜底。
优点：体积几十 KB、无版权风险、参数完全可控。
用法：`python scripts/gen_audio.py --project . --sfx ui_click,gameplay_place,...`

**配方库是开放的**：`gen_audio.py` 的 `SFX` 字典每项是一个 `() -> np.ndarray` 函数。
`audio_forge.py --synth` 会按 sfx-plan 的 `synth` 字段（配方名 + 参数）调用，
没有对应配方的标 `manual`，交人工或外部工具。

### L2 音乐生成（YuE2-Studio，本地 MCP）

**接入方式**：YuE2-Studio 运行时常驻 `http://127.0.0.1:8791/mcp`（streamable HTTP，218 工具）。
必须保持应用窗口进程运行，关窗即停服。

**最小调用链**：

```
song_create { style, lyrics, title, duration_seconds }
  → song_job_get { job_id }        轮询至 completed
  → library_list / library_song_get  取文件路径
```

**`style` 的写法（这是唯一需要设计的地方）**：

```
<genre> · <mood> · <instruments> · <tempo> · <texture>
```

示例（本项目实际使用）：
```
calm:    "ambient folk, gentle, solo music box and soft pad, 72 bpm, sparse, no drums"
tense:   "dark minimal techno, uneasy, low pulse and metallic ticks, 104 bpm, no melody"
victory: "uplifting orchestral pop, triumphant, brass and bells, 128 bpm, major key"
```

**硬约束（踩过的坑）**：

| 项 | 事实 | 应对 |
|---|---|---|
| 时长 | 请求 45s 实际出 33.8s（受乐谱 token 预算约束） | 按实测时长设计循环，不要假设 |
| 格式 | 48kHz **立体声 FLAC**，33s ≈ 6.2MB | **必须转码**，否则一个文件吃掉首包 1/3 |
| 内容 | 会带人声/歌词（若给了 lyrics） | BGM 层 **lyrics 留空**，否则人声会干扰游戏反馈音 |
| 结构 | 有前奏/收尾，不做无缝循环 | 必须自行裁段 + 交叉淡化 |
| 变调 | 每次生成调性不保证一致 | 固定 seed（若不支持则由 AudioContext 统一 pitch 微调） |

**转码与循环化（强制）**：

```bash
# 1) 取中段（跳过前奏尾奏），单声道 96kbps
ffmpeg -y -i in.flac -ss 2 -t 30 -ac 1 -ar 44100 -codec:a libmp3lame -b:a 96k out.mp3

# 2) 交叉淡化做无缝循环（30s 素材，首尾各 0.5s 叠加）
ffmpeg -y -i out.mp3 -filter_complex \
  "[0]atrim=0:0.5,asetpts=N/SR/TB,afade=t=out:d=0.5[a];\
   [0]atrim=29.5:30,asetpts=N/SR/TB,afade=t=in:d=0.5[b];\
   [a][b]amix=inputs=2:duration=longest" loop_head.mp3
```

体积换算：96kbps 单声道 ≈ **12KB/s** → 30s ≈ 360KB → 3 段 BGM ≈ 1.1MB。

### L3 对白（本地 TTS 2.5）

**接入方式**：HTTP 端点，配置在 `.gamedev/audio.yaml`：

```yaml
tts:
  enabled: true
  provider: local            # local | none
  endpoint: ""               # 例 http://127.0.0.1:9880/tts   ← 待 boss 确认实际端口
  method: POST
  # 请求体按 provider 实际 API 填，audio_forge 只做变量替换
  body_template: '{"text":"{text}","speaker":"{voice}","speed":1.0}'
  voices:
    narrator: "zh-female-warm"
    protagonist: "zh-male-young"
    antagonist: "zh-male-deep"
  out_format: wav            # 落地后统一转 mp3
```

**对白设计约束（防止变成 AVG）**：

- 单条 ≤2 行、≤40 字（约 3 秒音频）
- 只写**推动认知**的台词：说规则、说代价、说转折。不写寒暄
- 每条必须有 `cue`（对应关卡事件），无归属台词直接删
- 进游戏时**可跳过**，跳过不损失玩法信息

**体积**：3 秒 96kbps 单声道 ≈ 36KB。12 条 ≈ 430KB。
超预算时降级顺序：① 只配关键节点（转折/结局）② 降 64kbps ③ 全改字幕。

---

## 4. 三份产物的 schema

### 4.1 `docs/05-audio/sfx-plan.json`

```json
{
  "version": "2.0",
  "total_budget_kb": 400,
  "items": [
    {
      "id": "ui_click",
      "layer": "ui",
      "cue": "menu_any_button",
      "desc": "极短确认音，塑料感",
      "duration_ms": 60,
      "pitch_dir": "flat",
      "gain_db": -12,
      "variants": 1,
      "priority": "high",
      "synth": { "recipe": "click", "params": {} },
      "file": "assets/audio/sfx/ui_click.mp3"
    }
  ]
}
```

`synth.recipe` 与 `gen_audio.py` 的配方名对应；无对应时 `synth: null` + `"manual": "reason"`。

### 4.2 `docs/05-audio/music-plan.json`

```json
{
  "version": "2.0",
  "provider": "yue2",
  "endpoint": "http://127.0.0.1:8791/mcp",
  "items": [
    {
      "id": "calm",
      "mood": "calm",
      "when": "关卡 1-3 / 菜单",
      "style": "ambient folk, gentle, music box and soft pad, 72 bpm, sparse, no drums",
      "lyrics": "",
      "duration_seconds": 30,
      "target_file": "assets/audio/bgm/calm.mp3",
      "transcode": { "ss": 2, "t": 28, "ac": 1, "bitrate": "96k", "loop": true }
    }
  ]
}
```

**字段与 YuE2 `song_create` 入参一一对应**（`style` / `lyrics` / `title` / `duration_seconds`），
`audio_forge.py --emit-yue2` 会直接产出可喂 MCP 的调用清单 `yue2-calls.json`。

### 4.3 `docs/05-audio/voice-plan.json`

```json
{
  "version": "2.0",
  "enabled": true,
  "reason": "",
  "cover_ratio_target": 0.6,
  "items": [
    {
      "id": "v01",
      "cue": "lv1_start",
      "speaker": "narrator",
      "voice": "zh-female-warm",
      "text": "灯灭了三十年，今晚该有人点它。",
      "emotion": "calm",
      "target_file": "assets/audio/voice/keeper_lv1_start_0.mp3"
    }
  ]
}
```

`enabled: false` 时必须写 `reason`（如"纯动作游戏，无对白"），否则 U5 判 0。

---

## 5. 混音（游戏内）

| 项 | 值 | 说明 |
|---|---|---|
| 主音量 | 0.8 | 留 20% 余量给系统提示 |
| 层间关系 | ui −12 / gameplay −8 / feedback −6 / ambience −18 / music −14 (dB) | 反馈层必须最响，否则玩家听不到自己做得对不对 |
| Ducking | 对白播放时 music −6dB，200ms 内淡出/淡入 | 否则台词被盖 |
| 静音存档 | `localStorage` 记 `muted` 与两个独立滑杆（bgm / sfx） | 平台审核常查"能否单独关音乐" |
| iOS 解锁 | 首次 `pointerdown` 内 `resume()` AudioContext | 不做过审必挂 |

---

## 6. 体积预算（20MB 首包口径）

| 项 | 预算 | 换算 |
|---|---|---|
| 16–24 个音效 | ≤ 250KB | 平均 10KB/个（96kbps，<1s） |
| 2–3 段 BGM | ≤ 1.1MB | 30s × 12KB/s × 3 |
| 对白 12–20 条 | ≤ 600KB | 3s × 12KB/s × 16 |
| **音频合计** | **≤ 2MB** | 占首包 10% |

超出时按 §3 L3 的降级顺序处理，并在 `audio-plan.json` 记 `degraded: [...]`。

---

## 7. 验收清单

- [ ] `sfx-plan` 条目 ≥16 且四层齐全
- [ ] 所有 `file` 路径真实存在，且是 `.mp3`（**不能留 .wav**，`gate_check` 直接失败）
- [ ] `music-plan` ≥2 段且 `mood` 不同，每段有 `transcode` 参数
- [ ] 好/坏反馈的音高走向符合 §1 表格
- [ ] 对白覆盖 ≥60% 或有 `enabled:false` + `reason`
- [ ] 游戏内可分别静音 bgm / sfx
- [ ] iOS 首次交互已解锁 AudioContext

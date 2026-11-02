# 07b · 音频总监（Audio Director）

**目标**：从「音效播放」升级为**能表达情绪、空间与状态的动态音频系统**。
**上游**：`creative-dna.audio` + `docs/05-audio/sfx-plan.json`。**下游**：模板 `src/game/audio.ts`。

## 为什么需要这一步

v2 的 `audio_forge` 产出 plan、`gen_audio` 产出 mp3，然后**没有了** —— 模板里没有任何播放层。
分层的意义（ui/gameplay/feedback/ambience）在运行时不存在，四个层只是四个文件夹。
**自适应音乐、动态混音、并发控制、距离衰减全都无从谈起。**

## 1. 自适应音乐：stem 分轨

```bash
python scripts/audio_director.py --project . --plan    # → audio-dna.json
python scripts/audio_director.py --project . --emit     # → stem-render-plan.json
```

**核心思路**：所有状态共用同一组 stem（melody / rhythm / bass / percussion / atmosphere），
切换状态**只改各轨音量**，不换曲 —— 所以切换点听不出接缝。

| 状态 | 典型配比变化 |
|---|---|
| exploration | melody 0.35 / rhythm 0 / bass 0.2 / percussion 0 / atmosphere 0.5 |
| danger | melody 0.25 / rhythm 0.35 / bass 0.7 / percussion 0.1 / atmosphere 0.4 |
| critical | melody 0.2 / rhythm 0.9 / bass 0.85 / percussion 0.5 / atmosphere 0.15 |
| victory | melody 0.85 / rhythm 0.4 / bass 0.5 / percussion 0.55 / atmosphere 0.3 |

**判据：任意两个状态的分轨配比必须不同。** 相同 = 切换听不出区别 = 自适应是假的（gate 会拦）。

### 通道与降级

| 通道 | 能力 | 说明 |
|---|---|---|
| YuE2-Studio（MCP） | 逐轨生成 | 需要窗口运行；产物 48kHz 立体声 FLAC，必须转码 |
| **`gen_stems.py`（程序化）** | 5 条 stem 一次合成 | 无外部依赖，**始终可用**，是本作的降级方案 |

```bash
python scripts/gen_stems.py --project . --seconds 20 --bpm 68 --root 45
```

用 numpy 合成同调同速的 5 条 loop，尾部与头部交叉淡化保证无缝循环，输出 96kbps 单声道 MP3。
**没有音乐生成服务时这是唯一能真正跑通 stem 方案的路。**

## 2. 动态音效

`audio-dna.sfx` 定义运行时规则（`audio.ts` 执行）：

| 规则 | 默认 | 解决什么 |
|---|---|---|
| `variants` | 3 | 同类音效多变体，避免机关枪 |
| `pitch_jitter_semitones` | 1.5 | 变体靠音高抖动 |
| `min_interval_ms` | 60 | 全局最小间隔（防同帧一堆事件） |
| `same_sound_cooldown_ms` | 90 | 同名冷却 |
| `max_concurrent` | 12 | 并发上限 |
| `max_concurrent_per_sound` | 3 | 单音上限 |
| `distance` | ref 400 / rolloff 1.2 | 世界空间音效按距离衰减 |

优先级：`high`（胜负/受击）永不被并发上限挤掉，且会触发 **ducking**（旋律与氛围压低 6dB 让反馈浮出来）。

## 3. 情绪化声音设计

`emotional_rules` 是**状态驱动**的，不是氛围词：

- 玩家资源 ≤20%：环境声 -70%，加入 60→110bpm 心跳，低频 +6dB
- 进入安全区：心跳 2 秒内淡出，环境声恢复，音乐降 3dB
- 叙事揭示：全部 stem 静音 0.3 秒，只留一个 bell，再整体淡入

## 4. 声音即玩法

`gameplay_hooks` 声明「哪个事件由声音承担机制职责」，**每条必须有 `visual_fallback`** ——
静音玩家与听障玩家必须也能通关。这不是建议，gate 会拦。

例：回声定位（声音给方位与距离）+ 屏幕边缘方向指示条（视觉替代）。

## 5. 音频质检（真实测量，不是声明）

```bash
python scripts/audio_director.py --project . --qc
```

用 ffmpeg 解码成 wav，再逐项测量：

| 项 | 阈值 | 判据 |
|---|---|---|
| 文件存在 | — | 缺失即 FAIL |
| 采样率 | ≥22050 | 过低告警 |
| 声道 | 单声道 | 立体声告警（体积） |
| 削波 | 峰值 <0.999 | 削波即 FAIL |
| 异常静音 | RMS ≥0.002 | 静音即 FAIL |
| 循环接缝 | 首尾 50ms RMS 差 ≤0.08 | 超阈告警 |
| 总体积 | ≤2MB | 超预算告警 |

产出 `docs/05-audio/audio-qc.json`。**没有实测数据，音频审核判 UNVERIFIED，不算通过。**

## 6. 调试模式

`audio.ts` 的 `debugLines()` 返回：当前音乐状态、各 stem 实时音量、活跃声道数 / 并发上限、
ducking 是否开启、最近一个事件、是否静音。开发时挂在画面角落即可。

## 自检

- [ ] `music.states` ≥2 且配比互不相同
- [ ] 至少一个状态让某条 stem 为 0（真分层，不是整体调音量）
- [ ] `emotional_rules` ≥2 条，每条有 `when` + `change`
- [ ] `gameplay_hooks` 每条都有 `visual_fallback`
- [ ] `--qc` 的 verdict 不是 FAIL
- [ ] 源码里 `new AudioDirector` + `setState(` 真实存在
- [ ] 降级（无外部音乐通道）已在 `meta.degraded` 如实标注

# 模块 07 · 配乐与音效（audio forge）

**阶段**：P2 ｜ **前置**：G2 通过 ｜ **产出**：`assets/audio/bgm/`、`assets/audio/sfx/` ｜ 可与 04、05→06 并行

## 目标

产出与游戏氛围匹配的 BGM 与音效，并控制体积。

**体积预算**：音频总体积 ≤ 2MB（首包 ≤20MB 的硬门槛下，音频是容易失控的一项）。

## 步骤

### 0. 先生成音频方案（**v2 新增，必做**）

v1 的「音效 ≤5、BGM ≤1」已被丰富度门禁取代：**≥16 个音效且四层覆盖，BGM 2–3 段情绪互异**。
所以先让 `audio_forge.py` 出一份分层方案，再谈生产。

```bash
# 蓝图 → sfx-plan / music-plan / voice-plan（三层）
python <skill>/scripts/audio_forge.py --project <project> --plan

# 探测三个通道（L1 合成 / L2 YuE2-Studio / L3 TTS）
python <skill>/scripts/audio_forge.py --project <project> --probe

# L1：程序化合成全部可自动的音效 + BGM 兜底
python <skill>/scripts/audio_forge.py --project <project> --synth

# L2：出 YuE2 MCP 调用清单（song_create 参数 + ffmpeg 转码命令）
python <skill>/scripts/audio_forge.py --project <project> --emit-yue2

# L3：出 TTS 请求清单
python <skill>/scripts/audio_forge.py --project <project> --emit-tts
```

**分层规格与硬约束见 `references/audio-design.md`**，三条最容易忘的：

1. **反馈层必须有方向性** —— 好事上行、坏事下行。玩家不看 UI 也知道自己做对没。
2. **YuE2 产物必须转码** —— 48kHz 立体声 FLAC 33s ≈ 6.2MB，直接进包会吃掉首包 1/3。
   按 `yue2-calls.json` 里的 `ffmpeg` 字段转 96kbps 单声道。
3. **BGM 的 lyrics 必须留空** —— 有人声会盖住反馈音，玩家听不出命中。

### 1. 确定音频需求

从 `docs/05-audio/sfx-plan.json` 读取（不再是 `scope.json`）。四层结构：

| layer | 触发 | 时长 | 音量 | 数量 |
|---|---|---|---|---|
| `ui` | 按钮/菜单 | 40–120ms | −12dB | ≥4 |
| `gameplay` | 玩法主行为 | 80–250ms | −8dB | ≥4 |
| `feedback` | 状态变化 | 150–600ms | −6dB | ≥6（含 stinger） |
| `ambience` | 持续环境 | 循环 8–20s | −18dB | ≥1 |

总量控制：**音效 ≥16 个 / 合计 ≤400KB，BGM 2–3 段 / 合计 ≤1.2MB**。

### 2. 确定音乐氛围

从 `docs/02-art/palette.json` 的 `mood` 字段派生音乐描述，例如：

```
playful, warm, light percussion, major key, loopable, 110 BPM
```

氛围必须与美术风格一致，不要出现「暖色卡通美术 + 黑暗电子乐」的错配。

### 3. 生成

- BGM：用音乐生成能力产出可无缝循环的器乐，**不要人声**
- SFX：短促、辨识度高；可用程序化合成（Web Audio）作为补充或降级手段

### 4. 压缩与格式

| 类型 | 格式 | 码率建议 |
|---|---|---|
| BGM | `.ogg`（优先）/ `.mp3` | 96–128 kbps |
| SFX | `.ogg` / `.mp3` | 64–96 kbps |

**不要**用 wav 交付（体积过大）。

### 5. 循环点校验

BGM 必须能无缝循环：首尾相接不爆音、无明显节拍断裂。若生成结果不支持无缝循环，用淡入淡出（各 50ms）处理。

### 6. iOS 音频恢复（必做）

iOS 会在切后台后把 AudioContext 置为 `interrupted`。**必须在用户手势回调内恢复**：

```ts
document.addEventListener('touchend', () => {
  const ctx = (this.sound as Phaser.Sound.WebAudioSoundManager).context;
  if (ctx && ctx.state === 'suspended') ctx.resume();
});
```

只监听 `visibilitychange` **无效**。

### 7. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage audio_forge
```

## 自检

- [ ] BGM 1 条，音效 ≤5 个
- [ ] BGM 可无缝循环
- [ ] 音频总体积 ≤2MB
- [ ] 全部为 ogg/mp3，无 wav
- [ ] 音乐氛围与美术风格一致
- [ ] iOS 音频恢复逻辑已实现
- [ ] 广告播放期间音频会暂停（适配层负责）

## 降级

音乐生成不可用时：用 Web Audio API 程序化合成音效（方波/三角波 + 包络），跳过 BGM。标记 `audio_forge: degraded`，游戏仍必须可玩。

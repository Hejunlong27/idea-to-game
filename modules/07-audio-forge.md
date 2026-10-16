# 模块 07 · 配乐与音效（audio forge）

**阶段**：P2 ｜ **前置**：G2 通过 ｜ **产出**：`assets/audio/bgm/`、`assets/audio/sfx/` ｜ 可与 04、05→06 并行

## 目标

产出与游戏氛围匹配的 BGM 与音效，并控制体积。

**体积预算**：音频总体积 ≤ 2MB（首包 ≤20MB 的硬门槛下，音频是容易失控的一项）。

## 步骤

### 1. 确定音频需求

从 `docs/01-brief/scope.json` 的 `assets` 字段读取清单。按超休闲游戏的惯例：

| 类型 | 数量 | 时长 | 用途 |
|---|---|---|---|
| BGM | 1 | 30–60s 可循环 | 主玩法背景 |
| SFX · 成功 | 1 | <0.5s | 合成 / 得分 |
| SFX · 交互 | 1 | <0.3s | 点击 / 放置 |
| SFX · 失败 | 1 | <1s | 游戏结束 |
| SFX · 其它 | ≤2 | <0.5s | 连击 / 升级等 |

总量控制：**音效 ≤5 个，BGM ≤1 条**（见 `references/genre-playbook.md`）。

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

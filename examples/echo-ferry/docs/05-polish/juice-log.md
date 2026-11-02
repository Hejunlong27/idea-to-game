# 手感与表现日志（Juice Log）· 回声摆渡

> 记录「哪个事件 → 用了哪些效果 → 为什么是这个强度」。
> 真相源是 `docs/04-core-loop/juice-plan.json`，本文只解释设计意图。

## 分级原则

| 档位 | 严重度 | 效果预算 | 本作对应事件 |
|---|---|---|---|
| micro | 0–0.3 | 1–2 个，无镜头无闪屏 | `player_move`、`memory_spent`、`item_collected` |
| light | 0.3–0.55 | 2–3 个，可轻微震动 | `enemy_spawn`、`game_start`、`state_changed` |
| medium | 0.55–0.8 | 3–4 个，可 hit stop | `player_hit`、`echo_ping`、`soul_delivered` |
| heavy | 0.8–1.0 | 5–6 个，可闪屏 + 慢动作 | `player_death`、`memory_empty`、`level_completed` |

## 几个刻意的决定

### 1. 敲钟不用震动

`echo_ping` 用「水纹扩散 + 10 个粒子 + 60ms hit stop」，**没有 camera_shake**。
原因：震动在本作的语义是「被抓住」。敲钟是玩家主动获取信息的动作，
如果它震屏，玩家会把「主动」误读成「挨打」，机制的信息就传错了。

### 2. 记忆归零用「暗」而不是「闪」

`memory_empty` 是本作的标志性时刻。所有方案里最容易的做法是全屏闪白 —— 但这里需要的是**暗**。
所以用：慢动作 500ms + hit stop 180ms + 轻微推近 + 20 个粒子 + 环境动画拉满。
画面在 600ms 内把所有残影的 alpha 归零，配合音频切到 critical（心跳 110bpm、环境声 -70%）。

### 3. 正向事件与受击事件的语义严格分开

| 语义 | 用的效果 | 不用的效果 |
|---|---|---|
| 受击/威胁 | 震动、红色闪屏、粒子（危险色） | 推近、UI 弹入 |
| 奖励/完成 | 推近、粒子（强调色）、UI 弹入 | 震动 |

`soul_delivered` 与 `player_hit` 的严重度相近（0.8 / 0.75），但效果集完全不重叠。

### 4. 移动是最频繁的事件

`player_move` 只做 0.35 强度的形变 + 环境水纹。任何镜头效果在这里都会变成噪声
（玩家每秒可能移动 2 次）。

## 硬上限（不可配置放宽）

| 项 | 值 | 原因 |
|---|---|---|
| 闪屏频率 | ≤1 次/秒 | 光敏性癫痫 |
| 震动时长 | ≤300ms | 晕动 |
| hit stop | ≤140ms | 超过会打断节奏 |
| 同屏粒子 | ≤120（低端设备 60） | 帧率 |

## 无障碍

- `prefers-reduced-motion: reduce` 时：关闭震动、闪屏、推近、慢动作；保留形变与粒子（减半）
- 敲钟的回声同时给出**视觉**水纹与**音频**三连回声 —— 静音玩家与听障玩家都能获得信息
- 文字全部由 Phaser Text 渲染，可被系统字体缩放影响，不画进素材

## 与代码的对应

| 配置项 | 文件 |
|---|---|
| 规则与强度 | `src/game/juice-config.ts`（由 `juice_forge.py --emit-ts` 生成） |
| 效果实现 | `src/game/juice.ts` |
| 事件源 | `src/game/scenes/PlayScene.ts`（只 emit，不做表现） |

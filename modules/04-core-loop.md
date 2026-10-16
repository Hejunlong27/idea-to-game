# 模块 04 · 玩法主循环（core loop）

**阶段**：P2 ｜ **前置**：G2 通过 ｜ **产出**：`src/game/`、`docs/04-core-loop/notes.md` ｜ 可与 05→06、07 并行

## 目标

**用几何占位素材**把玩法跑通并自测可玩。此环节的验收标准是「好玩与否」，不是「好看与否」。

> ★ 这是全流程的成本控制点。玩法不成立就投入生图成本，是最大的浪费。

## 步骤

### 1. 设计状态机

在 `docs/04-core-loop/notes.md` 中先写清状态与迁移：

```
Boot → Ready → Playing → Paused → GameOver → (Restart) Ready
```

每个状态的进入/退出动作、允许的输入、可用的 UI。

### 2. 实现主循环

按 `docs/01-brief/gdd.md` 实现：

- 输入处理（拖拽 / 点击 / 滑动 / 键盘，与 `scope.json` 的 `controls` 一致）
- 核心玩法机制（合成 / 生成 / 碰撞 / 移动）
- 计分与进度
- 失败判定与结束
- 重开

**约束**：
- 禁止 import 任何平台 SDK
- 素材一律用 `Phaser.GameObjects.Rectangle` / `Circle` / 文本标签等**几何占位**，不引用 `assets/`
- 所有数值（速度、尺寸、生成概率、难度参数）抽到 `src/game/config.ts`，便于 P3 调参

### 3. 接入适配层

- 进入可玩状态时调用 `platform.gameplayStart()`
- 离开可玩状态（暂停/结束）时调用 `platform.gameplayStop()`
- 最高分通过 `platform.save()` / `load()` 持久化

### 4. 自测（关键）

在浏览器中实际玩一遍，逐条确认：

- [ ] 完整闭环可跑通：开始 → 游玩 → 结束 → 重开
- [ ] 计分随玩法正确变化
- [ ] 无卡死状态，任何状态都能回到 Ready
- [ ] 首个 10 秒内有明确的正反馈
- [ ] 失败后 2 秒内可重开
- [ ] 控制台零报错
- [ ] **自己觉得好玩**（若不好玩，就地改玩法，不要往下走）

### 5. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage core_loop
```

通过后写 `state.yaml` 的 `core_loop.self_test: playable`。

## 自检

- [ ] 状态机无死状态
- [ ] 数值全部抽到 `config.ts`
- [ ] `src/game/` 无平台 SDK 引用
- [ ] 素材全为几何占位
- [ ] 自测通过并记录 `self_test: playable`

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 边做玩法边接正式素材 | 玩法改了素材就废 | 严格用占位素材 |
| 数值写死在代码里 | P3 无法调参 | 抽到 `config.ts` |
| 玩法不好玩但硬着头皮往下 | 最终游戏没人玩 | 就地改，最多重试 3 次 |

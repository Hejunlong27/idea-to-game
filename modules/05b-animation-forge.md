# 05b · 动画与表现力（Animation Director）

**目标**：让游戏不再只是静态图片的组合。
**上游**：`docs/01-brief/creative-dna.json` + `docs/02-art/visual-dna.json`。
**下游**：模板 `src/game/juice.ts`（运行时）。

## 为什么需要这一步

v2 把 `cameras.main.shake()` 写死在 `PlayScene.hitTarget()` 里：换玩法要重写一遍手感，
而且所有事件共用同一组参数 —— 玩家分不清轻重。任务书要求的 14 类效果，v2 实际只有 shake 一种。

## 14 类效果

| 效果 | 作用 | 性能 | 无障碍 |
|---|---|---|---|
| `squash_stretch` | 受击/落地形变 | 极低 | 无影响 |
| `anticipation` | 动作前反向蓄力 | 极低 | 可关 |
| `follow_through` | 附属物延迟回位 | 低 | 无影响 |
| `secondary_motion` | 装饰元素持续微动 | 中（对象数） | 低端降 1/3 |
| `parallax` | 多层背景不同速率 | 低 | reduced-motion 时固定 |
| `particles` | 事件位置爆发 | 中高 | 低端减半 |
| `environmental` | 背景随状态变化 | 低 | 无影响 |
| `ui_motion` | 数值/条状/按钮 | 低 | 无影响 |
| `camera_shake` | 短时抖动 | 低 | **必须可关** |
| `camera_zoom` | 强调推近 | 低 | 可关 |
| `hit_stop` | 命中冻结 40–140ms | 低 | 可关 |
| `slow_motion` | 关键帧减速 | 低 | 可关 |
| `screen_flash` | 全屏色闪 | 低 | **≤1 次/秒（硬上限）** |
| `transition` | 场景切换遮盖 | 低 | 可关 |

## 步骤

### 1. 出表现矩阵

```bash
python scripts/juice_forge.py --project . --plan
```

按事件严重度分档，**不是所有事件同一套效果**：

| 档位 | 严重度 | 效果预算 |
|---|---|---|
| micro | 0–0.3 | 1–2 个，无镜头无闪屏 |
| light | 0.3–0.55 | 2–3 个，可轻微震动 |
| medium | 0.55–0.8 | 3–4 个，可 hit stop / zoom |
| heavy | 0.8–1.0 | 5–6 个，可闪屏 + 慢动作 |

产出 `docs/04-core-loop/juice-plan.json`，每条规则带 `why`（为什么是这个强度）。

### 2. 生成运行时配置

```bash
python scripts/juice_forge.py --project . --emit-ts
```

写入 `src/game/juice-config.ts`。改设计 → 重跑 → 运行时行为随之改变，不需要改代码。

### 3. 接入场景

```ts
const bus = new EventBus(() => this.time.now, this.time.now);
const juice = new JuiceDirector(this, bus);
juice.setTargetResolver(() => 当前事件对应的对象);
juice.attach();                       // 订阅全部事件
// update(dt) 里：juice.update(delta)
// SHUTDOWN 里：juice.destroy()
```

**玩法只 emit 事件，不直接调 shake / 粒子。**

### 4. 校验

```bash
python scripts/juice_forge.py --project . --validate --strict
```

会查：schema、是否所有事件同一套效果、闪屏是否用于 <0.7 的事件、关键事件是否被覆盖、
效果类型是否 ≥8 类、闪屏 ≤1/s 与震动 ≤300ms 的硬上限。

## 三条硬规则

1. **动画不得影响玩法确定性**：`hit_stop` / `slow_motion` 只缩放 `tweens.timeScale`，
   **不碰** `update()` 的逻辑步长。审核会扫描 `time.timeScale`，出现即 FAIL。
2. **强度必须分级**：正向事件（奖励/完成）不用震动，负向事件（受击/威胁）不用推近 —— 语义不能混。
3. **清理**：场景 SHUTDOWN 时 `destroy()`，否则监听器与音频对象跨场景泄漏。

## 自检

- [ ] 效果类型 ≥8 类（只靠 shake + 粒子 + 形变等于没升级）
- [ ] 每个 tier 都有事件，且 heavy 事件有 hit_stop 或 zoom
- [ ] 闪屏只用于 ≥0.7 的事件
- [ ] 源码里 `new JuiceDirector` + `juice.update` 真实存在
- [ ] `prefers-reduced-motion` 分支存在
- [ ] SHUTDOWN 里有 `destroy()`

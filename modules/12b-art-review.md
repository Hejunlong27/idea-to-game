# 12b · 专项审核（Specialist Review）

**目标**：在「能不能上架」（A–H 八维）之外，再判「值不值得上架」。
**执行者**：审核官。**铁律**：只审不写、必须给证据、不许虚报。

## 与 `12-review.md` 的分工

| 审核 | 判据 | 问题 |
|---|---|---|
| `review_gate.py`（A–H） | `references/crazygames-standard.md` | 能上架吗？（合规、技术、可玩性） |
| `specialist_review.py`（六项） | 本文件 + 各 DNA schema | 值得上架吗？（创意、视觉身份、声音身份、表现、体验） |

两者**都是一票否决**。R2 与 ship 会同时校验。

## 六项审核

### 1. 创意审核（6 条）

| 项 | 判据 |
|---|---|
| C1 | ≥5 个方案，最小两两结构距离 ≥3（防换皮） |
| C2 | Creative DNA 通过 schema |
| C3 | 独特机制满足 6 条：一句话/非数值/互动≥2/改变策略/标志时刻/独特性论证 |
| C4 | 启发式相似度不是 HIGH（否则必须重设计核心机制） |
| C5 | 叙事与机制真实耦合（`narrative_mechanic_link` 非空且 ≥12 字） |
| C6 | 每条模式引用都有 `source` + `license` |

### 2. 美术审核（6 条）

| 项 | 判据 | 证据来源 |
|---|---|---|
| A1 | Visual DNA 通过 schema | 文件 |
| A2 | 色彩对比度全达标 | `color.contrast_checks` |
| A3 | **实机截图的主色相与 DNA 距离 ≤25°** | 真读 PNG 像素，算色相直方图 |
| A4 | 一致性状态不虚报（`full_ref_chain` 时参考图必须存在） | 文件存在性 |
| A5 | 文字由 Text 渲染（不画进素材） | 源码正则 |
| A6 | 场景叙事 ≥2 条 | `scene_narrative` |

**A3 是本审核的关键**：不看你「声明」用了什么色，而是量你**实际画面**的主色相
离 DNA 色板有多远。这是「文档自评」和「真实审核」的分界线。

### 3. 动画与表现审核（8 条）

| 项 | 判据 |
|---|---|
| N1 | 表现矩阵通过 schema |
| N2 | 效果类型 ≥8 类 |
| N3 | ≥3 种不同效果组合（不是所有事件同一套） |
| N4 | 闪屏 ≤1/s、震动 ≤300ms |
| N5 | 源码里真实 `new JuiceDirector` 且每帧 `update` |
| N6 | `prefers-reduced-motion` 分支存在 |
| N7 | SHUTDOWN 里有 `destroy()` |
| N8 | **没有改写 `time.timeScale`**（会破坏玩法确定性） |

### 4. 音频审核（6 条）

| 项 | 判据 |
|---|---|
| U1 | Audio DNA 通过 schema |
| U2 | 音乐状态配比互不相同（否则自适应是假的） |
| U3 | **实测波形**：无缺失/削波/静音，接缝不超阈 |
| U4 | 源码里真实 `new AudioDirector` 且调用 `setState` |
| U5 | 声音承担玩法职责时有 `visual_fallback` |
| U6 | 体积在预算内 |

### 5. 体验审核（5 条）

| 项 | 判据 |
|---|---|
| E1 | 体验蓝图通过 schema |
| E2 | E1–E8 全验证（UNVERIFIED 不算通过） |
| E3 | 曲线峰值在 climax |
| E4 | 每关都有取舍决策 |
| E5 | 标志时刻绑定真实事件 |

### 6. 试玩审核（7 条）

| 项 | 判据 |
|---|---|
| P1 | ≥3 种策略跑过 |
| P2 | 零运行时错误 |
| P3 | 无卡死 |
| P4 | 首次正反馈 ≤30s |
| P5 | 重复率 <70% |
| P6 | ≥2 张截图 |
| P7 | 报告里有「AI 试玩 ≠ 真人测试」声明 |

## 判定

| 结论 | 条件 | 能否交付 |
|---|---|---|
| `PASS` | 全部 PASS | ✅ |
| `FAIL` | 任一 FAIL | ❌ 硬阻断 |
| `INCOMPLETE` | 无 FAIL 但有 UNVERIFIED | ❌ **未验证不算通过** |

## 运行

```bash
python scripts/specialist_review.py --project .            # 六项全跑
python scripts/specialist_review.py --project . --only art # 只跑一项
python scripts/specialist_review.py --project . --strict   # 非 PASS 时返回 2
```

产物：
- `docs/09-review/specialist-{creative,art,animation,audio,experience,playtest}.json`
- `docs/09-review/specialist-report.md`
- `docs/09-review/verdict-specialist.json`（`gate_check` 读它做阻断）

## 审核官不得做的事

- ❌ 修改 `src/`、`assets/`、`docs/00–08`
- ❌ 把缺产物写成 PASS
- ❌ 用「美术风格很好」「音乐很有沉浸感」这类空话代替证据
- ❌ 只测修过的条目（复审必须全量重跑）

## 证据长什么样

| 不合格 | 合格 |
|---|---|
| 美术风格统一 | 6 张截图主色相与 DNA 距离 8°/12°/15°/9°/11°/14°（阈值 25°） |
| 音频正常 | 27 个文件：缺失 0、削波 0、静音 0、接缝可疑 0；总 1455KB/2048KB |
| 动画很流畅 | 21 条规则产生 9 类效果、14 种不同组合；闪屏上限 1/s，震动上限 300ms |
| 体验不错 | E1–E8 全 PASS：首次正反馈 4.1s、重复率 13%、无卡死 |

# 模块 01 · 立项（brief）

**阶段**：P0 ｜ **前置**：**门禁 G0 通过（`delivery.platform_confirmed: true`）** ｜ **产出**：`docs/01-brief/gdd.md`、`docs/01-brief/scope.json` ｜ **后置门禁**：G1

## 前置检查（不满足则退回）

- [ ] `docs/00-platforms/platform-plan.md` 存在
- [ ] `state.yaml` 的 `delivery.platforms` 非空且 `platform_confirmed: true`

**不满足时不要继续** —— 回到 `modules/00-platforms.md`，先向用户确认目标平台。

## 目标

把一句 idea（或一款同款游戏名）变成可执行的立项文档，并**主动收窄范围**。

## 步骤

### 1. 解析输入

- **若输入是想法描述**：直接结构化
- **若输入是同款游戏名**：联网检索该游戏的玩法机制、操作方式、核心循环。只借鉴机制，不复制美术与品牌

### 2. 映射品类

读 `references/genre-playbook.md`，把 idea 映射到超休闲品类（合成 / 点击放置 / 跑酷 / 躲避 / 物理益智 / 轻塔防）。

若 idea 无法映射到任一品类的可做范围，明确告知用户并给出最近的可行替代。

### 3. 写 GDD

按 `references/genre-playbook.md` 的「品类拆解模板」写 `docs/01-brief/gdd.md`，至少覆盖：

- 一句话玩法
- 核心循环
- 操作方式与是否单手可玩
- 单局时长目标
- 失败条件
- 计分规则
- 难度曲线
- 首个 10 秒体验
- 屏幕方向（portrait / landscape）
- 与参考游戏的差异点（若来自同款游戏名）

### 3b. 写内容蓝图（**v2 新增，必做，不可跳过**）

GDD 只写玩法，**内容和深度写在另一份文件里**：`docs/01-brief/content-blueprint.json`。

```bash
# 1) 先分析：推断品类 / 推荐叙事框架 / 匹配机制候选 / 列素材角色需求
python <skill>/scripts/content_forge.py --idea "<一句话想法>" --analyze

# 2) 生成骨架（带 _todo 与数量要求）
python <skill>/scripts/content_forge.py --project <project> --scaffold

# 3) 按 docs/01-brief/story.md 与蓝图里的 _todo 逐项填写（这一步是创作，脚本不代劳）
#    —— 世界观 3 条规则、主角 want/need/flaw/arc、三幕、每关 decision、≥12 条对白…

# 4) 校验槽位
python <skill>/scripts/content_forge.py --project <project> --validate
```

**蓝图必须覆盖四块**（判据见 `references/content-depth.md`）：

| 块 | 必填 | 常见错误 |
|---|---|---|
| `world` | logline ≥16 字、3 条**约束型**世界规则 | 规则写成形容词（"这里很神秘"），不是约束 |
| `story` | 主角四要素（want≠need）、三幕 have turn、≥12 条对白（带 cue） | 有对白但没有触发点，游戏里没地方播 |
| `mechanics` | 机制 ≥5 个且每个 `interacts` 引用真实 id | 机制堆量但互不相干（加法而非乘法） |
| `levels` | 每关 `decision` 能写成「A好但B坏」 | 写成"躲开障碍"（没有取舍） |

参考 `references/mechanic-vocab.md` 的"一主两副"原则与五条非数值难度轴。

### 4. 写 scope.json

按 `references/contracts.md` 的 schema 写 `docs/01-brief/scope.json`，必须包含 `mvp_features`、`out_of_scope`、`assets`（生图与配乐环节的输入清单）。

**范围控制硬约束**（v2 修订 —— 原「音效 ≤5、BGM ≤1」已被丰富度门禁取代）：

| 项 | v1 上限 | **v2 要求** | 理由 |
|---|---|---|---|
| MVP 功能 | ≤5 | ≤6 | 每个功能应对应一个机制，机制合计 ≥5 |
| 素材数量 | ≤30 | ≤40，且 processed 后 ≤2.5MB | 需要覆盖 6 类 role（角色/道具/地块/背景/UI/特效） |
| 音效 | ≤5 | **≥16**，四层覆盖，合计 ≤400KB | 分层是"听出局势"的前提（content-depth U1/U2） |
| BGM | ≤1 | **2–3 段**，情绪互异，合计 ≤1.2MB | 无段落推进 = 全程同一听觉平面 |

体积红线不变（取最严平台），只是把"数量上限"换成"数量下限 + 体积上限"。
理由：v1 的限制是为省体积，但真正撑大体积的是分辨率不是数量（96kbps 音效 10KB/个）。

### 5. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage brief
python <skill>/scripts/gate_check.py --project <project> --stage content
```

### 5b. 丰富度门禁 RC（**v2 新增**）

```bash
python <skill>/scripts/richness_check.py --project <project> --stage design
```

结论 `RICH` 才能进入 P1 写代码；`THIN` 必须回 P0 补内容。
**这是设计期最强的一道闸**：写完代码再补故事等于重做。

### 6. 门禁 G1（必须人工）

向用户汇报，明确询问：

1. 核心玩法是否认可？
2. 范围边界（MVP 清单 + 不做清单）是否同意？
3. 有无要加/要砍的功能？

**得到明确确认后**才写入 `state.yaml` 的 `gate: G1_passed`。

## 自检

- [ ] G0 已通过（`delivery.platform_confirmed: true`）
- [ ] GDD 八个必答问题全部有答案
- [ ] `scope.json` 的 `assets` 清单能覆盖玩法所需（无遗漏、无冗余）
- [ ] MVP 功能数 ≤5
- [ ] `out_of_scope` 非空（说明确实做了取舍）
- [ ] GDD 中记录了**用户选定的平台**，且玩法的屏幕方向与平台要求相容
- [ ] 已获用户明确确认

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| **跳过 G0 直接立项** | 交付包范围与用户预期不符，返工 | 必须先确认平台 |
| 范围过大（做了 8 个功能） | 做不完或质量差 | 砍到 ≤5 项 |
| 素材清单漏项 | P2 生图后才发现缺素材，返工 | 逐条对照玩法推演所需素材 |
| 未做差异化（同款游戏） | IP 风险；GD 会因同款拒收 | 至少一处机制或美术上的差异 |
| 跳过 G1 直接开工 | 方向错了全白干 | 必须停下来问 |

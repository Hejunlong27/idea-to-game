# 模块 01 · 立项（brief）

**阶段**：P0 ｜ **前置**：无 ｜ **产出**：`docs/01-brief/gdd.md`、`docs/01-brief/scope.json` ｜ **后置门禁**：G1

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

### 4. 写 scope.json

按 `references/contracts.md` 的 schema 写 `docs/01-brief/scope.json`，必须包含 `mvp_features`、`out_of_scope`、`assets`（生图与配乐环节的输入清单）。

**范围控制硬约束**（见 `references/genre-playbook.md`）：MVP 功能 ≤5 项、素材 ≤30 个、音效 ≤5 个、BGM ≤1 条。

### 5. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage brief
```

### 6. 门禁 G1（必须人工）

向用户汇报，明确询问：

1. 核心玩法是否认可？
2. 范围边界（MVP 清单 + 不做清单）是否同意？
3. 有无要加/要砍的功能？

**得到明确确认后**才写入 `state.yaml` 的 `gate: G1_passed`。

## 自检

- [ ] GDD 八个必答问题全部有答案
- [ ] `scope.json` 的 `assets` 清单能覆盖玩法所需（无遗漏、无冗余）
- [ ] MVP 功能数 ≤5
- [ ] `out_of_scope` 非空（说明确实做了取舍）
- [ ] 已获用户明确确认

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 范围过大（做了 8 个功能） | 做不完或质量差 | 砍到 ≤5 项 |
| 素材清单漏项 | P2 生图后才发现缺素材，返工 | 逐条对照玩法推演所需素材 |
| 未做差异化（同款游戏） | IP 风险 | 至少一处机制或美术上的差异 |
| 跳过 G1 直接开工 | 方向错了全白干 | 必须停下来问 |

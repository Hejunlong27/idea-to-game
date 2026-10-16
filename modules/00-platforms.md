# 模块 00 · 平台确认（platforms）

**阶段**：P-1 ｜ **前置**：收到用户第一个指令 ｜ **产出**：`state.yaml` 的 `delivery.platforms`、`docs/00-platforms/platform-plan.md` ｜ **后置门禁**：G0

## 目标

**这是整个流程的第一个动作。** 在开始任何立项、编码、生图工作之前，先让用户确定要发到哪些平台。

**原因**：平台选择会同时决定五件事 —— 体积红线、SDK 接入方式、合规前置条件、商店素材规格、投递顺序。定晚了就是返工。

---

## 步骤 1 · 主动告知支持范围

收到用户第一个指令后，**先输出下面这张表**，让用户知道可以选什么。不要等用户来问。

| 平台 key | 名称 | 区域 | 形态 | 体积红线（首包） | 额外前置条件 |
|---|---|---|---|---|---|
| `crazygames` | CrazyGames | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 无（Basic Launch 自助提交） |
| `poki` | Poki | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 提报制：需可玩链接 + 3 张实机截图 |
| `gamedistribution` | GameDistribution | 海外 | 分发聚合（3000+ 发布商） | ≤50MB | SDK 强制；审核最长 3 周；不收同款 |
| `playgama` | Playgama | 海外 | 分发网络（25+ 平台） | ≤50MB | 需自行接入 Bridge SDK |
| `taptap` | TapTap | 国内 | 网页游戏 H5 / Tap 小游戏 | **≤60MB**（优秀 ≤20MB） | **Tap 小游戏需前置备案**；广告位需在 Dirichlet 创建 |

同时说明：
- 支持**多选**，也支持后续追加
- 一份代码可同时出多平台包（不改玩法代码）
- **国内平台（tapTap）与海外平台的投递节奏不同**，国内需预留备案周期

---

## 步骤 2 · 询问用户

必须明确提问，例如：

> 你准备把这些游戏发到哪些平台？可从上面表格里选（支持多选）。
> - 只发海外 → 建议先选 `crazygames`
> - 只发国内 → 建议先选 `taptap`
> - 都要 → 建议 `crazygames` + `taptap`
> - 不确定 → 告诉我一句「只看数据」，我按海外优先排

**硬规则**：
- **不得替用户默认选择**，不得用「我先按全平台做」敷衍过去
- 用户回复模糊（如"都要吧"）时，确认是「上表全部 5 个」还是「海外+国内各一个代表」
- 用户选 `gamedistribution` 时提醒：该平台不收同款，需要做差异化版本

---

## 步骤 3 · 记录到状态机

```bash
python <skill>/scripts/init_project.py \
  --name <project> --idea "<idea>" \
  --platforms crazygames,taptap \
  --style-ref <path>
```

或项目已存在时直接更新：

```bash
python <skill>/scripts/state.py set-platforms --project <proj> --platforms crazygames,taptap
```

写入 `state.yaml`：

```yaml
delivery:
  tier: null
  platform_confirmed: true
  platforms: [crazygames, taptap]
  platform_notes:
    taptap: "需前置备案，排期在后；先发网页游戏形态拿反馈"
```

---

## 步骤 4 · 写平台计划

`docs/00-platforms/platform-plan.md` 至少包含：

1. **选定平台清单**（key + 名称）
2. **每个平台的体积红线**，取其中**最严的一条**作为全程体积预算
   - 例：选了 crazygames + taptap → 预算取分钟队是 **20MB**（CrazyGames 移动端首页），不是 60MB
3. **各平台前置条件与责任方**
   - 需要用户自己完成的：账号实名认证、小游戏前置备案、Dirichlet 广告位创建、Poki 提报
   - 技能负责的：构建、SDK 适配、过审自检、素材文案
4. **投递顺序与排期**（国内/海外分开排）
5. **每个平台的商店素材要求**（标题/描述字数、截图数量与格式）

---

## 步骤 5 · 门禁 G0

向用户复述一遍「你选的平台 + 因此确定的体积预算 + 需要你自己办的前置事项」，得到确认后：

```bash
python <skill>/scripts/state.py set-platforms --project <proj> --platforms <...> --confirm
```

写入 `delivery.platform_confirmed: true`。**未确认前不得进入 P0。**

---

## 体积预算取最严原则（重要）

选了多个平台时，**取所有平台中最严的红线**作为全程预算，而不是各平台各算一份。

| 选择组合 | 全程首包预算 | 说明 |
|---|---|---|
| 仅 `crazygames` | 20MB | 移动端首页资格 |
| 仅 `taptap` | 60MB | TapTap 官方硬线（但优秀值 20MB） |
| `crazygames` + `taptap` | **20MB** | 取最严，同时满足两者 |
| 全部 5 个 | **20MB** | 同上 |

这样做的原因：一份代码出一个包，如果按 60MB 做，CrazyGames 那份就废了。**按最严的做，所有平台都过。**

---

## 自检

- [ ] 已向用户输出支持平台表
- [ ] 已明确提问，且用户给出了平台选择
- [ ] **未替用户默认选择**
- [ ] `delivery.platforms` 非空且只含合法 key
- [ ] `delivery.platform_confirmed: true`
- [ ] `docs/00-platforms/platform-plan.md` 已产出，含体积预算与投递顺序
- [ ] 若含国内平台，已提醒备案周期与广告位创建

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 跳过提问，直接按全平台做 | 做了一堆用不上的平台包，浪费 | 必须先问 |
| 替用户默认选 crazygames | 用户要发国内却给了海外包 | 不得默认 |
| 各平台各算体积预算 | CrazyGames 那份超 20MB 被拒 | 取最严 |
| 未提醒备案 | TapTap 小游戏卡在上架，返工排期 | G0 时就说清 |

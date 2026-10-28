# 模块 11 · 打包与交付（ship）

**阶段**：P4 ｜ **前置**：`10-qa` 通过 **+ 审核官 R2 终审通过** ｜ **产出**：`dist/<选定平台>.zip`、`docs/08-ship/`

## 目标

产出**用户选定平台**的可提交压缩包与过审自检清单。

**注意**：
- 本环节**只产出文件，不执行提交**。实际提交动作永远由用户执行。
- **交付包的平台范围必须与 `delivery.platforms` 完全一致，不多不少。**
- **审核官一票否决**：`docs/09-review/verdict-r2.json` 的 `verdict` 非 `PASS` / `PASS_WITH_DEVIATIONS` 时，本环节不得开始。这一条由 `gate_check.py` 强制拦截，无法绕过。

## 步骤

### 0. 确认审核已通过（先做，不通过不许往下）

```bash
python <skill>/scripts/gate_check.py --project <project> --stage review_final
```

必须看到：
- `verdict` ∈ {`PASS`, `PASS_WITH_DEVIATIONS`}
- `rounds.md` 记录了全部轮次
- 所有 `blocker` 问题单状态为 `fixed`

```bash
python <skill>/scripts/state.py show --project <project>
```

确认 `review_plan` / `review_graybox` / `review_final` 三者均为 `done`（**审核环节一个都不能跳**）。

### 1. 读取交付范围

```bash
python <skill>/scripts/state.py show --project <project>
```

确认 `delivery.platforms` 与 `platform_confirmed: true`。这是本环节的**唯一范围依据**。

### 2. 一键跑完（推荐）

`ship_pack.py` 把本环节所有确定性动作串起来：构建 → 体积审计 → 过审自检 → 打 zip → 商店素材 → 生成自检清单。

```bash
python <skill>/scripts/ship_pack.py --build              # 按 state.yaml 的选定平台全流程
python <skill>/scripts/ship_pack.py --platforms taptap   # 不重新构建，只审计已有 dist/
```

产物：

| 路径 | 内容 |
|---|---|
| `dist/<平台>.zip` | 提交包，解压后根目录直接是 `index.html` |
| `docs/06-perf/measure-<平台>.json` | 体积/文件数原始数据 |
| `docs/08-ship/precheck-<平台>.json` | 过审自检逐条结果 |
| `docs/08-ship/store/<平台>/` | `icon.png` / `cover.png` / `screenshot-1..3.png` |
| `docs/08-ship/submit-checklist.md` | 逐平台实测数值 + 待人工事项 |
| `docs/08-ship/store-copy.md` | 文案骨架（不存在时创建） |

它会做但**不会替你做**的事：
- R2 终审未通过时**只警告不阻断**（阻断由 `gate_check.py --stage ship` 负责）—— 演练可以跑，正式交付不行
- 截图缺失时**如实报缺**，不会拿美术稿冒充实机截图
- 不执行任何平台提交动作

### 3. 手工分步（需要单独控制时）

**只构建选定平台**，不要 `build:all`：

```bash
# 示例：用户只选了 crazygames 与 taptap
npm run build:cg && npm run build:taptap
```

对照表：

| 平台 key | 构建命令 | 产物目录 |
|---|---|---|
| `crazygames` | `npm run build:cg` | `dist/crazygames/` |
| `poki` | `npm run build:poki` | `dist/poki/` |
| `gamedistribution` | `npm run build:gd` | `dist/gamedistribution/` |
| `playgama` | `npm run build:pg` | `dist/playgama/` |
| `taptap` | `npm run build:taptap` | `dist/taptap/` |

若 `dist/` 中存在**非选定平台**的历史产物，先删掉再打包 —— 否则会被判「超出交付范围」。

### 4. 逐平台过审自检（手工）

```bash
python <skill>/scripts/precheck.py --dir dist/crazygames --platform crazygames
python <skill>/scripts/precheck.py --dir dist/taptap     --platform taptap
```

自检项（参数表在 `scripts/_common.py` 的 `PLATFORMS`）：

- [ ] 首包体积达标（按该平台红线）
- [ ] 文件数达标
- [ ] **无根绝对路径引用**
- [ ] `index.html` 位于产物根目录
- [ ] `body` 含 `user-select: none`
- [ ] **适配层标识 `i2g-platform:<key>` 命中**，且无 `i2g-platform:mock`
- [ ] 平台 SDK 注入状态正确（TapTap / Playgama 应为宿主注入或无 SDK）
- [ ] SDK 调用有异常捕获
- [ ] iOS 音频恢复逻辑存在
- [ ] 中国大陆平台：已确认前置备案（人工核对）
- [ ] 中国大陆平台：**无境外 CDN / 外部资源依赖**（Google Fonts、境外统计、境外图床一律不许）
- [ ] 中国大陆平台：隐私政策说明已准备

### 5. 打包（手工）

```bash
node scripts/zip-all.mjs
```

每个 zip 解压后根目录直接是 `index.html`，本地可直接打开运行。

### 6. 校验交付范围一致性

```bash
python <skill>/scripts/gate_check.py --project <project> --stage ship
```

该命令会检查：选定但缺产物、未选却出现产物 —— 两者都判失败。

### 7. 准备商店素材

写 `docs/08-ship/store-copy.md`：

| 项 | 约束 |
|---|---|
| 标题 | ≤60 字符 |
| 简短描述 | ≤120 字符 |
| 详细描述 | ≤500 字符 |
| 截图 | 3 张实机截图，PNG/JPEG/WebP，单张 ≤5MiB |
| 隐私政策 | 若收集任何数据则必须有 |

截图必须是**实机游玩画面**，不是美术稿或宣传图。

**平台差异**：
- Poki：提报时需提供可玩构建链接 + 3 张实机截图
- TapTap：宣传物料需完整上传；小游戏有独立审核规范；需完成**前置备案**
- GameDistribution：需先确认无同款游戏

### 8. 写自检清单

`docs/08-ship/submit-checklist.md` 逐条打勾，并附**逐平台实测数值**（首包 MB、文件数、帧率）。

### 9. 输出最终交付报告

**必须包含一行明确的 CrazyGames 标准结论**（三选一，措辞不得模糊，模板见 `modules/12-review.md` 第八节）：

```
CrazyGames 标准：⚠️ 达到必需标准（存在建议项偏离）
结论：PASS_WITH_DEVIATIONS（第 3 轮通过）
REQ 条目 60/60 通过；GUIDE 偏离 3 条，用户已确认接受
偏离清单：E6 / D6 / A9
```

报告其余内容至少包含：

1. 项目名与一句话玩法
2. **用户在 G0 选定的平台清单**
3. 达到的档位（L1/L2/L3）
4. **每个选定平台**的 zip 路径
5. 逐平台实测数据：首包体积、文件数、帧率
6. **审核结论摘要**：R0/R1/R2 各轮 verdict、总轮次、REQ 通过率
7. **降级项清单**（`status: degraded` 的阶段及影响）
8. **需要用户自己完成的前置事项**（实名认证 / 前置备案 / 广告位创建 / 提报）
9. 未通过项与原因
10. 建议的下一步

**禁止的表述**：「基本达标」「接近标准」「小问题不影响提交」「后续版本会改」。

## 投递顺序建议

不要第一天把同一份包全平台投递（GD 拒收同款，CG/Poki 常有首发或独家窗口；国内平台另有备案周期）。

**海外优先**
1. **CrazyGames Basic Launch** —— 门槛最低，7–21 天拿真实数据
2. **Playgama** —— 一次上传铺量长尾
3. **Poki** —— 备好截图与文案后提报
4. **GameDistribution** —— 做差异化版本后提交

**国内优先**
1. **TapTap 网页游戏（H5/WEB）** —— 零 SDK、无需备案，最快拿社区反馈
2. **TapTap 小游戏** —— 完成前置备案后上，才能拿到 SDK 生态能力与广告变现

## TapTap 专项（若选定）

TapTap 提供官方 CLI，可做半自动上架：

```bash
npm i -g @taptap/cli --registry=https://registry.npmjs.org/
taptap-cli auth login
taptap-cli skills list        # 查看随 CLI 同步的 AI 能力说明
```

⚠️ **涉及账号登录与提审，属对外发布动作 —— 必须由用户自己执行，技能不得代跑。**
CLI 的写操作需先 `--dry-run` 预览、用户确认后加 `--yes`；提审是 high-risk-write，需三步走并携带 `review_fingerprint`。

## 自检

- [ ] **审核官 R2 终审已通过**（`verdict` ∈ {`PASS`, `PASS_WITH_DEVIATIONS`}），R0/R1 均 `done`
- [ ] `delivery.platforms` 已由用户确认（G0）
- [ ] **选定平台的 zip 均已产出，且仅包含选定平台**
- [ ] 每个 zip 解压后可独立运行
- [ ] `precheck.py` 对每个选定平台全绿
- [ ] `gate_check.py --stage ship` 通过（含审核结论与范围一致性）
- [ ] 商店素材齐备且符合字数约束
- [ ] 隐私政策已准备（如需要）
- [ ] 自检清单含**逐平台**实测数值
- [ ] 交付报告含**明确的 CrazyGames 标准结论行**
- [ ] 最终交付报告已输出，含用户需自行完成的前置事项

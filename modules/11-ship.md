# 模块 11 · 打包与交付（ship）

**阶段**：P4 ｜ **前置**：`10-qa` 通过 ｜ **产出**：`dist/<选定平台>.zip`、`docs/08-ship/`

## 目标

产出**用户选定平台**的可提交压缩包与过审自检清单。

**注意**：
- 本环节**只产出文件，不执行提交**。实际提交动作永远由用户执行。
- **交付包的平台范围必须与 `delivery.platforms` 完全一致，不多不少。**

## 步骤

### 1. 读取交付范围

```bash
python <skill>/scripts/state.py show --project <project>
```

确认 `delivery.platforms` 与 `platform_confirmed: true`。这是本环节的**唯一范围依据**。

### 2. 逐平台构建

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

### 3. 逐平台过审自检

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

### 4. 打包

```bash
node scripts/zip-all.mjs
```

每个 zip 解压后根目录直接是 `index.html`，本地可直接打开运行。

### 5. 校验交付范围一致性

```bash
python <skill>/scripts/gate_check.py --project <project> --stage ship
```

该命令会检查：选定但缺产物、未选却出现产物 —— 两者都判失败。

### 6. 准备商店素材

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

### 7. 写自检清单

`docs/08-ship/submit-checklist.md` 逐条打勾，并附**逐平台实测数值**（首包 MB、文件数、帧率）。

### 8. 输出最终交付报告

至少包含：

1. 项目名与一句话玩法
2. **用户在 G0 选定的平台清单**
3. 达到的档位（L1/L2/L3）
4. **每个选定平台**的 zip 路径
5. 逐平台实测数据：首包体积、文件数、帧率
6. **降级项清单**（`status: degraded` 的阶段及影响）
7. **需要用户自己完成的前置事项**（实名认证 / 前置备案 / 广告位创建 / 提报）
8. 未通过项与原因
9. 建议的下一步

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

- [ ] `delivery.platforms` 已由用户确认（G0）
- [ ] **选定平台的 zip 均已产出，且仅包含选定平台**
- [ ] 每个 zip 解压后可独立运行
- [ ] `precheck.py` 对每个选定平台全绿
- [ ] `gate_check.py --stage ship` 通过（范围一致性）
- [ ] 商店素材齐备且符合字数约束
- [ ] 隐私政策已准备（如需要）
- [ ] 自检清单含**逐平台**实测数值
- [ ] 最终交付报告已输出，含用户在需自行完成的前置事项

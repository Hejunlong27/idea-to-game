# 模块 11 · 打包与交付（ship）

**阶段**：P4 ｜ **前置**：`10-qa` 通过 ｜ **产出**：`dist/*.zip`、`docs/08-ship/`

## 目标

产出可直接提交平台的压缩包与过审自检清单。

**注意**：本环节**只产出文件，不执行提交**。实际提交动作永远由用户执行。

## 步骤

### 1. 构建三平台产物

```bash
npm run build:all
```

产出 `dist/crazygames/`、`dist/poki/`、`dist/playgama/`。

### 2. 过审自检

```bash
python <skill>/scripts/precheck.py --dir dist/crazygames --platform crazygames
python <skill>/scripts/precheck.py --dir dist/poki       --platform poki
python <skill>/scripts/precheck.py --dir dist/playgama   --platform playgama
```

自检项（对照 `references/platform-requirements.md`）：

- [ ] 首包体积达标
- [ ] 文件数达标
- [ ] **无绝对路径引用**（CrazyGames 会直接拒审）
- [ ] `index.html` 位于 zip 根目录
- [ ] `body` 含 `user-select: none`
- [ ] 适配层已按目标平台注入（非 `mock`）
- [ ] SDK 调用有异常捕获
- [ ] iOS 音频恢复逻辑存在

### 3. 打包

```bash
node scripts/zip-all.mjs
```

每个 zip 解压后根目录直接是 `index.html`，本地可直接打开运行。

### 4. 准备商店素材

写 `docs/08-ship/store-copy.md`：

| 项 | 约束 |
|---|---|
| 标题 | ≤60 字符 |
| 简短描述 | ≤120 字符 |
| 详细描述 | ≤500 字符 |
| 截图 | 3 张实机截图，PNG/JPEG/WebP，单张 ≤5MiB |
| 隐私政策 | 若收集任何数据则必须有 |

截图必须是**实机游玩画面**，不是美术稿或宣传图。

### 5. 写自检清单

`docs/08-ship/submit-checklist.md` 逐条打勾，并附**实测数值**（首包 MB、文件数、帧率）。

### 6. 输出最终交付报告

至少包含：

1. 项目名与一句话玩法
2. 达到的档位（L1/L2/L3）
3. 各平台 zip 路径
4. 实测数据：首包体积、文件数、帧率
5. **降级项清单**（`status: degraded` 的阶段及影响）
6. 未通过项与原因
7. 建议的下一步

## 投递顺序建议

不要第一天把同一份包全平台投递（GameDistribution 拒收同款，CrazyGames/Poki 常有首发或独家窗口）。

1. **CrazyGames Basic Launch** —— 门槛最低，7–21 天拿真实数据
2. **Playgama** —— 一次上传铺量长尾
3. **Poki** —— 备好截图与文案后提报
4. **GameDistribution** —— 做差异化版本后提交

## 自检

- [ ] 三平台 zip 均已产出
- [ ] 每个 zip 解压后可独立运行
- [ ] `precheck.py` 全绿
- [ ] 商店素材齐备且符合字数约束
- [ ] 隐私政策已准备（如需要）
- [ ] 自检清单含实测数值
- [ ] 最终交付报告已输出

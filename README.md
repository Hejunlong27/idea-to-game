# IdeaToGame

把一个游戏想法（一段描述，或一款同款游戏名）+ 一张美术风格参考图，端到端变成一个完整可玩、可提交到 CrazyGames / Poki / GameDistribution 的 HTML5 小游戏。

**单一技能包** —— 11 个能力环节全部内置，不依赖任何外部安装的技能。

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## 一、包结构

```
idea-to-game/
├─ SKILL.md                        # 入口：触发场景、工作流、模块索引、约束
├─ README.md                       # 本文件：包结构说明与使用示例
│
├─ modules/                        # 12 个能力环节的详细执行步骤（按需读取）
│  ├─ 00-platforms.md              # P-1 平台确认：问用户发哪些平台（门禁 G0）
│  ├─ 01-brief.md                  # P0 立项：idea → 一页 GDD + 范围边界
│  ├─ 02-scaffold.md               # P1 项目骨架 + 平台适配层 + 目标平台构建
│  ├─ 03-art-bible.md              # P1 参考图 → 色板 + 风格规范 + 提示词模板
│  ├─ 04-core-loop.md              # P2 灰盒玩法主循环（先用几何占位）
│  ├─ 05-art-forge.md              # P2 生图
│  ├─ 06-sprite-tools.md           # P2 切图 / 抠图 / 图集打包
│  ├─ 07-audio-forge.md            # P2 配乐 + 音效
│  ├─ 08-polish.md                 # P3 手感 juice + UI + 难度曲线 + 存档
│  ├─ 09-perf-audit.md             # P3 逐平台体积 / 帧率 / 内存审计
│  ├─ 10-qa.md                     # P4 自动化走查 + 试玩链接
│  └─ 11-ship.md                   # P4 按选定平台打包 + 过审自检
│
├─ references/                     # 参考资料（按需读取）
│  ├─ pipeline.md                  # 阶段定义、门禁、并行、回退策略
│  ├─ contracts.md                 # 各阶段文件契约 + state.yaml schema
│  ├─ delivery-standards.md        # L1 / L2 / L3 三档验收清单
│  ├─ platform-requirements.md     # 5 个平台的硬红线（已核实官方文档）
│  └─ genre-playbook.md            # 超休闲品类拆解与范围控制规则
│
├─ scripts/                        # 确定性工具脚本
│  ├─ _common.py                   # 公共工具（路径、状态读写、绝对路径扫描）
│  ├─ init_project.py              # 建项目目录 + 复制模板 + 初始化状态机
│  ├─ state.py                     # 读写 .gamedev/state.yaml（show / set / next）
│  ├─ gate_check.py                # 阶段产物校验（门禁检查）
│  ├─ palette_extract.py           # 从参考图提取主色板（K-means）
│  ├─ sprite_tools.py              # 网格切分 / 抠图 / 裁边 / 缩放
│  ├─ pack_atlas.py                # 打包 Phaser 纹理图集（多页支持）
│  ├─ measure_bundle.py            # 体积 / 文件数 / 绝对路径审计
│  └─ precheck.py                  # 提交前过审自检（按平台）
│
└─ assets/
   └─ template/                    # Phaser 3 + Vite 项目模板（P1 复制到项目根目录）
      ├─ package.json              # 含 build:cg / build:poki / build:pg / build:gd
      ├─ vite.config.ts            # base: './' —— 保证相对路径
      ├─ tsconfig.json
      ├─ index.html                # 含 user-select:none 与移动端 viewport
      ├─ README.md                 # 模板使用说明
      ├─ scripts/zip-all.mjs       # 打包为 <platform>.zip
      └─ src/
         ├─ types.ts               # PlatformBridge 接口
         ├─ main.ts                # 入口：注入适配器 + iOS 音频恢复
         ├─ platform/              # 适配器 + 工厂（mock/crazygames/poki/gamedistribution/playgama/taptap）
         └─ game/                  # 纯玩法逻辑（config / scenes / util）
```

### 依赖

| 用途 | 依赖 |
|---|---|
| 状态与门禁脚本 | Python 3.9+，`pyyaml` |
| 图像脚本（色板/切图/图集） | Python 3.9+，`pillow`，`numpy` |
| 项目模板 | Node 18+，`phaser` `^3.90`、`vite` `^5`、`typescript` `^5` |
| Playgama 平台 | 可选：`@playgama/bridge`（未装则自动降级） |

```bash
pip install pyyaml pillow numpy
```

---

## 二、触发场景

技能在以下任一情形被使用：

| 用户说法 | 行为 |
|---|---|
| 「做个合成水果的小游戏」 | **先问平台** → 确认后走完整流程 |
| 「照《合成大西瓜》做一个」 | **先问平台** → 联网查玩法 → 映射品类 → 走完整流程 |
| 「做一个躲避障碍的网页游戏，风格参考这张图」 | **先问平台** → 参考图进入 P1 |
| 「把游戏发到 CrazyGames / TapTap」 | 平台已明确 → 直接进入 P4 打包与过审自检 |
| 「继续做上次那个游戏」 | 从 `.gamedev/state.yaml` 断点续跑 |

**不适用**：3D 重资产游戏、长剧情游戏、多人联网游戏。

## 支持的平台

**收到用户第一个指令后，技能必须先输出这张表并询问目标平台，拿到回复才开始立项。**

| 平台 key | 名称 | 区域 | 形态 | 首包红线 | 额外前置条件 |
|---|---|---|---|---|---|
| `crazygames` | CrazyGames | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 无（Basic Launch 自助提交） |
| `poki` | Poki | 海外 | Web 游戏平台 | ≤50MB（移动端首页 ≤20MB） | 提报制：需可玩链接 + 3 张实机截图 |
| `gamedistribution` | GameDistribution | 海外 | 分发聚合（3000+ 发布商） | ≤50MB | SDK 强制；审核最长 3 周；不收同款 |
| `playgama` | Playgama | 海外 | 分发网络（25+ 平台） | ≤50MB | 需自行接入 Bridge SDK |
| `taptap` | TapTap | 国内 | 网页游戏 H5 / Tap 小游戏 | **≤60MB**（优秀 ≤20MB） | **Tap 小游戏需前置备案**；广告位需在 Dirichlet 创建 |

**三条规则**：
1. **不得替用户默认选择**，也不得用「先按全平台做」敷衍。
2. **交付包只含用户选定的平台**，不多不少（`gate_check.py --stage ship` 会校验）。
3. **体积预算取最严的一条** —— 如 `crazygames` + `taptap` → 按 20MB 做，不是各算一份。

---

## 三、使用示例

### 示例 1 · 从零做一个游戏（完整流程）

用户输入：

> 做一个合成水果的小游戏，风格参考 `D:/ref/cute-fruit.png`

**第 0 步（必做）**：技能先输出「支持的平台」表，问「发到哪些平台」。用户答：**海外一个（CrazyGames）+ 国内一个（TapTap）**。

执行：

```bash
# 1. 建项目（带上用户选定的平台）
python <skill>/scripts/init_project.py \
  --name merge-fruit \
  --idea "做一个合成水果的小游戏" \
  --platforms crazygames,taptap \
  --style-ref D:/ref/cute-fruit.png \
  --genre merge \
  --out D:/games

# 2. 门禁 G0 —— 向用户复述「平台 + 体积预算 20MB（取最严）+ 需自行办的前置事项」，确认后：
python <skill>/scripts/state.py set-platforms --project D:/games/merge-fruit --confirm

# 3. P0 立项 —— 读 modules/01-brief.md，产出 GDD 与范围
#    注意：docs/00-platforms/platform-plan.md 必须先产出，gate_check 会校验
python <skill>/scripts/gate_check.py --project D:/games/merge-fruit --stage brief
python <skill>/scripts/state.py set --project D:/games/merge-fruit --stage brief --status done

# 4. 门禁 G1 —— 停下来问用户：方向认可吗？
python <skill>/scripts/state.py set --project D:/games/merge-fruit --stage brief --gate G1_passed

# 5. P1 地基（scaffold 与 art-bible 可并行）
python <skill>/scripts/palette_extract.py \
  --input D:/games/merge-fruit/assets/ref/cute-fruit.png \
  --out D:/games/merge-fruit/docs/02-art/palette.json --colors 8

# 6. 门禁 G2 —— 停下来问用户：色板与画风符合预期吗？

# 7. P2 生产
#    04-core-loop：先用几何占位把玩法跑通，自测可玩
#    05-art-forge：按 prompts/ 生图 → assets/raw/
python <skill>/scripts/sprite_tools.py \
  --input D:/games/merge-fruit/assets/raw/sheet.png \
  --grid 3x3 --trim --out D:/games/merge-fruit/assets/processed/
python <skill>/scripts/pack_atlas.py \
  --input D:/games/merge-fruit/assets/processed/ \
  --out D:/games/merge-fruit/assets/atlas/atlas --padding 2

# 8. P3 打磨 + 逐平台审计
python <skill>/scripts/measure_bundle.py --dir D:/games/merge-fruit/dist/crazygames --platform crazygames
python <skill>/scripts/measure_bundle.py --dir D:/games/merge-fruit/dist/taptap     --platform taptap

# 9. P4 只构建选定平台 + 打包 + 过审自检
cd D:/games/merge-fruit && npm run build:cg && npm run build:taptap && npm run zip:all
python <skill>/scripts/precheck.py --dir dist/crazygames --platform crazygames
python <skill>/scripts/precheck.py --dir dist/taptap     --platform taptap
python <skill>/scripts/gate_check.py --project . --stage ship   # 校验交付范围一致
```

### 示例 2 · 断点续跑

```bash
python <skill>/scripts/state.py show --project D:/games/merge-fruit
python <skill>/scripts/state.py next --project D:/games/merge-fruit
```

输出：

```
项目: merge-fruit  |  品类: merge
想法: 做一个合成水果的小游戏
参考图: assets/ref/style.png
----------------------------------------------------------------
[x] platforms      done  (crazygames, taptap)
[x] brief          done         G1_passed
[x] scaffold       done
[x] art_bible      done         G2_passed
[x] core_loop      done         self_test=playable
[~] art_forge      in_progress  sprites 8/12
[ ] sprite_tools   pending
...
下一个动作：art_forge（当前 in_progress）
```

### 示例 3 · 已有游戏只做提交自检

```bash
python <skill>/scripts/precheck.py --dir ./mygame/dist --platform poki
```

输出（节选）：

```
[PASS] index.html 位于产物根目录
[PASS] 总大小 <= 250MB            实测 12.4MB
[PASS] 文件数 <= 1500             实测 37
[FAIL] 无绝对路径引用             发现 2 处，例如 index.js: /assets/atlas.png
[PASS] body 含 user-select: none
[PASS] 已注入 poki SDK            命中标记：PokiSDK
[FAIL] 含 iOS 音频恢复逻辑        需在 touchend/click 回调内调用 audioContext.resume()
```

### 示例 4 · 素材处理链

```bash
# 生图产出 3x3 网格图 → 切分并裁边
python <skill>/scripts/sprite_tools.py --input raw/fruits_sheet.png --grid 3x3 --trim --out processed/

# 白底图抠图
python <skill>/scripts/sprite_tools.py --input raw/icon.png --matte --bg-color "#FFFFFF" --out processed/

# 统一缩放到 64x64
python <skill>/scripts/sprite_tools.py --input processed/ --resize 64x64 --out processed/

# 打图集（产出 atlas.png + atlas.json）
python <skill>/scripts/pack_atlas.py --input processed/ --out assets/atlas/atlas --padding 2 --max-size 2048
```

`pack_atlas.py` 会直接打印 Phaser 加载代码：

```js
this.load.atlas('atlas', 'assets/atlas/atlas.png', 'assets/atlas/atlas.json');
```

---

## 四、流程要点

### 共三处需要人工确认

| 门禁 | 位置 | 为什么 |
|---|---|---|
| **G0 平台确认** | **收到第一个指令后立即** | 交付范围由它决定，定晚了要返工 |
| **G1 方向确认** | 立项产出后 | 方向错了后面全白干，此处纠错成本最低 |
| **G2 风格确认** | 风格规范产出后 | 风格定错，所有生图素材作废，返工成本最高 |

### 四条硬约束

1. **先问平台再开工** —— 未收到用户平台回复不得进入立项。
2. **交付包范围 = 用户选定的平台**，不多不少（脚本会校验）。
3. **体积预算取最严的一条** —— 多平台不是各算一份。
4. **灰盒先行** —— 玩法必须先用几何占位跑通并自测可玩，之后才允许生图。
5. **不自动提交平台** —— 技能只产出 zip 与自检清单，提交动作（含 TapTap 前置备案、Poki 提报、taptap-cli 上传）永远由用户执行。

### 降级策略

生图不可用 → 程序化几何占位；配乐不可用 → Web Audio 合成音。**任何情况下游戏都必须能跑起来**，降级项会在最终交付报告中显式列出。

---

## 五、产出

| 产物 | 位置 |
|---|---|
| 可运行游戏项目 | 项目根目录（`npm run dev` 即玩） |
| 各阶段文档与报告 | `docs/01-brief` … `docs/08-ship` |
| 三平台可分发包 | `dist/crazygames.zip`、`dist/poki.zip`、`dist/playgama.zip` |
| 过审自检清单 | `docs/08-ship/submit-checklist.md` |
| 商店素材文案 | `docs/08-ship/store-copy.md` |

交付标准分三档（L1 可玩 / L2 可交付 / L3 可过审），完整清单见 `references/delivery-standards.md`。

---

## 六、许可

[Apache License 2.0](LICENSE) © 2026 Hejunlong27

允许商用、修改、分发，需保留版权声明与许可声明，并附带 NOTICE 变更说明（若分发修改版本）。


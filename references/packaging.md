# 打包与分发

技能包有两个形态，**用途不同，不要混**。

## 形态一：可安装分发包（本包采用）

```
idea-to-game/
    SKILL.md          ← 入口，frontmatter 8 个必填字段齐全
    INSTALL.md        ← 安装说明
    README.md         ← 人读的项目介绍
    LICENSE
    scripts/          ← 29 个 Python 生成器 + 3 个 TS 测试脚本的源
    modules/          ← 30 份能力环节说明（SKILL.md 引用 22 份）
    references/       ← 判据、契约、5 份 JSON Schema、3 份设计文档
    assets/
        template/     ← 整个 Vite + Phaser 工程模板（新项目从这复制）
        data/         ← 6 个模式库（创意/玩法/视觉/音频/情绪）
        styles/       ← 画风预设
        workflows/    ← ComfyUI 工作流
    tests/            ← 49 个 pytest
    docs/             ← v3 升级文档（审计/架构/实施/测试/迁移/状态）
    examples/         ← 真实项目（echo-ferry，含可玩单文件）
```

打包：

```bash
python scripts/build_skill_package.py                 # → dist/idea-to-game-3.0.0.zip
python scripts/build_skill_package.py --no-examples   # 不带 examples，包体最小
```

产物约 5.2MB / 343 文件（原始 9.3MB，压缩到 56%）。

**打包前置门禁**：脚本会先跑 `verify_skill.py`，FAIL 就中止。
这不是形式主义 —— 分发包最大的坑是「装上了但静默不工作」，
而这类问题（漏模式库、模板缺文件、frontmatter 少字段、文件编码错）
全都能机器判定。

## 形态二：技能市场上架包（本包**不适用**）

平台规范（`https://open.workbuddy.cn/docs/skill`）只认三个子目录：

```
{skill-name}/
    SKILL.md
    references/
    scripts/
    templates/
```

其他目录平台直接不解析，`assets/`、`examples/`、`README.md`、`LICENSE` 都会被剔除。

### 为什么本技能不改成上架结构

不是懒，是**改了会坏**：

| 冲突点 | 现状 | 拍平后 |
|---|---|---|
| `assets/template/` | 完整 Vite 工程（`src/game/scenes/*.ts`、`vite.config.ts`、`package.json`） | 会被压成 `templates/PlayScene.ts`、`templates/package.json`… 目录结构消失，`init_project.py` 无法复制出一个可构建的项目 |
| `assets/data/` | 6 个模式库，7 个脚本按 `SKILL_DIR/assets/data/<子目录>/<文件>.json` 读取 | 拍平后路径全断，生成器静默降级成通用文案 |
| `modules/` | 30 份环节说明，SKILL.md 引用 54 处 | 平台不认该目录，全部丢弃 → 技能只剩一个空壳 |
| `tests/` | 49 个 pytest | 同上 |

用 `skill-market-packager` 直接打这个包，实测结果是：`assets/` 下 200+ 文件被拍平进
`templates/` 与 `references/`，`modules/` `docs/` `tests/` 全部移出包外。
打出来的包能通过平台解析，但**装上去跑不动**。

要真上架，需要先做一次结构性重构：

1. `modules/*.md` → `references/modules/*.md`，改 SKILL.md 里 54 处引用 + 12 个脚本的提示文案
2. `assets/template/` → `templates/project/`，改 `_common.py` 的 `TEMPLATE_DIR` 与 `init_project.py`
3. `assets/data/` → `references/data/`，改 7 个脚本的 `DATA` 常量
4. 加一层路径兼容（同时认 `assets/` 与 `templates/`），让 GitHub 版与市场版共用一份代码
5. 全量回归：49 个 pytest + 模板新建项目 + 构建 + 浏览器测试

预估改动 80+ 处引用，回归风险集中在「静默降级」这类不报错的问题上。
**当前判断：不做。** 这个技能的使用场景是本地/团队协作，不是市场分发。
若将来确实要上架，按上面 5 步走，并且必须先把 `verify_skill.py` 的目录检查改成
可切换的布局模式，否则自检会一直 FAIL。

## 版本号约定

`SKILL.md` 的 `version` 是唯一真相源，打包脚本从它读版本号。

| 变更 | 版本 |
|---|---|
| 加能力环节 / 改文件契约 | minor +1（3.0.0 → 3.1.0） |
| 只修 bug / 改文案 | patch +1（3.0.0 → 3.0.1） |
| 破坏旧项目兼容 | major +1 |

状态机阶段、JSON Schema、`state.yaml` 字段属于**契约**，
新增字段必须向后兼容（旧项目读不到就取默认值），删除字段等于 major。

## 分发给别人时

带上三样东西：

1. `dist/idea-to-game-3.0.0.zip`
2. 一句安装命令：`python scripts/install_skill.py --zip idea-to-game-3.0.0.zip`
3. 依赖清单（`INSTALL.md` 的「依赖」表）

不要只丢一个仓库链接 —— 对方不知道要装 Python 依赖、不知道要 Chrome、
不知道 ComfyUI 是可选的，会在第一步就卡住。

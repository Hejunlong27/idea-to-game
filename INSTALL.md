# 安装

三种方式，选一种。装完都必须能通过自检（见文末）。

## 方式一：一条命令（推荐）

```bash
python scripts/install_skill.py --zip dist/idea-to-game-3.0.0.zip
```

脚本会读 zip 里的 `name` 与 `version`，装到 `~/.workbuddy-ai/skills/idea-to-game/`，
已有版本先备份成 `idea-to-game.bak-<时间戳>`，装完自动跑自检。

从源码目录装（开发时用，跳过打包）：

```bash
python scripts/install_skill.py --dir .
```

## 方式二：手动解压

```bash
unzip idea-to-game-3.0.0.zip -d ~/.workbuddy-ai/skills/
```

Windows PowerShell：

```powershell
Expand-Archive idea-to-game-3.0.0.zip -DestinationPath "$env:USERPROFILE\.workbuddy-ai\skills"
```

**目录名必须叫 `idea-to-game`**（等于 SKILL.md 的 `name`）。改名会让脚本按 `SKILL_DIR` 定位资源时出错。

## 方式三：从 GitHub

```bash
git clone https://github.com/Hejunlong27/idea-to-game.git \
  ~/.workbuddy-ai/skills/idea-to-game
```

克隆下来是完整仓库（含 `docs/` `examples/` 与 git 历史），比 zip 多 3MB 左右。

## 依赖

| 依赖 | 必需 | 用途 | 检查 |
|---|---|---|---|
| Python ≥ 3.9 | 是 | 全部生成器与校验器 | `python -V` |
| PyYAML | 是 | 读写 `state.yaml` | `python -c "import yaml"` |
| Node ≥ 20 | 做游戏时必需 | Vite 构建、浏览器测试 | `node -v` |
| Pillow / numpy | 切图与波形质检 | 图像与音频处理 | `python -c "import PIL, numpy"` |
| ffmpeg | 音频转码 | MP3 编码、波形分析 | `ffmpeg -version` |
| Chrome / Chromium | 浏览器测试 | `qa.mjs` `smoke.mjs` `playtest.mjs` | 见下 |

一键装 Python 依赖：

```bash
pip install pyyaml pillow numpy pytest
```

Chrome 由 `puppeteer-core` 驱动，模板的 `package.json` 已声明该依赖。
如果本机 Chrome 不在默认路径，设环境变量 `CHROME_PATH`。

**可选的外部生成服务**（都不装也能跑，会自动降级）：

| 服务 | 不装时的降级 |
|---|---|
| ComfyUI（`127.0.0.1:8188`） | 美术走程序化矢量绘制 |
| YuE2 / 音乐生成 | `gen_stems.py` 程序化合成 stem |
| TTS | 无配音，只有文字 |

## 验证安装

```bash
cd ~/.workbuddy-ai/skills/idea-to-game
python scripts/verify_skill.py
```

期望结尾：

```
合计：PASS 13　WARN 0　FAIL 0
结论：PASS —— 可以打包分发。
```

再跑一次完整测试（约 40 秒）：

```bash
python -m pytest tests -q
```

期望 `49 passed`。端到端用例会真合成 22 个音效与 5 条 stem 并做波形质检，
所以必须装了 ffmpeg 才会全绿；没有 ffmpeg 时该用例会 `skip` 而不是伪装通过。

## 升级

```bash
# 已有版本会自动备份成 idea-to-game.bak-<时间戳>
python scripts/install_skill.py --zip dist/idea-to-game-<新版本>.zip
```

回滚：把 `.bak-*` 目录改回 `idea-to-game`，删掉新版。

## 卸载

```bash
rm -rf ~/.workbuddy-ai/skills/idea-to-game
```

## 常见问题

**技能装了但不触发？**
看 `SKILL.md` 的 `description` 是否含你实际会说的话。触发词集中在描述末尾，
改完需要重开会话让技能重新加载。

**`state.py` 报找不到项目？**
所有脚本都要求 `--project <项目目录>`，且该目录下要有 `.gamedev/state.yaml`。
新项目用 `init_project.py` 创建。

**Windows 上中文乱码？**
所有文件都是 UTF-8。如果终端是 GBK，先 `chcp 65001`。

**为什么不能上架技能市场？**
平台只认 `SKILL.md` + `references/` `scripts/` `templates/` 三目录，
本技能的脚本依赖 `assets/template`（整个 Vite 工程模板）与 `assets/data`（模式库），
拍平会直接破坏运行。详见 `references/packaging.md`。

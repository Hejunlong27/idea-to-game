# examples · 真实项目

这里的每个目录都是一个**跑通全流程的真实游戏**，不是示例代码片段。

| 目录 | 版本 | 丰富度 | 说明 |
|---|---|---|---|
| `echo-ferry/` | v3.0 | 94.0 `RICH` | 《回声摆渡》—— 第一个走完 v3 五份身份契约的项目 |

## echo-ferry ·《回声摆渡》

> 雾海上没有方向，只有回声。**敲钟能看见一瞬，也会被黑暗听见。**
> 亮过的地方会留下残影 —— 而残影是「当时」的位置，黑暗里的东西会移动。
> 你打的是幻影。记忆格用完的那一刻，整片海同时熄灭。

**核心机制的独特性**：视野不是被给予的，是被借来的；借来的地图会腐烂。

### 怎么玩

双击 `standalone.html`（单文件，零依赖，离线可玩）。
方向键 / WASD 划一格，空格敲钟，触摸设备点相邻格。

### 这个目录能证明什么

v3 的十项能力在这里都有**真实产物**，不是文档声明：

| 能力 | 证据位置 |
|---|---|
| 创意发散（5 个结构不同的方向 + 7 维评分） | `docs/01-brief/creative-concepts.json` |
| Creative DNA | `docs/01-brief/creative-dna.json` |
| Visual DNA + 三套风格提案 | `docs/02-art/visual-dna.json`、`style-proposals.json` |
| 角色一致性（front / side / back + i2i ref） | `docs/02-art/consistency-plan.json`、`style-tests/report.md` |
| AI 生图实测（ComfyUI + Qwen-Image 2.1 turbo） | `docs/02-art/style-tests/*.png` |
| Audio DNA（5 stem × 4 状态自适应音乐） | `docs/05-audio/audio-dna.json`、`audio-qc.json` |
| Juice Plan（事件 → 14 类效果） | `docs/04-core-loop/juice-plan.json` |
| Experience Blueprint（情绪曲线 + E1–E8） | `docs/03-experience/experience-blueprint.json` |
| 六项专项审核（38 条实测证据） | `docs/09-review/verdict-specialist.json`、`specialist-report.md` |
| 自动试玩（4 策略） | `docs/07-qa/playtest.json`、`playtest-report.html` |

### 美术是混合的

| 素材 | 来源 | 体积 |
|---|---|---|
| 船 / 幽影 / 灵魂 / 礁石 / 钟 / 背景 | AI 生图（ComfyUI，按 Visual DNA 出） | 224 KB |
| 地块 / 水纹 / 粒子 / 光晕 / UI | 程序化矢量绘制 | 0 KB |

接入方式：AI 图映射到固定纹理键（`t_boat` / `t_wraith` / `t_soul` / `t_rock` / `t_bell` / `t_bg`），
`src/game/art.ts` 每段程序化绘制前先判 `textures.exists()`，存在即跳过 —— **删掉 `assets/img/` 的图会自动回退到程序化版本，玩法代码零改动**。

### 音乐也是降级通道的产物

`assets/audio/bgm/` 的 5 条 stem 由 `scripts/gen_stems.py` 程序化合成（YuE2 未运行时）。
已如实标注，不冒充 AI 音乐生成。

### 未做的事

- **R2 终审与平台提交未执行**（这是 Showcase，不提交 CrazyGames）。`state.yaml` 里标 `skipped` 并写明原因。
- **真机帧率未验证**（开发机无 GPU，SwiftShader 下的帧率不代表真机）。

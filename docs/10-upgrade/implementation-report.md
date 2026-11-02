# v3.0 实施报告

> 时间：2026-11-01　起点：`8691e14`（v2.0 内容深度引擎）
> 结论：**10 项核心任务全部落地并有实测证据**；6 项依赖外部条件（无 GPU / 无生图通道 / 无音乐服务 / 无 TTS），已如实标注。

## 一、原项目审计结论

详见 `repository-audit.md`。三句话概括：

1. **v2 的生产链路是扎实的**（20 脚本 / 15 阶段 / 两道质量闸 / 4 个真实游戏），不能推倒。
2. **缺的不是能力数量，是纵向一致性** —— 玩法/叙事/美术/音频各自有生成器和评分项，
   但没有共享的身份定义，也没有跨域一致性校验。这是「作品没有辨识度」的机制性原因。
3. **创意环节的缺失是根因**：`content_forge.infer_genre()` 用关键词选出唯一品类，
   系统从第一步就只有一条路 —— 后面所有环节都在为这条唯一的设想服务。

审计还发现 4 个**真实缺陷**（不是设计取舍）：

| 缺陷 | 后果 | v3 处置 |
|---|---|---|
| T4：`asset_forge.mk_item()` 从不写 `use_hero_ref` | 角色一致性 ref 链**实际从未生效**（看起来有） | 已修复，默认写入；有测试断言 |
| T7：模板缺 `qa.mjs` / `smoke.mjs` | 每个项目重写一遍 QA，无法统一校验 | 已回灌模板 |
| T9：`state.py` 用 `STAGES.index()+1` 推模块名 | 插阶段后提示全错 | 改为 `STAGE_MODULES` 显式映射 |
| 模板 `build` 输出 `dist/` | vite 清空 outDir 会把平台产物一起删 | 改为 `dist/preview` |

## 二、新增能力

### 脚本（8 个新增，2 个增强）

| 脚本 | 行数量级 | 职责 |
|---|---|---|
| `creative_forge.py` | ~880 | 发散（最远点采样）/ 反转 / 7 维评分 / 相似度 / DNA |
| `art_director.py` | ~600 | 三套提案 / Visual DNA / 一致性计划 / 对比度校验 |
| `audio_director.py` | ~600 | 自适应音乐 / 动态音效规则 / 波形质检 / TS 配置生成 |
| `gen_stems.py` | ~230 | 程序化合成 5 条无缝 stem（无外部依赖） |
| `juice_forge.py` | ~430 | 事件→表现矩阵 / 硬上限校验 / TS 配置生成 |
| `experience_forge.py` | ~480 | 情绪曲线 / 每关 10 项 / E1–E8 程序化验证 |
| `specialist_review.py` | ~560 | 六项专项审核（38 条检查，带真实证据） |
| `schema_check.py` | ~330 | JSON Schema Draft-07 子集校验器（零依赖） |
| `playtest.py` | ~330 | 起服务 + 跑浏览器试玩 + 出 HTML 报告 |
| `asset_forge.py`（增强） | +120 | 真实读 Visual DNA / 修 ref 链 / 一致性体检 |
| `gate_check.py`（增强） | +260 | 8 个新阶段门禁 + 专项审核一票否决 |

### 数据与契约

| 类型 | 数量 | 说明 |
|---|---|---|
| JSON Schema | 5 | creative-dna / visual-dna / audio-dna / juice-plan / experience-blueprint |
| 创意模式库 | 6 个目录 | 24 动词 / 9 反转维 / 16 原型 / 12 风格 / 10 乐器族 / 8 情绪规则 / 14 效果；**全部带 source + license** |
| 模块文档 | 8 份 | 01c / 03b / 05b / 07b / 08b / 08c / 10b / 12b |
| 判据文档 | 3 份 | game-event-schema / audio-emotion-design / creative-identity |
| 测试 | 49 用例 | 4 个文件 + conftest |

### 模板运行时（3 个模块）

| 文件 | 行数 | 职责 |
|---|---|---|
| `events.ts` | ~280 | 统一事件总线 |
| `audio.ts` | ~390 | 自适应音频（stem 状态机 / 变体 / 距离 / ducking / 调试） |
| `juice.ts` | ~420 | 14 类效果 / 分级 / 降级 / 无障碍 |

### 模板测试脚本（3 个）

`qa.mjs`（断言 + 帧率基线 + 移动端）/ `smoke.mjs`（闭环）/ `playtest.mjs`（四策略真玩）

## 三、修改的文件

| 文件 | 改动 |
|---|---|
| `scripts/_common.py` | `STAGES` 15→24（append 8）；新增 `STAGE_MODULES`、`V3_STAGES` |
| `scripts/state.py` | 用 `STAGE_MODULES` 替代序号推断；`show` 标注 v3 阶段 |
| `scripts/gate_check.py` | 8 个阶段的 `REQUIRED_FILES` + 8 个 checker；`ship` 增加专项审核阻断 |
| `scripts/asset_forge.py` | `read_style` 读 Visual DNA；`build_prompt` 加 DNA 槽位；`mk_item` 写 `use_hero_ref`；lint 加一致性体检 |
| `assets/template/package.json` | `build` → `dist/preview`；新增 `test` / `qa` / `smoke` / `playtest` |
| `assets/template/src/game/scenes/PlayScene.ts` | 重写为事件驱动（示范接线） |
| `assets/data/mechanic-vocab.json`、`story-frames.json` | 补 `source` + `license`（合规要求） |

## 四、新增的文件（分类）

```
scripts/    creative_forge.py art_director.py audio_director.py gen_stems.py
            juice_forge.py experience_forge.py specialist_review.py
            schema_check.py playtest.py
tests/      conftest.py test_schema_check.py test_state_and_contracts.py
            test_creative.py test_pipeline.py
references/ game-event-schema.md audio-emotion-design.md creative-identity.md
references/schemas/  creative-dna visual-dna audio-dna juice-plan experience-blueprint
modules/    01c-creative-director 03b-art-director 05b-animation-forge
            07b-audio-director 08b-game-juice 08c-experience-designer
            10b-playtest-agent 12b-art-review
assets/data/ creative-patterns/{interaction-verbs,twist-dimensions,animation-patterns,character-patterns}
             gameplay-patterns/archetypes  visual-styles/styles
             audio-styles/palettes  emotional-patterns/curves  README.md
assets/template/src/game/  events.ts audio.ts juice.ts audio-config.ts juice-config.ts
assets/template/scripts/   qa.mjs smoke.mjs playtest.mjs
docs/10-upgrade/  repository-audit upgrade-roadmap architecture-v3
                  implementation-report test-report migration-guide feature-status
```

## 五、关键架构变化

### 1. 从「一个蓝图桶」到「五份身份契约」

v2：身份散落在 `content-blueprint.json` 的 world/story/art/audio 四个子树，无交叉约束。
v3：Creative DNA 是根，Visual / Audio / Juice / Experience 四份契约各自从它派生，
下游**强制读取**（`asset_forge` 读 Visual DNA、`audio.ts` 读 `audio-config.ts`、
`specialist_review` 读全部五份）。

### 2. 从「文档驱动」到「配置驱动运行时」

DNA → `--emit-ts` → `audio-config.ts` / `juice-config.ts` → 运行时行为。
**改设计不用改代码。** 这是「DNA 真的接入流水线」的可验证证据（测试断言 spec 里
`visual_dna_applied` 全 true、提示词里能查到材质与光照槽位）。

### 3. 从「玩法代码直接调表现」到「事件总线」

玩法只 `bus.emit()`。表现、音频、UI、埋点、测试各自订阅。
本作实测：155 个事件驱动了 9 类表现效果与 4 个音乐状态。

### 4. 从「数内容数量」到「可验证的体验判据」

E1–E8 每条都有程序化验证路径与证据字符串；**UNVERIFIED 不算通过**（gate 当 warning，审核当阻断）。

### 5. 审核从「声明」到「实测」

| 审核项 | v2 | v3 |
|---|---|---|
| 美术 | 数「有没有素材」 | **读截图像素**算主色相与 DNA 的距离 |
| 音频 | 查「不是 wav、不超 2MB」 | **ffmpeg 解码后测**峰值/RMS/循环接缝 |
| 动画 | 无 | 读源码确认 `new JuiceDirector` + `update` + `destroy` + 无 `time.timeScale` |
| 体验 | 无 | 读试玩报告：首次正反馈、重复率、卡死 |
| 试玩 | 无 | 4 策略真操作 155 个事件 |

## 六、实际完成的功能

见 `feature-status.md`。汇总：**DONE 46 / PARTIAL 4 / BLOCKED 6 / PLANNED 2**。

关键 DONE：
- 5 个结构不同的创意方向（最远点采样保证）
- 五份身份契约 + schema + 语义校验
- Visual DNA 12 区块，`asset_forge` 真实读取
- 角色一致性 ref 链（修复了一个「看起来有、实际走不到」的缺陷）
- stem 自适应音乐（4 状态 × 5 轨，配比互不相同）+ 波形质检
- 14 类表现效果 + 强度分级 + 无障碍
- E1–E8 体验判据
- 六项专项审核（38 条证据）
- 49 个 pytest
- 可玩的 Showcase（3 关，策略玩家能打通到第 3 关）

## 七、暂时无法实现的功能及原因

| 项 | 状态 | 原因 | 需要什么 |
|---|---|---|---|
| 真机帧率验证 | BLOCKED | 本机无 GPU，SwiftShader 软光栅把绘制调用开销放大数倍 | 一台中端 Android 设备 |
| 4G 首包时间 | BLOCKED | 沙盒网络不具代表性 | 真机 + 4G |

| YuE2 音乐生成 | BLOCKED | YuE2-Studio 未运行（8791 不通） | 启动窗口并保持运行 |
| TTS 配音 | BLOCKED | 端点未配置 | boss 提供 TTS 2.5 端点 |
| AI 图像审核（视觉模型） | PLANNED | 无可用视觉模型 | 接入多模态模型 |
| 混响 / 低通滤波 | PARTIAL | 需要 WebAudio 节点链，本作未用 | 后续按需接入 |
| 试玩录制视频 | PLANNED | 体积大、优先级低 | — |

## 八、自动化测试结果

```
pytest tests -q            → 49 passed in 27.37s
npm run build              → ✓ 3.87s
npm run standalone         → ✓ 3435KB，外部请求 0
npm run test:standalone    → ✓ 全部通过
qa.mjs                     → ✓ 全绿（帧率跳过：SwiftShader）
smoke.mjs                  → ✓ 闭环可走
playtest.mjs               → 155 事件 / 0 错误 / 0 卡死 / 首次正反馈 4.1s
```

详见 `test-report.md`。

## 九、Showcase 试玩方式

```bash
cd D:/w.ai/2026-10-16-09-25-56/echo-ferry

# 方式一：单文件版，双击即玩（推荐给 boss）
dist/standalone.html

# 方式二：走 HTTP（开发预览）
npm run build:cg
npm run serve:cg          # 打开 http://127.0.0.1:5173
```

操作：方向键 / WASD 划一格，空格敲钟，也可点相邻格。

**玩法一句话**：敲钟能看见一瞬，也会被黑暗听见；亮过的地方留下会腐烂的残影，而影子会移动。

## 十、性能与包体积

| 项 | 实测 | 红线 |
|---|---|---|
| 产物总体积 | 3.2 MB | 50MB（移动端 20MB） |
| 文件数 | 34 | 1500 |
| JS（含 Phaser） | 1528 KB（gzip 356KB） | — |
| 音频 | 1448 KB | 2MB 预算 |
| 美术素材 | 224 KB（6 张 AI 图 + 程序化地块） | — |
| 帧率 | 43 FPS @ SwiftShader（**不代表真机**） | 60fps 待真机验证 |

## 十一、下一阶段建议

1. **补上唯一未闭合的门禁**：真机帧率。给 `qa.mjs` 加一个「手动录入真机数据」的通道，
   否则这道门禁永远在沙盒里失效。
2. **生图通道可用后做 A/B**：同一份 `visual-dna.json`，程序化 vs AI 生图，验证视觉是否一致。
   这是「Visual DNA 真的能约束出图」的终极验证。
3. **创意库扩容**：24 动词 → 40，16 原型 → 24。当前 5 个方案的结构差异刚好卡在 3/5 的及格线。
4. **旧项目实跑迁移**：对 4 个既有游戏各跑一次，把 `migration-guide.md` 从「应该能跑」变成「已验证能跑」。
5. **审核官再进一步**：A3（截图色相）已程序化，下一步做「视觉焦点」与「层次」的可测指标。

# v3.0 测试报告

> 全部数值来自真实执行。**未执行的项标为「未验证」，不标记 PASS。**
> 执行环境：Windows / Python 3.13（托管 venv）/ Node 22.22.2 / Chrome（无头，SwiftShader 软光栅）

## 一、Python 测试

```
$ python -m pytest tests -q
.................................................                        [100%]
49 passed in 27.31s
```

| 测试文件 | 用例 | 覆盖 |
|---|---|---|
| `test_schema_check.py` | 9 | 校验器自测 25 例、5 份 schema 结构、类型/必填/枚举/const 报错、`non_numeric` 必须为 true |
| `test_state_and_contracts.py` | 11 | 旧 15 阶段保留、v3 8 阶段新增、阶段顺序、模块映射、旧项目缺键不崩、G0 未确认时 brief 必须失败 |
| `test_creative.py` | 12 | 发散确定性、5 方案结构距离 ≥3、反转维度不重复、空方案判 REJECT、相似度能识别打地鼠、`numeric_only` 不误判否定句、DNA 语义校验 |
| `test_pipeline.py` | 17 | 色彩数学、三套提案可区分、Visual DNA 12 区块、对比度拦截、一致性不虚报、**asset_forge 真实读取 DNA + ref 链生效**、音频状态互不相同、**真实波形检测削波/静音**、表现分档与硬上限、体验 UNVERIFIED 语义、专项审核缺产物为 INCOMPLETE、**ship 被 FAIL/INCOMPLETE 阻断**、端到端全链路 |

### 端到端用例（`test_full_pipeline_end_to_end`）

从零建项目，一路跑到专项审核：

```
init_project → creative_forge --diverge → (填一个方案) → --evaluate → --dna
  → --validate --strict
  → art_director --propose → --dna → --consistency → --validate
  → audio_forge --plan → audio_director --plan → --emit → --emit-ts → --validate
  → gen_audio（22 音效）→ gen_stems（5 stem）→ --qc
  → juice_forge --plan → --emit-ts → --validate
  → experience_forge --plan → --validate
  → gate_check × 6 阶段 → schema_check --all
```

全部退出码 0。**其中「缺 audio-qc.json 时 audio_director 门禁必须失败」是专门断言的反向用例。**

## 二、Node 测试（Showcase `echo-ferry`）

| 命令 | 结果 |
|---|---|
| `npm install` | ✅ 94 包，50s |
| `npx tsc --noEmit` | ✅ 0 错误（严格模式） |
| `npm run build:cg` | ✅ 4.3s，`dist/crazygames` 1.49MB JS + 1.45MB 音频 |
| `npm run build` | ✅ 输出 `dist/preview`（**修复：不再清空 dist/ 导致平台产物被删**） |
| `npm run standalone` | ✅ `dist/standalone.html` 3435KB，外部请求 0 |
| `npm run test:standalone` | ✅ 全部通过（file:// 下两种情形都符合预期） |

`test:standalone` 的关键断言：
- A4 真的出画面（非黑采样点 4096/4096）
- B1 `file://` 直开时看门狗立即给出提示（而非静默 Loading）
- B2 提示里含可执行动作（standalone / serve）

## 三、浏览器测试

### 3.1 `qa.mjs`

| 检查项 | 结果 | 证据 |
|---|---|---|
| boot 完成 | ✅ | `__bootDone` 出现 |
| canvas 尺寸合理 | ✅ | 720×1280（显示 405×720） |
| `__gameState` 可读 | ✅ | 12 个字段 |
| 操作后状态变化 | ✅ | memory 5→4，ghosts 4，revealed true |
| 事件系统有输出 | ✅ | 4 条 |
| 移动端无溢出 | ✅ | 390×844 |
| `user-select: none` | ✅ | 计算样式 `none` |
| 零 pageerror / console.error | ✅ | 0 |
| 无资源 404 | ✅ | 0（favicon 已单独归类） |
| 帧率 | ⚠ **未判定** | 游戏 43 FPS / 基线 126 FPS，renderer=SwiftShader → 需真机复测 |

### 3.2 `smoke.mjs`

✅ 通过：3 张阶段截图，11 条事件，0 错误，闭环可走。

### 3.3 `playtest.mjs`（4 策略 × 50s）

| 策略 | 操作数 | 事件 | 最终关 | 送达 |
|---|---|---|---|---|
| novice | 80 | 9 类 | 2 | 1 |
| explorer | 92 | 10 类 | 2 | 4 |
| strategist | 125 | 8 类 | **3** | 3 |
| extreme | 289 | 8 类 | 2 | 6 |

汇总：**155 个事件、0 运行时错误、0 卡死、重复率 0.13、首次正反馈 4.098s**。

策略玩家能打到第 3 关 → 证明三关内容真实可通，不是只有第一关能玩。

## 四、内容与质量门禁

| 门禁 | 结果 |
|---|---|
| `content_forge --validate` | ERROR 0（WARN 7：自定义机制 id 不在词库，属预期） |
| `richness_check --stage design` | **94.0 / 100 → RICH**（玩法 30/30、叙事 25/25、美学 19/25、音频 20/20） |
| `experience_forge --verify` | **E1–E8 全 PASS**（0 FAIL、0 UNVERIFIED） |
| `audio_director --qc` | **PASS**：27 文件 1455.4KB，缺失 0 / 削波 0 / 静音 0 / 接缝可疑 0 |
| `specialist_review` | **PASS**：38 条证据，0 FAIL、0 UNVERIFIED |
| `measure_bundle` | PASS：2.87MB / 28 文件，绝对路径检查通过 |

### 专项审核的 38 条证据（摘要）

| 审核 | 条数 | 关键证据 |
|---|---|---|
| 创意 | 6 | 5 方案结构距离 3/5；与 stealth 原型重合 0.48（LOW） |
| 美术 | 6 | **6 张截图主色相与 DNA 距离 8°–19°（阈值 25°）** |
| 动画 | 8 | 21 条规则 / 9 类效果 / 14 种组合；闪屏 ≤1/s、震动 ≤300ms |
| 音频 | 6 | 4 状态 × 5 stem 配比互不相同；实测无削波/静音 |
| 体验 | 5 | E1–E8 全 PASS |
| 试玩 | 7 | 4 策略、0 错误、无卡死、首次正反馈 4.1s |

## 四·补、生图通道验证（2026-11-01 22:30 补测）

| 项 | 结果 |
|---|---|
| ComfyUI `/system_stats` | 200，0.42.1，RTX 4060 Laptop 8GB |
| `gen_assets --probe` | `[PASS] ComfyUI: 可达 · 模型齐备` |
| 实测出图 | 6 张（hero / hero_side / hero_back / villain / bg_1 / tile_1），1024² 约 25s |
| 提示词 lint | 33 个文件 **ERROR 0** |
| 色调一致性 | 4 张核心图的色相全部落在 Visual DNA 色板内 |

过程中修掉 5 个真 bug（中文字段泄漏进提示词、中文 id 塌缩、反派误挂主角 ref、背景被误抠、三视图重复）。
详见 `echo-ferry/docs/02-art/style-tests/report.md`。

## 五、未验证项（诚实清单）

| 项 | 状态 | 原因 | 怎么补 |
|---|---|---|---|
| 真机帧率 | **BLOCKED** | 本机无 GPU，SwiftShader 软光栅，逐次绘制调用开销被放大数倍 | 真机（中端 Android）跑 `qa.mjs` |
| 4G 首包时间 | **BLOCKED** | 沙盒网络环境不具代表性 | 真机测 `gameplayStart` |
| 真人试玩 | **未做** | 需要人 | 由 boss 玩 3 局，重点看「前 10 秒是否一看就懂」 |
| AI 生图一致性 | **已验证** | 已用同一份 Visual DNA 出图 6 张，色相全部落在色板内 | 已完成 |
| 姿态控制（side view） | **未达预期** | ref 图权重压过文字指令，侧视仍偏正面 | 需 ControlNet 或降低 ref 权重 |
| YuE2 音乐 | **未做** | YuE2-Studio 未运行（8791 不通） | 启动后跑 `--emit` 的清单 |
| TTS 配音 | **BLOCKED** | 端点未配置 | boss 提供端点后填 `.gamedev/audio.yaml` |

## 六、测试自身的可信度

- 所有断言都通过**子进程跑真实脚本**并读落盘文件，不 import 内部函数替代执行
- 反向用例占一定比例（空方案必须 REJECT、缺 QC 必须拦、专项审核缺产物必须 INCOMPLETE）
- 端到端用例会真的合成音频（22 音效 + 5 stem）并做波形质检，不是 mock
- 测试跑完不动仓库内的任何文件（全部在 `tmp_path`）

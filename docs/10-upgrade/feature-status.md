# 功能状态（Feature Status）

> 标记口径（严格）：
> - **DONE**：真实实现 + 已接入流水线 + 有自动化测试或实测证据
> - **PARTIAL**：部分实现，或未接入流水线，或缺测试
> - **BLOCKED**：依赖外部条件（凭证 / 设备 / 服务）
> - **PLANNED**：只有设计，尚未实现
>
> **严禁把 PLANNED / PARTIAL 写成 DONE。**

## 一、创意与身份

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 5 个结构不同的创意方向 | **DONE** | `creative_forge --diverge`；最远点采样保证最小两两距离 ≥3；测试断言 5 方案两两差异 ≥3 维 |
| 创意反转（9 维度） | **DONE** | `--twist`；每个维度带「假设 / 改写 / 代价」；库文件带 license |
| Unique Mechanic 6 条判据 | **DONE** | 评分项 C2 + `--validate` 语义检查 |
| 启发式相似度分析 | **DONE** | 与 16 个原型做结构指纹比对；**明确不宣称原创性** |
| 7 维创意评分（带证据） | **DONE** | 每条评分都有 `note` 证据；空方案必判 REJECT |
| Creative DNA + Schema | **DONE** | `creative-dna.schema.json`（8 区块）+ 语义校验 9 条 |
| DNA 被下游真实读取 | **DONE** | `art_director` 读 visual / `audio_director` 读 audio / `experience_forge` 读 experience |
| 创意模式库（6 类） | **DONE** | 24 动词 / 9 反转维 / 16 原型 / 12 风格 / 10 乐器族 / 8 情绪规则；全部带 source+license |
| 蓝图与 DNA 一致性校验 | **PARTIAL** | `content_forge` 尚未强制读 DNA；目前靠 `--validate` 的间接检查 |

## 二、美术

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 三套风格提案（混血） | **DONE** | `art_director --propose`；混 2 个风格的不同轴，优先用 DNA 已声明风格 |
| Visual DNA + Schema | **DONE** | 12 区块（含轮廓/材质/纹理/光照/阴影/镜头/景深/UI/字体/角色比例/动画/FX） |
| `asset_forge` 真实读 Visual DNA | **DONE** | spec 里 `visual_dna_applied` 全 true；提示词里能查到材质与光照槽位（有测试） |
| 角色一致性 ref 链 | **DONE（修复 + 实测）** | 修复 `use_hero_ref` 从不被写入的缺陷；主角自动出 front/side/back 三视图，side/back 挂 i2i ref；**有真实产物对比**（同一角色，服装/灯/船一致） |
| 一致性状态不虚报 | **DONE** | 四态 `full_ref_chain`/`seed_only`/`prompt_only`/`degraded_no_ref`；gate 校验参考图真实存在 |
| 场景视觉叙事 | **DONE** | `scene_narrative`（触发 → 画面变化 → 意味着什么），审核要求 ≥2 条 |
| 美术审核（程序化） | **DONE** | 真读截图像素算色相分布，与 DNA 距离 ≤25°；对比度检查 |
| AI 图像审核（视觉模型） | **PLANNED** | 本机无可用视觉模型；不假装已执行（美术审核用像素统计代替） |
| Visual DNA 能否约束出图 | **DONE** | 6 张接入图的色相全部落在 DNA 色板内，无新色相 |
| AI 生图通道验证 | **DONE** | ComfyUI 0.42.1 + Qwen-Image 2.1 turbo 实测出图 6 张（1024² 约 25s）；`gen_assets --probe` PASS。见 `echo-ferry/docs/02-art/style-tests/report.md` |

## 三、动画与表现

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 14 类效果 | **DONE** | `juice.ts` 全部实现；`juice-plan` 覆盖 9 类 |
| 事件 → 表现矩阵 | **DONE** | 21 条规则，按 severity 分 4 档，每条带 `why` |
| 强度分级 | **DONE** | `scale = fx.scale × (0.5 + intensity)`；审核查「≥3 种不同组合」 |
| 性能降级 | **DONE** | high/medium/low 三档，粒子 100%/60%/30% |
| 无障碍（reduced-motion） | **DONE** | 关闭震动/闪屏/推近/慢动作；闪屏硬上限 1/s、震动 300ms |
| 不影响逻辑确定性 | **DONE** | 只缩放 `tweens.timeScale`；审核扫描 `time.timeScale` 出现即 FAIL |
| 资源清理 | **DONE** | SHUTDOWN 里 destroy；审核检查 |
| 粒子/视差在真机上的表现 | **BLOCKED** | 无 GPU，无法验证实际帧率影响 |

## 四、音频

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 自适应音乐（stem 分层） | **DONE** | 5 stem × 4 状态，配比互不相同；`audio.ts` 只改音量不换曲 |
| 状态机 + 过渡 | **DONE** | `setState` + `transitionMs` 线性插值 |
| 动态音效（变体/冷却/并发/距离） | **DONE** | 全部实现；确定性伪随机变体 |
| ducking | **DONE** | high 优先级音效触发 600ms 压低旋律与氛围 |
| 情绪化声设计 | **DONE** | 9 条 `emotional_rules`（含 DNA 的 4 条动态规则） |
| 声音即玩法 | **DONE** | 回声定位 + 屏幕边缘方向条作为视觉替代 |
| 音频调试模式 | **DONE** | `audio.debugLines()` 返回状态/各轨音量/并发/last event |
| 音频质检（真实波形） | **DONE** | ffmpeg 解码 + 峰值/RMS/接缝；27 文件实测 PASS |
| stem 程序化合成 | **DONE** | `gen_stems.py`，无缝循环（首尾交叉淡化） |
| YuE2 音乐生成 | **BLOCKED** | 服务未运行；`--emit` 清单已就绪 |
| TTS 配音 | **BLOCKED** | 端点未配置；`voice-plan` 已声明 `enabled: false` 并写原因 |
| 混响 / 低通 / 声像定位 | **PARTIAL** | 距离衰减与 ducking 已实现；混响与低通滤波未接（需 WebAudio 节点链） |

## 五、体验与试玩

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 情绪曲线（7 段） | **DONE** | 每段含 `player_does` + `feedback`；峰值必须在 climax |
| 每关体验表（10 项） | **DONE** | 含取舍决策、挑战轴、高潮、奖励、下一关钩子 |
| E1–E8 可验证判据 | **DONE** | 程序化验证，带证据；**UNVERIFIED 不算通过** |
| 试玩 Agent（4 策略） | **DONE** | puppeteer-core（**不是 Playwright**，见下） |
| 试玩报告（三类结论分开） | **DONE** | 程序检测 / AI 评价 / 待人工确认 三节 |
| 卡死检测 / 状态快照 / 截图 | **DONE** | 6 秒无变化判卡死；每 25 步截图 |
| 录制视频 | **PLANNED** | 未实现（puppeteer 可录但体积大，优先级低） |
| 固定随机种子 | **PARTIAL** | 事件时间戳来自场景时钟、变体用确定性哈希；但输入策略仍按步数取模，不是完整种子系统 |

> **关于 Playwright**：任务书写「优先使用 Playwright」，实际用 `puppeteer-core`。
> 原因：项目已有该依赖且模板 `shots.mjs` 一直用它；Playwright 需额外下载浏览器（沙盒网络受限）。
> 能力等价（都能真实点击/按键/截图/读状态），但**报告里不写 Playwright**。

## 六、事件系统与质量审核

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| 统一事件总线 | **DONE** | 类型化、优先级、去重、异常隔离、环形日志、不消耗随机数 |
| 事件契约文档 | **DONE** | `references/game-event-schema.md` |
| 一个事件驱动 5 个系统 | **DONE** | juice / audio / UI / 埋点 / 测试（本作实测 155 个事件） |
| 六项专项审核 | **DONE** | 38 条证据，0 FAIL / 0 UNVERIFIED |
| 专项审核一票否决 | **DONE** | `gate_check --stage ship` 校验 `verdict-specialist.json`；有反向测试 |
| 审核证据来自实测 | **DONE** | 美术读截图像素、音频读波形、动画读源码、体验读试玩数据 |
| 四维丰富度（v2） | **DONE（未改）** | 权重 30/25/25/20 与 THIN 判定完全保留 |
| A–H 八维（v2） | **DONE（未改）** | `review_gate.py` 未改动判据 |

## 七、工程与测试

| 能力 | 状态 | 证据 / 缺口 |
|---|---|---|
| JSON Schema 校验器（零依赖） | **DONE** | Draft-07 子集；25 例自测 |
| 5 份身份契约 schema | **DONE** | creative / visual / audio / juice / experience |
| pytest 套件 | **DONE** | 49 用例 / 27s / 全绿 |
| 浏览器三件套（qa/smoke/playtest） | **DONE** | **已回灌模板**（修掉了 v2 的 T7：模板缺这两个脚本） |
| 状态机向后兼容 | **DONE** | 旧 15 键保留 + 8 新键 append；有旧项目模拟测试 |
| 阶段 → 模块显式映射 | **DONE** | 修掉了「用序号推断文件名」的老 bug |
| 默认 build 不破坏平台产物 | **DONE** | 改为输出 `dist/preview` |
| 真机性能门禁 | **BLOCKED** | 无 GPU |

## 八、Showcase Demo（`echo-ferry` / 《回声摆渡》）

| 要求 | 状态 | 证据 |
|---|---|---|
| 真正可以玩 | **DONE** | 3 关；试玩策略玩家能打到第 3 关 |
| 完整开始与结束 | **DONE** | 菜单 → 3 关 → 结算（含失败教学文案） |
| 清晰操作引导 | **DONE** | 第 1 关 hint + 菜单操作说明 + 按钮文案 |
| 完整核心玩法 | **DONE** | 敲钟 → 残影 → 移动 → 接人 → 靠岸 |
| 至少一个独特机制 | **DONE** | 回声残影（会腐烂的地图）+ 回声暴露 + 记忆格 |
| 实际美术素材 | **DONE（程序化）** | 9 张矢量纹理，`art.ts` 生成；**已标注非 AI 生图** |
| 真实接入的音效 | **DONE** | 22 个 mp3 由 `gen_audio.py` 合成，游戏内实际播放 |
| 音乐状态变化 | **DONE** | 5 stem × 4 状态，`audio.ts` 运行时切换 |
| 动画与粒子反馈 | **DONE** | 21 条规则，实测触发 9 类效果 |
| 至少一个标志性时刻 | **DONE** | 记忆归零 → 全图熄灭 + 慢动作 + 心跳（`memory_empty` 事件，源码可定位） |
| 通过自动化测试 | **DONE** | QA 全绿 / 冒烟通过 / 试玩 0 错误 / 单文件版通过 |
| 通过 R2 终审 | **未做** | 不提交平台；`review_final` 与 `ship` 标为 skipped 并写明原因 |

## 九、汇总

| 状态 | 数量 |
|---|---|
| DONE | 49 |
| PARTIAL | 4 |
| BLOCKED | 4 |
| PLANNED | 2 |
| 未做（明确不做） | 1（R2 终审，因不提交平台） |

**PARTIAL 的 4 项**：蓝图与 DNA 强制一致性、混响/低通滤波、试玩种子系统、AI 图像审核前置条件。
**BLOCKED 的 4 项**：真机帧率、首包时间、YuE2 音乐、TTS 配音。
（AI 生图已从 BLOCKED 转为 DONE —— 之前探测 000 是因为 Comfy Desktop 没运行。）

# v3.0 升级路线图

> 目标：从「能生成完整游戏」升级为「能生成有原创创意、鲜明视觉身份、沉浸音频和优秀体验的游戏」。
> 原则：保留 v1/v2 全部成熟能力，只加不减；每个 Phase 独立可验证。

## 阶段划分与状态

| Phase | 内容 | 状态 | 验证方式 |
|---|---|---|---|
| P0 | 仓库审计与架构设计 | ✅ DONE | `docs/10-upgrade/repository-audit.md` |
| P1 | Creative Director + Creative DNA | ✅ DONE | `creative_forge.py` + 5 份 schema + 12 个测试 |
| P2 | Art Director + Visual DNA | ✅ DONE | `art_director.py` + `asset_forge` 真实读取 DNA |
| P3 | Audio Director + 自适应音乐 | ✅ DONE | `audio_director.py` + `gen_stems.py` + 模板 `audio.ts` |
| P4 | Animation Director + Game Juice | ✅ DONE | `juice_forge.py` + 模板 `events.ts`/`juice.ts` |
| P5 | Experience Designer + Playtest Agent | ✅ DONE | `experience_forge.py` + `playtest.py`/`playtest.mjs` |
| P6 | 统一事件系统 + 专项审核整合 | ✅ DONE | `specialist_review.py` + gate/state 集成 |
| P7 | Showcase Demo | ✅ DONE | `echo-ferry/`（可玩，QA/试玩通过） |
| P8 | 全面测试与文档 | ✅ DONE | 49 个 pytest + Node 构建/单文件版 |

## 依赖顺序（为什么这么排）

```
审计
 └─ schema_check + 5 份 schema ────┐
     └─ 创意模式库（6 类，带许可）  │
         └─ creative_forge ────────┴─► Creative DNA
                                          ├─► art_director ─► Visual DNA ─► asset_forge 读 DNA
                                          ├─► audio_director ─► audio.ts（运行时）
                                          ├─► juice_forge ─► juice.ts（运行时）
                                          └─► experience_forge ─► playtest ─► specialist_review
```

**关键判断：先做 P1。** 如果先做美术或音频，它们只能继续从蓝图的散字段取数，
等于把「四块各做各的」这笔债再欠一遍。

## 每个 Phase 的验收门槛

| Phase | 必须全绿 |
|---|---|
| P1 | 同一 idea 两次发散结果一致；5 方案结构距离 ≥3；DNA schema + 语义校验 0 错误 |
| P2 | 三套提案可区分；对比度全达标；`asset_forge` 的 spec 里 `visual_dna_applied` 全 true |
| P3 | 音乐状态配比互不相同；音频 QC 无缺失/削波/静音；`audio.ts` 在浏览器里能切状态 |
| P4 | 效果类型 ≥8；无同强度事件；闪屏 ≤1/s；源码里 `new JuiceDirector` 真实存在 |
| P5 | E1–E8 无 FAIL；试玩零错误、无卡死、首次正反馈 ≤30s |
| P6 | 六项专项审核无 FAIL/UNVERIFIED；`gate_check --stage ship` 能正确阻断 |
| P7 | `npm run build` / `standalone` / `test:standalone` 通过；QA 全绿；试玩能玩到第 3 关 |
| P8 | `pytest tests` 全绿；文档齐全 |

## 与原计划的偏差（如实记录）

| 原计划 | 实际 | 原因 |
|---|---|---|
| 用 Playwright | 用 `puppeteer-core` | 项目已有依赖，且模板 `shots.mjs` 一直用它；Playwright 需要额外下载浏览器（沙盒网络受限）。**能力等价，报告里不写 Playwright** |
| AI 生图做 Showcase 美术 | 程序化矢量绘制 | ComfyUI / RunningHub 均不可用（探测返回 000）。任务书允许「原创程序化素材，但必须如实标注」——已在 GDD / 报告 / feature-status 三处标注 |
| YuE2 生成 stem | `gen_stems.py` 程序化合成 | YuE2-Studio 未运行（8791 端口不通）。程序化 stem 反而更适合验证「同调同速可独立控音量」这个前提 |
| TTS 配音 | 字幕 | TTS 端点未配置（boss 尚未提供） |
| 真机帧率 | 未验证 | 本机无 GPU（SwiftShader），帧率门禁无法有效验证，已标注 BLOCKED |

## 下一阶段建议（v3.1）

1. **真机性能闭环**：把 `qa.mjs` 的帧率判定接上真机数据（或提供手动录入通道），补上唯一未闭合的门禁。
2. **生图通道回灌**：ComfyUI 可用时，用同一套 `visual-dna.json` 出图，验证「程序化 vs AI 生图」在同一 DNA 下是否视觉一致。
3. **创意库扩容**：目前 24 动词 / 16 原型 / 12 风格。目标 40 / 24 / 20，并加入「跨品类组合」的推荐权重。
4. **审核官自动化**：六项专项审核里 A3（截图色相）已程序化，下一步把「构图焦点」「视觉层次」也做成可测指标。
5. **旧项目迁移**：对 `slap-and-yeet` / `conveyor-panic` / `slime-whack` / `lighthouse-keep` 各跑一次 `migrate`，验证向后兼容不是纸面结论。

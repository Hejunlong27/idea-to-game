# 交付标准（delivery standards）

逐档验收。低档未通过不得进入高档。

> **验收范围 = 用户在 G0 选定的平台**。体积/帧率等硬指标一律取**选定平台中最严的一条**作为预算。

## 前置：平台确认（G0）

进入 L1 之前必须满足：

- [ ] 已向用户输出技能支持的平台清单
- [ ] 用户已明确回复目标平台（`delivery.platforms` 非空）
- [ ] `delivery.platform_confirmed: true`
- [ ] `docs/00-platforms/platform-plan.md` 已产出，含全程体积预算与投递顺序
- [ ] 若含 `taptap`，已提醒前置备案周期；若含 `poki`，已提醒需准备 3 张实机截图；若含 `gamedistribution`，已提醒需做差异化版本

## L1 · 可玩（Playable）

> 目标：证明这个玩法成立。素材可以是几何占位。

- [ ] `npm run dev` 启动零报错，浏览器打开即玩
- [ ] 完整闭环：开始 → 游玩 → 结束 → 重开
- [ ] 计分或进度系统生效，数值随玩法正确变化
- [ ] 核心操作在桌面端（鼠标 + 键盘）可用
- [ ] 游戏状态机无卡死：结束态可回到开始态
- [ ] `state.yaml` 中 `core_loop.self_test: playable`

## L2 · 可交付（Shippable）

> 目标：一个看起来是成品的游戏。

### 视觉
- [ ] 美术风格与参考图一致（主色板色相偏差在可接受范围）
- [ ] 所有素材来自同一 `style_tokens`，无风格跳脱的素材
- [ ] 图集打包完成，无散落小图（受文件数限制约束）

### 音频
- [ ] BGM 可无缝循环，切换场景不爆音
- [ ] 关键动作有 SFX（至少：成功、失败、交互）
- [ ] 音频总体积 ≤ 2MB

### 交互
- [ ] 移动端触摸可玩
- [ ] 竖屏或横屏至少一种方向可用，且与 `scope.json` 的 `orientation` 一致
- [ ] 有 juice：屏震 / 缓动 / 粒子 / 命中反馈（至少两项）
- [ ] 难度曲线与 GDD 描述一致

### 工程
- [ ] 存档可用（localStorage 或平台云存档），刷新后进度保留
- [ ] 控制台零报错、零未捕获异常
- [ ] `src/game/` 内无平台 SDK 引用
- [ ] **首包满足选定平台中最严的红线**（`delivery.size_budget_mb`）
- [ ] 总文件数 ≤ 1500
- [ ] 构建产物全部相对路径
- [ ] 4GB 内存基准下稳定 60fps

## L3 · 可过审（Submittable）

> 目标：能直接提交**用户选定的那些平台**。

### 前置：审核官终审通过（不可跳过）

- [ ] `docs/09-review/verdict-r2.json` 存在，且 `verdict` ∈ {`PASS`, `PASS_WITH_DEVIATIONS`}
- [ ] R0（`review_plan`）与 R1（`review_graybox`）阶段状态均为 `done` —— **审核环节一个都不能跳**
- [ ] `manual-checks.json` 无未填条目
- [ ] 所有 `blocker` 级问题单状态为 `fixed`
- [ ] `rounds.md` 已记录全部轮次
- [ ] 交付报告含明确的 CrazyGames 标准结论行（三选一，措辞不得模糊）

### 平台交付
- [ ] `scripts/precheck.py` 对**每个选定平台**分别自检、全部全绿
- [ ] **交付包平台范围与 `delivery.platforms` 完全一致**（不多不少）
- [ ] 每平台独立 zip，解压后本地可直接运行
- [ ] 每个 zip 内含正确的适配层标识（`i2g-platform:<key>`），无 `i2g-platform:mock`
- [ ] SDK 集成正确：`gameplayStart` / `gameplayStop` 事件在正确时机触发（TapTap 不强制）
- [ ] 广告调用有失败降级（广告拦截器场景下游戏照常可玩）
- [ ] iOS 音频恢复逻辑已实现：在 `touchend` / `click` 回调内调用 `audioContext.resume()`
- [ ] `body` 已加 `user-select: none`（含 -webkit/-moz/-ms 前缀）
- [ ] Chrome 与 Edge 实测通过
- [ ] 商店素材齐备：标题 ≤60 字符、简短描述 ≤120、详细描述 ≤500、3 张实机截图（PNG/JPEG/WebP，单张 ≤5MiB）
- [ ] 隐私政策页面（若收集任何数据）
- [ ] 素材版权链清晰，AI 生成素材保留生成记录
- [ ] **国内平台专项**：TapTap 小游戏前置备案已完成；广告位已在 Dirichlet 创建并拿到 `adUnitId`

## 最终交付报告

交付时输出一份汇总，至少包含：

1. 项目名与一句话玩法
2. 达到的档位（L1/L2/L3）
3. 各平台 zip 路径
4. 实测数据：首包体积、文件数、帧率
5. **降级项清单**（`status: degraded` 的阶段及其影响）
6. 未通过项与原因
7. 建议的下一步（提交哪个平台、需要补什么）

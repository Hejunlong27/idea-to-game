# CrazyGames 审核底线标准（审核官的唯一判据）

> 本文件是**审核官角色的唯一判据**。所有判定必须引用本文件的条目编号。
>
> 来源：CrazyGames 官方文档（2026-10 核实）
> - Requirements: `https://docs.crazygames.com/requirements/intro`
> - Gameplay: `https://docs.crazygames.com/requirements/gameplay`
> - Quality Guidelines: `https://docs.crazygames.com/requirements/quality`
> - Advertisement: `https://docs.crazygames.com/requirements/ads`
> - Technical: `https://docs.crazygames.com/requirements/technical`
> - Basic Launch Guide: `https://docs.crazygames.com/resources/basic-launch-metrics/`
>
> **本底线不可因用户选择其他平台而降低。** 若其他平台在某一维度更严，取更严者。

## 判定规则

每条目两种标记：

| 标记 | 含义 | 未通过时的后果 |
|---|---|---|
| **REQ** | CrazyGames 官方**必需**要求 | **一律阻塞**，必须修复后复审，**永不豁免、永不降级** |
| **GUIDE** | 官方**建议**（Guideline，非强制） | 不影响"达到必需标准"的结论，但**必须逐条记录为已知偏离**，并给出改进计划 |

单条判定三态：`PASS` / `FAIL` / `NA`（不适用须写明理由）。

---

## A. 玩法可玩性（Playability）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| A1 | REQ | 游戏无报错、无崩溃，能连续完成完整游玩 | "play seamlessly without errors or crashes" |
| A2 | REQ | 玩法**原创**：名称、素材、整体内容具备原创性 | "Game names, assets, and overall content should exhibit originality" |
| A3 | REQ | 名称/图标/描述与实际玩法一致，不误导；名称唯一可辨（不得直接用通用词，如只叫 "Chess"） | Quality: "not easily confused…", "clear about what it is" |
| A4 | REQ | 不使用他人 IP（除非自有） | "does not use a common identifier unless the developer owns the IP" |
| A5 | REQ | 品类/核心特性在提交后不发生大幅变更 | "Major features such as the game's genre should not change after submission" |
| A6 | REQ | 新用户直接进入玩法；**最多 1 次点击** | "land new users in gameplay immediately… maximum of 1 click is allowed" |
| A7 | GUIDE | 无过度重复或无聊的机械化任务 | "no overly repetitive or 'boring' tasks" |
| A8 | GUIDE | 目标清晰：玩家始终知道下一步做什么 | "clear goals that the player can reach" |
| A9 | GUIDE | 不同玩家群体都能获得乐趣 | "Various player segments can enjoy the game" |
| A10 | GUIDE | 游戏信息处理迅速，流程顺畅连续 | "processes information quickly… smooth flow and continuity" |
| A11 | GUIDE | 便于后续扩展内容（新关卡/美术/剧情） | "easy to improve or modify the game to add new content" |
| A12 | GUIDE | 单人玩法与多人玩法同等醒目；若不支持单人须明确说明 | Quality: solo play / with friends |

## B. 核心循环（Core Loop）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| B1 | REQ | 完整闭环可跑通：开始 → 游玩 → 结束 → 重开，无死状态 | Gameplay REQ |
| B2 | REQ | 响应及时：玩家操作到画面/音效反馈 **≤100ms** | "responds quickly to the player's actions" |
| B3 | GUIDE | 难度曲线存在且可描述（非随机噪声），挑战与节奏平衡 | "challenge, strategy… balanced and well-paced" |
| B4 | GUIDE | 会话平均游玩时长目标 **≥10 分钟** | CG KPI: "10+ minutes of average play time" |
| B5 | GUIDE | 有进度感：等级 / 解锁 / 升级 / 最高分至少一项 | "Add meaningful progression" |
| B6 | REQ | 存档生效，刷新/重进不丢进度 | "Save player progress: Lost progress means lost players" |
| B7 | GUIDE | 有回访钩子（每日奖励、每日任务等） | CG KPI: "Create daily hooks" |
| B8 | GUIDE | 新机制渐进引入，避免一次性灌输 | "Introduce new mechanics gradually" |

## C. 操作与引导（Controls & Onboarding）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| C1 | REQ | 引导**在玩法内**完成，聚焦核心操作，不逐一解释所有功能 | Quality: Onboarding |
| C2 | REQ | 引导**可跳过** | "Make the onboarding phase skippable" |
| C3 | REQ | 操作直观，在桌面/移动等不同设备上都成立 | "intuitive controls on different types of devices" |
| C4 | REQ | 按钮标签清晰表明如何继续 | "Buttons are clearly labeled" |
| C5 | REQ | 按钮**不得**延迟以困惑用户或诱导行为 | "Buttons do not have delays to confuse users or encourage other behaviors" |
| C6 | REQ | 按钮**不得**放大尺寸以诱导广告或其他行为 | "not sized to encourage ads or other behaviors" |
| C7 | REQ | 避开受限键：`Escape`（会退出全屏）、`Ctrl/Cmd + W`（会关标签页） | Quality: Restricted Keys |
| C8 | GUIDE | 键位适配键盘布局（如法语 AZERTY 的 WASD→ZQSD） | "key bindings adapt to the user's keyboard layout" |
| C9 | GUIDE | 视觉优先、少用文字做引导 | "Prioritize visuals and limit the use of text" |
| C10 | GUIDE | 提供操作提示（键盘覆盖图 / 鼠标手势演示） | "keyboard overlay or mouse gestures" |
| C11 | GUIDE | 全程操作一致，无中途换键 | "controls are consistent and intuitive throughout" |

## D. 画面与音频（Visual & Audio）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| D1 | REQ | 文字与图像在 **devicePixelRatio:1** 下清晰可读 | Gameplay REQ: "Readable Content" |
| D2 | REQ | 在 CG 全部 iframe 尺寸下内容可读（尺寸清单见 F1） | 同上 |
| D3 | REQ | 美术风格内部一致，不在写实↔卡通、高分辨率↔低分辨率之间跳变 | "aesthetic style should remain consistent and not switch between looks" |
| D4 | REQ | 无图形缺陷（如压缩伪影） | "free of graphical defects like compression artifacts" |
| D5 | REQ | 分辨率全游戏一致 | "consistent resolution throughout the game" |
| D6 | GUIDE | 音频电平一致，不过响也不过轻 | "Audio levels are consistent. Sounds aren't too loud or quiet" |
| D7 | GUIDE | 音乐与视觉体验互补 | "Any music in the game complements the visual experience" |
| D8 | GUIDE | 整体审美令人愉悦、画面精致 | "Graphics should be of high quality… visually pleasing" |

## E. 加载与性能（Loading & Performance）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| E1 | REQ | 总文件大小 ≤50MB（**未接 SDK**）／≤250MB（已接 SDK） | Requirements: Technical |
| E2 | REQ | 文件数 ≤1500 | 同上 |
| E3 | REQ | 首包 ≤50MB；**KPI 目标 ≤20MB** | Technical + CG KPI "build size below 20 MB" |
| E4 | REQ | 物理表现在不同刷新率（144Hz / 165Hz）下**一致** | "physics must perform consistently across different monitor refresh rates" |
| E5 | REQ | 加载快、无错误、无崩溃 | "must load quickly and play seamlessly without errors or crashes" |
| E6 | GUIDE | 加载到可玩 **≤10 秒** | CG KPI "load in under 10 seconds" |
| E7 | GUIDE | 玩法转化率设计目标 **≥80%**（开始 1 分钟后仍在玩） | CG KPI "convert 80%+ of players" |
| E8 | GUIDE | 首帧尽快出现，砍掉长开场/logo 动画 | "Get to gameplay fast: Cut long intros" |
| E9 | GUIDE | 按需加载：先跑第一关，其余后台加载 | "Load content dynamically" |
| E10 | GUIDE | 4GB 内存基准稳定 60fps（内部验收线：平均 ≥58fps / 最低 ≥50fps） | Technical: Chromebook 4GB 要求 |
| E11 | GUIDE | 60 秒运行内存无持续增长（无泄漏） | 内部工程标准 |

## F. 兼容性与适配（Compatibility & Responsive）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| F1 | REQ | 以下全部 iframe 尺寸下布局与文字正常（16:9）：`907×510`、`1216×684`、`1077×606`、`821×462`、`1366×768`、`1920×1080`、`1536×864`、`1280×720`、`800×450`（移动）、`1080×607`（平板） | Gameplay REQ 原文清单 |
| F2 | REQ | 支持鼠标、键盘；若支持移动则必须支持触摸 | Technical: Device & browser |
| F3 | REQ | 全屏模式正常；**禁止自定义游戏内全屏按钮** | "Custom in-game fullscreen buttons are prohibited" |
| F4 | REQ | 无跨推广（cross-promotion） | Gameplay REQ: "No Cross-Promotion" |
| F5 | REQ | **App Store 链接绝不出现在游戏内**（须用开发者后台的元数据字段） | "App Store links are never allowed in-game" |
| F6 | REQ | Chrome 与 Edge 实测可用 | Technical: "expect games to work on Chrome and Edge" |
| F7 | REQ | `body` 已加 `user-select: none`（含 -webkit/-moz/-ms 前缀） | Technical 移动端专项 |
| F8 | GUIDE | 竖屏游戏在桌面端可用（两侧留黑边或背景） | Technical: 竖屏允许条件 |
| F9 | GUIDE | 界面针对用户设备设计（桌面优先，移动可选） | Quality: "designed for the user's device" |
| F10 | GUIDE | 全屏模式下 `Ctrl/Cmd + W` 可禁用 | Quality: Restricted Keys |

## G. 广告与变现合规（Ads & Monetization）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| G1 | REQ | **只允许通过 CrazyGames SDK 的广告**；无外部广告 | Ads: "Only Ads requested through the CrazyGames SDK are allowed" |
| G2 | REQ | 视频广告**不得打断玩法**，不得突然出现；只在关卡切换、死亡、地图切换等逻辑点 | "Video ads can not interrupt gameplay and shouldn't come as a surprise" |
| G3 | REQ | **禁止在导航按钮上触发中插广告**（主菜单图标、设置、商店等） | "Do not show a midgame ad on a navigational button" |
| G4 | REQ | 广告请求/播放期间**游戏暂停**：禁用按钮或用 spinner 阻断交互，直到 `adFinished` 或 `adError` | "Block the UI until either an adFinished or adError event occurs" |
| G5 | REQ | 广告播放时游戏静音，结束恢复；**仅在广告真正开始播放时静音**（不是一请求就静音） | "Only mute the audio when the ad actually starts playing" |
| G6 | REQ | 正确处理 `adError`（未填充），游戏必须继续 | "Handle unfilled ad calls correctly" |
| G7 | REQ | **不链式播放多个广告** | "Chain multiple ads" 被明令禁止 |
| G8 | REQ | 激励视频**不得出现在活跃玩法屏幕**上 | "should not appear on an active gameplay screen" |
| G9 | REQ | 激励视频不得过于频繁（需计时器或隐藏请求按钮） | "Do not offer a rewarded ad too often" |
| G10 | REQ | 激励视频的「跳过」与「观看」按钮**同尺寸、同字体、同颜色**；不得隐藏或延迟跳过键 | Ads: Reward UI |
| G11 | REQ | 须明确标示「观看广告换取奖励」（如视频图标）+ 提供替代获取途径 | Ads: Reward UI |
| G12 | REQ | `adFinished` 后给出明确的奖励反馈；`adError` 时**不发奖** | Ads: Rewarded ads callbacks |
| G13 | REQ | **不得**将「关卡间中插广告」与「看激励视频续玩本关」叠加 | "It's not allowed to combine a midgame ad between levels with a rewarded to keep playing" |
| G14 | REQ | 不得设计成「只能靠看广告才能过关」 | "Poorly designed levels that can only be completed by a rewarded ad are not acceptable" |
| G15 | REQ | Banner 仅在平均停留 ≥5 秒的有用界面；不遮挡 UI；不在玩法中显示；同屏 ≤2 个；与游戏内容明确区分 | Ads: In-game banner ads |
| G16 | REQ | **广告拦截器用户必须能正常游玩，不得给予劣势**；被限制的功能须提示（用非弹窗方式）；不得保留可点但无效的激励广告按钮 | Ads: Adblockers |
| G17 | REQ | **Basic Launch 阶段**：广告被禁用时游戏也必须正常运行（否则拒审）；不得出现无效果的激励广告按钮 | Ads: Warning |
| G18 | REQ | 内购（若适用）：仅用 CrazyGames Xsolla 账号与 SDK 的 `userId`；内购为 **Invite Only** | Requirements: In-game Purchases |

## H. 平台技术规范（Platform Technical Specs）

| 编号 | 级别 | 判定条件 | 判据来源 |
|---|---|---|---|
| H1 | REQ | 构建产物**全部相对路径**，无根绝对路径引用 | Technical: "Use only relative paths" |
| H2 | REQ | SDK 集成（Full 阶段）：`gameplayStart` / `gameplayStop` 在正确时机触发 | Technical: Full SDK Integration |
| H3 | REQ | **iOS 音频恢复**：在 `touchend` / `click` 回调内调用 `audioContext.resume()`（仅监听 visibilitychange 无效） | Technical: Resuming audio after iOS interrupts it |
| H4 | REQ | 提供**英文**本地化；若有翻译须准确高质量；按 SDK `locale` 切换，无则回退英文 | Gameplay REQ: Language Support |
| H5 | REQ | PEGI 12 合规（CG 面向 13+ 受众） | Gameplay REQ: "Suited for minors… PEGI 12 compliant" |
| H6 | REQ | 账号集成（若适用）：无外部登录选项；进度绑定 CG 账号；使用 CG 用户名与头像；CG 用户自动登录 | Requirements: Account integration |
| H7 | REQ | 多人（若适用）：房间信息、邀请链接、即时开局流程、回合间保留房间、`DisableChat` 偏好 | Requirements: Multiplayer |
| H8 | REQ | 若采集 SDK 事件之外的额外个人数据，须向新玩家提供条款/隐私政策提示（建议用简单提示而非阻断式弹窗） | Technical: User Consent |
| H9 | REQ | 提交时提供定性元数据（游戏描述、操作说明）与游戏封面素材 | Requirements intro |
| H10 | GUIDE | 跨推广的允许例外：隐私政策/条款；菜单上的社区链接（不得直通可玩网页版）；仅桌面游戏在主菜单或 demo 结束时的商店链接；CG 首页/分类回链（不推广）；同系列游戏链接 | Gameplay REQ 例外条款 |

---

## 被明令禁止的设计（出现即 REJECTED，无讨论空间）

1. 外部广告或非 CG SDK 的广告
2. 自定义游戏内全屏按钮
3. 跨推广（推广其他游戏或平台）
4. 游戏内出现 App Store 链接
5. 广告打断玩法 / 在导航按钮上弹广告 / 链式广告
6. 阻止或惩罚广告拦截器用户
7. 「只能靠看广告才能过关」的关卡设计
8. 激励视频的跳过按钮被隐藏或延迟
9. 复用他人 IP 的名称或标识
10. 提交后大幅变更游戏品类

## 版本管理

平台政策会变。每次使用本底线前，先确认是否需要重新核对官方文档；
若平台更新，**只更新本文件**，审核脚本与模块会自动跟随（条目编号即契约）。

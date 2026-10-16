# 平台要求（platform requirements）

各平台硬红线。构建、审计、打包环节必须对照本文件。

> 数据核实时间：2026-10-16。平台政策会变，每次打包前建议重新核对官方文档。

## 官方文档入口

| 平台 | 文档 | 开发者后台 |
|---|---|---|
| CrazyGames | `https://docs.crazygames.com/` | `https://developer.crazygames.com/` |
| Poki | `https://developers.poki.com/` | 同上（提报制表单） |
| GameDistribution | `https://gamedistribution.com/developers/` | 同上 |
| Playgama | `https://wiki.playgama.com/` | 同上 |

## CrazyGames（首发推荐）

### 体积与文件数
- 总文件大小 **≤ 250MB**
- 文件数 **≤ 1500**
- **首包 ≤ 50MB**；**移动端首页资格要求首包 ≤ 20MB**
- 集成 SDK 后，首包体积 = 从加载开始到首个 `gameplay start` 事件之间的下载量（因此该事件必须在真正进入可玩状态时触发，不含菜单与额外加载）
- 未集成 SDK 时按总文件大小计算
- 外部托管资源按「到达可玩状态耗时 ≤ 20 秒」评估

### 路径
- **只允许相对路径**，绝对路径会加载失败

### 设备与浏览器
- 必须支持 Chrome 与 Edge；Safari 表现差会被单独禁用
- 大量用户使用 Chromebook，4GB 内存下不流畅会被禁用
- 桌面端支持鼠标 + 键盘；支持移动则需支持触摸
- 桌面端横屏游玩；竖屏游戏可发布（两侧留黑边或背景图）

### 移动端专项
- 首包 ≤ 20MB 才进移动端首页
- 方向由平台配置，开发者无需自己锁方向
- `body` 必须加：
  ```css
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  user-select: none;
  ```
- Unity 游戏 iOS 默认禁用（内存崩溃），达标后才评估开启
- iOS 音频恢复：AudioContext 在 iOS 会进入 `interrupted`，**必须在 `touchend` 或 `click` 回调内调用 `resume()`**；只监听 `visibilitychange` 无效
  ```js
  document.addEventListener("touchend", () => {
    if (audioContext && audioContext.state === "suspended") audioContext.resume();
  });
  ```
  已知 Howler（`Howler.ctx`）与 PlayCanvas（`pc.app.soundManager.context`）有此问题

### SDK 与变现

**SDK script 标签**（需在提交前对照官方文档核对，平台可能更换 CDN）：

```html
<script src="https://sdk.crazygames.com/crazygames-sdk-v3.js"></script>
```

模板已在 `vite.config.ts` 的 `SDK_SCRIPTS` 中配置按构建模式自动注入。

- **Basic Launch**（7–21 天，需 ≥500 plays 触发评估）：只需基础实现，轻量 QA，**广告禁用**，无收入
- **Full Launch**：需完整实现（`gameplayStart/Stop`、Data 模块存档、User 模块账号），Full QA，开启分成
- Basic 阶段即使接了广告也会被禁用
- Sitelock 需白名单 CrazyGames 的多个域名及其 App 独立域名

### 提交流程
1. `developers.crazygames.com` 登录 → Submit Game
2. 上传 zip，页面自动解析并做基础校验
3. 填写 Game Info：标题（≤60 字符）、简短描述（≤120）、详细描述（≤500）
4. 可用官方 Preview 工具先自测

### 支持的引擎
Unity、Defold、Godot、Phaser、PlayCanvas、Construct、Pixi.js、BabylonJS、GameMaker、Cocos、GDevelop、Wonderland 等。

## Poki

- 体量：1 亿月活、10 亿+ 月游戏次数、500+ 开发者
- **提报制**：需提交表单，附可玩构建链接（无需登录即可访问）或玩法视频 + 3 张实机截图（PNG/JPEG/WebP，单张 ≤5MiB）
- 需先阅读并遵守 Content & Brand Guidelines
- 表单要求说明所用引擎；官方选项包含 Unity / Godot / Construct / Cocos Creator / Phaser / PlayCanvas / Defold / 自研 / ThreeJS / AI 生成 / 其他
- **官方 Phaser 插件 `@poki/phaser-3` 仅支持 Phaser 3**（最近维护 2026-05），自动处理 SDK 注入、loading 事件、`gameplayStart/Stop`、广告期间禁输入禁音
- SDK 核心调用：`PokiSDK.init()`、`gameLoadingFinished()`、`gameplayStart()`、`gameplayStop()`、`commercialBreak()`、`rewardedBreak()`、`setDebug(true)`

**SDK script 标签**：

```html
<script src="https://game-cdn.poki.com/scripts/v2/poki-sdk.js"></script>
```

注意：`PokiSDK.init()` 是回调式（非 Promise），模板适配器中已用 Promise 包装并加了 3 秒兜底超时，避免 SDK 不回调时游戏卡死。

## GameDistribution

- 体量：3.5 亿月游戏次数、105 国、3000+ 发布商
- **SDK 强制集成**（否则不予上线）
- 审核最长 **3 周**
- **不允许目录中出现同款游戏** —— 同一款游戏投多个平台前需做差异化
- 提交前自查：无同款、不侵犯 IP、游戏与宣传素材设计干净清晰
- 变现：pre-roll / mid-roll / rewarded 广告分成

## Playgama

- 体量：4.5 亿月触达
- 免费统一 SDK（Playgama Bridge，MIT），一套 SDK 覆盖 25+ 平台：Playgama、Microsoft Store、Facebook、YouTube Playables、Discord、Huawei、Xiaomi、Reddit、MSN、Y8、Lagged、GameDistribution、CrazyGames、Playhop、Yandex Games、Poki
- 支持引擎：Unity、Godot、Construct 3、GDevelop、GameMaker、Defold、Cocos Creator、Scratch、Plain JS（含 Phaser / PlayCanvas / LayaAir）
- **注意**：Playgama 不代发 Poki 与 CrazyGames，这两个需用各自 SDK 直接提交
- **SDK 接入方式**：Playgama Bridge 通常通过 script 标签挂到 `window.bridge`。模板的适配器只读取 `window.bridge`，不做网络请求 —— 目标是 Playgama 时需自行在 `index.html` 加入 Bridge SDK 的 script 标签，或 `npm i @playgama/bridge` 后改为静态 import
- 发布后进入分发网络，伙伴通过可分享链接嵌入

## 平台投递顺序建议

1. **CrazyGames Basic Launch** —— 门槛最低，7–21 天拿真实数据
2. **Playgama** —— 一次上传铺量长尾，零额外成本
3. **Poki** —— 准备截图与文案后提报，价值最高
4. **GameDistribution** —— 做差异化版本后提交（避免同款判定）

**不要第一天把同一份包全平台投递**：GD 拒收同款，CG/Poki 常有首发或独家窗口要求。

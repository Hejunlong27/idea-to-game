# 模拟器品类模板（Simulator）

IdeaToGame 的**品类模板**——回合制 + 数值系统 + 事件选择。默认实例是**修仙模拟器**，
但结构对炒股 / 家族 / 经营 / 养成类同样成立：**换主题只改 `content/*.json`，逻辑一行不动。**

## 核心抽象（这四样构成所有模拟器）

| 概念 | 作用 | 在哪 |
|---|---|---|
| 回合 | 每次行动推进一年/一天/一代 | `sim.ts` 的 `applyAction` |
| 属性 | 修为/灵石/心境 → 股价/现金/持仓 → 声望/子嗣/家产 | `config.ts` 的 `startStats` + `content` 里的 effects |
| 行动 | 玩家每回合的选择，可带前置条件与风险 | `content/actions.json` |
| 事件 | 概率触发、多选项、带后果 | `content/events.json` |
| 阶段 | 境界/等级/世代，达门槛自动晋升并延寿/加成 | `content/stages.json` |

## 它已经包含什么

- 5 个行动（打坐/采药/历练/休整/炼丹），含**前置条件**（钱不够不能炼丹）与**概率风险**（历练有 35% 受伤）
- 6 个事件（老者/妖兽/秘境/同门/心魔/商人），含**触发门槛**（秘境要修为 50、心魔要心境 ≤40）
- 5 个境界（炼气→筑基→金丹→元婴→化神），突破**累加寿元**，支持一次连跳多级
- 属性 clamp（心境 0–100，其余不为负）、寿元耗尽结算与评级
- **结局收集**：5 种结局（按最终境界），结算显示「已收集 X / 5」，这是重玩动机的核心
- **存档**：最高境界、已收集结局、游玩局数
- **新手引导**：首次进入提示「选一个行动」，做出第一个行动后消失
- 10 条确定性测试用例，**全部无 `wait`**

## 改成自己的模拟器

| 想做 | 改哪里 |
|---|---|
| 炒股模拟器 | `startStats` 换成 `{cash, shares, price, day}`；行动换成「买入/卖出/观望」；事件换成财报/黑天鹅 |
| 家族模拟器 | `startStats` 换成 `{generation, members, reputation, wealth}`；阶段换成「世代」 |
| 换行动 | `content/actions.json`（effects 用属性名，require 写门槛） |
| 换事件 | `content/events.json`（weight 控制频率，require 控制触发条件） |
| 换成长阶段 | `content/stages.json`（qiMin 换成任意属性的门槛字段需同步改 `tryBreakthrough`） |
| 调平衡 | `config.ts` 的 `startStats` / `eventChance` |

> `tryBreakthrough` 目前硬编码看 `qi`。换成别的属性名时，把那一处改成读 `SIM.growthStat` 即可。

## 测试

```bash
node scripts/scenario.mjs --serve          # 10 条用例
node scripts/scenario.mjs --serve --repeat 3   # 确定性验证（同 seed 必须同结果）
```

实测：10/10，三轮 30/30 稳定。**单条 170–370ms，无一个用例需要等待动画** ——
回合制玩法没有帧循环，`exec` 完全同步，这是模拟器品类测试比动作类稳的根本原因。

## 确定性怎么保证

`sim.ts` 不调 `Math.random()`，随机数由 `hashRand(seed, turn, salt)` 哈希得出。
同一 seed + 同一操作序列 → 必然同一结果。所以平衡调整可以回放对比，测试失败可以精确复现。

## 已知取舍

- **不含音频资源**：`audio.play()` 静默降级，跑 `audio_forge` 后自动生效。
- **单线叙事**：没有剧情分支树，事件是独立抽取的。要做长线剧情需在 `events.json` 加 `chain` 字段。
- **无存档**：一局约 60 回合，重开成本低。要长线进度需接 `PlatformBridge.save`。
- **无立绘**：默认纯文字面板。接 AI 生图后在 `art.ts` 补 `TEXTURES`，`BootScene` 的 IMG_KEYS 映射同名键。

---

## 通用命令


## 命令

```bash
npm install
npm run dev                 # 本地开发（mock 适配器）
npm run build:cg            # → dist/crazygames
npm run build:poki          # → dist/poki
npm run build:gd            # → dist/gamedistribution
npm run build:pg            # → dist/playgama
npm run build:taptap        # → dist/taptap
npm run build:all           # 全部（仅在确实要全平台时才用）
npm run zip:all             # 打成 dist/<platform>.zip
npm run serve:cg            # 起本地 HTTP 预览 dist/crazygames（默认 5199 端口）
npm run standalone          # 打「双击即玩」单文件 HTML → dist/standalone.html
npm run test:standalone     # 回归测试 file:// 下的两种情形
npm run shots               # 实机截图 → docs/07-qa/screenshots/（商店素材必需）
```

> ⚠️ **只构建用户选定的平台**，不要默认 `build:all` —— 未选定的平台产物会被
> `gate_check.py --stage ship` 判为「超出交付范围」。

## ⚠️ 不能双击 index.html（两次踩同一个坑，已从源头修）

构建产物是**外部 ES module**（`<script type="module" src="./index.js">`）。浏览器在 `file://` 下
会以 CORS（origin 为 `null`）为由**拒绝执行它，而且不报任何错** —— 页面就永远停在 `Loading…`，
看起来像卡死。同理，Phaser 加载器对图片 / 音频 / JSON 的 XHR 在 `file://` 下也会失败。

三种正确姿势：

| 想做什么 | 怎么做 |
|---|---|
| 本地看效果 | `npm run serve:cg`，然后开 `http://127.0.0.1:5199` |
| 双击即玩 / 发给别人看 | `npm run standalone` → 打开 `dist/standalone.html`（JS 内联 + 资源全变 data URI，零外部请求） |
| 提交平台 | 用 `dist/<平台>/` 或 `<平台>.zip`，平台自己会起 HTTP |

**已内置的两道防线**：

1. `index.html` 里的**启动看门狗**：`file://` 直开、脚本抛异常、8 秒未就绪，都会在页面上打印
   可操作的中文/英文提示，而不是静默停在 Loading。它依赖 `BootScene.create()` 里的
   `window.__bootDone = true`，**不要删那个标记**。
2. `scripts/test-standalone.mjs`：自动断言「单文件版在 file:// 下能跑」+
   「常规产物在 file:// 下会给出提示」。改完构建配置记得跑一次。

> 项目落地后，请把 `test-standalone.mjs` 的断言补成真实交互（进关卡 + 点一下真的生效）——
> 「能显示菜单」不等于「能玩」。

## 目录职责

| 路径 | 职责 |
|---|---|
| `src/types.ts` | 共享类型。`PlatformBridge` 接口定义在此 |
| `src/platform/` | 各平台适配器 + 工厂。**平台差异只允许出现在这里** |
| `src/game/` | 纯玩法逻辑。**禁止 import `src/platform/`** |
| `src/game/config.ts` | 全部可调数值。P3 调参只改这里；`ANIM` 配帧动画 |
| `src/game/anim.ts` | 帧动画：从图集注册 `<key>_loop`，`playFrames(sprite, key)` 播放 |
| `src/game/scenes/` | 场景：Boot / Menu / Play / GameOver |
| `src/game/util.ts` | 从 registry 取平台实例、存档读写、缩放工具 |
| `scripts/zip-all.mjs` | 打包脚本 |
| `scripts/serve.mjs` | 本地静态 HTTP 服务（预览用，产物不能双击打开） |
| `scripts/build-standalone.mjs` | 把构建产物内联成单文件 HTML（双击即玩） |
| `scripts/test-standalone.mjs` | file:// 启动行为回归测试 |
| `scripts/shots.mjs` | 实机截图（系统 Chrome + puppeteer-core），顺带收集控制台错误 |
| `vite.standalone.config.ts` | 单文件版的构建配置（资源全部内联成 data URI） |
| `index.html` | 含启动看门狗：启动失败必须给出可操作提示，不得静默停在 Loading |

## 平台适配器

| 文件 | 平台 | SDK 来源 |
|---|---|---|
| `mock.ts` | 本地开发 | 无 |
| `crazygames.ts` | CrazyGames | `sdk.crazygames.com`（script 注入） |
| `poki.ts` | Poki | `game-cdn.poki.com`（script 注入） |
| `gamedistribution.ts` | GameDistribution | `html5.api.gamedistribution.com`（script 注入） |
| `playgama.ts` | Playgama | 读 `window.bridge`，需自行加 script 或装 npm 包 |
| `taptap.ts` | TapTap | 读宿主注入的全局 `tap`；网页游戏形态无 SDK 时自动降级 |

每个适配器的 `name` 形如 `i2g-platform:<key>` —— `precheck.py` 靠这个标识判定构建产物里注入的是哪个平台。

## 契约

1. `src/game/` 内**不得**出现平台 SDK 引用。需要平台能力时用 `util.ts` 的 `bridge(scene)`。
2. 平台实例由 `src/main.ts` 通过 `game.registry.set('platform', ...)` 注入。
3. 所有 SDK 调用必须 try/catch，失败时静默降级 —— 广告拦截器场景下游戏必须照常可玩。
4. 构建产物必须全部相对路径（`vite.config.ts` 已设 `base: './'`）。

## 替换为真实玩法

模板自带「点靶子」占位玩法，用于验证工程链路。执行 `modules/04-core-loop.md` 时：

1. 按 GDD 重写 `src/game/scenes/PlayScene.ts`
2. 更新 `src/game/config.ts` 的数值
3. 保留 `bridge(scene).gameplayStart() / gameplayStop()` 的调用时机
4. 保留 `src/game/util.ts` 的存档读写

## 接入正式素材

`modules/06-sprite-tools.md` 产出图集后：

1. 把 `atlas.png` / `atlas.json` 放到 `assets/atlas/`
2. 在 `src/game/config.ts` 中设 `ASSETS.useAtlas = true`
3. `BootScene.preload()` 会自动加载图集
4. 把场景中的 `'ph_target'` 换成图集帧名（如 `'game', 'fruit_1'`）

## 平台 SDK 注入

`vite.config.ts` 顶部的 `SDK_SCRIPTS` 常量按构建模式把平台 SDK 的 script 标签注入 `index.html`：

| mode | 注入的 SDK |
|---|---|
| `crazygames` | `https://sdk.crazygames.com/crazygames-sdk-v3.js` |
| `poki` | `https://game-cdn.poki.com/scripts/v2/poki-sdk.js` |
| `gamedistribution` | `https://html5.api.gamedistribution.com/main.min.js` |
| `playgama` | 留空 —— 需自行加入 Bridge SDK script，或改用 npm 包静态 import |
| `taptap` | 留空 —— Tap 小游戏 SDK 由 TapTap 容器注入全局 `tap`，**自行引入会被判违规** |
| 其他（dev） | 不注入 |

⚠️ **提交前必须对照平台官方文档核对这些 URL**，平台可能更换 CDN 地址。核对方式：

```bash
npm run build:cg && grep -o 'sdk.crazygames.com[^"]*' dist/crazygames/index.html
```

## 新增平台

1. 新建 `src/platform/<name>.ts`，实现 `PlatformBridge`，`name` 设为 `i2g-platform:<name>`
2. 在 `src/platform/index.ts` 的 `PLATFORM_TARGETS` 与 **if 链**中注册（**不要用 switch**，见文件内注释）
3. 在 `package.json` 加 `build:<name>` 脚本
4. 在 `vite.config.ts` 的 `SDK_SCRIPTS` 中加该平台的 SDK URL（宿主注入型留空）
5. 在技能包的 `scripts/_common.py` 的 `PLATFORMS` 表登记红线参数
6. 在 `references/platform-requirements.md` 补充该平台要求

无需改动任何玩法代码。

# 塔防品类模板（Tower Defense）

IdeaToGame 的**品类模板**——不是空骨架，是一套已验证可玩的塔防核心循环 + 10 条确定性测试用例。
Phaser 3 + Vite + TypeScript，内置多平台适配层与 Game Test API。

## 它已经包含什么

| 能力 | 说明 |
|---|---|
| 两张地图 | 7×9 网格，路径由 `LEVELS[].path` 折线定义，相邻点必须共线 |
| 可建造判定 | 网格内 + 非路径 + 非基地，三条件缺一不可 |
| 三种塔 | 箭塔（单体）/ 炮塔（溅射）/ 冰塔（减速），颜色与数值都不同 |
| 塔升级 | 每座可升到 Lv3，伤害 ×1.45/级、射程 +0.12/级，费用递增 |
| 塔出售 | 返还累计投入的 60%，建错不用重开 |
| 三种敌人 | 小妖（基准）/ 甲兽（4 点护甲，逼你换塔）/ 疾影（2 倍速，低血） |
| 波次编排 | 每波用 `{ 敌人类型: 数量 }` 描述，按类型交替生成 |
| 战斗结算 | 护甲减伤（最低 1 点）、溅射 60% 波及、减速挂 1.5s |
| 打击反馈 | 伤害飘字（带偏移防重叠）、弹道线、击杀缩放、漏怪震屏 |
| 关卡推进 | 通关且有下一关 → 结算页显示「下一关」；失败重开本关 |
| 星级 | **看漏怪不看分数**：零漏怪 3 星、漏 ≤3 只 2 星、通关 1 星 |
| 存档 | 每关 `{ stars, best }`，只升不降；累计星数、最高分、引导完成标记 |
| 关卡解锁 | 第 1 关常开；之后每关需上一关通关（由 levels 推导，不单独存字段） |
| 新手引导 | 首次进关显示「点空地建塔」，建完第一座塔即消失并写入存档 |
| 确定性测试 | **17 条用例**，全部断言逻辑状态（不是像素） |
| 可驱动测试接口 | `window.__test`，仅 DEV 生效，发行包不存在 |

## 改造成自己的塔防

| 想改什么 | 改哪里 |
|---|---|
| 加地图 | `config.ts` 的 `LEVELS` 追加一项（path + waves + 起始资源） |
| 波次强度 | `LEVELS[].waves`，如 `[{ grunt: 5 }, { armored: 3, swift: 2 }]` |
| 加塔种类 | `TOWER_TYPES` 追加一项；要新机制（穿透/中毒）在 `fire()` 里加分支 |
| 加敌人种类 | `ENEMY_TYPES` 追加一项（hp/speed/armor/reward） |
| 数值平衡 | `TOWER_TYPES` / `ENEMY_TYPES` / `UPGRADE` / `SELL_REFUND` |
| 换美术 | `src/game/art.ts` 的 `TEXTURES` 与 `buildTextures` |

**加地图和加塔类型都不用改逻辑代码** —— `td.ts` 是纯函数层（路径展开、坐标换算、进度插值，全部参数化），`PlayScene` 只读 config 的表。

## 测试与修复

```bash
node scripts/scenario.mjs --serve              # 17 条用例（自己起 dev server）
node scripts/scenario.mjs --serve --repeat 2   # 可复现性验证
node scripts/iterate.mjs start|verify|rollback --issue docs/10-iteration/ISS-xxx.json
```

实测：17/17 通过，`--repeat 2` → 34/34 稳定。单条 130–1500ms（含等待动画），全量约 8s。

用例覆盖：建造扣费 / 非法位置 / 资源边界 / 重复建造 / 敌人推进 / 击杀奖励 /
漏怪扣命 / 失败判定 / 胜利判定 / 重置干净 / 炮塔造价 / 升级属性 / 护甲减伤 /
冰塔减速 / 溅射多目标 / 出售返还 / 第二关数据。

> 契约见技能包的 `references/game-test-schema.md`。

## 已知取舍

- **不含音频资源**：模板不带 mp3，`audio.play()` 全部静默降级。跑 `audio_forge` 环节生成音效后自动生效。
- **底部留白**：网格下方预留约 200px，给塔选择栏 / 升级按钮 / 波次预告用。
- **敌人无飞行/无 BOSS**：三种敌人都是地面单位，路径固定。要加飞行单位需在 `pathPointAt` 之外再开一条直线路径。
- **塔无朝向**：塔是圆形，不转向。要做出「炮管转向」需在 `fire()` 里记录角度并旋转贴图。
- **存档只在本地/平台层**：走 `PlatformBridge.save`，换设备不继承。要做云存档需接平台账号体系。
- **星级只有一档标准**：目前只按漏怪。要加「限时」「限塔数」等条件需在 `starsOf()` 里扩展。

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

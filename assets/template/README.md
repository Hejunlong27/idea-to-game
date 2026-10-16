# 项目模板说明

Phaser 3 + Vite + TypeScript，内置多平台适配层。由 IdeaToGame 技能在 P1 阶段复制到项目根目录。

## 命令

```bash
npm install
npm run dev                 # 本地开发（mock 适配器）
npm run build:cg            # → dist/crazygames
npm run build:poki          # → dist/poki
npm run build:pg            # → dist/playgama
npm run build:gd            # → dist/gamedistribution
npm run build:all           # 全部
npm run zip:all             # 打成 dist/<platform>.zip
```

## 目录职责

| 路径 | 职责 |
|---|---|
| `src/types.ts` | 共享类型。`PlatformBridge` 接口定义在此 |
| `src/platform/` | 各平台适配器 + 工厂。**平台差异只允许出现在这里** |
| `src/game/` | 纯玩法逻辑。**禁止 import `src/platform/`** |
| `src/game/config.ts` | 全部可调数值。P3 调参只改这里 |
| `src/game/scenes/` | 场景：Boot / Menu / Play / GameOver |
| `src/game/util.ts` | 从 registry 取平台实例、存档读写、缩放工具 |
| `scripts/zip-all.mjs` | 打包脚本 |

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
| 其他（dev） | 不注入 |

⚠️ **提交前必须对照平台官方文档核对这些 URL**，平台可能更换 CDN 地址。核对方式：

```bash
npm run build:cg && grep -o 'sdk.crazygames.com[^"]*' dist/crazygames/index.html
```

## 新增平台

1. 新建 `src/platform/<name>.ts`，实现 `PlatformBridge`
2. 在 `src/platform/index.ts` 的 switch 中注册
3. 在 `package.json` 加 `build:<name>` 脚本
4. 在 `vite.config.ts` 的 `SDK_SCRIPTS` 中加该平台的 SDK URL
5. 在 `references/platform-requirements.md` 补充该平台红线

无需改动任何玩法代码。

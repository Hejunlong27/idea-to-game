# 模块 02 · 项目脚手架（scaffold）

**阶段**：P1 ｜ **前置**：G1 通过 ｜ **产出**：可运行项目骨架、`docs/03-scaffold/architecture.md` ｜ 可与 `03-art-bible` 并行

## 目标

建立 Phaser 3.90 + Vite + TypeScript 项目，并把**平台差异全部收敛到适配层**，让玩法代码零平台依赖。

## 技术栈（固定）

| 项 | 选择 | 理由 |
|---|---|---|
| 引擎 | **Phaser 3.90 LTS** | Poki 官方插件 `@poki/phaser-3` 仅支持 Phaser 3；3.x 生态与语料最成熟 |
| 构建 | Vite | 产物小、打包快，便于按平台出多份构建 |
| 语言 | TypeScript | 适配层接口需要类型约束 |
| 物理 | Phaser 内置 Matter.js | 物理益智类够用，不引入额外依赖 |

**不要**改用 Unity WebGL 或 Godot 4 Web：首包体积（25MB+）会直接丧失 CrazyGames 移动端首页资格。

## 步骤

### 1. 复制模板

把 `<skill>/assets/template/` 整个复制到项目根目录。

```bash
cp -r <skill>/assets/template/. <project>/
```

### 2. 安装依赖

```bash
cd <project> && npm install
```

### 3. 校验骨架

```bash
npm run dev
```

必须零报错，浏览器打开出现可交互画面。

### 4. 确认适配层就位

`src/types.ts` 定义 `PlatformBridge` 接口；`src/platform/` 放各平台实现：

| 文件 | 作用 |
|---|---|
| `../types.ts` | `PlatformBridge` 接口定义（放 src 根目录，使 src/game 可引用类型而不依赖 src/platform） |
| `platform/index.ts` | 工厂：按 `import.meta.env.MODE` 选择实现 |
| `platform/mock.ts` | 本地开发用（广告直接返回成功，存档走 localStorage） |
| `platform/crazygames.ts` | CrazyGames SDK v3 |
| `platform/poki.ts` | Poki SDK v2 |
| `platform/playgama.ts` | Playgama Bridge（读 `window.bridge`） |
| `platform/gamedistribution.ts` | GameDistribution SDK |
| `platform/taptap.ts` | TapTap（读宿主注入的全局 `tap`；网页游戏形态自动降级） |

平台实例由 `src/main.ts` 通过 `game.registry.set('platform', ...)` 注入；场景用 `src/game/util.ts` 的 `bridge(scene)` 读取。

**适配器必须保留 `name: 'i2g-platform:<key>'` 标识** —— `precheck.py` 靠它在构建产物里判定适配层是否被正确注入，比猜字符串可靠。

### 5. 确认构建脚本

模板提供 5 个平台目标：

```bash
npm run build:cg        # → dist/crazygames       (mode crazygames)
npm run build:poki      # → dist/poki             (mode poki)
npm run build:gd        # → dist/gamedistribution (mode gamedistribution)
npm run build:pg        # → dist/playgama         (mode playgama)
npm run build:taptap    # → dist/taptap           (mode taptap)
```

**只跑用户在 G0 选定的那几个目标**，不要 `build:all` 一把梭 —— 未选定的平台产物会被 `gate_check.py --stage ship` 判为「超出交付范围」。

```bash
# 示例：用户只选了 crazygames 与 taptap
npm run build:cg && npm run build:taptap
```

### 6. 核对并填入各平台 SDK 的 script 标签

`vite.config.ts` 中的 `SDK_SCRIPTS` 常量负责按构建模式把平台 SDK 注入 `index.html`。

**这是必须人工核对的一步** —— 平台会更换 CDN 地址：

| 平台 | 待核对的 URL | 核对来源 |
|---|---|---|
| crazygames | `https://sdk.crazygames.com/crazygames-sdk-v3.js` | `docs.crazygames.com` |
| poki | `https://game-cdn.poki.com/scripts/v2/poki-sdk.js` | `sdk.poki.com` |
| gamedistribution | `https://html5.api.gamedistribution.com/main.min.js` | `gamedistribution.com/developers/` |
| playgama | **留空** | 需自行在 `index.html` 加入 Bridge SDK script，或改用 npm 包静态 import |
| taptap | **留空（故意）** | Tap 小游戏的 SDK 由 TapTap 容器注入全局 `tap`；**自行引入会被判违规**。网页游戏形态本就不需要 SDK |

核对方式：构建一次，检查 `dist/<platform>/index.html` 的 `</head>` 前是否出现对应 script 标签。

```bash
npm run build:cg && grep -o 'sdk.crazygames.com[^"]*' dist/crazygames/index.html
# taptap 应确认「没有」外部 SDK script
npm run build:taptap && grep -c 'taptap' dist/taptap/index.html
```

### 7. 写架构说明

`docs/03-scaffold/architecture.md` 记录：目录职责、适配层接口、构建目标、新增平台的方法、**各平台 SDK 的注入方式与 URL 核对结果**。

### 8. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage scaffold
```

## 适配层契约

```ts
// src/types.ts
export interface PlatformBridge {
  readonly name: string;
  init(): Promise<void>;
  /** 进入可玩状态时调用。CrazyGames 用它测首包体积，必须在真正可玩时触发 */
  gameplayStart(): void;
  gameplayStop(): void;
  /** 插屏广告（暂停点）。返回是否成功播放 */
  showMidroll(): Promise<boolean>;
  /** 激励视频。返回是否完整观看 */
  showRewarded(): Promise<boolean>;
  save(data: SaveData): Promise<void>;
  load(): Promise<SaveData | null>;
}
```

**规则**：
- `src/game/` 内禁止 import `src/platform/`；需要平台能力时用 `src/game/util.ts` 的 `bridge(scene)`
- 所有 SDK 调用必须 try/catch，失败时静默降级（广告拦截器场景下游戏必须照常可玩）
- 适配器的 `name` 必须为 `i2g-platform:<key>`（供构建产物校验）
- 新增平台 = 新增一个 adapter 文件 + 在 `platform/index.ts` 的 `PLATFORM_TARGETS` 与 switch 注册 + 加一条 `build:<name>` 脚本 + 在 `_common.py` 的 `PLATFORMS` 表登记，不改玩法代码

## 自检

- [ ] `npm run dev` 零报错
- [ ] **用户在 G0 选定的每个平台，其 `build:*` 脚本都能跑通**
- [ ] 适配层文件齐备（`src/types.ts` + `src/platform/` 共 7 个文件，含 `taptap.ts`）
- [ ] `src/game/` 内无 `src/platform/` 引用
- [ ] **各平台 SDK script 标签 URL 已对照官方文档核对**（taptap / playgama 应为空）
- [ ] `npm run build:cg` 后 `dist/crazygames/index.html` 中出现 SDK script 标签
- [ ] 每个产物中能检索到对应的 `i2g-platform:<key>` 标识
- [ ] `index.html` 已含 `user-select: none` 与移动端 viewport 设置
- [ ] 构建产物无绝对路径

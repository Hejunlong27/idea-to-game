# 生图通道验证报告（ComfyUI · Qwen-Image 2.1 turbo）

> 日期：2026-11-01 22:30　通道：本机 ComfyUI `127.0.0.1:8188`（0.42.1）
> GPU：RTX 4060 Laptop 8GB　模型：`qwen_image_2.1_turbo_int8_convrot`
> 结论：**通道可用，Visual DNA → 提示词 → 图像 链路成立**。之前判定 BLOCKED 是因为 Comfy Desktop 未运行。

## 一、通道状态

| 项 | 结果 |
|---|---|
| `GET /system_stats` | 200 |
| ComfyUI 版本 | 0.42.1 |
| 设备 | `cuda:0 NVIDIA GeForce RTX 4060 Laptop GPU` 8.0GB |
| 单张耗时 | 1024² 约 24–30s（1344×1024 约 30s） |
| `gen_assets.py --probe` | `[PASS] ComfyUI: 可达 · 模型齐备` |
| RunningHub | `[FAIL] 缺少 workflowId`（未配置，不影响 auto 降级） |

**启动方式**（Desktop 应用没开时）：
```bash
cd "D:/Comfy-Desktop/ComfyUI-Installs/Minimax H3 低显存专用/ComfyUI"
./.venv/Scripts/python.exe main.py --port 8188 --disable-auto-launch
```

## 二、出图结果

| 素材 | 尺寸 | 结果 | 判断 |
|---|---|---|---|
| `hero.png`（主角正面） | 618×653（裁边后） | 单个摆渡人站在木船上、长外套、船头暖灯、无五官 | ✅ 完全符合 Visual DNA |
| `hero_side.png`（侧视，挂 ref） | 900×1024 | 同一角色、同服装、同灯、同船 | ✅ 身份一致；⚠ 视角仍偏正面 |
| `villain.png`（反派） | 492×874 | 无定形墨色怪物、两点红眼、撕纸边缘 | ✅ 与主角形成「圆润 vs 无定形」对比 |
| `bg_1.png`（背景） | 1408×1056 | 雾夜海面 + 远处灯塔光束 + 分层雾 | ✅ 全幅无透明缺口 |

**色调验证**：四张图的主色相都落在 DNA 色板内（`#0E1B2A` 墨蓝 / `#F2C14A` 暖黄），没有引入新色相。

## 三、过程中发现并修掉的 5 个真 bug

| # | 问题 | 症状 | 修法 |
|---|---|---|---|
| 1 | Visual DNA 的中文字段直接拼进英文提示词 | 28/28 提示词含中文，模型会忽略或乱画 | 加 `en_only()` 过滤 + `light_en()` 把光照转英文；DNA 保留中文给人看，另加 `camera_en` 给机器 |
| 2 | `slug()` 对纯中文返回 `"item"` | 主角/反派/4 个母题**全部塌成同一个 id**，互相覆盖 | `slug()` 返回空串 + `uniq_id()` 保证唯一 |
| 3 | 反派人物的 `use_hero_ref` 也指向主角 | **反派直接复制了主角的船和灯**（换皮） | ref 只给主角自己的姿态；新增 `is_hero` 标记 |
| 4 | `remove_bg` 对全屏背景图也生效 | 背景在天际线被挖出一条透明带（19.1% 透明） | sidecar 的 `remove_bg: false` 优先于全局配置；`scene` 类素材默认不抠 |
| 5 | 三视图生成代码块被插入两次 | 出现重复 id `hero_side` / `hero_back` | 去重；侧/背视图继承基准图的 subject |

另外修了 lint 的一个误报：keyart 模板里的英文 "hero in center" 被当成 id 泄漏。

## 四、一致性评估（诚实版）

| 维度 | 结论 |
|---|---|
| 身份一致性（服装/配色/道具） | ✅ 强。side 视图与 front 视图是同一个角色，可直接用于游戏 |
| 姿态控制（"side view" 指令） | ⚠ 弱。ref 图权重压过文字，侧视仍偏正面。要真正的三视图需要更强的 ControlNet 或降低 ref 权重 |
| 风格统一 | ✅ 强。四张图共享同一套纸纹/墨边/色板 |

**结论：ref 链适合「保证同一个角色」，不适合「强制某个视角」。** 这一点之前只写在文档里，现在有实测依据。

## 五、对 v3 状态的影响

| 项 | 之前 | 现在 |
|---|---|---|
| AI 生图通道 | BLOCKED（探测 000） | **DONE**：通道可用，DNA→提示词→图像链路已验证 |
| 角色一致性 ref 链 | DONE（仅逻辑） | **DONE**：有真实产物对比（front vs side） |
| Visual DNA 是否真能约束出图 | UNVERIFIED | **DONE**：4 张图色相全部落在 DNA 色板内 |

## 六、落地：混合方案（boss 已确认）

**做法**：AI 图负责「质感」（角色 / 道具 / 背景），程序化负责「绝对一致」（地块 / 水纹 / 粒子 / UI）。

| 素材 | 来源 | 体积 |
|---|---|---|
| 船（含摆渡人） | AI `hero.png` → 176×176 | 35KB |
| 幽影 | AI `villain.png` → 140×140 | 13KB |
| 灵魂 | AI `prop_1.png` → 100×100 | 10KB |
| 礁石 | AI `prop_2.png` → 120×120 | 24KB |
| 钟（按钮） | AI `prop_3.png` → 132×132 | 12KB |
| 背景（菜单） | AI `bg_1.png` → 720×1280 JPEG q86 | 122KB |
| 水面 / 岸边 / 水纹 / 粒子 / 光晕 | 程序化 | 0KB |
| **合计** | | **224KB**（全 AI 图方案约 4.5MB） |

**接入方式（关键设计）**：
`BootScene` 用 `import.meta.glob` 把 `assets/img/*.png` 加载到**游戏内固定纹理键**
（`t_boat` / `t_wraith` / `t_soul` / `t_rock` / `t_bell` / `t_bg`），
`art.ts` 里每个程序化块都先判断 `textures.exists(key)`，存在就跳过。

于是：
- 删掉 `assets/img/` 的某张图 → 自动回退到程序化版本，玩法代码零改动
- 换一张新图 → 只要文件名不变，也不用改代码

**接入后修掉的 3 个视觉问题**（都是「图进去了但不好看」）：
1. AI 图按 1.6 倍尺寸出，进游戏没缩放 → 船比格子大 2 倍，溢出边界
2. 记忆槽位用 `setVisible(false)` 隐藏已用格 → 记忆耗尽时玩家看到「记忆」后面一片空白，以为 UI 坏了。改成**槽位常驻 + 变暗**
3. 敲钟水纹从 0.15 缩放到 1.5（192px×1.5=288px，横跨 3 格）→ 收到 0.78

## 七、验收（接入 AI 图之后）

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | 0 错误 |
| `npm run build:cg` | ✅ 3.2MB / 34 文件 |
| `npm run standalone` + `test:standalone` | ✅ 3718KB，外部请求 0 |
| `qa.mjs` | ✅ 12/12 全绿（含无资源 404） |
| `smoke.mjs` | ✅ 闭环可走 |
| `playtest.mjs`（4 策略 × 45s） | ✅ 136 事件 / 0 错误 / 0 卡死 / 首次正反馈 5.57s |
| `specialist_review` | ✅ 38 条证据全过 |

**结论**：混合方案成立。AI 图让画面从「干净的几何」变成「有质感的纸艺水彩」，体积只增加 224KB（+7%）。

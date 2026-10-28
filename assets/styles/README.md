# 画风预设库（styles）

从 **RHSTORY 画风库（服务端全量，306 条）** 里筛出的 5 档，专门给 HTML5 小游戏素材用。

**不是照搬。** 原库的提示词是给「AI 漫剧/视频」写的，动辄 300 字、还带「生成时必须把这些风格特征落实到角色造型…」这类模板句，直接喂给文生图会稀释主体。这里的每一条都做了三件事：

1. **蒸馏**：压成一行 30–50 词的英文 `style_tokens`（游戏资产向、主体优先、可注入任意提示词）
2. **配色板**：给出可直接写进 `palette.json` 的 primary / accent / background
3. **标风险**：写清这档风格在**小游戏**里的具体坑（半像素、抠图成本、视角不一致、版权措辞）

## 5 档一览

| key | 名称 | 来源 | 适合品类 | 一句话判断 |
|---|---|---|---|---|
| `pixel-game` | 像素游戏风 | 2D #71（id 199） | 平台跳跃 / 街机 / roguelike / 塔防 | **最稳**：体积小、识别度高、UI 好统一 |
| `flat-vector` | 扁平矢量插画 | 2D #70（id 197） | 超休闲 / 解谜 / 点击放置 | **最省事**：与程序化 UI 同源，多语言零成本 |
| `lowpoly-3d` | 低多边形游戏风 | 3D #19（id 198） | 经营建造 / 物理益智 / 合成升级 | 想要「3D 游戏感」但不想付 WebGL 代价 |
| `chibi-2d` | 2D Q版卡通 | 2D #4（id 108） | 合成消除 / 养成 / 儿童向 / 换装 | **受众最广**、审核最安全 |
| `ghibli` | 吉卜力手绘 | 2D #13（id 113） | 治愈经营 / 叙事冒险 / 农场小镇 | 质感最好但最「重」，素材数要压住 |

## 怎么用

```bash
python <skill>/scripts/style_lib.py list                 # 看全部
python <skill>/scripts/style_lib.py show pixel-game      # 看单条完整配置
python <skill>/scripts/style_lib.py apply pixel-game --project .   # 写进项目
```

`apply` 会做两件事：

- 合并写入 `docs/02-art/palette.json`（`style_tokens` / `primary` / `accent` / `background` / `negative`）
- 写 `docs/02-art/style.json`（来源、后处理要求、风险、建议尺寸），便于追溯

已有 `style_tokens` 时会拒绝覆盖，除非加 `--force`。

建项目时直接指定：

```bash
python <skill>/scripts/init_project.py --name fruit-merge --idea "合成水果" \
  --platforms taptap --style chibi-2d
```

## 选择建议

| 你的情况 | 选 |
|---|---|
| 第一次做、想最快出可交付包 | `flat-vector` 或 `pixel-game` |
| 目标是 CrazyGames 移动端首页（首包 ≤20MB） | `pixel-game`（素材最轻） |
| 玩法靠角色亲和力（养成/合成/儿童） | `chibi-2d` |
| 想要「看起来像 3D」但用 2D 渲染 | `lowpoly-3d` |
| 卖点是氛围与叙事 | `ghibli`（素材数控制在 15 个以内） |

## 已知边界

- **像素风必须后处理**：AI 出的「像素」带半像素与渐变，要最近邻缩放 + 量化调色板；用 `sprite_tools.py --pad-to` 统一网格
- **吉卜力的品牌名不进商店文案**：写「手绘水彩动画风」，别写 Ghibli（版权与审核风险）
- **低多边形必须锁视角**：同一批素材全部 45° 俯视 + 固定光位，否则拼在一起像贴错图
- 原库 306 条里绝大多数是**真人/影视/恐怖**向，与休闲小游戏不匹配，所以只挑了这 5 档；需要其他风格时按同样方法蒸馏后加 JSON 即可

## 实测记录（2026-10-28，Qwen-Image 2.1 turbo / 1024×1024 / seed 固定）

同一提示词（a cute round slime monster…）+ 五套 style_tokens 各出一张，结论：

| 风格 | 结果 | 备注 |
|---|---|---|
| `pixel-game` | ✅ 一次到位 | 像素块、硬边、描边都对；小尺寸可读性最好 |
| `flat-vector` | ✅ 一次到位 | 纯色块 + 统一描边，和程序化 UI 最搭 |
| `lowpoly-3d` | ⚠️ 可用但有瑕疵 | 面片明暗正确，但模型自带了**地面投影**，泛洪抠图抠不掉（右下角残留色块）。已把 `cast shadow, drop shadow, ground shadow` 加进默认 negative |
| `chibi-2d` | ✅ 一次到位 | 大头短身、腮红、马卡龙配色，最讨喜 |
| `ghibli` | ✅ 一次到位 | 水彩渐变与柔光明显，但边缘最"软"，小尺寸要慎用 |

对照图：`dist/samples/styles/contact-sheet.png`（含 HTML 画廊）。

**帧动画实测**（`--frames slime_idle --grid 2x2 --count 4`）：

- 4 帧风格/比例一致，切分后画布统一（这条曾经有 bug：每格各算各的画布 → 365/376/367/377px，播放会抖）
- 但 `idle breathing` 被理解成"正面/侧面交替"而不是"同一机位的呼吸起伏"
  → 要真正做循环动画，提示词必须写死 **same camera angle, same pose, only the body squash and stretch changes**
- 结论：**2×2 是动画的安全上限**，格数再多一致性会崩

## 新增一档

在 `assets/styles/` 下加一个 `<key>.json`，字段照抄任一现有文件：

```json
{
  "key": "my-style",
  "name": "中文名",
  "name_en": "English Name",
  "source": { "library": "RHSTORY 画风库（服务端全量）", "group": "2d", "index": 0, "style_id": 0 },
  "style_tokens": "…30–50 词英文，主体优先，不含具体物体…",
  "palette": { "primary": ["#…×5–8"], "accent": ["#…"], "background": "#…" },
  "negative_extra": "该风格必须排除的东西",
  "sprite_hint": "后处理要求",
  "gen": { "size": 1024, "steps": 28, "cfg": 7.0 },
  "best_for": ["品类"],
  "risk": "在小游戏里的具体坑",
  "notes": "一句话判断"
}
```

`style_lib.py list` 会自动收录。

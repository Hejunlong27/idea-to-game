# Asset Registry —— 素材台账与一致性检查

素材散在四个地方，各说各话：生成台账（`assets/raw/manifest.json`）记来源，规格（`docs/02-art/asset-spec.json`）记要求，文件在 `assets/` 下，引用在 `src/` 里。

出问题时（「这张图哪来的」「改了 prompt 要不要重出」「这个文件还有人用吗」）要翻四个地方。Registry 把它们合并成一张表并自动检查不一致。

## 三个子命令

```bash
python scripts/asset_registry.py scan     # 扫描项目 → assets/registry.json
python scripts/asset_registry.py check    # 一致性检查 → docs/02-art/asset-registry-report.json
python scripts/asset_registry.py report   # 人读汇总
```

`check` 有 FAIL 时退出码 1，可直接进 CI / `gate_check`。

## 数据模型

```json
{
  "version": 1,
  "budget_kb": 2000,
  "summary": { "images": 6, "audio": 27, "ai": 6, "procedural": 27, "unknown": 0 },
  "assets": [
    {
      "id": "boat",
      "type": "image",
      "path": "assets/img/boat.png",
      "source": "ai",
      "provider": "comfyui",
      "seed": 625110056,
      "prompt_sha": "684c5f054e8d",
      "prompt_preview": "watercolor picture book illustration, ...",
      "width": 224, "height": 224,
      "bytes": 34816,
      "hash": "sha256:...",
      "used_by": ["src/game/scenes/BootScene.ts"],
      "used": true,
      "linked_by": "link"
    }
  ]
}
```

`source` 三档：`ai`（生图）/ `procedural`（程序化合成）/ `unknown`（找不到来源）。

## 三级关联：文件名 → 生成记录

落盘文件名往往被改过（`hero` 生成出来存成 `boat.png`），所以关联按优先级来：

| 优先级 | 方式 | 说明 |
|---|---|---|
| 1 | `assets/registry-links.json` | 人工映射，最可靠 |
| 2 | 文件名 == 台账 id | 精确匹配 |
| 3 | 文件名出现在 prompt 里且唯一命中 | 启发式，可能误配 |

都不中就标 `unknown` —— **这本身是有价值的发现**：素材与生成记录脱钩了，改 prompt 时不知道要重出哪张。

`registry-links.json` 只在「文件名被改过」时才需要：

```json
{ "boat": "hero", "bg": "bg_1", "wraith": "villain" }
```

## 检查项

| 级别 | code | 说明 |
|---|---|---|
| FAIL | `broken_link` | 台账记了但文件不存在 |
| FAIL | `empty_file` | 0 字节，生成失败的残骸 |
| FAIL | `bad_image` | 读不出尺寸 |
| FAIL | `over_budget` | 图片总体积超过 `asset-spec.total_budget_kb` |
| WARN | `orphan` | 文件在但没有任何源码引用（仅图片） |
| WARN | `no_source` | 图片找不到生成记录 |
| WARN | `no_prompt` | AI 图但没有 prompt，无法复现 |
| INFO | `orphan` | 音频未被直接引用 —— 只提示不警告 |

**为什么音频孤儿只算 INFO**：音频常通过 `key + '_b'` 拼接或配置表引用，grep 不到不代表没用。图片是直接引用，判定可靠。

## 两个边界情况

**纯程序化项目**（塔防 / 模拟器）没有 `assets/`：`scan` 生成空台账并明确说「全部使用程序化美术」，`check` 直接 PASS。**这不是错误状态。**

**音频来源**：没有生成记录时默认标 `procedural`（本项目音频统一由 `gen_audio.py` 合成）。要区分手动音效，在 `registry-links.json` 里登记。

## 与其他工具的关系

| 工具 | 管什么 |
|---|---|
| `gen_assets.py` | 生图**过程**：调用通道、断点续跑、写 manifest |
| `asset_forge.py` | 生图**之前**：要什么素材、prompt 怎么组 |
| `asset_registry.py` | 生图**之后**：成品在哪、谁在用、有没有对不上 |
| `measure_bundle.py` | 打包**之后**：产物体积与平台红线 |

Registry 不重复前面任何一个的职责，它只做「合并 + 检查」。

## 实测（echo-ferry）

```
图片 6 张 / 211.8KB（预算 2000KB，已用 11%）
音频 27 个 / 1455.3KB
AI 生成 6 · 程序化 27 · 来源不明 0
检查结论：PASS（FAIL 0 / WARN 0 / INFO 13）
```

首次跑出来是 **AI 生成 0、来源不明 33** —— 因为落盘名和生成 id 全对不上。
补了 `registry-links.json` 才关联上，这正好证明「台账不合并就是废纸」。

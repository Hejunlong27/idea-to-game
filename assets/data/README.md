# 创意参考库（v3）

这些库是**抽象设计原则**，不是素材库，也不是固定模板。

## 目录

| 路径 | 内容 | 消费脚本 |
|---|---|---|
| `assets/data/creative-patterns/interaction-verbs.json` | 24 个交互动词 + 结构指纹 | `creative_forge.py --diverge` |
| `assets/data/creative-patterns/twist-dimensions.json` | 9 个创意反转维度（改什么 + 代价） | `creative_forge.py --twist` |
| `assets/data/creative-patterns/animation-patterns.json` | 14 类表现效果 + 强度分级 + 反模式 | `juice_forge.py` |
| `assets/data/creative-patterns/character-patterns.json` | 剪影规则、头身比、一致性协议 | `art_director.py`、`asset_forge.py` |
| `assets/data/gameplay-patterns/archetypes.json` | 16 个玩法原型的结构指纹 | `creative_forge.py --evaluate`（相似度对照） |
| `assets/data/visual-styles/styles.json` | 12 个视觉风格 + 5 条可混合轴 | `art_director.py` |
| `assets/data/audio-styles/palettes.json` | stem 分层、乐器族、情绪映射、变体规则 | `audio_director.py` |
| `assets/data/emotional-patterns/curves.json` | 情绪曲线、变体、8 条体验判据 | `experience_forge.py` |

## 硬规则（任务书 §12）

1. **不复制受版权保护的素材。** 本目录里没有任何图片、音频、关卡数据或数值表。
2. **不照搬特定商业游戏的完整设计。** 原型库只记录「结构指纹」与「如何做出差异」，不记录某款游戏的具体内容。
3. **可以研究公开的设计原则和抽象机制。** 这正是本目录的内容。
4. **支持用户提供参考图与参考游戏。** 用户提供的参考放进项目 `assets/ref/`，在 `creative-dna.json` 的 `references` 里登记。
5. **每个模式必须记录 `source` 与 `license`。** 现有全部条目为 `CC0-1.0` + 「原创整理」。
6. **不是固定模板。** `art_director.py` 会混合 2–3 个风格的轴（shape / material / light / texture / edge），
   `creative_forge.py` 会重新组合动词 + 反转 + 情绪，产出的组合不在库里。
7. **必须按 Creative DNA 重新组合。** 引用模式时，DNA 的 `references` 要写 `how_used`（怎么改的），
   不能只写 `pattern_id`。

## 新增模式的要求

```json
{
  "id": "kebab_or_snake_id",
  "zh": "中文名",
  "source": "来源（原创整理 / 公开文章 / 用户提供）",
  "license": "CC0-1.0 / CC-BY-4.0 / 用户授权",
  "note": "一句话说明它解决什么问题"
}
```

缺 `source` 或 `license` 的条目会被 `creative_forge.py --validate` 判为错误。

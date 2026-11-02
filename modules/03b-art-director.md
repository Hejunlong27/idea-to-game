# 03b · 美术总监（Art Director）

**目标**：从「AI 素材生成」升级为**真正的视觉设计系统**。
**上游**：`docs/01-brief/creative-dna.json` 的 `visual` 段。**下游**：`asset_forge` 拼提示词、`art_review` 审画面。

## 为什么需要这一步

v2 的美术环节只有 `palette.json`（style_tokens + 几个颜色），`asset_forge.ROLES` 的 9 个模板
全是**出图参数**，没有一条描述「这套视觉的语言」。**颜色不是视觉身份。**

## 步骤

### 1. 三套风格提案

```bash
python scripts/art_director.py --project . --propose
```

**不是风格选择器**：每套提案混合 2 个风格库条目的不同轴（shape / material / light / texture / edge），
产出的组合不在库里。DNA 里已声明的风格优先，避免提案与身份脱节。

每套含 11 项：风格名、参考方向、色彩体系、轮廓语言、材质、光照、镜头、环境氛围、UI 语言、
角色设计、正向提示词、负向提示词，外加**对比度检查**。

判据：三套必须一眼可分（轮廓来源 / 色温 / 饱和度不同），且 `对比度全部达标`。

### 2. 收敛成 Visual DNA

```bash
python scripts/art_director.py --project . --dna --pick S1
```

产出 `docs/02-art/visual-dna.json`，12 个区块：

| 区块 | 关键字段 | 为什么必须 |
|---|---|---|
| `style` | identity / style_tokens / negative | 出图的锚点，≥15 词 |
| `color` | primary / accent / danger / ratio / usage_rules | 语义色比例，不是色卡 |
| `form` | outline / shape_language / materials / texture_rules / detail_density | 决定「看起来像不像一套」 |
| `light` | direction / quality / temperature / shadow_rules | 光照方向错 = 素材拼贴感 |
| `camera` | view / angle / depth_of_field / parallax_layers | 视角统一 |
| `ui` | language / corner_radius / stroke / typography / text_render | 文字必须 Text 渲染 |
| `character` | ratio / silhouette_rules / anchor_color / consistency | 64px 可辨 |
| `motion` | style / easing / looping / feedback_rules | 动画语言 |
| `fx` | style / palette / rules | 特效不得引入新色相 |
| `scene_narrative` | trigger / visual_change / meaning | 环境承担叙事 |

**同时会同步写 `palette.json`**（向后兼容：`asset_forge` / `richness_check` 仍读它）。

### 3. 角色一致性

```bash
python scripts/art_director.py --project . --consistency
```

**「多张图用同一 prompt」不构成一致性方案。** 协议是：

1. 先出**基准图**（front），固定 seed，记录 `consistency_key`
2. 用基准图做 **i2i ref** 生成 side / back / 表情，seed 相同
3. 所有衍生姿态提示词必须含 `HERO_ANCHOR` 段
4. 出图后程序化比对：主色直方图距离 <0.18、剪影宽高比偏差 <0.12
5. 通道不支持 i2i 时，`status` 必须标为 `degraded_no_ref` 并写原因

四种状态：`full_ref_chain` / `seed_only` / `prompt_only` / `degraded_no_ref`。
**`gate_check` 会校验 `full_ref_chain` 时参考图必须真实存在 —— 不允许虚报。**

> v3 修复了一个真实缺陷：`asset_forge.mk_item()` 过去从不写 `use_hero_ref`，
> 导致 ref 链条件永远不成立 —— 机制「看起来有，实际走不到」。

### 4. 校验

```bash
python scripts/art_director.py --project . --validate --strict
```

会查：schema、对比度（正文 ≥4.5、强调 ≥3）、锚定色与危险色色相距离 ≥30°、
style_tokens ≥15 词、文字渲染声明、一致性状态自洽、场景叙事非空。

## 自检

- [ ] 三套提案在轮廓/色温/饱和度上一眼可分
- [ ] `color.contrast_checks` 全部 pass
- [ ] `character.anchor_color` 与 `danger` 色相距离 ≥30°
- [ ] `style.style_tokens` ≥15 词且含材质/光照
- [ ] `scene_narrative` ≥2 条（环境随进度变化）
- [ ] 一致性 `status` 与实际参考图自洽（不虚报）
- [ ] `--validate --strict` 退出码 0

## 门禁

`G2`（人工确认整体风格）在这里之后。风格定错，所有素材作废，返工成本最高。

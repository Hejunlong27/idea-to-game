# 迁移指南（v2 → v3）

> 核心承诺：**旧项目可以继续运行。** 不删阶段、不改字段语义、不提高原有门槛。

## 一、什么都不做也能跑

v3 只做了三件「加法」：

1. `STAGES` **append** 了 8 个新键（`creative` / `creative_dna` / `visual_dna` /
   `audio_director` / `juice` / `experience` / `playtest` / `review_specialist`）
2. `gate_check.REQUIRED_FILES` 增加了对应阶段
3. 模板新增了 `events.ts` / `audio.ts` / `juice.ts` / `audio-config.ts` / `juice-config.ts`
   与 `qa.mjs` / `smoke.mjs` / `playtest.mjs`

**旧项目的 state.yaml 里没有新键**，`load_state` 取值时会得到 `pending`（`stages.get(s, {}).get("status", "pending")`）。
所以：

```bash
python scripts/state.py show --project <旧项目>   # 正常显示，新阶段为 pending
python scripts/gate_check.py --project <旧项目> --stage brief   # 判据未变，结论不变
```

**已有测试覆盖这一点**：`test_legacy_project_without_v3_keys_still_works` 构造了一个只有 15 个键的 v2 项目，
断言 `show` 不崩、`next` 给出的模块路径正确。

## 二、逐项兼容性

| 变更 | 对旧项目的影响 | 说明 |
|---|---|---|
| 新增 8 个阶段 | 无 | 缺失即 pending；不参与旧阶段的判定 |
| `STAGE_MODULES` 显式映射 | 修复 | 以前 `state.py next` 用 `STAGES.index(s)+1` 推模块名，插阶段就全错 |
| `richness_check` 四维权重 | **未改** | 30/25/25/20 与 THIN 判定完全保留 |
| X1–X4 交叉校验 | **未改** | 新增的只是 X5（身份一致性），且仅在 DNA 存在时才检查 |
| `crazygames-standard.md` A–H | **未改** | `review_gate.py` 的判据与探针未动 |
| `asset_forge` 读 Visual DNA | 向后兼容 | 没有 `visual-dna.json` 时自动退回 `palette.json`，行为与 v2 一致 |
| `asset_forge` 写 `use_hero_ref` | **行为变化** | v2 该字段从不被写入（ref 链实际失效）；v3 会写入，**主角后续姿态默认挂 ref**。若旧项目不希望挂 ref，在 `asset-spec.json` 里显式设 `use_hero_ref: false` |
| `asset_forge` spec 版本 | 字段新增 | `version` 2.0 → 3.0，新增 `visual_dna` / `visual_dna_applied` / `consistency_status`；旧字段全保留 |
| 模板 `package.json` 的 `build` | **行为变化** | 输出从 `dist/` 改为 `dist/preview/`。原因：vite 会清空 outDir，`npm run build` 会把 `dist/crazygames` 一起删掉 |
| 模板新增 `npm run test` | 新增 | `build && test:standalone` |
| `PlayScene.ts` 重写 | **需要迁移** | 旧项目如果直接用模板的占位玩法，会被覆盖。**升级前先备份 `src/game/scenes/PlayScene.ts`** |
| 事件 / 音频 / 表现 | 可选接入 | 三个模块互不依赖，可以只接其中一个 |

## 三、旧项目升级步骤（推荐顺序）

```bash
# 0. 备份（模板文件会被覆盖）
cp src/game/scenes/PlayScene.ts /tmp/PlayScene.v2.ts.bak

# 1. 补齐模板新增文件（不覆盖已有玩法代码）
cp <skill>/assets/template/src/game/events.ts        src/game/
cp <skill>/assets/template/src/game/audio.ts         src/game/
cp <skill>/assets/template/src/game/juice.ts         src/game/
cp <skill>/assets/template/src/game/audio-config.ts  src/game/
cp <skill>/assets/template/src/game/juice-config.ts  src/game/
cp <skill>/assets/template/scripts/{qa,smoke,playtest}.mjs scripts/

# 2. 状态机补键（脚本会自动补，也可手动跑一次 show 触发）
python <skill>/scripts/state.py show --project .

# 3. 从现有产物反推身份（不必从零做创意发散）
#    已有 palette.json → 可手工写 visual-dna.json，或跑 art_director --propose 重新提案
python <skill>/scripts/art_director.py --project . --propose

# 4. 音频与表现（如果项目已有 sfx-plan）
python <skill>/scripts/audio_director.py --project . --plan
python <skill>/scripts/audio_director.py --project . --qc
python <skill>/scripts/juice_forge.py --project . --plan

# 5. 逐阶段校验
python <skill>/scripts/gate_check.py --project . --stage visual_dna
```

## 四、旧项目可以跳过哪些新阶段

| 阶段 | 什么时候可以 `skipped` | 必须写的 note |
|---|---|---|
| `creative` | 项目已进入生产，方向已定 | 「v2 时期立项，无发散记录」 |
| `creative_dna` | 同上 | 同上 |
| `visual_dna` | 视觉已定稿且不打算改 | 「沿用 v2 palette.json」 |
| `art_forge` / `sprite_tools` | 美术为程序化绘制 | 「无位图素材」 |
| `audio_director` | 项目只有简单音效、无自适应音乐需求 | 「v2 音频，不做自适应」 |
| `juice` | 表现已在玩法代码里硬编码 | 「沿用 v2 手感」 |
| `experience` | 关卡已定型 | 「v2 关卡设计」 |
| `playtest` | 无可用浏览器环境 | 「环境限制，未跑」 |
| `review_specialist` | **不建议跳过** | 它是 R2 的前置；跳过等于放弃「值不值得上架」的判定 |

```bash
python scripts/state.py set --project . --stage visual_dna --status skipped \
       --note "沿用 v2 palette.json"
```

## 五、已知的坑（升级时容易踩）

| 坑 | 症状 | 处理 |
|---|---|---|
| 直接 `cp -r template/* .` | 覆盖了 `PlayScene.ts`，玩法丢失 | 只拷新增文件，不整目录覆盖 |
| `npm run build` 清空 dist | `dist/crazygames` 被删 | v3 已改为输出 `dist/preview`；旧项目手动改 `package.json` |
| `use_hero_ref` 突然生效 | 主角姿态开始走 i2i，出图变慢/风格变了 | 这是修 bug 的预期结果；不接受就在 spec 里设 `false` |
| `gate_check --stage ship` 多了一条 | 缺 `verdict-specialist.json` 被拦 | 这是有意的：专项审核也是一票否决。跑 `specialist_review.py` 生成 |
| 新阶段全是 pending 导致 `next` 指向 creative | 旧项目 `next` 让你去做创意发散 | 按第四节 skip 掉不需要的，`next` 就会跳过 |

## 六、回滚

v3 没有删除任何文件，回滚只需：

```bash
git checkout <v2 tag> -- scripts/ modules/ references/ assets/template/
# 或整体
git reset --hard <v2 commit>
```

`state.yaml` 里多出来的 v3 键对 v2 脚本无影响（v2 的 `STAGES` 不含它们，`show` 不会显示，`set` 会拒绝但不会损坏文件）。

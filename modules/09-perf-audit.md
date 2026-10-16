# 模块 09 · 性能与体积审计（perf audit）

**阶段**：P3 ｜ **前置**：`08-polish` 完成 ｜ **产出**：`docs/06-perf/report.md`

## 目标

对照**用户选定平台**的红线做量化审计。首包体积与 60fps 是能否拿到移动端流量的生死线。

**体积预算取最严**：多平台时按 `delivery.size_budget_mb`（最严的一条）做，不是各平台各算一份。

## 步骤

### 1. 体积与文件数审计（逐平台）

```bash
# 对用户在 G0 选定的每个平台分别审计
python <skill>/scripts/measure_bundle.py --dir dist/crazygames --platform crazygames
python <skill>/scripts/measure_bundle.py --dir dist/taptap     --platform taptap
```

平台红线参数表在 `scripts/_common.py` 的 `PLATFORMS` 中（单一真相源），包含：

| 平台 | 总大小 | 文件数 | 首包 |
|---|---|---|---|
| crazygames | ≤250MB | ≤1500 | ≤50MB（移动端首页 ≤20MB） |
| poki | ≤250MB | ≤1500 | ≤50MB（移动端首页 ≤20MB） |
| gamedistribution | ≤250MB | ≤1500 | ≤50MB |
| playgama | ≤250MB | ≤1500 | ≤50MB |
| taptap | ≤250MB | ≤1500 | **≤60MB**（优秀 ≤20MB） |

### 2. 帧率与内存测量

用浏览器自动化采集：

- 连续运行 60 秒，记录平均帧率与最低帧率
- 记录 JS heap 曲线，确认无持续增长（内存泄漏）
- 记录启动到可玩状态耗时（CrazyGames 外部资源按 ≤20 秒评估）

**基准环境**：模拟 4GB 内存的低端设备（降低 CPU 节流倍率）。

### 3. 排查常见瓶颈

| 现象 | 常见原因 | 处理 |
|---|---|---|
| 帧率波动大 | 每帧创建对象（GC 压力） | 对象池复用 |
| 启动慢 | 素材未压缩 / 首包过大 | 纹理压缩、延迟加载非首屏素材 |
| 内存持续增长 | 事件监听未解绑、纹理未释放 | 场景销毁时解绑与 `destroy()` |
| Draw Call 高 | 未用图集 | 打图集（见 `06-sprite-tools`） |
| 移动端卡 | DPR 过高 | 按设备能力降 DPR |

### 4. 写报告

`docs/06-perf/report.md` 记录：三项体积指标实测值、帧率曲线、内存曲线、启动耗时、发现的问题与处理、优化前后对比。

### 5. 回退机制

- 首包超**最严红线** → 自动执行：纹理压缩 → 降分辨率 → 音频降码率 → 砍非必要素材，**最多 3 次**
- 帧率不达标 → 回退 `08-polish` 降级渲染（减粒子/阴影/后处理，降 DPR），**最多 3 次**
- 每次回退在 `state.yaml` 的 `perf_audit.retries` 递增
- 连续 3 次仍不达标 → 停止并上报

### 6. 校验

```bash
python <skill>/scripts/gate_check.py --project <project> --stage perf_audit
```

## 自检

- [ ] **用户在 G0 选定的每个平台**都已跑过 `measure_bundle.py`
- [ ] 首包满足所有选定平台中最严的红线（`delivery.size_budget_mb`）
- [ ] TapTap 产物 ≤60MB（若选了 taptap）
- [ ] CrazyGames 产物 ≤20MB（若选了 crazygames，移动端首页资格）
- [ ] 总文件数 ≤1500
- [ ] 总文件大小 ≤250MB
- [ ] 平均帧率 ≥58fps，最低 ≥50fps（4GB 基准）
- [ ] 60 秒运行内存无持续增长
- [ ] 启动到可玩 ≤3 秒（本地）/ ≤20 秒（外部托管）
- [ ] 报告已产出，含**逐平台**实测数值

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 只测桌面端不测低端设备 | 移动端用户流失 | 用 4GB 基准测 |
| 只看平均帧率 | 掩盖卡顿尖峰 | 同时记录最低帧率 |
| 不测内存泄漏 | 玩久了崩溃 | 跑 60 秒看 heap 曲线 |
| 超标了直接砍玩法 | 体验受损 | 先压缩素材，再砍内容 |

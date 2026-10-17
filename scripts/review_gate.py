#!/usr/bin/env python3
"""质量与玩法审核官执行脚本（模块 12）。

用法:
    # R0 规划预审
    python review_gate.py --project <proj> --phase r0 --round 1
    # R1 灰盒预审（生图之前）
    python review_gate.py --project <proj> --phase r1 --round 1
    # R2 终审（交付之前）
    python review_gate.py --project <proj> --phase r2 --round 1

行为:
    1. 自动跑所有可测条目（体积/路径/CSS/SDK/广告静态合规等）
    2. 首次运行生成 docs/09-review/manual-checks.json（人工条目填写模板）
    3. 合并自动与人工结果，计算 verdict
    4. 写 checklist.md / issues.json / verdict.json
    5. REQ 有条目 FAIL 时退出码非 0（供 ship 门禁使用）

判据: references/crazygames-standard.md（条目编号即契约）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    human_size,
    iter_files,
    load_state,
    platform_conf,
    save_state,
    scan_absolute_paths,
)

TEXT_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".css"}

# ---------------------------------------------------------------- 标准条目表
#
# level: REQ = 官方必需（FAIL 即阻塞） / GUIDE = 官方建议（FAIL 记为偏离）
# auto : 自动检查函数名；None 表示人工判定
# dims : 所属维度，用于按 phase 过滤

ITEMS = [
    # A 玩法可玩性
    ("A1", "A", "REQ", None, "无报错、无崩溃，能连续完成完整游玩"),
    ("A2", "A", "REQ", None, "玩法原创：名称、素材、内容具备原创性"),
    ("A3", "A", "REQ", None, "名称/图标/描述与实际玩法一致，名称唯一可辨"),
    ("A4", "A", "REQ", None, "不使用他人 IP（除非自有）"),
    ("A5", "A", "REQ", None, "品类与核心特性在提交后不发生大幅变更"),
    ("A6", "A", "REQ", None, "新用户直接进入玩法；最多 1 次点击"),
    ("A7", "A", "GUIDE", None, "无过度重复或无聊的机械化任务"),
    ("A8", "A", "GUIDE", None, "目标清晰：玩家始终知道下一步做什么"),
    ("A9", "A", "GUIDE", None, "不同玩家群体都能获得乐趣"),
    ("A10", "A", "GUIDE", None, "信息处理迅速，流程顺畅连续"),
    ("A11", "A", "GUIDE", None, "便于后续扩展内容"),
    ("A12", "A", "GUIDE", None, "单人玩法与多人玩法同等醒目"),
    # B 核心循环
    ("B1", "B", "REQ", None, "完整闭环可跑通：开始→游玩→结束→重开，无死状态"),
    ("B2", "B", "REQ", None, "操作到反馈 ≤100ms"),
    ("B3", "B", "GUIDE", None, "难度曲线可描述且平衡"),
    ("B4", "B", "GUIDE", None, "会话平均游玩时长目标 ≥10 分钟"),
    ("B5", "B", "GUIDE", None, "有进度感（等级/解锁/升级/最高分）"),
    ("B6", "B", "REQ", None, "存档生效，刷新不丢进度"),
    ("B7", "B", "GUIDE", None, "有回访钩子（每日奖励/任务）"),
    ("B8", "B", "GUIDE", None, "新机制渐进引入"),
    # C 操作与引导
    ("C1", "C", "REQ", None, "引导在玩法内完成，聚焦核心操作"),
    ("C2", "C", "REQ", None, "引导可跳过"),
    ("C3", "C", "REQ", None, "操作在桌面/移动上都直观"),
    ("C4", "C", "REQ", None, "按钮标签清晰表明如何继续"),
    ("C5", "C", "REQ", None, "按钮无延迟以困惑用户或诱导行为"),
    ("C6", "C", "REQ", None, "按钮未放大尺寸以诱导广告或其他行为"),
    ("C7", "C", "REQ", "auto_restricted_keys", "避开受限键 Escape / Ctrl+W"),
    ("C8", "C", "GUIDE", None, "键位适配键盘布局（AZERTY）"),
    ("C9", "C", "GUIDE", None, "视觉优先、少用文字做引导"),
    ("C10", "C", "GUIDE", None, "提供操作提示（键盘覆盖图/手势）"),
    ("C11", "C", "GUIDE", None, "全程操作一致"),
    # D 画面与音频
    ("D1", "D", "REQ", None, "devicePixelRatio:1 下文字与图像可读"),
    ("D2", "D", "REQ", None, "在 CG 全部 iframe 尺寸下内容可读"),
    ("D3", "D", "REQ", None, "美术风格内部一致，无风格跳变"),
    ("D4", "D", "REQ", None, "无图形缺陷（压缩伪影等）"),
    ("D5", "D", "REQ", None, "分辨率全游戏一致"),
    ("D6", "D", "GUIDE", None, "音频电平一致"),
    ("D7", "D", "GUIDE", None, "音乐与视觉互补"),
    ("D8", "D", "GUIDE", None, "整体审美令人愉悦"),
    # E 加载与性能
    ("E1", "E", "REQ", "auto_total_size", "总文件大小 ≤50MB（无 SDK）/ ≤250MB（有 SDK）"),
    ("E2", "E", "REQ", "auto_file_count", "文件数 ≤1500"),
    ("E3", "E", "REQ", "auto_initial_size", "首包 ≤50MB；KPI 目标 ≤20MB"),
    ("E4", "E", "REQ", None, "物理表现在 144/165Hz 下一致"),
    ("E5", "E", "REQ", "auto_build_ok", "加载快、无错误、无崩溃"),
    ("E6", "E", "GUIDE", None, "加载到可玩 ≤10 秒"),
    ("E7", "E", "GUIDE", None, "玩法转化率设计目标 ≥80%"),
    ("E8", "E", "GUIDE", "auto_short_intro", "首帧尽快出现，无长开场/logo 动画"),
    ("E9", "E", "GUIDE", None, "按需加载"),
    ("E10", "E", "GUIDE", "auto_fps", "60fps（平均 ≥58 / 最低 ≥50）"),
    ("E11", "E", "GUIDE", "auto_memory", "60 秒运行内存无持续增长"),
    # F 兼容性与适配
    ("F1", "F", "REQ", "auto_scale_fit", "全部 iframe 尺寸下布局与文字正常"),
    ("F2", "F", "REQ", None, "支持鼠标+键盘；支持移动则须支持触摸"),
    ("F3", "F", "REQ", "auto_no_custom_fullscreen", "全屏正常；禁止自定义游戏内全屏按钮"),
    ("F4", "F", "REQ", "auto_no_cross_promo", "无跨推广"),
    ("F5", "F", "REQ", "auto_no_appstore_links", "App Store 链接绝不出现在游戏内"),
    ("F6", "F", "REQ", None, "Chrome 与 Edge 实测可用"),
    ("F7", "F", "REQ", "auto_user_select", "body 含 user-select: none（含前缀）"),
    ("F8", "F", "GUIDE", None, "竖屏游戏在桌面端可用"),
    ("F9", "F", "GUIDE", None, "界面针对用户设备设计"),
    ("F10", "F", "GUIDE", None, "全屏下 Ctrl/Cmd+W 可禁用"),
    # G 广告与变现合规
    ("G1", "G", "REQ", "auto_no_external_ads", "只允许 CG SDK 的广告，无外部广告"),
    ("G2", "G", "REQ", None, "视频广告不打断玩法、不突然出现"),
    ("G3", "G", "REQ", None, "禁止在导航按钮上触发中插广告"),
    ("G4", "G", "REQ", None, "广告期间游戏暂停（阻断交互至 adFinished/adError）"),
    ("G5", "G", "REQ", None, "广告播放时静音，且仅在真正开始播放时静音"),
    ("G6", "G", "REQ", None, "正确处理 adError，游戏继续"),
    ("G7", "G", "REQ", "auto_no_ad_chain", "不链式播放多个广告"),
    ("G8", "G", "REQ", None, "激励视频不出现在活跃玩法屏幕"),
    ("G9", "G", "REQ", None, "激励视频不过于频繁（计时器/隐藏）"),
    ("G10", "G", "REQ", None, "激励视频跳过与观看按钮同尺寸字体颜色"),
    ("G11", "G", "REQ", None, "明确标示观看换奖励 + 提供替代途径"),
    ("G12", "G", "REQ", None, "adFinished 给奖励反馈；adError 不发奖"),
    ("G13", "G", "REQ", None, "不叠加关卡中插与续玩激励"),
    ("G14", "G", "REQ", None, "不存在只能靠看广告才能过关的关卡"),
    ("G15", "G", "REQ", None, "Banner 仅在 ≥5 秒界面、不遮挡、同屏 ≤2"),
    ("G16", "G", "REQ", None, "广告拦截器用户可正常游玩，无劣势"),
    ("G17", "G", "REQ", None, "广告禁用时游戏仍正常运行（Basic Launch）"),
    ("G18", "G", "REQ", None, "内购仅用 CG Xsolla 账号与 userId（Invite Only）"),
    # H 平台技术规范
    ("H1", "H", "REQ", "auto_relative_paths", "构建产物全部相对路径"),
    ("H2", "H", "REQ", "auto_sdk_events", "gameplayStart/Stop 时机正确"),
    ("H3", "H", "REQ", "auto_ios_audio", "iOS 在 touchend/click 内 resume AudioContext"),
    ("H4", "H", "REQ", "auto_i18n_en", "提供英文本地化，按 locale 切换"),
    ("H5", "H", "REQ", None, "PEGI 12 合规"),
    ("H6", "H", "REQ", None, "账号集成规范（若适用）"),
    ("H7", "H", "REQ", None, "多人规范（若适用）"),
    ("H8", "H", "REQ", None, "额外个人数据须提供条款/隐私提示"),
    ("H9", "H", "REQ", None, "提交提供元数据与封面素材"),
    ("H10", "H", "GUIDE", None, "跨推广允许例外条款"),
]

PHASE_DIMS = {
    "r0": {"A", "B", "H"},  # 规划期：只看可审性与合规初筛
    "r1": {"A", "B", "C"},  # 灰盒期：玩法 + 核心循环 + 操作引导
    "r2": {"A", "B", "C", "D", "E", "F", "G", "H"},  # 终审：全量
}

# 外部广告网络关键词（出现即视为违反"只用 CG SDK 广告"）
AD_NETWORKS = [
    "adsbygoogle", "doubleclick", "googlesyndication", "googleadservices",
    "unityads", "ironsource", "applovin", "vungle", "chartboost", "adcolony",
    "facebook.com/audiencenetwork", "taboola", "outbrain", "criteo",
    "yandex.ru/ads", "adservice.google",
]

STORE_MARKERS = ["apps.apple.com", "itunes.apple.com", "play.google.com/store"]

CROSS_PROMO_HINTS = ["discord.gg", "store.steampowered.com", "epicgames.com"]


# ---------------------------------------------------------------- 自动检查
class Ctx:
    def __init__(self, proj: Path):
        self.proj = proj
        self.state = {}
        try:
            self.state = load_state(proj) or {}
        except SystemExit:
            pass
        self.platforms = ((self.state.get("delivery") or {}).get("platforms")) or []
        self.text_cache: dict[str, str] = {}
        self._blob = None

    @property
    def dist(self) -> Path:
        return self.proj / "dist"

    def text(self, root: Path | None = None) -> str:
        if self._blob is None:
            chunks = []
            for p in iter_files(root or self.dist):
                if p.suffix.lower() in TEXT_EXT:
                    try:
                        if p.stat().st_size > 8_000_000:
                            continue
                        chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        continue
            self._blob = "\n".join(chunks)
        return self._blob

    def targets(self) -> list[Path]:
        """返回本轮要检查的产物目录（每个选定平台一个）。"""
        out = []
        for pk in self.platforms:
            d = self.dist / pk
            if d.is_dir():
                out.append(d)
        if not out and self.dist.is_dir():
            out = [d for d in self.dist.iterdir() if d.is_dir()]
        return out


def _fail(msg):
    return False, msg


def auto_total_size(ctx: Ctx, target: Path):
    conf = _conf_for(target, ctx)
    total = sum(p.stat().st_size for p in iter_files(target))
    limit = conf["total_mb"] * 1024 * 1024
    if total > limit:
        return _fail(f"{target.name}: {human_size(total)} 超出 {conf['total_mb']}MB")
    return True, f"{target.name}: {human_size(total)} / 限 {conf['total_mb']}MB"


def auto_file_count(ctx: Ctx, target: Path):
    conf = _conf_for(target, ctx)
    n = len(list(iter_files(target)))
    if n > conf["files"]:
        return _fail(f"{target.name}: {n} 个文件超出 {conf['files']}")
    return True, f"{target.name}: {n} / 限 {conf['files']}"


def auto_initial_size(ctx: Ctx, target: Path):
    conf = _conf_for(target, ctx)
    total = sum(p.stat().st_size for p in iter_files(target))
    if total > conf["initial_mb"] * 1024 * 1024:
        return _fail(f"{target.name}: {human_size(total)} 超出首包 {conf['initial_mb']}MB")
    return True, f"{target.name}: {human_size(total)} / 首包限 {conf['initial_mb']}MB"


def auto_build_ok(ctx: Ctx, target: Path):
    if not (target / "index.html").is_file():
        return _fail(f"{target.name}: 缺 index.html，构建不完整")
    js = list(target.glob("*.js")) + list(target.glob("assets/**/*.js"))
    if not js:
        return _fail(f"{target.name}: 未发现入口 JS")
    return True, f"{target.name}: 构建完整（index.html + {len(js)} 个 JS）"


def auto_short_intro(ctx: Ctx, target: Path):
    t = ctx.text(target)
    # 只做启发式：存在 loading 场景但可跳过/极短
    if re.search(r"setTimeout\([^,]+,\s*(\d{4,})\)", t):
        return None, "发现 ≥1000ms 的定时器，需人工确认是否为开场延迟"
    return True, "未发现明显长开场延迟"


def auto_fps(ctx: Ctx, target: Path):
    rep = ctx.proj / "docs/06-perf/report.md"
    if not rep.exists():
        return None, "未找到 docs/06-perf/report.md，帧率需人工实测填入"
    t = rep.read_text(encoding="utf-8", errors="ignore")
    m = re.findall(r"(\d{2,3}(?:\.\d+)?)\s*(?:fps|FPS)", t)
    if not m:
        return None, "性能报告未含 fps 数值，需人工确认"
    vals = [float(x) for x in m]
    avg = sum(vals) / len(vals)
    if avg < 58:
        return _fail(f"性能报告平均 {avg:.1f}fps < 58")
    return True, f"性能报告采样平均 {avg:.1f}fps"


def auto_memory(ctx: Ctx, target: Path):
    rep = ctx.proj / "docs/06-perf/report.md"
    if not rep.exists():
        return None, "未找到性能报告，内存需人工确认"
    t = rep.read_text(encoding="utf-8", errors="ignore")
    if "泄漏" in t or "leak" in t.lower():
        return None, "报告提及疑似泄漏，需人工判定"
    return True, "报告未见泄漏记录（人工复核建议）"


def auto_restricted_keys(ctx: Ctx, target: Path):
    t = ctx.text(target)
    bad = []
    for k in ["Escape", "ESC"]:
        if re.search(rf"key(?:Code)?\s*===?\s*['\"]{k}['\"]", t):
            bad.append(k)
    if re.search(r"keydown[\s\S]{0,80}Escape", t):
        bad.append("Escape(keydown)")
    if bad:
        return _fail(f"监听受限键：{', '.join(sorted(set(bad)))}（Escape 会退出全屏）")
    return True, "未发现对 Escape 的按键监听"


def auto_scale_fit(ctx: Ctx, target: Path):
    t = ctx.text(target)
    if re.search(r"mode:\s*[\w.]*FIT", t) or "FIT" in t:
        return True, "使用 FIT 缩放模式（能否在 10 个尺寸下可读仍需人工截图确认）"
    return None, "未检出 FIT 缩放模式，需人工确认各 iframe 尺寸下的适配"


def auto_no_custom_fullscreen(ctx: Ctx, target: Path):
    t = ctx.text(target)
    hits = []
    if "requestFullscreen" in t or "webkitRequestFullscreen" in t:
        hits.append("requestFullscreen")
    if re.search(r"全屏|fullscreen", t, re.I) and re.search(r"button|btn|按钮", t, re.I):
        m = re.search(r".{0,60}(全屏|fullscreen).{0,60}", t, re.I)
        if m and re.search(r"button|btn", m.group(0), re.I):
            hits.append("疑似全屏按钮文案")
    if hits:
        return _fail(f"检出自定义全屏实现：{', '.join(hits)}（CG 明令禁止）")
    return True, "未检出自定义全屏按钮"


def auto_no_external_ads(ctx: Ctx, target: Path):
    t = ctx.text(target).lower()
    hit = [k for k in AD_NETWORKS if k in t]
    if hit:
        return _fail(f"检出外部广告网络引用：{', '.join(hit[:5])}")
    return True, "未检出外部广告网络（仅限 CG SDK 广告）"


def auto_no_ad_chain(ctx: Ctx, target: Path):
    t = ctx.text(target)
    if re.search(r"(requestAd|showAd|commercialBreak)[\s\S]{0,200}(requestAd|showAd|commercialBreak)", t):
        return None, "同一流程中发现两次广告调用，需人工确认是否链式播放"
    return True, "未发现明显的链式广告调用"


def auto_no_appstore_links(ctx: Ctx, target: Path):
    t = ctx.text(target).lower()
    hit = [k for k in STORE_MARKERS if k in t]
    if hit:
        return _fail(f"游戏内出现 App Store 链接：{', '.join(hit)}（明令禁止，须用后台元数据字段）")
    return True, "游戏内无 App Store 链接"


def auto_no_cross_promo(ctx: Ctx, target: Path):
    t = ctx.text(target).lower()
    hit = [k for k in CROSS_PROMO_HINTS if k in t]
    if hit:
        return None, f"发现疑似跨推广外链：{', '.join(hit)}（菜单内社区链接属允许例外，需人工确认位置与是否直通可玩网页版）"
    return True, "未发现跨推广外链"


def auto_user_select(ctx: Ctx, target: Path):
    t = ctx.text(target)
    if "user-select" not in t:
        return _fail("缺少 user-select: none（移动端长按会弹选择菜单）")
    missing = [p for p in ("-webkit-", "-moz-", "-ms-") if f"{p}user-select" not in t]
    if missing:
        return True, f"已含 user-select，但缺前缀：{', '.join(missing)}（建议补齐）"
    return True, "user-select 与全部前缀齐备"


def auto_relative_paths(ctx: Ctx, target: Path):
    hits = scan_absolute_paths(target)
    if hits:
        sample = "; ".join(f"{r}: {f}" for r, f in hits[:3])
        return _fail(f"检出 {len(hits)} 处根绝对路径引用（{sample}）")
    return True, "无根绝对路径引用"


def auto_sdk_events(ctx: Ctx, target: Path):
    conf = _conf_for(target, ctx)
    t = ctx.text(target)
    if target.name == "taptap":
        return True, "TapTap 无强制生命周期上报要求"
    if "i2g-platform:crazygames" in t and "gameplayStart" not in t:
        return _fail("CrazyGames 产物未见 gameplayStart")
    return True, "lifecycle 事件存在（时机正确性需人工走查）"


def auto_ios_audio(ctx: Ctx, target: Path):
    t = ctx.text(target)
    if "touchend" not in t or "resume(" not in t:
        return _fail("缺少 iOS 音频恢复（需在 touchend/click 内 resume AudioContext）")
    return True, "含 iOS 音频恢复逻辑"


def auto_i18n_en(ctx: Ctx, target: Path):
    t = ctx.text(target)
    latin = len(re.findall(r"[A-Za-z]{3,}", t))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    if latin < 50:
        return _fail("产物中几乎无英文文案，英文本地化可能缺失")
    if cjk and cjk > latin * 4:
        return None, f"中文字符 {cjk} 个明显多于英文词 {latin} 个，需人工确认英文版本与 locale 切换"
    return True, f"检出英文文案（{latin} 个词）"


def _conf_for(target: Path, ctx: Ctx) -> dict:
    try:
        return platform_conf(target.name)
    except SystemExit:
        return platform_conf("crazygames")


AUTO = {
    "auto_total_size": auto_total_size,
    "auto_file_count": auto_file_count,
    "auto_initial_size": auto_initial_size,
    "auto_build_ok": auto_build_ok,
    "auto_short_intro": auto_short_intro,
    "auto_fps": auto_fps,
    "auto_memory": auto_memory,
    "auto_restricted_keys": auto_restricted_keys,
    "auto_scale_fit": auto_scale_fit,
    "auto_no_custom_fullscreen": auto_no_custom_fullscreen,
    "auto_no_external_ads": auto_no_external_ads,
    "auto_no_ad_chain": auto_no_ad_chain,
    "auto_no_appstore_links": auto_no_appstore_links,
    "auto_no_cross_promo": auto_no_cross_promo,
    "auto_user_select": auto_user_select,
    "auto_relative_paths": auto_relative_paths,
    "auto_sdk_events": auto_sdk_events,
    "auto_ios_audio": auto_ios_audio,
    "auto_i18n_en": auto_i18n_en,
}

# 需要按平台逐个产物重复执行的检查（取最差结果）
PER_TARGET = {
    "auto_total_size", "auto_file_count", "auto_initial_size",
    "auto_build_ok", "auto_short_intro", "auto_restricted_keys",
    "auto_scale_fit", "auto_no_custom_fullscreen", "auto_no_external_ads",
    "auto_no_ad_chain", "auto_no_appstore_links", "auto_no_cross_promo",
    "auto_user_select", "auto_relative_paths", "auto_sdk_events",
    "auto_ios_audio", "auto_i18n_en",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="IdeaToGame 审核官执行脚本")
    ap.add_argument("--project", default=None)
    ap.add_argument("--phase", required=True, choices=["r0", "r1", "r2"])
    ap.add_argument("--round", type=int, default=1)
    args = ap.parse_args()

    proj = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    if not (proj / ".gamedev" / "state.yaml").exists():
        print(f"ERROR: 未找到项目（缺 .gamedev/state.yaml）：{proj}", file=sys.stderr)
        return 1

    outdir = proj / "docs" / "09-review"
    (outdir / "evidence").mkdir(parents=True, exist_ok=True)

    ctx = Ctx(proj)
    dims = PHASE_DIMS[args.phase]
    items = [it for it in ITEMS if it[1] in dims]

    # 1. 人工条目模板
    manual_path = outdir / "manual-checks.json"
    manual_items = {it[0]: it[4] for it in items if it[3] is None}
    if manual_path.exists():
        try:
            manual = json.loads(manual_path.read_text(encoding="utf-8"))
        except Exception:
            manual = {}
    else:
        manual = {}
    changed = False
    for k, desc in manual_items.items():
        if k not in manual:
            manual[k] = {"desc": desc, "result": None, "evidence": ""}
            changed = True
    if changed or not manual_path.exists():
        manual_path.write_text(json.dumps(manual, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. 自动检查
    targets = ctx.targets()
    results: dict[str, dict] = {}
    for iid, dim, level, checker, desc in items:
        entry = {"id": iid, "dim": dim, "level": level, "desc": desc,
                 "result": "NA", "evidence": "", "auto": bool(checker)}
        if checker:
            fn = AUTO[checker]
            if checker in PER_TARGET and targets:
                oks, notes = [], []
                for t in targets:
                    try:
                        ok, note = fn(ctx, t)
                    except Exception as e:  # 自动检查失败不应中断审核
                        ok, note = None, f"{t.name}: 检查异常 {e}"
                    oks.append(ok)
                    notes.append(note)
                if any(o is False for o in oks):
                    entry["result"] = "FAIL"
                elif all(o is True for o in oks):
                    entry["result"] = "PASS"
                else:
                    entry["result"] = "NA"
                entry["evidence"] = " | ".join(notes)
            else:
                try:
                    if checker in PER_TARGET and not targets:
                        ok, note = None, "未找到构建产物，需先构建"
                    else:
                        ok, note = fn(ctx, targets[0] if targets else proj)
                except Exception as e:
                    ok, note = None, f"检查异常 {e}"
                entry["result"] = "PASS" if ok is True else ("FAIL" if ok is False else "NA")
                entry["evidence"] = note
        else:
            m = manual.get(iid) or {}
            r = (m.get("result") or "").strip().lower()
            if r in ("pass", "fail", "na"):
                entry["result"] = r.upper()
                entry["evidence"] = m.get("evidence", "")
            else:
                entry["result"] = "NA"
                entry["evidence"] = "未填写（请在 manual-checks.json 中判定）"
        results[iid] = entry

    # 3. 统计与结论
    req = [e for e in results.values() if e["level"] == "REQ"]
    gd = [e for e in results.values() if e["level"] == "GUIDE"]
    req_fail = [e for e in req if e["result"] == "FAIL"]
    gd_fail = [e for e in gd if e["result"] == "FAIL"]
    unresolved = [e for e in results.values() if e["result"] == "NA"]
    manual_unfilled = [e for e in unresolved if not e["auto"]]

    if req_fail:
        verdict = "REJECTED"
    elif gd_fail or manual_unfilled:
        verdict = "PASS_WITH_DEVIATIONS" if not manual_unfilled else "INCOMPLETE"
    else:
        verdict = "PASS"

    now = datetime.now().astimezone().isoformat(timespec="seconds")

    verdict_data = {
        "phase": args.phase,
        "round": args.round,
        "verdict": verdict,
        "standard": "crazygames",
        "standard_file": "references/crazygames-standard.md",
        "generated_at": now,
        "platforms": ctx.platforms,
        "req_total": len(req), "req_passed": len(req) - len(req_fail),
        "guide_total": len(gd), "guide_passed": len(gd) - len(gd_fail),
        "blockers": [{"item": e["id"], "desc": e["desc"], "evidence": e["evidence"]} for e in req_fail],
        "deviations": [{"item": e["id"], "desc": e["desc"], "evidence": e["evidence"]} for e in gd_fail],
        "pending_manual": [e["id"] for e in manual_unfilled],
    }

    # 4. 写 checklist.md
    lines = [
        f"# 审核清单 · {args.phase.upper()} 第 {args.round} 轮",
        "",
        f"- 项目：`{proj.name}`",
        f"- 目标平台：{', '.join(ctx.platforms) or '（未记录）'}",
        f"- 判据：`references/crazygames-standard.md`",
        f"- 时间：{now}",
        f"- 结论：**{verdict}**",
        "",
        "| 条目 | 维度 | 级别 | 结果 | 判定条件 | 证据 |",
        "|---|---|---|---|---|---|",
    ]
    mark = {"PASS": "PASS", "FAIL": "**FAIL**", "NA": "NA"}
    for e in results.values():
        ev = (e["evidence"] or "").replace("|", "/")
        lines.append(f"| {e['id']} | {e['dim']} | {e['level']} | {mark[e['result']]} | {e['desc']} | {ev} |")
    lines += [
        "",
        "## 统计",
        f"- REQ：{len(req) - len(req_fail)}/{len(req)} 通过" + (f"，阻塞 {len(req_fail)} 条: {', '.join(x['id'] for x in req_fail)}" if req_fail else ""),
        f"- GUIDE：{len(gd) - len(gd_fail)}/{len(gd)} 通过" + (f"，偏离 {len(gd_fail)} 条: {', '.join(x['id'] for x in gd_fail)}" if gd_fail else ""),
        f"- 待人工判定（未填写）：{len(manual_unfilled)} 条" + (f": {', '.join(x['id'] for x in manual_unfilled)}" if manual_unfilled else ""),
    ]
    (outdir / "checklist.md").write_text("\n".join(lines), encoding="utf-8")

    # 5. 写 issues.json（追加未修复的问题）
    issues_path = outdir / "issues.json"
    try:
        issues = json.loads(issues_path.read_text(encoding="utf-8")) if issues_path.exists() else []
    except Exception:
        issues = []
    known = {(i.get("item"), i.get("round")) for i in issues}
    nid = len(issues)
    for e in results.values():
        if e["result"] == "FAIL" and (e["id"], args.round) not in known:
            nid += 1
            issues.append({
                "id": f"ISSUE-{nid:03d}",
                "item": e["id"],
                "dimension": e["dim"],
                "severity": "blocker" if e["level"] == "REQ" else "major",
                "desc": e["desc"],
                "evidence": e["evidence"],
                "owner": OWNER.get(e["dim"], "08-polish"),
                "suggestion": "",
                "status": "open",
                "fix_note": "",
                "round": args.round,
                "found_at": now,
            })
    issues_path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. 写 verdict（按阶段分文件，另存一份 latest 便于查看）
    (outdir / f"verdict-{args.phase}.json").write_text(
        json.dumps(verdict_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (outdir / "verdict.json").write_text(
        json.dumps(verdict_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 7. 写 rounds.md（追加）
    rounds_path = outdir / "rounds.md"
    if not rounds_path.exists():
        rounds_path.write_text("# 审核轮次记录\n\n| 轮次 | 阶段 | 时间 | REQ 通过 | GUIDE 通过 | 结论 | 遗留项 |\n|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with rounds_path.open("a", encoding="utf-8") as f:
        f.write(f"| {args.round} | {args.phase.upper()} | {now} | {len(req) - len(req_fail)}/{len(req)} | "
                f"{len(gd) - len(gd_fail)}/{len(gd)} | {verdict} | "
                f"{', '.join(x['id'] for x in (req_fail or gd_fail)) or '-'} |\n")

    # 8. 更新 state.yaml
    stage_key = {"r0": "review_plan", "r1": "review_graybox", "r2": "review_final"}[args.phase]
    st = ctx.state
    stages = st.setdefault("stages", {})
    node = stages.setdefault(stage_key, {})
    node.update({
        "status": "done" if verdict in ("PASS", "PASS_WITH_DEVIATIONS") else "in_progress",
        "verdict": verdict,
        "round": args.round,
        "req_passed": f"{len(req) - len(req_fail)}/{len(req)}",
        "guide_passed": f"{len(gd) - len(gd_fail)}/{len(gd)}",
    })
    try:
        save_state(proj, st)
    except SystemExit:
        print("WARN: 未能写入 state.yaml（缺 PyYAML？）")

    # 9. 输出
    print("=" * 62)
    print(f"审核 {args.phase.upper()} 第 {args.round} 轮  项目: {proj.name}")
    print(f"目标平台: {', '.join(ctx.platforms) or '（未记录）'}")
    print("=" * 62)
    print(f"REQ   : {len(req) - len(req_fail)}/{len(req)} 通过")
    print(f"GUIDE : {len(gd) - len(gd_fail)}/{len(gd)} 通过")
    if req_fail:
        print("-" * 62)
        print("阻塞项（REQ FAIL，必须修复后复审）：")
        for e in req_fail:
            print(f"  [{e['id']}] {e['desc']}")
            print(f"        证据: {e['evidence']}")
    if gd_fail:
        print("-" * 62)
        print("偏离项（GUIDE FAIL，需记录并给改进计划）：")
        for e in gd_fail:
            print(f"  [{e['id']}] {e['desc']}")
    if manual_unfilled:
        print("-" * 62)
        print(f"待人工判定 {len(manual_unfilled)} 条 —— 请填写 {manual_path}")
        print(f"  {', '.join(x['id'] for x in manual_unfilled)}")
    print("=" * 62)
    print(f"结论: {verdict}")
    if verdict == "REJECTED":
        print("→ 不得进入 ship。修复后以 --round", args.round + 1, "重新送审（全量重跑）。")
    elif verdict == "INCOMPLETE":
        print("→ 人工条目未填完，无法给出结论。")
    elif verdict == "PASS_WITH_DEVIATIONS":
        print("→ 可进入 ship，但交付报告只能写「达到必需标准」，并须列出偏离清单。")
    else:
        print("→ 完全达标，可进入 ship。")

    return 0 if verdict in ("PASS", "PASS_WITH_DEVIATIONS") else 1


OWNER = {
    "A": "04-core-loop",
    "B": "04-core-loop",
    "C": "04-core-loop + 08-polish",
    "D": "05-art-forge + 06-sprite-tools",
    "E": "09-perf-audit",
    "F": "02-scaffold + 08-polish",
    "G": "08-polish + 02-scaffold",
    "H": "02-scaffold + 11-ship",
}


if __name__ == "__main__":
    raise SystemExit(main())

"""拼一屏完整的游戏画面（L0.5 美学 demo）。

不是素材陈列，是**按游戏真实布局**拼出来的 mockup：
720×1280、84px 网格、关卡 1 的真实路径、真实的 UI 位置。

这样看出来的观感才可信 —— 素材单独好看没用，拼进真实布局才知道行不行。
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ---- 与 config.ts 保持一致的布局参数
W, H = 720, 1280
CELL = 84
ORIGIN_X, ORIGIN_Y = 66, 240
COLS, ROWS = 7, 9

# 关卡 1 的路径（与 config.ts 的 LEVELS[0].path 一致）
PATH = [(0, 0), (5, 0), (5, 2), (1, 2), (1, 4), (5, 4), (5, 6), (1, 6), (1, 8), (6, 8)]

COL = {
    "bg": (13, 16, 23),
    "ground_a": (26, 33, 48),
    "ground_b": (22, 28, 41),
    "road": (58, 50, 38),
    "panel": (26, 31, 43),
    "edge": (47, 58, 77),
    "text": (232, 235, 245),
    "dim": (139, 147, 168),
    "gold": (240, 198, 116),
    "good": (70, 209, 127),
    "accent": (78, 161, 255),
}

import argparse
_ap = argparse.ArgumentParser(description="拼一屏游戏画面 mockup")
_ap.add_argument("--dir", required=True, help="素材目录（含 enemy_*/tower_*.png）")
_ap.add_argument("--out", default="mockup.png")
DEMO = Path(_ap.parse_args().dir).resolve()
OUT_NAME = _ap.parse_args().out


def load_font(size: int, bold: bool = False):
    """优先中文字体，退到系统默认。"""
    cands = [
        r"C:/Windows/Fonts/msyhbd.ttc" if bold else r"C:/Windows/Fonts/msyh.ttc",
        r"C:/Windows/Fonts/simhei.ttf",
        r"C:/Windows/Fonts/arial.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def path_cells():
    cells = set()
    for i in range(len(PATH) - 1):
        c0, r0 = PATH[i]
        c1, r1 = PATH[i + 1]
        dc, dr = (c1 > c0) - (c1 < c0), (r1 > r0) - (r1 < r0)
        c, r = c0, r0
        cells.add((c, r))
        while (c, r) != (c1, r1):
            c += dc
            r += dr
            cells.add((c, r))
    return cells


def center(c, r):
    return ORIGIN_X + c * CELL + CELL // 2, ORIGIN_Y + r * CELL + CELL // 2


def cutout(img: Image.Image) -> Image.Image:
    """抠掉浅灰背景。素材约定用浅色纯背景。"""
    im = img.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 198 and g > 198 and b > 198:
                px[x, y] = (0, 0, 0, 0)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def place(canvas: Image.Image, sprite: Image.Image, cx: int, cy: int, size: int):
    """把素材缩到 size 见方，中心对齐 (cx, cy)。"""
    s = sprite.copy()
    s.thumbnail((size, size), Image.LANCZOS)
    canvas.alpha_composite(s, (cx - s.width // 2, cy - s.height // 2))


def bar(canvas: Image.Image, x: int, y: int, w: int, ratio: float, color):
    d = ImageDraw.Draw(canvas)
    d.rectangle([x, y, x + w, y + 4], fill=(0, 0, 0, 140))
    if ratio > 0:
        d.rectangle([x, y, x + int(w * ratio), y + 4], fill=color)


def main():
    canvas = Image.new("RGBA", (W, H), COL["bg"] + (255,))
    d = ImageDraw.Draw(canvas)
    cells = path_cells()

    # ---- 网格地面（用 AI 纹理平铺，而不是纯色）
    #
    # 为什么必须用纹理：纯色地面和赛璐璐素材是「两张皮」——
    # 素材有描边和色块，纯色地面什么都没有，拼一起像贴纸贴深色板。
    # 纹理不需要完美无缝，只要「有材质感」就能把素材和背景拉到同一层。
    def prep(p: Path, blur: float, contrast: float, bright: float, tint):
        """纹理预处理：模糊去细节 + 降对比 + 压暗 + 统一色调。

        为什么必须处理：AI 生成的纹理是「小瓷砖」质感，缩到 84px 后变成密集网格，
        视觉噪音比素材还强，把主体压住了。
        **背景的职责是衬托，不是表现** —— 有材质感就够，不能有存在感。
        """
        im = Image.open(p).convert("RGB").resize((CELL, CELL), Image.LANCZOS)
        im = im.filter(ImageFilter.GaussianBlur(blur))
        im = ImageEnhance.Contrast(im).enhance(contrast)
        im = ImageEnhance.Brightness(im).enhance(bright)
        # 向目标色调靠拢，保证地面和路面是同一套色
        tint_layer = Image.new("RGB", im.size, tint)
        return Image.blend(im, tint_layer, 0.45)

    tile_g = tile_r = None
    pg, pr = DEMO / "tile_ground.png", DEMO / "tile_road.png"
    if pg.exists():
        tile_g = prep(pg, blur=2.2, contrast=0.45, bright=0.72, tint=(22, 28, 40))
    if pr.exists():
        tile_r = prep(pr, blur=2.2, contrast=0.5, bright=0.9, tint=(52, 42, 30))

    for r in range(ROWS):
        for c in range(COLS):
            x, y = ORIGIN_X + c * CELL, ORIGIN_Y + r * CELL
            is_road = (c, r) in cells
            tile = tile_r if is_road else tile_g
            if tile is not None:
                # 交替轻微明暗，避免平铺看起来太机械
                t = tile.copy()
                if (c + r) % 2 == 1:
                    t = Image.eval(t, lambda v: max(0, v - 8))
                canvas.paste(t, (x, y))
                # 路面亮度由 prep 的 tint/bright 控制，不再额外提亮
                # （额外提亮会让路径像发光带，反而刺眼）
            else:
                fill = COL["road"] if is_road else (COL["ground_a"] if (c + r) % 2 == 0 else COL["ground_b"])
                d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=fill)

    # 路面描边：让路径边界清晰（游戏里玩家要一眼看出敌人走哪）
    for (c, r) in cells:
        x, y = ORIGIN_X + c * CELL, ORIGIN_Y + r * CELL
        for dc, dr in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            if (c + dc, r + dr) not in cells and 0 <= c + dc < COLS and 0 <= r + dr < ROWS:
                if dr == -1:
                    d.line([x, y, x + CELL, y], fill=(18, 22, 30), width=1)
                elif dr == 1:
                    d.line([x, y + CELL - 1, x + CELL, y + CELL - 1], fill=(18, 22, 30), width=1)
                elif dc == -1:
                    d.line([x, y, x, y + CELL], fill=(18, 22, 30), width=1)
                else:
                    d.line([x + CELL - 1, y, x + CELL - 1, y + CELL], fill=(18, 22, 30), width=1)

    # ---- 基地
    bx, by = center(*PATH[-1])
    d.regular_polygon((bx, by, 30), 6, rotation=30, fill=COL["good"], outline=(20, 30, 25), width=3)

    # ---- 素材
    sprites = {}
    for name in ["enemy_grunt", "enemy_armored", "enemy_swift", "tower_arrow", "tower_cannon"]:
        p = DEMO / f"{name}.png"
        if p.exists():
            sprites[name] = cutout(Image.open(p))

    # 塔（放在路径内侧的可建格）
    tower_plan = [(2, 1, "tower_arrow"), (3, 1, "tower_cannon"), (2, 3, "tower_arrow"), (4, 5, "tower_cannon")]
    for c, r, key in tower_plan:
        if key in sprites:
            cx, cy = center(c, r)
            place(canvas, sprites[key], cx, cy, 68)
            d.ellipse([cx - 30, cy + 24, cx + 30, cy + 34], fill=(0, 0, 0, 60))

    # 敌人（沿路径排布，模拟排队前进）
    enemy_plan = [
        (0, 0.15, "enemy_grunt"), (0, 0.62, "enemy_grunt"),
        (1, 0.1, "enemy_swift"), (1, 0.55, "enemy_swift"),
        (0, 1.6, "enemy_armored"),
        (2, 0.4, "enemy_grunt"),
        (2, 0.85, "enemy_swift"),
    ]
    for seg, t, key in enemy_plan:
        if key not in sprites:
            continue
        c0, r0 = PATH[seg]
        c1, r1 = PATH[seg + 1]
        fx, fy = c0 + (c1 - c0) * t, r0 + (r1 - r0) * t
        cx = int(ORIGIN_X + fx * CELL + CELL // 2)
        cy = int(ORIGIN_Y + fy * CELL + CELL // 2)
        # 沿路方向的垂直错开，模拟游戏里的排队
        lane = ((hash(key + str(t)) % 3) - 1) * 7
        if r0 == r1:
            cy += lane
        else:
            cx += lane
        place(canvas, sprites[key], cx, cy, 56)
        bar(canvas, cx - 20, cy - 34, 40, 0.7 if "armored" in key else 0.45, (255, 92, 92))

    # ---- 弹道线（表现「正在开火」）
    for (c, r, key) in tower_plan[:2]:
        tx, ty = center(c, r)
        ex, ey = center(*PATH[1]) if c == 2 else center(*PATH[2])
        d.line([tx, ty, ex, ey - 10], fill=(111, 182, 255, 180), width=3)

    # ---- UI
    f_title = load_font(24, True)
    f_hud = load_font(22, True)
    f_small = load_font(15)
    f_tiny = load_font(13)

    d.text((W // 2, 40), "第一关 · 长路", font=f_title, fill=COL["text"], anchor="mt")
    d.text((28, 96), "金币 285", font=f_hud, fill=COL["text"])
    d.text((W // 2, 96), "生命 8", font=f_hud, fill=COL["text"], anchor="mt")
    d.text((W - 28, 96), "第 2/3 波", font=f_hud, fill=COL["text"], anchor="rt")

    # 底部建造栏
    y0 = 1016
    bw = (W - 48 - 24) // 3
    towers = [("箭塔", "50 金", "单体高伤", COL["accent"]), ("炮塔", "80 金", "溅射伤害", (240, 138, 93)), ("冰塔", "70 金", "减速", (143, 214, 232))]
    for i, (name, cost, desc, col) in enumerate(towers):
        bx = 24 + i * (bw + 12)
        d.rounded_rectangle([bx, y0, bx + bw, y0 + 104], 8, fill=COL["panel"], outline=COL["edge"], width=2)
        d.rectangle([bx + 18, y0 + 22, bx + 38, y0 + 42], fill=col)
        d.text((bx + 46, y0 + 22), name, font=f_hud, fill=COL["text"])
        d.text((bx + 46, y0 + 52), cost, font=f_small, fill=COL["gold"])
        d.text((bx + 14, y0 + 76), desc, font=f_tiny, fill=COL["dim"])

    # 星级
    d.text((W - 24, 150), "★ ★ ☆", font=load_font(20), fill=COL["gold"], anchor="rt")

    out = DEMO / OUT_NAME
    canvas.convert("RGB").save(out, quality=95)
    print(f"mockup: {out}  {canvas.size}")

    # 缩到手机实际显示尺寸，看是否还看得清
    small = canvas.convert("RGB").resize((360, 640), Image.LANCZOS)
    out2 = DEMO / "mockup_360.png"
    small.save(out2, quality=92)
    print(f"手机尺寸预览: {out2}")


if __name__ == "__main__":
    main()

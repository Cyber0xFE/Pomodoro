"""生成应用图标 — Neon Cyan HUD 风格，中心显示 "25".

特征:
- 深色球体背景 (Neon Cyan 主题的 edge 色 #0D1117)
- 双层霓虹青色光晕外环 (#00F0FF)
- 12 个刻度（4 个主刻度在 3/6/9/12 点）
- 中心大号数字 "25"（霓虹青色）
"""

from PIL import Image, ImageDraw, ImageFont
import math

SIZES = [16, 32, 48, 256]

# Neon Cyan 主题配色
NEON = (0, 240, 255)           # #00F0FF — 霓虹青
NEON_BRIGHT = (80, 245, 255)   # 稍亮的霓虹青（用于高光）
BG_OUTER = (20, 28, 38)        # 球体外圈（比 edge 稍亮）
BG_INNER = (13, 17, 23)        # 球体内圈 = #0D1117 (edge)
WHITE = (255, 255, 255)


def get_font(size_px: int, bold: bool = True):
    """获取合适大小的字体."""
    candidates = [
        "consolab.ttf" if bold else "consola.ttf",
        "consolaz.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size_px)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    margin = size * 0.04
    r = (size - margin * 2) / 2

    # ── 外层双层霓虹光晕 ──
    # 浅色外层
    glow_outer = r + size * 0.08
    draw.ellipse(
        [cx - glow_outer, cy - glow_outer, cx + glow_outer, cy + glow_outer],
        fill=NEON + (50,),
    )
    # 亮色内层
    glow_mid = r + size * 0.04
    draw.ellipse(
        [cx - glow_mid, cy - glow_mid, cx + glow_mid, cy + glow_mid],
        fill=NEON + (90,),
    )
    # 极亮层
    glow_inner = r + size * 0.015
    draw.ellipse(
        [cx - glow_inner, cy - glow_inner, cx + glow_inner, cy + glow_inner],
        fill=NEON_BRIGHT + (150,),
    )

    # ── 球体外圈 ──
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG_OUTER)

    # ── 球体内圈（更深） ──
    inner_pad = size * 0.025
    ir = r - inner_pad
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=BG_INNER)

    # ── 12 个刻度线 ──
    for i in range(12):
        angle = math.radians(i * 30 - 90)

        is_main = i % 3 == 0
        if is_main:
            inner_r = r - size * 0.08
            outer_r = r - size * 0.025
            tick_w = max(1, int(size * 0.018))
            color = NEON_BRIGHT + (230,)
        else:
            inner_r = r - size * 0.05
            outer_r = r - size * 0.02
            tick_w = max(1, int(size * 0.008))
            color = NEON + (150,)

        x1 = cx + inner_r * math.cos(angle)
        y1 = cy + inner_r * math.sin(angle)
        x2 = cx + outer_r * math.cos(angle)
        y2 = cy + outer_r * math.sin(angle)
        draw.line([x1, y1, x2, y2], fill=color, width=tick_w)

    # ── 中心数字 "25" ──
    if size >= 48:
        text = "25"
        font_size = int(size * 0.38)
        font = get_font(font_size, bold=True)

        # 测量文字尺寸
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # 文字居中绘制（霓虹青色，直接显示在深色背景上）
        tx = cx - tw / 2 - bbox[0]
        ty = cy - th / 2 - bbox[1]
        draw.text((tx, ty), text, fill=NEON, font=font)

    return img


def draw_icon_small(size: int) -> Image.Image:
    """小尺寸（16/32）专用：超采样 + 简化元素 + 边缘羽化."""
    from PIL import ImageFilter
    ss = 8
    big_size = size * ss
    img = Image.new("RGBA", (big_size, big_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = big_size / 2, big_size / 2
    r = big_size * 0.42

    # 辉光（多层）
    for gr, alpha in [(r + big_size * 0.12, 30),
                       (r + big_size * 0.08, 55),
                       (r + big_size * 0.04, 90),
                       (r + big_size * 0.015, 140)]:
        draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=NEON + (alpha,))

    # 球体
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG_INNER)
    # 描边
    sw = max(2, int(big_size * 0.035))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=None, outline=NEON_BRIGHT + (220,), width=sw)

    # 只画 4 个主刻度（3/6/9/12 点）
    for i in [0, 3, 6, 9]:
        angle = math.radians(i * 30 - 90)
        inner_r = r - big_size * 0.10
        outer_r = r - big_size * 0.015
        x1 = cx + inner_r * math.cos(angle)
        y1 = cy + inner_r * math.sin(angle)
        x2 = cx + outer_r * math.cos(angle)
        y2 = cy + outer_r * math.sin(angle)
        lw = max(2, int(big_size * 0.035))
        draw.line([x1, y1, x2, y2], fill=NEON_BRIGHT + (240,), width=lw)

    # 中心小圆点（小尺寸无法显示 "25" 文字）
    cr = max(2, int(big_size * 0.10))
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                 fill=NEON_BRIGHT + (255,))

    # 高质量缩回
    result = img.resize((size, size), Image.LANCZOS)
    result = result.filter(ImageFilter.SMOOTH)
    return result


def main():
    output = "app/assets/icons/pomodoro.ico"

    # 用最大尺寸绘制，让 PIL 自动缩放出其他尺寸
    master = draw_icon(256)
    master.save(
        output,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Icon saved: {output}")


if __name__ == "__main__":
    main()

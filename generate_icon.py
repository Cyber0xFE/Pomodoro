"""生成应用图标 — 仿照参考 HUD 风格.

参考图特征:
- 深灰蓝球体
- 双层霓虹青色光晕外环
- 12 个白色刻度（4 个粗大主刻度在 3/6/9/12 点）
- 中心大号时间数字（白底蓝字）
- 下方 "STANDBY" 状态文字
"""

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 32, 48, 256]

NEON = (107, 230, 240)       # 霓虹青（与参考图接近）
NEON_BRIGHT = (160, 240, 245)
BG_OUTER = (52, 65, 85)       # 球体外圈深蓝灰
BG_INNER = (38, 50, 68)       # 球体内圈更深
DARK = (28, 38, 52)
WHITE = (255, 255, 255)
TEXT_BLUE = (90, 200, 230)


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

    # ── 球体外圈（较亮的环） ──
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG_OUTER)

    # ── 球体内圈（更深） ──
    inner_pad = size * 0.025
    ir = r - inner_pad
    draw.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=BG_INNER)

    # ── 12 个刻度线 ──
    for i in range(12):
        angle_deg = i * 30 - 90
        import math
        angle = math.radians(angle_deg)

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

    # ── 中心时间文字（白底蓝字） ──
    if size >= 48:
        time_text = "10:00"
        font_size = int(size * 0.32)
        font = get_font(font_size, bold=True)

        # 测量文字尺寸
        bbox = draw.textbbox((0, 0), time_text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # 白底圆角矩形
        pad_x = size * 0.04
        pad_y = size * 0.015
        box_x = cx - tw / 2 - pad_x
        box_y = cy - th / 2 - pad_y - size * 0.02
        draw.rounded_rectangle(
            [box_x, box_y, box_x + tw + pad_x * 2, box_y + th + pad_y * 2],
            radius=int(size * 0.04),
            fill=WHITE,
        )
        # 蓝色文字
        tx = cx - tw / 2 - bbox[0]
        ty = cy - th / 2 - bbox[1] - size * 0.02
        draw.text((tx, ty), time_text, fill=TEXT_BLUE, font=font)

        # ── 状态文字 "STANDBY" ──
        status_font = get_font(int(size * 0.06), bold=False)
        status_text = "STANDBY"
        sbbox = draw.textbbox((0, 0), status_text, font=status_font)
        sw = sbbox[2] - sbbox[0]
        sx = cx - sw / 2 - sbbox[0]
        sy = cy + size * 0.16 - sbbox[1]
        draw.text((sx, sy), status_text, fill=NEON_BRIGHT, font=status_font)

    return img


def draw_icon_small(size: int) -> Image.Image:
    """小尺寸（16/32）专用：超采样 + 简化元素 + 边缘羽化."""
    import math
    from PIL import ImageFilter
    # 8x 超采样 + 8 倍细节
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

    # 只画 4 个主刻度（3/6/9/12 点），避免小元素过多
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

    # 中心实心圆（不画十字，避免在 16px 上变成像素块）
    cr = max(2, int(big_size * 0.10))
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                 fill=NEON_BRIGHT + (255,))

    # 高质量缩回
    result = img.resize((size, size), Image.LANCZOS)
    # 轻微平滑，进一步消除锯齿
    result = result.filter(ImageFilter.SMOOTH)
    return result


def main():
    images = []
    for s in SIZES:
        if s >= 48:
            images.append(draw_icon(s))
        else:
            images.append(draw_icon_small(s))

    output = "app/assets/icons/pomodoro.ico"
    images[0].save(
        output,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Icon saved: {output}")


if __name__ == "__main__":
    main()

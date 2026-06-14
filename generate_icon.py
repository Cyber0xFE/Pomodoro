"""生成赛博朋克风格图标 — 超采样抗锯齿."""

import math
from PIL import Image, ImageDraw

SIZES = [16, 32, 48, 256]
CYAN = (0, 240, 255)
DARK = (10, 12, 16)
SCALE = 4  # 超采样倍数


def draw_icon(size: int) -> Image.Image:
    """在 SCALE 倍尺寸画布上绘制，然后缩放获得抗锯齿."""
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2
    m = max(4, s // 12)
    r = (s - m * 2) / 2

    # ── 1. 深色圆形底 ──
    draw.ellipse([m, m, s - m, s - m], fill=DARK + (255,))

    # ── 2. 外层辉光 ──
    for i in range(3):
        gr = r + i * (s * 0.02)
        ga = [12, 25, 45][i]
        gw = max(3, int(s * 0.05 + i * s * 0.02))
        draw.ellipse(
            [cx - gr, cy - gr, cx + gr, cy + gr],
            fill=None, outline=CYAN + (ga,), width=gw,
        )

    # ── 3. 霓虹圆环 ──
    ring_w = max(3, s // 14)
    draw.ellipse(
        [cx - r * 0.75, cy - r * 0.75, cx + r * 0.75, cy + r * 0.75],
        fill=None, outline=CYAN + (220,), width=ring_w,
    )

    # ── 4. 四角 HUD 标线 ──
    corner_len = r * 0.35
    corner_gap = r * 0.55
    corner_w = max(2, s // 40)
    for dx in (-1, 1):
        for dy in (-1, 1):
            hx = cx + dx * corner_gap
            hy = cy + dy * corner_gap
            draw.line(
                [hx, hy, hx + dx * corner_len, hy],
                fill=CYAN + (200,), width=corner_w,
            )
            draw.line(
                [hx, hy, hx, hy + dy * corner_len],
                fill=CYAN + (200,), width=corner_w,
            )

    # ── 5. 中心点 ──
    dot_r = max(3, s // 22)
    draw.ellipse(
        [cx - dot_r * 1.8, cy - dot_r * 1.8, cx + dot_r * 1.8, cy + dot_r * 1.8],
        fill=CYAN + (25,),
    )
    draw.ellipse(
        [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
        fill=CYAN + (255,),
    )

    # ── 6. 高光 ──
    hl_r = r * 0.1
    hl_x = cx - r * 0.3
    hl_y = cy - r * 0.35
    draw.ellipse(
        [hl_x - hl_r, hl_y - hl_r, hl_x + hl_r, hl_y + hl_r],
        fill=(255, 255, 255, 45),
    )

    # ── 缩放回目标尺寸（LANCZOS 获得平滑边缘） ──
    return img.resize((size, size), Image.LANCZOS)


def main():
    images = []
    for s in SIZES:
        images.append(draw_icon(s))

    output = "app/assets/icons/pomodoro.ico"
    images[0].save(
        output, format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Icon saved: {output}")


if __name__ == "__main__":
    main()

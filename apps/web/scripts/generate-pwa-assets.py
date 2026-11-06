"""Generate every PWA raster asset from the brand mark.

Run from apps/web with the API virtualenv (which has Pillow):

    ../api/.venv/Scripts/python scripts/generate-pwa-assets.py

Outputs (committed to the repo):
    public/icons/icon-192.png / icon-512.png            regular (rounded, "any")
    public/icons/icon-maskable-192.png / -512.png       maskable (full-bleed, safe zone)
    public/icons/shortcut-{provider,trainee,employer,admin}.png
    public/apple-touch-icon.png                         180x180, full-bleed square
    public/splash/splash-<width>x<height>.png           Apple startup images
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PETROL = (30, 93, 95, 255)        # #1E5D5F
MARIGOLD = (227, 174, 39, 255)    # #E3AE27
PAPER = (238, 249, 247, 255)      # #EEF9F7
CREAM = (250, 249, 246, 255)      # #FAF9F6 page background

# Brand path from src/app/icon.svg, in the 32x32 viewBox space.
PATH_POINTS = [(6.0, 24.5), (13.0, 18.0), (19.5, 13.5), (26.0, 7.5)]
DOTS = [(13.0, 18.0), (19.5, 13.5)]
ARROW_A = (20.8, 7.1)
ARROW_TIP = (26.0, 7.5)
ARROW_B = (25.6, 12.7)

PUBLIC = Path(__file__).resolve().parent.parent / "public"
SPLASH_SIZES = [
    (1290, 2796),  # iPhone Pro Max
    (1179, 2556),  # iPhone Pro
    (1284, 2778),  # iPhone Plus
    (1170, 2532),  # iPhone
    (1125, 2436),  # iPhone X-class
    (2048, 2732),  # iPad Pro 12.9
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _scaled(point: tuple[float, float], origin_x: float, origin_y: float, span: float):
    """Map a 32-space point into a span x span box anchored at origin."""
    return (origin_x + point[0] / 32.0 * span, origin_y + point[1] / 32.0 * span)


def draw_mark(draw: ImageDraw.ImageDraw, origin_x: float, origin_y: float, span: float) -> None:
    """Draw the rising milestone path inside the given box."""
    stroke = max(2, int(span * (2.6 / 32.0)))
    radius = stroke / 2
    points = [_scaled(p, origin_x, origin_y, span) for p in PATH_POINTS]

    for start, end in zip(points, points[1:]):
        draw.line([start, end], fill=MARIGOLD, width=stroke)
    for centre in points:
        draw.ellipse(
            [centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius],
            fill=MARIGOLD,
        )
    for centre_scaled in DOTS:
        cx, cy = _scaled(centre_scaled, origin_x, origin_y, span)
        dot = span * (2.1 / 32.0)
        draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=PAPER)

    for start, end in (
        (_scaled(ARROW_A, origin_x, origin_y, span), _scaled(ARROW_TIP, origin_x, origin_y, span)),
        (_scaled(ARROW_TIP, origin_x, origin_y, span), _scaled(ARROW_B, origin_x, origin_y, span)),
    ):
        draw.line([start, end], fill=MARIGOLD, width=stroke)
        for centre in (start, end):
            draw.ellipse(
                [centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius],
                fill=MARIGOLD,
            )


def regular_icon(size: int) -> Image.Image:
    """Rounded petrol square with transparent corners (the "any" purpose)."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size * 0.02
    span = size - 2 * margin
    draw.rounded_rectangle(
        [margin, margin, margin + span, margin + span], radius=span * 0.24, fill=PETROL
    )
    inset = span * 0.14
    draw_mark(draw, margin + inset, margin + inset, span - 2 * inset)
    return image


def maskable_icon(size: int) -> Image.Image:
    """Full-bleed square; artwork inside the 80% maskable safe zone."""
    image = Image.new("RGBA", (size, size), PETROL)
    draw = ImageDraw.Draw(image)
    span = size * 0.62
    draw_mark(draw, (size - span) / 2, (size - span) / 2, span)
    return image


def full_bleed_icon(size: int) -> Image.Image:
    """Full-bleed square with the mark at touch-icon proportions."""
    image = Image.new("RGBA", (size, size), PETROL)
    draw = ImageDraw.Draw(image)
    draw_mark(draw, size * 0.17, size * 0.17, size * 0.66)
    return image


def shortcut_icon(size: int, letter: str) -> Image.Image:
    """Round petrol badge with a white role initial — manifest shortcuts."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([0, 0, size - 1, size - 1], fill=PETROL)
    font = _load_font(int(size * 0.5))
    left, top, right, bottom = draw.textbbox((0, 0), letter, font=font)
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
        letter,
        font=font,
        fill=PAPER,
    )
    draw.ellipse([size * 0.66, size * 0.66, size * 0.84, size * 0.84], fill=MARIGOLD)
    return image


def splash(width: int, height: int) -> Image.Image:
    """Apple startup image: cream background, mark + wordmark, centred."""
    image = Image.new("RGB", (width, height), CREAM)
    draw = ImageDraw.Draw(image)

    mark = full_bleed_icon(192).resize((144, 144), Image.LANCZOS)
    image.paste(mark, ((width - 144) // 2, int(height * 0.38)), mark)

    font = _load_font(64)
    text = "TrackSkill AI"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_y = int(height * 0.38) + 144 + 48
    draw.text(
        ((width - (right - left)) / 2 - left, text_y - top), text, font=font, fill=PETROL
    )

    underline_w, underline_h = int((right - left) * 0.4), 8
    draw.rounded_rectangle(
        [
            (width - underline_w) // 2,
            text_y + (bottom - top) + 24,
            (width - underline_w) // 2 + underline_w,
            text_y + (bottom - top) + 24 + underline_h,
        ],
        radius=4,
        fill=MARIGOLD,
    )
    return image


def main() -> None:
    (PUBLIC / "icons").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "splash").mkdir(parents=True, exist_ok=True)

    for size in (192, 512):
        regular_icon(size).save(PUBLIC / "icons" / f"icon-{size}.png")
        maskable_icon(size).save(PUBLIC / "icons" / f"icon-maskable-{size}.png")

    full_bleed_icon(180).save(PUBLIC / "apple-touch-icon.png")

    for name, letter in (
        ("provider", "P"),
        ("trainee", "T"),
        ("employer", "E"),
        ("admin", "A"),
    ):
        shortcut_icon(96, letter).save(PUBLIC / "icons" / f"shortcut-{name}.png")

    for width, height in SPLASH_SIZES:
        splash(width, height).save(PUBLIC / "splash" / f"splash-{width}x{height}.png")

    print(f"assets written to {PUBLIC}")


if __name__ == "__main__":
    main()

"""Gera os ícones PNG (site e app Android) a partir do mesmo desenho do icon.svg."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BLUE = (47, 111, 237, 255)
WHITE = (255, 255, 255, 255)


def draw(size: int, background: bool = True, padding: float = 0.0) -> Image.Image:
    """Desenha em 4x e reduz para ficar sem serrilhado."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = s / 512
    if background:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=112 * k, fill=BLUE)
    # Para o ícone adaptativo do Android o desenho precisa caber na "zona segura".
    scale = 1 - padding
    off = s * padding / 2

    def p(x, y):
        return (off + x * k * scale, off + y * k * scale)

    w = 32 * k * scale
    x0, y0 = p(96, 120)
    x1, y1 = p(416, 336)
    d.rounded_rectangle((x0, y0, x1, y1), radius=28 * k * scale, outline=WHITE, width=round(w))
    d.line([p(256, 336), p(256, 400)], fill=WHITE, width=round(w))
    d.line([p(196, 400), p(316, 400)], fill=WHITE, width=round(w))
    for cx, cy in (p(196, 400), p(316, 400)):
        d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=WHITE)
    d.polygon([p(226, 170), p(330, 226), p(284, 237), p(263, 283)], fill=WHITE)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main():
    static = ROOT / "static"
    draw(192).save(static / "icon-192.png")
    draw(512).save(static / "icon-512.png")

    res = ROOT / "android" / "app" / "src" / "main" / "res"
    for density, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        folder = res / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        draw(px).save(folder / "ic_launcher.png")
        # Primeiro plano do ícone adaptativo (108dp, com margem).
        fg = draw(round(px * 108 / 48), background=False, padding=0.42)
        fg.save(folder / "ic_launcher_foreground.png")
    print("ícones gerados")


if __name__ == "__main__":
    main()

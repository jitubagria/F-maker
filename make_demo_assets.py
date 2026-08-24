"""Build DEMO template backgrounds + logos + a synthetic test photo.
These stand in for the real Photoshop PNG templates and real drive photos,
just to prove the engine end to end."""
import os, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

R = os.path.dirname(os.path.abspath(__file__))
W, H = 1024, 468
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def grad(c1, c2, w, h, diagonal=False):
    base = Image.new("RGB", (w, h), c1)
    top = Image.new("RGB", (w, h), c2)
    mask = Image.new("L", (w, h))
    md = mask.load()
    for y in range(h):
        for x in range(w):
            t = ((x + y) / (w + h)) if diagonal else (x / w)
            md[x, y] = int(255 * t)
    return Image.composite(top, base, mask)


def template_bg(path, c1, c2, accent, right_panel):
    img = grad(c1, c2, W, H, diagonal=True).convert("RGBA")
    d = ImageDraw.Draw(img)
    # faint darker panel on the right where the photo sits
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.ellipse([W-560, -180, W+140, H+180], fill=accent + (60,))
    img.alpha_composite(panel)
    # thin accent line under logo area
    d.rectangle([48, 84, 240, 90], fill=accent + (255,))
    img.convert("RGB").save(path)
    print("bg:", os.path.basename(path))


def logo(path, text, color):
    img = Image.new("RGBA", (600, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FB, 74)
    # gear-ish mark
    d.ellipse([6, 24, 92, 110], outline=(255, 255, 255, 255), width=8)
    d.ellipse([34, 52, 64, 82], fill=(255, 255, 255, 255))
    d.text((110, 30), text, font=f, fill=(255, 255, 255, 255))
    img.save(path)
    print("logo:", os.path.basename(path))


def synthetic_photo(path):
    """A crude 'student photo' on a plain background, so rembg has a subject
    to cut out. Real pipeline uses your actual drive photos."""
    img = Image.new("RGB", (600, 800), (210, 214, 222))
    d = ImageDraw.Draw(img)
    # head
    d.ellipse([220, 120, 380, 300], fill=(214, 170, 140))
    # hair
    d.chord([220, 100, 380, 260], 180, 360, fill=(45, 32, 26))
    # shoulders / shirt (white uniform)
    d.polygon([(180, 800), (200, 470), (300, 360), (400, 470), (420, 800)],
              fill=(245, 245, 248))
    # tie
    d.polygon([(300, 380), (285, 430), (300, 620), (315, 430)], fill=(26, 92, 56))
    img.save(path, "JPEG", quality=92)
    print("photo:", os.path.basename(path))


if __name__ == "__main__":
    template_bg(os.path.join(R, "templates/matrix_news_bg.png"),
                (12, 60, 36), (26, 92, 56), (245, 197, 24), True)
    template_bg(os.path.join(R, "templates/edunews_news_bg.png"),
                (10, 30, 90), (18, 58, 138), (245, 197, 24), True)
    logo(os.path.join(R, "templates/logo_matrix.png"), "MATRIX", (255, 255, 255))
    logo(os.path.join(R, "templates/logo_edunews.png"), "EDUNEWS", (255, 255, 255))
    synthetic_photo(os.path.join(R, "raw_photos/student1.jpg"))

#!/usr/bin/env python3
"""
HexaPremium — premium social-image design compiler.
Topic/content JSON in -> premium design PNG out. All text is typeset by code
(never AI-drawn), rendered at 2x supersample, downscaled + sharpened so it
survives platform compression.

Style engine: combinatorial axes (layout x theme x card-style x decor x font-pair).
A seed picks the combo deterministically; a history file prevents repeats.

Usage:
  python3 hexapremium.py --content content.json --out out.png \
      [--platform linkedin-post] [--seed 42] [--layout hero] [--theme peach] \
      [--cardstyle sticker] [--decor dots] [--fontpair bold] [--no-history]
Prints one JSON line: {out, seed, combo, platform, size_px, qa:{...}}
"""
import argparse, colorsys, json, math, os, random, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

SS = 2  # supersample factor

PLATFORMS = {
    "linkedin-post":   (1600, 900),
    "linkedin-square": (1200, 1200),
    "linkedin-cover":  (1584, 396),
    "ig-square":       (1080, 1080),
    "ig-portrait":     (1080, 1350),
    "story":           (1080, 1920),
    "yt-thumbnail":    (1280, 720),
}

FONT_DIR_DEJAVU = "/usr/share/fonts/truetype/dejavu"
FONT_DIR_NOTO = "/usr/share/fonts/truetype/noto"

def _font_path(name, *dirs):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None

def has_bengali(s):
    return any("\u0980" <= ch <= "\u09FF" for ch in str(s))

class Fonts:
    """Font-pair axis: which typefaces pair for display/body/mono."""
    PAIRS = {
        "bold":   dict(display="DejaVuSans-Bold.ttf", body="DejaVuSans.ttf",
                       body_b="DejaVuSans-Bold.ttf", mono="DejaVuSansMono.ttf",
                       mono_b="DejaVuSansMono-Bold.ttf"),
        "serif":  dict(display="DejaVuSerif-Bold.ttf", body="DejaVuSans.ttf",
                       body_b="DejaVuSans-Bold.ttf", mono="DejaVuSansMono.ttf",
                       mono_b="DejaVuSansMono-Bold.ttf"),
        "mono":   dict(display="DejaVuSansMono-Bold.ttf", body="DejaVuSans.ttf",
                       body_b="DejaVuSans-Bold.ttf", mono="DejaVuSansMono.ttf",
                       mono_b="DejaVuSansMono-Bold.ttf"),
    }
    def __init__(self, pair="bold"):
        self.spec = self.PAIRS.get(pair, self.PAIRS["bold"])
        self.cache = {}
    def get(self, kind, size, bengali=False):
        size = max(6, int(size * SS))
        key = (kind, size, bengali)
        if key in self.cache:
            return self.cache[key]
        if bengali:
            name = "NotoSansBengali-Bold.ttf" if kind in ("display", "body_b", "mono_b") else "NotoSansBengali-Regular.ttf"
            p = _font_path(name, FONT_DIR_NOTO)
        else:
            p = _font_path(self.spec[kind], FONT_DIR_DEJAVU, FONT_DIR_NOTO)
        f = ImageFont.truetype(p, size) if p else ImageFont.load_default()
        self.cache[key] = f
        return f

# ---------------------------------------------------------------- themes
# bg gradient top->bottom, ink (main text), sub (muted), accent, accent2,
# card (fill), dark (terminal card fill), on_dark (text on accent/dark)
THEMES = {
    "peach":  dict(bg1=(255, 214, 170), bg2=(250, 166, 108), ink=(16, 32, 56),
                   sub=(94, 106, 128), accent=(234, 88, 12), accent2=(185, 28, 28),
                   card=(255, 255, 255), dark=(13, 20, 38), chip=(16, 32, 56),
                   on_chip=(255, 255, 255), banner=(13, 22, 41)),
    "navy":   dict(bg1=(10, 18, 38), bg2=(23, 42, 84), ink=(16, 32, 56),
                   sub=(94, 106, 128), accent=(249, 115, 22), accent2=(220, 38, 38),
                   card=(255, 255, 255), dark=(6, 10, 24), chip=(249, 115, 22),
                   on_chip=(255, 255, 255), banner=(249, 115, 22)),
    "mint":   dict(bg1=(209, 250, 229), bg2=(110, 231, 183), ink=(6, 46, 38),
                   sub=(71, 96, 88), accent=(5, 150, 105), accent2=(190, 24, 93),
                   card=(255, 255, 255), dark=(4, 32, 26), chip=(6, 46, 38),
                   on_chip=(255, 255, 255), banner=(6, 46, 38)),
    "sunset": dict(bg1=(253, 186, 140), bg2=(244, 114, 182), ink=(49, 10, 46),
                   sub=(110, 74, 106), accent=(190, 24, 93), accent2=(124, 58, 237),
                   card=(255, 255, 255), dark=(38, 8, 34), chip=(49, 10, 46),
                   on_chip=(255, 255, 255), banner=(49, 10, 46)),
    "mono":   dict(bg1=(24, 24, 27), bg2=(9, 9, 11), ink=(24, 24, 27),
                   sub=(100, 100, 110), accent=(245, 197, 66), accent2=(239, 68, 68),
                   card=(255, 255, 255), dark=(0, 0, 0), chip=(245, 197, 66),
                   on_chip=(24, 24, 27), banner=(245, 197, 66)),
    "sky":    dict(bg1=(191, 219, 254), bg2=(125, 178, 250), ink=(12, 30, 62),
                   sub=(80, 96, 124), accent=(29, 78, 216), accent2=(185, 28, 28),
                   card=(255, 255, 255), dark=(8, 20, 44), chip=(12, 30, 62),
                   on_chip=(255, 255, 255), banner=(12, 30, 62)),
}
DARK_THEMES = {"navy", "mono"}

# ---------------------------------------------------------------- helpers
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def gradient(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(c1, c2, y / max(1, h - 1)))
    return img

def text_w(draw, s, font):
    return draw.textlength(str(s), font=font)

def wrap(draw, s, font, maxw):
    words = str(s).split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_w(draw, t, font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines or [""]

def fit_size(draw, s, kind, fonts, start, maxw, minimum=10):
    """Largest font size <= start whose single line fits maxw."""
    bn = has_bengali(s)
    size = start
    while size > minimum:
        if text_w(draw, s, fonts.get(kind, size, bn)) <= maxw:
            return size
        size -= 2
    return minimum

def shadow_layer(size, radius, blur=14, alpha=110):
    lay = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle([blur, blur, size[0] - blur, size[1] - blur],
                        radius=radius, fill=(10, 10, 20, alpha))
    return lay.filter(ImageFilter.GaussianBlur(blur // 2))

class Canvas:
    def __init__(self, w, h, theme, fonts, cardstyle, decor):
        self.w, self.h = w, h
        self.th = theme
        self.fonts = fonts
        self.cardstyle = cardstyle
        self.img = gradient(w * SS, h * SS, theme["bg1"], theme["bg2"]).convert("RGBA")
        self.d = ImageDraw.Draw(self.img)
        self._decor(decor)

    def _decor(self, decor):
        d, th = self.d, self.th
        W, H = self.w * SS, self.h * SS
        dot_col = (255, 255, 255, 34)
        if decor == "dots":
            step = 46 * SS
            for x in range(step // 2, W, step):
                for y in range(step // 2, H, step):
                    d.ellipse([x - 2 * SS, y - 2 * SS, x + 2 * SS, y + 2 * SS], fill=dot_col)
        elif decor == "grid":
            step = 54 * SS
            for x in range(0, W, step):
                d.line([(x, 0), (x, H)], fill=(255, 255, 255, 17), width=SS)
            for y in range(0, H, step):
                d.line([(0, y), (W, y)], fill=(255, 255, 255, 17), width=SS)
        elif decor == "rings":
            cx, cy = int(W * 0.82), int(H * 0.18)
            for r in range(60 * SS, 420 * SS, 56 * SS):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 34), width=2 * SS)
        # "plain" = nothing

    # -- primitives (logical coords; SS applied inside)
    def rrect(self, box, rad, fill=None, outline=None, width=1):
        b = [v * SS for v in box]
        self.d.rounded_rectangle(b, radius=rad * SS, fill=fill, outline=outline,
                                 width=max(1, int(width * SS)) if outline else 1)
    def rect(self, box, fill):
        self.d.rectangle([v * SS for v in box], fill=fill)
    def line(self, pts, fill, width=2):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=max(1, int(width * SS)))
    def ellipse(self, box, fill=None, outline=None, width=2):
        self.d.ellipse([v * SS for v in box], fill=fill, outline=outline,
                       width=max(1, int(width * SS)) if outline else 1)
    def text(self, xy, s, kind, size, fill, anchor="la", align="left"):
        f = self.fonts.get(kind, size, has_bengali(s))
        self.d.text((xy[0] * SS, xy[1] * SS), str(s), font=f, fill=fill, anchor=anchor, align=align)
    def tw(self, s, kind, size):
        return text_w(self.d, s, self.fonts.get(kind, size, has_bengali(s))) / SS
    def wrap(self, s, kind, size, maxw):
        return wrap(self.d, s, self.fonts.get(kind, size, has_bengali(s)), maxw * SS)
    def paste(self, layer, x, y):
        self.img.alpha_composite(layer, (int(x * SS), int(y * SS)))

    # -- card shell: returns inner draw target info; supports card styles
    def card(self, x, y, w, h, dark=False, tilt=0.0):
        """Draw a card background at logical (x,y,w,h). Returns (x,y,w,h)."""
        th = self.th
        fill = th["dark"] if dark else th["card"]
        pad = 10
        lay = Image.new("RGBA", (int((w + pad * 2) * SS), int((h + pad * 2) * SS)), (0, 0, 0, 0))
        sh = shadow_layer(lay.size, 18 * SS, blur=(16 if self.cardstyle == "sticker" else 10) * SS,
                          alpha=120 if self.cardstyle == "sticker" else 84)
        lay.alpha_composite(sh, (0, 0))
        ld = ImageDraw.Draw(lay)
        box = [pad * SS, pad * SS, (w + pad) * SS, (h + pad) * SS]
        if self.cardstyle == "glass":
            fill = fill + (246,) if len(fill) == 3 else fill
            ld.rounded_rectangle(box, radius=16 * SS, fill=fill)
            ld.rounded_rectangle(box, radius=16 * SS, outline=th["accent"] + (255,), width=2 * SS)
            ld.rectangle([box[0] + 16 * SS, box[1], box[2] - 16 * SS, box[1] + 5 * SS], fill=th["accent"] + (255,))
        else:
            ld.rounded_rectangle(box, radius=16 * SS, fill=fill)
        if tilt and self.cardstyle == "sticker":
            lay = lay.rotate(tilt, resample=Image.BICUBIC, expand=False)
        self.img.alpha_composite(lay, (int((x - pad) * SS), int((y - pad) * SS)))
        return (x, y, w, h)

    def finish(self, out_path):
        img = self.img.convert("RGB")
        img = img.resize((self.w, self.h), Image.LANCZOS)
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = ImageEnhance.Contrast(img).enhance(1.02)
        img.save(out_path, quality=95)
        return img.size

# ---------------------------------------------------------------- person cutout
def cutout_person(path, mode="hsv"):
    """Return RGBA person image. mode 'hsv': teal/cyan studio-bg removal
    (proven on Jony's LinkedIn avatar). mode 'none': plain rounded paste."""
    im = Image.open(path).convert("RGB")
    if mode != "hsv":
        out = im.convert("RGBA")
        return out
    small = im.resize((im.width // 3, im.height // 3), Image.LANCZOS).convert("HSV")
    px = small.load()
    alpha = Image.new("L", small.size, 0)
    ap = alpha.load()
    for yy in range(small.height):
        for xx in range(small.width):
            hh, ss, vv = px[xx, yy]
            hue = hh * 360 / 255.0
            sat = ss / 255.0
            if 176 <= hue <= 208 and sat >= 0.86:
                a = 0
            elif 172 <= hue <= 212 and sat >= 0.78:
                a = 110
            else:
                a = 255
            ap[xx, yy] = a
    alpha = alpha.resize(im.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    # trim to content bbox
    bbox = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    return out

# ---------------------------------------------------------------- cards
CODE_COLORS = dict(plain=(226, 232, 240), cmd=(147, 197, 253), ok=(74, 222, 128),
                   bad=(248, 113, 113), warn=(251, 191, 36), dim=(148, 163, 184),
                   accent=(251, 146, 60), white=(255, 255, 255))
BAR_COLORS = dict(critical=(220, 38, 38), high=(234, 88, 12), medium=(234, 179, 8),
                  low=(59, 130, 246), default=(37, 99, 235))

def draw_card(cv, x, y, w, card, k, cs, tilt=0.0):
    """Draw one card; return its height (logical px)."""
    th, F = cv.th, cv.fonts
    t = card.get("type", "text")
    dark = t == "code"
    P = 18 * k * cs
    # --- measure content first (heights), then draw shell, then content
    if t == "stat":
        val = str(card.get("value", ""))
        vs = fit_size(cv.d, val, "display", F, 58 * k * cs, w - 2 * P)
        lab_lines = cv.wrap(card.get("label", ""), "body_b", 17 * k * cs, w - 2 * P)
        sub_lines = cv.wrap(card.get("sub", ""), "body", 14 * k * cs, w - 2 * P) if card.get("sub") else []
        h = P + vs * 1.15 + 6 * k + len(lab_lines) * 22 * k * cs + len(sub_lines) * 19 * k * cs + P * 0.6
        cv.card(x, y, w, h, dark=False, tilt=tilt)
        cy = y + P * 0.8
        cv.text((x + P, cy), val, "display", vs, th["accent"]); cy += vs * 1.15 + 6 * k
        for ln in lab_lines:
            cv.text((x + P, cy), ln, "body_b", 17 * k * cs, th["ink"]); cy += 22 * k * cs
        for ln in sub_lines:
            cv.text((x + P, cy), ln, "body", 14 * k * cs, th["sub"]); cy += 19 * k * cs
        return h
    if t == "code":
        lines = card.get("lines", [])
        ms = 15 * k * cs
        if lines:
            widest = max(lines, key=lambda ln: len(str(ln.get("t", ""))))
            ms = fit_size(cv.d, str(widest.get("t", "")), "mono", F, ms, w - 2 * P)
        lh = 25 * k * cs * (ms / (15 * k * cs))
        h = P + 20 * k * cs + 10 * k + len(lines) * lh + P * 0.7
        cv.card(x, y, w, h, dark=True, tilt=tilt)
        cy = y + P * 0.75
        for i, c in enumerate([(248, 113, 113), (251, 191, 36), (74, 222, 128)]):
            cv.ellipse([x + P + i * 20 * k, cy, x + P + i * 20 * k + 11 * k, cy + 11 * k], fill=c)
        cv.text((x + P + 74 * k, cy - 3 * k), card.get("title", "terminal"), "mono", 13.5 * k * cs, (148, 163, 184))
        cy += 20 * k * cs + 10 * k
        for ln in lines:
            cv.text((x + P, cy), ln.get("t", ""), "mono", ms, CODE_COLORS.get(ln.get("c", "plain"), CODE_COLORS["plain"]))
            cy += lh
        return h
    if t == "toggles":
        rows = card.get("rows", [])
        title_lines = cv.wrap(card.get("title", ""), "display", 21 * k * cs, w - 2 * P)
        sub_lines = cv.wrap(card.get("sub", ""), "body", 14.5 * k * cs, w - 2 * P) if card.get("sub") else []
        row_h = 42 * k * cs
        h = P + len(title_lines) * 26 * k * cs + len(sub_lines) * 20 * k * cs + 6 * k + len(rows) * row_h + P * 0.55
        cv.card(x, y, w, h, tilt=tilt)
        cy = y + P * 0.8
        for ln in title_lines:
            cv.text((x + P, cy), ln, "display", 21 * k * cs, th["ink"]); cy += 26 * k * cs
        for ln in sub_lines:
            cv.text((x + P, cy), ln, "body", 14.5 * k * cs, th["sub"]); cy += 20 * k * cs
        cy += 6 * k
        for name, ver in rows:
            cv.text((x + P, cy + 6 * k * cs), name, "body_b", 16.5 * k * cs, th["ink"])
            vw = cv.tw(ver, "body", 14 * k * cs)
            tw_, th_ = 46 * k, 25 * k
            tx = x + w - P - tw_
            cv.text((tx - 12 * k - vw, cy + 7 * k * cs), ver, "body", 14 * k * cs, th["sub"])
            cv.rrect([tx, cy + 3 * k, tx + tw_, cy + 3 * k + th_], th_ / 2, fill=th["accent"])
            cv.ellipse([tx + tw_ - th_ + 3 * k, cy + 6 * k, tx + tw_ - 3 * k, cy + th_], fill=(255, 255, 255))
            cy += row_h
        return h
    if t == "bars":
        rows = card.get("rows", [])
        title_lines = cv.wrap(card.get("title", ""), "display", 21 * k * cs, w - 2 * P)
        row_h = 40 * k * cs
        h = P + len(title_lines) * 26 * k * cs + 6 * k + len(rows) * row_h + P * 0.5
        cv.card(x, y, w, h, tilt=tilt)
        cy = y + P * 0.8
        for ln in title_lines:
            cv.text((x + P, cy), ln, "display", 21 * k * cs, th["ink"]); cy += 26 * k * cs
        cy += 6 * k
        for row in rows:
            label, pct = row[0], float(row[1])
            col = BAR_COLORS.get(str(row[2]).lower(), th["accent"]) if len(row) > 2 else th["accent"]
            cv.text((x + P, cy), label, "body_b", 15 * k * cs, th["ink"])
            bw = w - 2 * P
            by = cy + 21 * k * cs
            cv.rrect([x + P, by, x + P + bw, by + 12 * k], 6 * k, fill=(226, 232, 240))
            cv.rrect([x + P, by, x + P + bw * max(0.02, min(1.0, pct / 100.0)), by + 12 * k], 6 * k, fill=col)
            cy += row_h
        return h
    if t == "checklist":
        items = card.get("items", [])
        title_lines = cv.wrap(card.get("title", ""), "display", 21 * k * cs, w - 2 * P)
        item_lines = [cv.wrap(it, "body", 16 * k * cs, w - 2 * P - 34 * k) for it in items]
        h = P + len(title_lines) * 26 * k * cs + 8 * k + sum(len(il) * 22 * k * cs + 7 * k for il in item_lines) + P * 0.5
        cv.card(x, y, w, h, tilt=tilt)
        cy = y + P * 0.8
        for ln in title_lines:
            cv.text((x + P, cy), ln, "display", 21 * k * cs, th["ink"]); cy += 26 * k * cs
        cy += 8 * k
        for it, il in zip(items, item_lines):
            r = 10.5 * k
            cv.ellipse([x + P, cy + 1 * k, x + P + 2 * r, cy + 1 * k + 2 * r], fill=th["accent"])
            cv.text((x + P + r, cy + r - 8.5 * k * cs), "✓", "body_b", 13.5 * k * cs, (255, 255, 255), anchor="ma")
            for ln in il:
                cv.text((x + P + 32 * k, cy), ln, "body", 16 * k * cs, th["ink"]); cy += 22 * k * cs
            cy += 7 * k
        return h
    if t == "quote":
        q_lines = cv.wrap(card.get("text", ""), "display", 25 * k * cs, w - 2 * P)
        by_lines = cv.wrap(card.get("by", ""), "body", 14.5 * k * cs, w - 2 * P) if card.get("by") else []
        h = P + len(q_lines) * 33 * k * cs + len(by_lines) * 20 * k * cs + P * 0.7
        cv.card(x, y, w, h, tilt=tilt)
        cy = y + P * 0.85
        for ln in q_lines:
            cv.text((x + P, cy), ln, "display", 25 * k * cs, th["ink"]); cy += 33 * k * cs
        for ln in by_lines:
            cv.text((x + P, cy + 2 * k), ln, "body", 14.5 * k * cs, th["sub"]); cy += 20 * k * cs
        return h
    # default: text card
    title_lines = cv.wrap(card.get("title", ""), "display", 21 * k * cs, w - 2 * P) if card.get("title") else []
    body_lines = cv.wrap(card.get("body", ""), "body", 16.5 * k * cs, w - 2 * P)
    h = P + len(title_lines) * 26 * k * cs + (6 * k if title_lines else 0) + len(body_lines) * 23 * k * cs + P * 0.6
    cv.card(x, y, w, h, tilt=tilt)
    cy = y + P * 0.8
    for ln in title_lines:
        cv.text((x + P, cy), ln, "display", 21 * k * cs, th["ink"]); cy += 26 * k * cs
    cy += 6 * k if title_lines else 0
    for ln in body_lines:
        cv.text((x + P, cy), ln, "body", 16.5 * k * cs, th["sub"] if title_lines else th["ink"]); cy += 23 * k * cs
    return h

def masonry(cv, cards, cols, k, cs, top, bottom_limit, gap=22):
    """cols: list of (x, w). Returns max column bottom (overflow if > bottom_limit)."""
    heights = [top for _ in cols]
    tilt_cycle = [1.1, -1.1, 0.7, -0.7, 0.0]
    for i, card in enumerate(cards):
        ci = min(range(len(cols)), key=lambda j: heights[j])
        x, w = cols[ci]
        tilt = tilt_cycle[i % len(tilt_cycle)] if cv.cardstyle == "sticker" else 0.0
        h = draw_card(cv, x, heights[ci], w, card, k, cs, tilt=tilt)
        heights[ci] += h + gap * k
    return max(heights) - gap * k

def lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255.0

def draw_banner(cv, content, k):
    th = cv.th
    bh = 62 * k
    cv.rect([0, 0, cv.w, bh], fill=th["banner"])
    tc = (255, 255, 255) if lum(th["banner"]) < 0.6 else th["ink"]
    left, mid, right = content.get("hook_left", ""), content.get("hook", ""), content.get("hook_right", "")
    if left:
        cv.text((30 * k, bh / 2), left, "body_b", 15.5 * k, tc, anchor="lm")
    if right:
        cv.text((cv.w - 30 * k, bh / 2), right, "body_b", 15.5 * k, tc, anchor="rm")
    if mid:
        ms = fit_size(cv.d, mid, "display", cv.fonts, 27 * k, cv.w * 0.52)
        cv.text((cv.w / 2, bh / 2), mid, "display", ms, tc, anchor="mm")
    return bh

def draw_cta(cv, content, k, y=None):
    th = cv.th
    cta = content.get("cta", "")
    if not cta:
        return 0
    fs = 17 * k
    tw_ = cv.tw(cta, "body_b", fs) + 56 * k
    ch = 44 * k
    yy = (cv.h - ch - 26 * k) if y is None else y
    x = (cv.w - tw_) / 2
    tc = th["on_chip"]
    lay = shadow_layer((int((tw_ + 20) * SS), int((ch + 20) * SS)), 22 * SS, blur=10 * SS, alpha=90)
    cv.paste(lay, x - 10, yy - 10)
    cv.rrect([x, yy, x + tw_, yy + ch], ch / 2, fill=th["chip"])
    cv.text((cv.w / 2, yy + ch / 2), cta, "body_b", fs, tc, anchor="mm")
    return ch

def bg_text_colors(cv):
    dark = cv.theme_name in DARK_THEMES
    return ((255, 255, 255) if dark else cv.th["ink"],
            (203, 213, 225) if dark else cv.th["sub"])

# ---------------------------------------------------------------- layouts
def layout_hero(cv, content, cs, person):
    k = cv.k
    W, H = cv.w, cv.h
    ink, sub = bg_text_colors(cv)
    y = draw_banner(cv, content, k) if content.get("hook") else 26 * k
    y += 30 * k
    title = content.get("title", "")
    ts = fit_size(cv.d, title, "display", cv.fonts, 60 * k * cs, W - 200 * k)
    # title may wrap to 2 lines if a single line can't fit at min size
    t_lines = [title] if cv.tw(title, "display", ts) <= W - 200 * k else cv.wrap(title, "display", 44 * k * cs, W - 220 * k)
    for ln in t_lines:
        cv.text((W / 2, y), ln, "display", ts if len(t_lines) == 1 else 44 * k * cs, ink, anchor="ma")
        y += (ts if len(t_lines) == 1 else 44 * k * cs) * 1.18
    if content.get("subtitle"):
        s_lines = cv.wrap(content["subtitle"], "body", 21 * k * cs, W - 320 * k)
        for ln in s_lines:
            cv.text((W / 2, y + 4 * k), ln, "body", 21 * k * cs, sub, anchor="ma"); y += 29 * k * cs
    y += 22 * k
    bottom_limit = H - 96 * k
    cards = content.get("cards", [])
    if person is not None:
        ph = bottom_limit - y + 60 * k
        pw = ph * person.width / person.height
        px = (W - pw) / 2
        person = person.resize((int(pw * SS), int(ph * SS)), Image.LANCZOS)
        cv.paste(person, px, bottom_limit - ph + 84 * k)
        colw = (W - pw) / 2 - 84 * k
        cols = [(44 * k, colw), (W - 44 * k - colw, colw)]
    else:
        cols = [(48 * k, (W - 96 * k - 24 * k) / 2), (48 * k + (W - 96 * k - 24 * k) / 2 + 24 * k, (W - 96 * k - 24 * k) / 2)]
    end = masonry(cv, cards, cols, k, cs, y, bottom_limit)
    draw_cta(cv, content, k)
    return end <= bottom_limit + 4, end - bottom_limit

def layout_split(cv, content, cs, person):
    k = cv.k
    W, H = cv.w, cv.h
    ink, sub = bg_text_colors(cv)
    y0 = draw_banner(cv, content, k) if content.get("hook") else 0
    lx, lw = 52 * k, W * 0.40
    y = y0 + 44 * k
    if person is not None:
        ph = H * 0.34
        pw = ph * person.width / person.height
        if pw > lw:
            pw = lw; ph = pw * person.height / person.width
        person = person.resize((int(pw * SS), int(ph * SS)), Image.LANCZOS)
        cv.paste(person, lx, y)
        y += ph + 20 * k
    title = content.get("title", "")
    ts = 46 * k * cs
    for ln in cv.wrap(title, "display", ts, lw):
        cv.text((lx, y), ln, "display", ts, ink); y += ts * 1.16
    if content.get("subtitle"):
        for ln in cv.wrap(content["subtitle"], "body", 20 * k * cs, lw):
            cv.text((lx, y + 4 * k), ln, "body", 20 * k * cs, sub); y += 28 * k * cs
    y += 12 * k
    for b in content.get("bullets", []):
        bl = cv.wrap(b, "body", 17.5 * k * cs, lw - 30 * k)
        cv.text((lx + 2 * k, y), "▸", "body_b", 17.5 * k * cs, cv.th["accent"])
        for ln in bl:
            cv.text((lx + 26 * k, y), ln, "body", 17.5 * k * cs, ink); y += 24 * k * cs
        y += 6 * k
    brand = (content.get("brand") or {}).get("name", "")
    if brand:
        cv.text((lx, H - 52 * k), brand, "display", 19 * k, cv.th["accent"])
    rx = lx + lw + 44 * k
    rw = W - rx - 48 * k
    end = masonry(cv, content.get("cards", []), [(rx, rw)], k, cs, y0 + 40 * k, H - 40 * k, gap=20)
    return end <= H - 36 * k, end - (H - 36 * k)

def layout_grid(cv, content, cs, person):
    k = cv.k
    W, H = cv.w, cv.h
    ink, sub = bg_text_colors(cv)
    y = draw_banner(cv, content, k) if content.get("hook") else 26 * k
    y += 28 * k
    title = content.get("title", "")
    ts = fit_size(cv.d, title, "display", cv.fonts, 50 * k * cs, W - 120 * k)
    cv.text((52 * k, y), title, "display", ts, ink); y += ts * 1.2
    if content.get("subtitle"):
        cv.text((52 * k, y), content["subtitle"], "body", 20 * k * cs, sub); y += 32 * k * cs
    y += 14 * k
    n = 3 if W >= 1300 else 2
    total_w = W - 104 * k
    cw = (total_w - (n - 1) * 22 * k) / n
    cols = [(52 * k + i * (cw + 22 * k), cw) for i in range(n)]
    end = masonry(cv, content.get("cards", []), cols, k, cs, y, H - 100 * k)
    draw_cta(cv, content, k)
    return end <= H - 96 * k + 4, end - (H - 96 * k)

def layout_dashboard(cv, content, cs, person):
    k = cv.k
    W, H = cv.w, cv.h
    ink, sub = bg_text_colors(cv)
    y = draw_banner(cv, content, k) if content.get("hook") else 26 * k
    y += 26 * k
    title = content.get("title", "")
    ts = fit_size(cv.d, title, "display", cv.fonts, 46 * k * cs, W - 120 * k)
    cv.text((52 * k, y), title, "display", ts, ink)
    if content.get("subtitle"):
        stw = cv.tw(content["subtitle"], "body", 19 * k * cs)
        cv.text((W - 52 * k, y + ts * 0.32), content["subtitle"], "body", 19 * k * cs, sub, anchor="ra")
    y += ts * 1.25 + 12 * k
    cards = content.get("cards", [])
    bottom_limit = H - 96 * k
    if not cards:
        draw_cta(cv, content, k)
        return True, 0
    fw = (W - 104 * k) * 0.565
    fh = draw_card(cv, 52 * k, y, fw, cards[0], k, cs)
    rx = 52 * k + fw + 24 * k
    rw = W - rx - 52 * k
    end_r = masonry(cv, cards[1:], [(rx, rw)], k, cs, y, bottom_limit, gap=20)
    end = max(y + fh, end_r)
    draw_cta(cv, content, k)
    return end <= bottom_limit + 4, end - bottom_limit

LAYOUTS = {"hero": layout_hero, "split": layout_split, "grid": layout_grid,
           "dashboard": layout_dashboard}

# ---------------------------------------------------------------- style engine
AXES = dict(layout=list(LAYOUTS), theme=list(THEMES),
            cardstyle=["flat", "sticker", "glass"], decor=["dots", "grid", "rings", "plain"],
            fontpair=list(Fonts.PAIRS))
TOTAL_COMBOS = 1
for _v in AXES.values():
    TOTAL_COMBOS *= len(_v)

def combo_key(c):
    return "|".join(c[a] for a in ("layout", "theme", "cardstyle", "decor", "fontpair"))

def choose_combo(seed, history_keys, explicit):
    rng = random.Random(seed)
    base = {a: (explicit.get(a) or rng.choice(AXES[a])) for a in AXES}
    if explicit:
        return base
    for _ in range(300):
        c = {a: rng.choice(AXES[a]) for a in AXES}
        if combo_key(c) not in history_keys:
            return c
    return base

def render(content, combo, platform, out_path, person_img=None):
    W, H = PLATFORMS[platform]
    theme = THEMES[combo["theme"]]
    fonts = Fonts(combo["fontpair"])
    person_layer = None
    if person_img is not None:
        ph = int(H * 0.62 * SS)
        pw = int(ph * person_img.width / person_img.height)
        person_layer = person_img.resize((pw, ph), Image.LANCZOS)
    k = (W / 1600.0) if W >= H else (W / 1200.0)
    def measure(cs):
        scratch = Canvas(W, H, theme, fonts, combo["cardstyle"], combo["decor"])
        scratch.theme_name = combo["theme"]; scratch.k = k
        p = person_layer.copy() if person_layer is not None else None
        return LAYOUTS[combo["layout"]](scratch, content, cs, p)
    fits, over, cs_used = False, None, 1.0
    for cs in (1.0, 0.93, 0.86, 0.79):
        ok, over = measure(cs)
        cs_used = cs
        if ok:
            fits = True
            break
    if fits and over is not None and over < -0.20 * H:
        # underfilled canvas (tall formats): grow content to fill premium-style
        for cs in (1.15, 1.3, 1.45):
            ok, over2 = measure(cs)
            if ok:
                cs_used, over = cs, over2
            else:
                break
    cv = Canvas(W, H, theme, fonts, combo["cardstyle"], combo["decor"])
    cv.theme_name = combo["theme"]; cv.k = k
    LAYOUTS[combo["layout"]](cv, content, cs_used, person_layer)
    size = cv.finish(out_path)
    qa = dict(fits=fits, content_scale=cs_used, overflow_px=round(max(0.0, over or 0), 1),
              cards=len(content.get("cards", [])), min_font_ok=cs_used >= 0.79)
    return size, qa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--platform", default="linkedin-post", choices=list(PLATFORMS))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--layout"); ap.add_argument("--theme"); ap.add_argument("--cardstyle")
    ap.add_argument("--decor"); ap.add_argument("--fontpair")
    ap.add_argument("--history", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "history.json"))
    ap.add_argument("--no-history", action="store_true")
    args = ap.parse_args()

    with open(args.content, encoding="utf-8") as f:
        content = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(args.content))
    if not content.get("title") and content.get("topic"):
        content["title"] = content["topic"]

    hist = []
    if not args.no_history and os.path.exists(args.history):
        try:
            hist = json.load(open(args.history, encoding="utf-8"))
        except Exception:
            hist = []
    hist_keys = {h.get("combo", "") for h in hist}

    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 9)
    explicit = {a: getattr(args, a) for a in AXES if getattr(args, a)}
    for a, v in explicit.items():
        if v not in AXES[a]:
            print(json.dumps({"error": f"bad {a}: {v}", "options": AXES[a]})); sys.exit(2)
    combo = choose_combo(seed, hist_keys, explicit)

    person_img = None
    pinfo = content.get("person") or {}
    if pinfo.get("image"):
        ppath = pinfo["image"]
        if not os.path.isabs(ppath):
            ppath = os.path.join(base_dir, ppath)
        person_img = cutout_person(ppath, pinfo.get("cutout", "none"))

    size, qa = render(content, combo, args.platform, args.out, person_img)
    rec = dict(seed=seed, combo=combo_key(combo), topic=content.get("title", "")[:80],
               out=os.path.abspath(args.out))
    if not args.no_history:
        hist.append(rec)
        with open(args.history, "w", encoding="utf-8") as f:
            json.dump(hist[-500:], f, ensure_ascii=False, indent=1)
    print(json.dumps(dict(out=rec["out"], seed=seed, combo=combo, platform=args.platform,
                          size_px=list(size), total_combos=TOTAL_COMBOS, qa=qa), ensure_ascii=False))

if __name__ == "__main__":
    main()

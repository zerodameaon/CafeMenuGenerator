"""The decorative layer of the holiday sign designs: moons, leaves,
snowflakes, fireworks and so on, drawn as inline SVG/CSS.

Everything here is absolutely positioned and pointer-free, so it never
takes part in layout and can't trip the wrap/overflow check. Keep new
decorations that way.
"""
from __future__ import annotations

import itertools
import math

def _spider_web_svg(size: int, color: str) -> str:
    """A corner cobweb anchored at the SVG's top-right corner."""
    spokes = 7
    angles = [math.pi / 2 + i * (math.pi / 2) / (spokes - 1) for i in range(spokes)]  # 90°..180°
    lines, rings = [], []
    for a in angles:
        lines.append(f'<line x1="{size}" y1="0" x2="{size + size * math.cos(a):.1f}" '
                     f'y2="{size * math.sin(a):.1f}"/>')
    for r in (0.22, 0.42, 0.62, 0.82):
        pts = [(size + r * size * math.cos(a), r * size * math.sin(a)) for a in angles]
        d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            # Control point pulled toward the corner so each strand sags.
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            cx, cy = mx + (size - mx) * 0.18, my * 0.82
            d += f" Q{cx:.1f},{cy:.1f} {x1:.1f},{y1:.1f}"
        rings.append(f'<path d="{d}"/>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" fill="none" '
            f'stroke="{color}" stroke-width="2.2" stroke-linecap="round">{"".join(lines)}{"".join(rings)}</svg>')


_BAT_PATH = (
    "M50 16 C47 11 44 10 42 13 C35 5 20 3 0 9 C10 13 14 19 14 27 C20 23 28 23 32 29 "
    "C36 25 42 25 46 31 L50 37 L54 31 C58 25 64 25 68 29 C72 23 80 23 86 27 "
    "C86 19 90 13 100 9 C80 3 65 5 58 13 C56 10 53 11 50 16 Z "
    "M45 14 L46 6 L49 12 Z M55 14 L54 6 L51 12 Z"
)


def _bat_svg(width: int, color: str, rotate: float) -> str:
    return (f'<svg width="{width}" height="{width * 0.4:.0f}" viewBox="0 0 100 40" '
            f'style="transform: rotate({rotate}deg)"><path d="{_BAT_PATH}" fill="{color}"/></svg>')


_MAPLE_PATH = (
    "M50 4 L57 20 L66 15 L63 38 L78 27 L82 34 L94 31 L88 45 L96 50 L74 64 L78 72 "
    "L54 68 L52 96 L48 96 L46 68 L22 72 L26 64 L4 50 L12 45 L6 31 L18 34 L22 27 "
    "L37 38 L34 15 L43 20 Z"
)
_MAPLE_VEINS = "M50 96 L50 22 M50 62 L80 36 M50 62 L20 36 M50 70 L72 66 M50 70 L28 66"
_ELM_PATH = "M50 4 C76 24 80 60 50 90 C20 60 24 24 50 4 Z"
_ELM_VEINS = "M50 98 L50 14 M50 40 L66 30 M50 40 L34 30 M50 58 L68 46 M50 58 L32 46"


def _leaf_svg(shape: str, size: int, color: str, rotate: float) -> str:
    path, veins = (_MAPLE_PATH, _MAPLE_VEINS) if shape == "maple" else (_ELM_PATH, _ELM_VEINS)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" '
            f'style="transform: rotate({rotate}deg)"><path d="{path}" fill="{color}"/>'
            f'<path d="{veins}" fill="none" stroke="rgba(42,26,17,0.45)" stroke-width="2.5" '
            f'stroke-linecap="round"/></svg>')


def _snowflake_svg(size: int, color: str) -> str:
    """Six arms, each with a pair of branches."""
    arms = []
    for i in range(6):
        a = math.radians(i * 60 - 90)
        ex, ey = 50 + 46 * math.cos(a), 50 + 46 * math.sin(a)
        arms.append(f"M50 50 L{ex:.1f} {ey:.1f}")
        bx, by = 50 + 28 * math.cos(a), 50 + 28 * math.sin(a)
        for side in (-1, 1):
            b = a + side * math.radians(40)
            arms.append(f"M{bx:.1f} {by:.1f} L{bx + 14 * math.cos(b):.1f} {by + 14 * math.sin(b):.1f}")
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" fill="none" '
            f'stroke="{color}" stroke-width="5" stroke-linecap="round"><path d="{" ".join(arms)}"/></svg>')


def _ornament_html(left: int, string_len: int, size: int, color: str) -> str:
    """A bauble hanging from the sign's top edge on a thin string."""
    cap = size * 0.28
    return (f'<div class="deco ornament-string" style="left:{left + size / 2 - 1:.0f}px; height:{string_len}px;"></div>'
            f'<div class="deco ornament-cap" style="left:{left + (size - cap) / 2:.0f}px; top:{string_len - 2}px; '
            f'width:{cap:.0f}px; height:{cap * 0.6:.0f}px;"></div>'
            f'<div class="deco ornament" style="left:{left}px; top:{string_len + cap * 0.5:.0f}px; '
            f'width:{size}px; height:{size}px; background: radial-gradient(circle at 35% 32%, '
            f'rgba(255,255,255,0.55) 0%, {color} 28%, {color} 70%, rgba(0,0,0,0.35) 100%);"></div>')


def _christmas_decorations(t: dict) -> tuple[str, str]:
    """Snowflakes drifting down the brand column, and baubles hanging into
    the sign's top-right corner."""
    css = """
.deco { position: absolute; pointer-events: none; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
.ornament-string { top: 0; width: 2px; background: rgba(230,193,90,0.55); }
.ornament-cap { background: #c9a74a; border-radius: 3px; }
.ornament { border-radius: 50%; }
"""
    # (left, top, size, opacity)
    flakes = (
        (466, 214, 92, 0.85), (396, 330, 46, 0.6), (566, 318, 60, 0.7),
        (594, 220, 30, 0.55), (494, 392, 34, 0.5),
    )
    deco = "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px; opacity:{o};">{_snowflake_svg(size, t["brand_text"])}</div>'
        for x, y, size, o in flakes
    )
    # Hang in the gap between the item text and the sign's right edge.
    deco += (_ornament_html(3596, 70, 58, "#c8262e") + _ornament_html(3686, 26, 72, "#d9b44a")
             + _ornament_html(3786, 96, 46, "#2f7a4f"))
    return css, deco


def _firework_svg(size: int, color: str, rays: int = 14) -> str:
    """A burst: rays from a gap around the center, each tipped with a spark."""
    parts = []
    for i in range(rays):
        a = 2 * math.pi * i / rays
        x0, y0 = 50 + 14 * math.cos(a), 50 + 14 * math.sin(a)
        x1, y1 = 50 + 40 * math.cos(a), 50 + 40 * math.sin(a)
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}"/>')
        parts.append(f'<circle cx="{50 + 47 * math.cos(a):.1f}" cy="{50 + 47 * math.sin(a):.1f}" '
                     f'r="2.6" fill="{color}" stroke="none"/>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" stroke="{color}" '
            f'stroke-width="2.6" stroke-linecap="round">{"".join(parts)}</svg>')


def _newyear_decorations(t: dict) -> tuple[str, str]:
    """Fireworks bursting in the brand column, and gold-and-silver confetti
    in the sign's top-right corner."""
    css = """
.deco { position: absolute; pointer-events: none; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
.confetti { border-radius: 2px; }
"""
    # (left, top, size, color, rays)
    bursts = (
        (440, 198, 150, t["gold"], 16),
        (372, 330, 80, "#c9ccd6", 12),
        (536, 322, 92, "#e6a0b4", 12),
        (578, 214, 50, "#c9ccd6", 10),
    )
    deco = "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px;">{_firework_svg(size, color, rays)}</div>'
        for x, y, size, color, rays in bursts
    )
    # (left, top, width, height, color, rotation)
    confetti = (
        (3620, 22, 18, 8, t["gold"], 28), (3668, 64, 14, 6, "#c9ccd6", -40),
        (3712, 18, 20, 8, "#e6a0b4", 62), (3760, 52, 16, 7, t["gold"], -18),
        (3800, 14, 12, 6, "#c9ccd6", 44), (3734, 102, 18, 7, t["gold"], 80),
        (3790, 132, 14, 6, "#e6a0b4", -60), (3650, 118, 12, 5, t["gold"], 12),
        (3700, 160, 10, 5, "#c9ccd6", -30), (3812, 196, 12, 6, t["gold"], 20),
    )
    deco += "".join(
        f'<div class="deco confetti" style="left:{x}px; top:{y}px; width:{w}px; height:{h}px; '
        f'background:{c}; transform: rotate({r}deg); opacity:0.75;"></div>'
        for x, y, w, h, c, r in confetti
    )
    return css, deco


def _star_svg(size: int, color: str) -> str:
    pts = []
    for i in range(10):
        r = 50 if i % 2 == 0 else 20
        a = -math.pi / 2 + i * math.pi / 5
        pts.append(f"{50 + r * math.cos(a):.1f},{52 + r * math.sin(a):.1f}")
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 100 100">'
            f'<polygon points="{" ".join(pts)}" fill="{color}"/></svg>')


def _veterans_decorations(t: dict) -> tuple[str, str]:
    """A small constellation of stars in the brand column, and a thin
    red-and-white stripe ribbon along the bottom of the whole sign."""
    css = """
.deco { position: absolute; pointer-events: none; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
.ribbon {
  left: 0; bottom: 0; width: 3840px; height: 14px;
  background: linear-gradient(#d63a43 0 5px, #f4f1ea 5px 9px, #d63a43 9px 14px);
  opacity: 0.85;
}
"""
    # (left, top, size, color)
    stars = (
        (452, 228, 112, t["brand_text"]),
        (396, 344, 50, t["gold"]),
        (566, 330, 58, t["gold"]),
        (588, 226, 34, t["brand_text"]),
        (500, 382, 30, t["brand_text"]),
    )
    deco = "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px;">{_star_svg(size, color)}</div>'
        for x, y, size, color in stars
    ) + '<div class="deco ribbon"></div>'
    return css, deco


def _thanksgiving_decorations(t: dict) -> tuple[str, str]:
    """Autumn leaves drifting down the brand column, and a few blown into
    the sign's top-right corner."""
    css = """
.deco { position: absolute; pointer-events: none; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
.corner-leaves { opacity: 0.5; }
"""
    # (shape, left, top, size, color, rotation)
    falling = (
        ("maple", 468, 206, 96, "#d9531e", -18),
        ("elm", 392, 300, 58, "#e2a32e", 34),
        ("maple", 540, 318, 70, "#a8321f", 22),
        ("elm", 470, 384, 48, "#c98a2c", -48),
        ("maple", 584, 236, 40, "#e2a32e", 8),
    )
    corner = (
        ("maple", 3712, -26, 120, "#d9531e", 28),
        ("elm", 3640, 8, 66, "#e2a32e", -62),
        ("maple", 3772, 92, 60, "#a8321f", -14),
    )
    deco = "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px;">{_leaf_svg(shape, size, color, rot)}</div>'
        for shape, x, y, size, color, rot in falling
    ) + '<div class="deco corner-leaves" style="left:0; top:0;">' + "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px;">{_leaf_svg(shape, size, color, rot)}</div>'
        for shape, x, y, size, color, rot in corner
    ) + "</div>"
    return css, deco


def _halloween_decorations(t: dict) -> tuple[str, str]:
    css = """
.deco { position: absolute; pointer-events: none; }
.moon {
  left: 430px; top: 250px; width: 170px; height: 170px; border-radius: 50%;
  background: radial-gradient(circle at 38% 38%, #fff4d6 0%, #f3dfae 55%, #d9bf86 100%);
  opacity: 0.85;
}
.moon-glow {
  left: 335px; top: 155px; width: 360px; height: 360px; border-radius: 50%;
  background: radial-gradient(circle, rgba(243,223,174,0.22) 0%, rgba(243,223,174,0.08) 45%, rgba(243,223,174,0) 70%);
}
.web { right: 0; top: 0; opacity: 0.32; }
.spider-thread { right: 150px; top: 0; width: 2px; height: 128px; background: rgba(239,227,200,0.35); }
.spider { right: 137px; top: 124px; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
/* Room for Nosifer's drips to hang below the logo and day name. */
.subtitle { margin-top: 22px; }
.day-name { margin-bottom: 16px; }
"""
    bat = "#0a070e"
    bats = (
        f'<div class="deco" style="left:395px; top:268px;">{_bat_svg(78, bat, -12)}</div>'
        f'<div class="deco" style="left:530px; top:330px;">{_bat_svg(52, bat, 14)}</div>'
        f'<div class="deco" style="left:575px; top:236px;">{_bat_svg(40, bat, -6)}</div>'
    )
    spider = (
        '<svg class="deco spider" width="28" height="30" viewBox="0 0 28 30" fill="none" '
        f'stroke="{t["brand_text"]}" stroke-width="1.8" stroke-linecap="round" opacity="0.6">'
        '<path d="M14 12 L4 4 M14 12 L2 12 M14 14 L3 22 M14 16 L6 28 '
        'M14 12 L24 4 M14 12 L26 12 M14 14 L25 22 M14 16 L22 28"/>'
        f'<ellipse cx="14" cy="14" rx="5" ry="6" fill="{t["brand_text"]}" stroke="none"/></svg>'
    )
    deco = (
        f'<div class="deco moon-glow"></div><div class="deco moon"></div>{bats}'
        f'<div class="deco web">{_spider_web_svg(260, t["brand_text"])}</div>'
        f'<div class="deco spider-thread"></div>{spider}'
    )
    return css, deco


# The CSS every decorated theme needs: lift the brand column and menu above
# the decorations.
_BASE_CSS = """
.deco { position: absolute; pointer-events: none; }
.canvas { position: relative; }
.menu, .brand { position: relative; z-index: 1; }
"""

# The empty middle of the brand column, between the subtitle and the day
# name: one big motif and four smaller ones around it, as (left, top, size).
_BRAND_SPOTS = ((452, 206, 110), (390, 330, 54), (552, 320, 66), (590, 222, 36), (494, 392, 34))
# The sign's top-right corner, past where the menu text reaches.
_CORNER_SPOTS = ((3700, 18, 64), (3632, 92, 34), (3786, 96, 40), (3800, 12, 26), (3730, 150, 24))

# SVG ids must be unique across the page, and one page can repeat a motif.
_ids = itertools.count()


def _place(spots, motifs, opacity: float = 1) -> str:
    """Puts each (size → svg, rotation) motif on the matching spot."""
    return "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px; transform: rotate({rot}deg); opacity:{opacity};">'
        f'{svg(size)}</div>'
        for (x, y, size), (svg, rot) in zip(spots, motifs)
    )


def _svg(size: int, body: str, view: str = "0 0 100 100", height: float | None = None) -> str:
    return (f'<svg width="{size}" height="{height or size:.0f}" viewBox="{view}">{body}</svg>')


_HEART_PATH = ("M50 88 C20 66 4 48 4 30 C4 16 15 6 28 6 C38 6 46 12 50 20 "
               "C54 12 62 6 72 6 C85 6 96 16 96 30 C96 48 80 66 50 88 Z")


def _heart_svg(size: int, color: str) -> str:
    return _svg(size, f'<path d="{_HEART_PATH}" fill="{color}"/>')


def _shamrock_svg(size: int, color: str) -> str:
    """Three small hearts with their points meeting in the middle, on a stem."""
    leaves = "".join(
        f'<path d="{_HEART_PATH}" fill="{color}" '
        f'transform="rotate({a} 50 50) translate(50 50) scale(0.44) translate(-50 -88)"/>'
        for a in (0, 120, 240)
    )
    stem = f'<path d="M50 50 Q52 76 64 96" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round"/>'
    return _svg(size, stem + leaves)


_EGG_PATH = "M50 4 C74 4 90 42 90 62 C90 84 72 98 50 98 C28 98 10 84 10 62 C10 42 26 4 50 4 Z"


def _egg_svg(size: int, color: str, band: str) -> str:
    """A dyed egg with a zigzag band and a stripe."""
    cid = f"egg{next(_ids)}"
    return _svg(size, (
        f'<defs><clipPath id="{cid}"><path d="{_EGG_PATH}"/></clipPath></defs>'
        f'<path d="{_EGG_PATH}" fill="{color}"/>'
        f'<g clip-path="url(#{cid})" fill="none" stroke="{band}" stroke-width="7" stroke-linejoin="round">'
        '<path d="M0 46 L12 38 L24 46 L36 38 L48 46 L60 38 L72 46 L84 38 L96 46 L108 38"/>'
        '<path d="M0 70 L100 70"/></g>'
    ))


def _flower_svg(size: int, petal: str, center: str, petals: int = 5) -> str:
    body = "".join(
        f'<ellipse cx="50" cy="27" rx="16" ry="24" fill="{petal}" transform="rotate({360 * i / petals:.0f} 50 50)"/>'
        for i in range(petals)
    )
    return _svg(size, body + f'<circle cx="50" cy="50" r="12" fill="{center}"/>')


def _poppy_svg(size: int) -> str:
    petals = "".join(
        f'<circle cx="{50 + 20 * math.cos(math.radians(a)):.1f}" cy="{50 + 20 * math.sin(math.radians(a)):.1f}" '
        f'r="27" fill="#c8102e" stroke="#8e0b21" stroke-width="2"/>'
        for a in (45, 135, 225, 315)
    )
    seeds = "".join(
        f'<circle cx="{50 + 15 * math.cos(math.radians(a)):.1f}" cy="{50 + 15 * math.sin(math.radians(a)):.1f}" '
        f'r="2.4" fill="#1a1a1a"/>'
        for a in range(0, 360, 45)
    )
    return _svg(size, petals + '<circle cx="50" cy="50" r="11" fill="#1a1a1a"/>' + seeds)


def _gear_svg(size: int, color: str, hole: str, teeth: int = 10) -> str:
    pts = []
    for i in range(teeth * 4):
        r = 46 if i % 4 in (1, 2) else 36
        a = 2 * math.pi * i / (teeth * 4)
        pts.append(f"{50 + r * math.cos(a):.1f},{50 + r * math.sin(a):.1f}")
    return _svg(size, f'<polygon points="{" ".join(pts)}" fill="{color}"/>'
                      f'<circle cx="50" cy="50" r="14" fill="{hole}"/>')


_TIE_PATH = "M40 6 L60 6 L64 16 L56 26 L70 80 L50 98 L30 80 L44 26 L36 16 Z"


def _tie_svg(size: int, color: str, stripe: str) -> str:
    cid = f"tie{next(_ids)}"
    stripes = "".join(f'<path d="M0 {y} L100 {y - 40}"/>' for y in range(40, 160, 18))
    return _svg(size, (
        f'<defs><clipPath id="{cid}"><path d="{_TIE_PATH}"/></clipPath></defs>'
        f'<path d="{_TIE_PATH}" fill="{color}"/>'
        f'<g clip-path="url(#{cid})" stroke="{stripe}" stroke-width="4">{stripes}</g>'
    ))


def _mask_svg(size: int, color: str, trim: str, eyes: str) -> str:
    """A Mardi Gras eye mask with a feather plume."""
    mask = ("M6 40 C20 28 38 30 50 40 C62 30 80 28 94 40 C96 58 84 72 66 68 "
            "C58 66 54 58 50 56 C46 58 42 66 34 68 C16 72 4 58 6 40 Z")
    plume = f'<path d="M84 34 C86 18 96 10 98 2 C90 8 80 16 78 32 Z" fill="{trim}"/>'
    return _svg(size, (
        plume + f'<path d="{mask}" fill="{color}" stroke="{trim}" stroke-width="3"/>'
        f'<ellipse cx="30" cy="48" rx="10" ry="6" fill="{eyes}"/><ellipse cx="70" cy="48" rx="10" ry="6" fill="{eyes}"/>'
    ))


def _coin_svg(size: int, color: str = "#f2c94c", rim: str = "#c99a2e") -> str:
    return _svg(size, f'<circle cx="50" cy="50" r="44" fill="{color}"/>'
                      f'<circle cx="50" cy="50" r="33" fill="none" stroke="{rim}" stroke-width="5"/>')


def _david_star_svg(size: int, color: str) -> str:
    return _svg(size, f'<g fill="none" stroke="{color}" stroke-width="6" stroke-linejoin="round">'
                      '<polygon points="50,6 88,72 12,72"/><polygon points="50,94 12,28 88,28"/></g>')


def _star_points(cx: float, cy: float, outer: float, inner: float, points: int = 5) -> str:
    return " ".join(
        f"{cx + (outer if i % 2 == 0 else inner) * math.cos(-math.pi / 2 + i * math.pi / points):.1f},"
        f"{cy + (outer if i % 2 == 0 else inner) * math.sin(-math.pi / 2 + i * math.pi / points):.1f}"
        for i in range(points * 2)
    )


def _menorah_svg(width: int, metal: str, candle: str, flame: str) -> str:
    """Nine candles, all lit, with the shamash raised in the middle."""
    arms = "".join(
        f'<path d="M{100 - 22 * k} 70 C{100 - 22 * k} {70 + 16 * k} {100 + 22 * k} {70 + 16 * k} {100 + 22 * k} 70"/>'
        for k in range(1, 5)
    )
    xs = [100 + 22 * k for k in range(-4, 5)]
    candles, flames = [], []
    for x in xs:
        top = 26 if x == 100 else 48
        candles.append(f'<rect x="{x - 4}" y="{top}" width="8" height="22" rx="1.5" fill="{candle}"/>')
        flames.append(f'<path d="M{x} {top - 20} C{x + 6} {top - 10} {x + 5} {top - 2} {x} {top - 2} '
                      f'C{x - 5} {top - 2} {x - 6} {top - 10} {x} {top - 20} Z" fill="{flame}"/>')
    return _svg(width, (
        f'<g fill="none" stroke="{metal}" stroke-width="5" stroke-linecap="round">{arms}'
        '<path d="M100 48 L100 138"/></g>'
        f'<path d="M72 150 L128 150 L116 138 L84 138 Z" fill="{metal}"/>'
        + "".join(candles) + "".join(flames)
    ), view="0 0 200 160", height=width * 0.8)


def _sunrise_svg(width: int, color: str) -> str:
    rays = "".join(
        f'<line x1="{110 + 58 * math.cos(math.radians(a)):.1f}" y1="{110 + 58 * math.sin(math.radians(a)):.1f}" '
        f'x2="{110 + 92 * math.cos(math.radians(a)):.1f}" y2="{110 + 92 * math.sin(math.radians(a)):.1f}"/>'
        for a in range(195, 346, 15)
    )
    return _svg(width, (
        f'<path d="M64 110 A46 46 0 0 1 156 110 Z" fill="{color}"/>'
        f'<g stroke="{color}" stroke-width="4" stroke-linecap="round">{rays}'
        '<line x1="6" y1="112" x2="214" y2="112"/></g>'
    ), view="0 0 220 120", height=width * 120 / 220)


def _nova_svg(size: int, color: str) -> str:
    """The Juneteenth flag's star: a white star inside a twelve-point burst."""
    return _svg(size, (
        f'<polygon points="{_star_points(50, 50, 48, 32, 12)}" fill="none" stroke="{color}" '
        'stroke-width="3" stroke-linejoin="round"/>'
        f'<polygon points="{_star_points(50, 52, 24, 10)}" fill="{color}"/>'
    ))


def _star_arc_svg(width: int, colors: tuple[str, str]) -> str:
    """Thirteen stars in an arch, like the original flag's circle."""
    stars = []
    for i in range(13):
        a = math.radians(200 + i * 140 / 12)
        stars.append(f'<polygon points="{_star_points(130 + 112 * math.cos(a), 150 + 112 * math.sin(a), 11, 4.4)}" '
                     f'fill="{colors[i % 2]}"/>')
    return _svg(width, "".join(stars), view="0 0 260 120", height=width * 120 / 260)


def _bead_strands_svg(strands) -> str:
    """Bead necklaces draped from the sign's top edge: (from x, to x, sag, color)."""
    beads = []
    for x0, x1, sag, color in strands:
        n = int(abs(x1 - x0) / 13)
        for i in range(n + 1):
            u = i / n
            # Quadratic Bezier with its control point at twice the sag.
            x = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * (x0 + x1) / 2 + u ** 2 * x1
            y = 2 * (1 - u) * u * 2 * sag
            beads.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}"/>')
    return f'<svg width="300" height="240" viewBox="0 0 300 240">{"".join(beads)}</svg>'


def _papel_picado_svg(colors: tuple[str, ...], hole: str) -> str:
    """A string of cut-paper flags along the sign's top edge."""
    flags = []
    for i, color in enumerate(colors):
        x, y = 16 + i * 78, 12 + 6 * math.sin(math.pi * (i + 0.5) / len(colors))
        zig = " ".join(f"L{x + 64 - j * 8} {y + (70 if j % 2 == 0 else 62)}" for j in range(9))
        flags.append(f'<path d="M{x} {y} L{x + 64} {y} {zig} Z" fill="{color}"/>')
        flags.append(f'<circle cx="{x + 32}" cy="{y + 30}" r="9" fill="{hole}"/>')
        for dx in (14, 50):
            flags.append(f'<path d="M{x + dx} {y + 12} l5 7 l-5 7 l-5 -7 Z" fill="{hole}"/>')
            flags.append(f'<circle cx="{x + dx}" cy="{y + 46}" r="4" fill="{hole}"/>')
    string = '<path d="M0 12 Q240 26 480 12" fill="none" stroke="rgba(255,244,224,0.6)" stroke-width="2"/>'
    return f'<svg width="480" height="100" viewBox="0 0 480 100">{string}{"".join(flags)}</svg>'


def _lantern_html(left: int, string_len: int, size: int, color: str, trim: str) -> str:
    """A paper lantern hanging from the sign's top edge, with a tassel."""
    h, cap_w = size * 0.82, size * 0.5
    cap_left = left + (size - cap_w) / 2
    body_top = string_len + 8
    return (
        f'<div class="deco" style="left:{left + size / 2 - 1:.0f}px; top:0; width:2px; height:{string_len}px; background:{trim};"></div>'
        f'<div class="deco" style="left:{cap_left:.0f}px; top:{string_len}px; width:{cap_w:.0f}px; height:10px; background:{trim}; border-radius:2px;"></div>'
        f'<div class="deco" style="left:{left}px; top:{body_top}px; width:{size}px; height:{h:.0f}px; border-radius:50%; '
        f'background: repeating-linear-gradient(90deg, rgba(0,0,0,0.14) 0 2px, transparent 2px {size / 5:.0f}px), '
        f'radial-gradient(circle at 50% 45%, #ff7a4a 0%, {color} 60%); box-shadow: 0 0 22px rgba(255,110,60,0.45);"></div>'
        f'<div class="deco" style="left:{cap_left:.0f}px; top:{body_top + h - 4:.0f}px; width:{cap_w:.0f}px; height:10px; background:{trim}; border-radius:2px;"></div>'
        f'<div class="deco" style="left:{left + size / 2 - 2:.0f}px; top:{body_top + h + 6:.0f}px; width:4px; height:30px; background:{trim};"></div>'
    )


def _hanukkah_decorations(t: dict) -> tuple[str, str]:
    deco = (f'<div class="deco" style="left:404px; top:214px;">{_menorah_svg(210, "#d9b45a", t["brand_text"], "#ffc94a")}</div>'
            + _place(_CORNER_SPOTS[:3], [(lambda s: _david_star_svg(s, t["gold"]), 0)] * 3, opacity=0.6))
    return _BASE_CSS, deco


def _mlk_decorations(t: dict) -> tuple[str, str]:
    deco = f'<div class="deco" style="left:396px; top:244px; opacity:0.75;">{_sunrise_svg(230, t["gold"])}</div>'
    return _BASE_CSS, deco


def _lunarnewyear_decorations(t: dict) -> tuple[str, str]:
    blossom = [(lambda s: _flower_svg(s, "#f9cdd3", t["gold"]), r) for r in (0, 20, -14, 30, 8)]
    deco = (_place(_BRAND_SPOTS, blossom)
            + _lantern_html(3600, 40, 70, "#e0302a", t["gold"]) + _lantern_html(3700, 12, 84, "#e0302a", t["gold"])
            + _lantern_html(3790, 64, 44, "#e0302a", t["gold"]))
    return _BASE_CSS, deco


def _mardigras_decorations(t: dict) -> tuple[str, str]:
    coin = lambda s: _coin_svg(s, t["gold"], "#b8901c")
    deco = (f'<div class="deco" style="left:420px; top:220px; transform: rotate(-8deg);">'
            f'{_mask_svg(150, "#7b3fa6", t["gold"], t["bg"])}</div>'
            + _place(_BRAND_SPOTS[1:], [(coin, 0), (coin, 0), (coin, 0), (coin, 0)], opacity=0.85)
            + '<div class="deco" style="left:3540px; top:0;">'
            + _bead_strands_svg(((40, 260, 120, "#7b3fa6"), (120, 300, 70, t["gold"]), (0, 180, 90, "#3fae5a")))
            + "</div>")
    return _BASE_CSS, deco


def _valentines_decorations(t: dict) -> tuple[str, str]:
    colors = ("#ff5c7a", "#f48fb1", "#e2365b", "#fbd3dd", "#ff8fa3")
    hearts = [(lambda s, c=c: _heart_svg(s, c), r) for c, r in zip(colors, (-10, 18, 12, -20, 6))]
    # Room for Pacifico's long descenders above the date.
    css = _BASE_CSS + ".day-name { margin-bottom: 14px; }\n"
    return css, _place(_BRAND_SPOTS, hearts) + _place(_CORNER_SPOTS, hearts, opacity=0.55)


def _presidents_decorations(t: dict) -> tuple[str, str]:
    deco = (f'<div class="deco" style="left:384px; top:232px;">'
            f'{_star_arc_svg(250, (t["brand_text"], t["gold"]))}</div>')
    return _BASE_CSS, deco


def _stpatricks_decorations(t: dict) -> tuple[str, str]:
    greens = ("#3fbf6a", "#2e9e55", "#57cf7d", "#2e9e55", "#3fbf6a")
    clovers = [(lambda s, c=c: _shamrock_svg(s, c), r) for c, r in zip(greens, (-8, 24, -20, 14, 36))]
    coins = [(lambda s: _coin_svg(s), 0)] * 5
    return _BASE_CSS, _place(_BRAND_SPOTS, clovers) + _place(_CORNER_SPOTS, coins, opacity=0.7)


def _easter_decorations(t: dict) -> tuple[str, str]:
    eggs = [(lambda s, c=c, b=b: _egg_svg(s, c, b), r) for c, b, r in (
        ("#f6b8c8", "#ffffff", -10), ("#b9d8f2", "#f8e19a", 16), ("#c8e6b5", "#f6b8c8", -18),
        ("#f8e19a", "#b9d8f2", 12), ("#d4c2f0", "#ffffff", -6))]
    flowers = [(lambda s, c=c: _flower_svg(s, c, "#f8e19a"), 0) for c in ("#f6b8c8", "#d4c2f0", "#b9d8f2", "#f6b8c8", "#d4c2f0")]
    return _BASE_CSS, _place(_BRAND_SPOTS, eggs) + _place(_CORNER_SPOTS, flowers, opacity=0.8)


def _cincodemayo_decorations(t: dict) -> tuple[str, str]:
    colors = ("#ff4f81", "#ffb627", "#3ccf91", "#4fb3ff", "#ff7a3d", "#c76bff")
    flowers = [(lambda s, c=c: _flower_svg(s, c, "#ffe066", 8), r) for c, r in zip(colors, (0, 15, -10, 20, 5))]
    deco = (_place(_BRAND_SPOTS, flowers)
            + f'<div class="deco" style="left:3360px; top:0;">{_papel_picado_svg(colors, t["bg"])}</div>')
    return _BASE_CSS, deco


def _mothers_decorations(t: dict) -> tuple[str, str]:
    colors = ("#f2a7b8", "#f7c6d2", "#e57f9b", "#fbe3e8", "#f2a7b8")
    flowers = [(lambda s, c=c: _flower_svg(s, c, "#f6d47a"), r) for c, r in zip(colors, (0, 18, -12, 30, 6))]
    return _BASE_CSS, _place(_BRAND_SPOTS, flowers) + _place(_CORNER_SPOTS, flowers, opacity=0.55)


def _memorial_decorations(t: dict) -> tuple[str, str]:
    poppies = [(_poppy_svg, r) for r in (0, 20, -15)]
    return _BASE_CSS, _place(_BRAND_SPOTS[:3], poppies, opacity=0.9)


def _fathers_decorations(t: dict) -> tuple[str, str]:
    ties = [(lambda s: _tie_svg(s, "#5d8fb8", t["gold"]), -12), (lambda s: _tie_svg(s, "#b8423c", t["brand_text"]), 14),
            (lambda s: _tie_svg(s, t["gold"], t["bg"]), -6)]
    return _BASE_CSS, _place(_BRAND_SPOTS[:3], ties)


def _juneteenth_decorations(t: dict) -> tuple[str, str]:
    star = lambda s: _svg(s, f'<polygon points="{_star_points(50, 52, 46, 19)}" fill="{t["gold"]}"/>')
    deco = (f'<div class="deco" style="left:440px; top:206px;">{_nova_svg(136, t["brand_text"])}</div>'
            + _place((_BRAND_SPOTS[1], _BRAND_SPOTS[2]), [(star, 0), (star, 0)]))
    return _BASE_CSS, deco


def _july4_decorations(t: dict) -> tuple[str, str]:
    bursts = (
        (440, 198, 150, "#e63946", 16), (372, 330, 80, t["brand_text"], 12),
        (536, 322, 92, "#5b8def", 12), (578, 214, 50, t["brand_text"], 10),
    )
    deco = "".join(
        f'<div class="deco" style="left:{x}px; top:{y}px;">{_firework_svg(size, color, rays)}</div>'
        for x, y, size, color, rays in bursts
    )
    stars = [(lambda s, c=c: _star_svg(s, c), r) for c, r in zip(
        (t["brand_text"], "#e63946", t["brand_text"], "#5b8def", t["brand_text"]), (0, 12, -10, 20, 5))]
    return _BASE_CSS, deco + _place(_CORNER_SPOTS, stars, opacity=0.6)


def _labor_decorations(t: dict) -> tuple[str, str]:
    gears = [(lambda s: _gear_svg(s, t["gold"], t["bg"]), 0), (lambda s: _gear_svg(s, "#9fb0c2", t["bg"], 8), 12),
             (lambda s: _gear_svg(s, "#9fb0c2", t["bg"]), 6), (lambda s: _gear_svg(s, t["gold"], t["bg"], 8), 0)]
    return _BASE_CSS, _place(_BRAND_SPOTS[:4], gears, opacity=0.9)


_DECORATORS = {
    "halloween": _halloween_decorations,
    "thanksgiving": _thanksgiving_decorations,
    "veterans": _veterans_decorations,
    "christmas": _christmas_decorations,
    "newyear": _newyear_decorations,
    "hanukkah": _hanukkah_decorations,
    "mlk": _mlk_decorations,
    "lunarnewyear": _lunarnewyear_decorations,
    "mardigras": _mardigras_decorations,
    "valentines": _valentines_decorations,
    "presidents": _presidents_decorations,
    "stpatricks": _stpatricks_decorations,
    "easter": _easter_decorations,
    "cincodemayo": _cincodemayo_decorations,
    "mothers": _mothers_decorations,
    "memorial": _memorial_decorations,
    "fathers": _fathers_decorations,
    "juneteenth": _juneteenth_decorations,
    "july4": _july4_decorations,
    "labor": _labor_decorations,
}


def decorations_html(variant: str, t: dict) -> tuple[str, str]:
    """Returns (css, html) for a theme's decorative layer ("", "" for none)."""
    decorate = _DECORATORS.get(variant)
    return decorate(t) if decorate else ("", "")

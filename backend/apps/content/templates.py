"""Built-in starter templates, generated with the organization's brand colors and fonts.

Templates are ordinary documents (documents.py): picking one copies it into the item,
after which it is edited like any other design. Organizations can also save their own
(models.ContentTemplate).
"""

import re
from typing import Any

from apps.brand.models import BrandGuideline

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _palette(guideline: BrandGuideline | None) -> dict[str, str]:
    colors = [c for c in (guideline.colors if guideline else []) if _HEX.match(str(c))]
    fonts = [str(f)[:80] for f in (guideline.fonts if guideline else []) if str(f).strip()]
    primary = colors[0] if colors else "#1f3a5f"
    accent = colors[1] if len(colors) > 1 else "#f2a541"
    return {
        "primary": primary,
        "accent": accent,
        "light": colors[2] if len(colors) > 2 else "#f7f4ef",
        "on_primary": "#ffffff",
        "ink": "#1b1b1b",
        "heading_font": fonts[0] if fonts else "Inter",
        "body_font": fonts[1] if len(fonts) > 1 else (fonts[0] if fonts else "Inter"),
    }


def _text(
    id: str,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    size: float,
    color: str,
    font: str,
    style: str = "normal",
    align: str = "left",
) -> dict[str, Any]:
    return {
        "id": id, "type": "text", "text": text, "x": x, "y": y, "width": w, "height": h,
        "font_size": size, "fill": color, "font_family": font, "font_style": style,
        "align": align, "line_height": 1.15,
    }  # fmt: skip


def _rect(
    id: str, x: float, y: float, w: float, h: float, fill: str, radius: float = 0
) -> dict[str, Any]:
    return {
        "id": id, "type": "rect", "x": x, "y": y, "width": w, "height": h,
        "fill": fill, "corner_radius": radius,
    }  # fmt: skip


def _announcement(p: dict[str, str]) -> dict[str, Any]:
    return {
        "kind": "design", "width": 1080, "height": 1080,
        "pages": [{
            "id": "p1", "name": "Post", "background": p["primary"],
            "elements": [
                _rect("band", 0, 760, 1080, 320, p["accent"]),
                _text("headline", "Big news is here", 80, 180, 920, 300, 110, p["on_primary"],
                      p["heading_font"], "bold"),
                _text("sub", "Tell people what's new and why it matters to them.", 80, 500,
                      920, 160, 44, p["on_primary"], p["body_font"]),
                _text("cta", "Visit us this week", 80, 870, 920, 90, 52, p["ink"],
                      p["heading_font"], "bold"),
            ],
        }],
    }  # fmt: skip


def _tip(p: dict[str, str]) -> dict[str, Any]:
    return {
        "kind": "design", "width": 1080, "height": 1350,
        "pages": [{
            "id": "p1", "name": "Post", "background": p["light"],
            "elements": [
                _rect("bar", 80, 120, 120, 16, p["accent"], 8),
                _text("label", "TIP OF THE WEEK", 80, 170, 920, 70, 40, p["primary"],
                      p["body_font"], "bold"),
                _text("tip", "One practical tip your customers can use today.", 80, 300, 920,
                      600, 88, p["ink"], p["heading_font"], "bold"),
                _text("footer", "Save this for later", 80, 1180, 920, 70, 40, p["primary"],
                      p["body_font"]),
            ],
        }],
    }  # fmt: skip


def _story(p: dict[str, str]) -> dict[str, Any]:
    return {
        "kind": "design", "width": 1080, "height": 1920,
        "pages": [{
            "id": "p1", "name": "Story", "background": p["primary"],
            "elements": [
                _text("headline", "Limited time", 90, 520, 900, 300, 130, p["on_primary"],
                      p["heading_font"], "bold", "center"),
                _text("sub", "Add the offer details here", 90, 860, 900, 200, 56,
                      p["on_primary"], p["body_font"], "normal", "center"),
                _rect("pill", 240, 1380, 600, 140, p["accent"], 70),
                _text("cta", "Tap to learn more", 240, 1420, 600, 70, 48, p["ink"],
                      p["heading_font"], "bold", "center"),
            ],
        }],
    }  # fmt: skip


def _carousel(p: dict[str, str]) -> dict[str, Any]:
    def page(i: int, title: str, body: str) -> dict[str, Any]:
        return {
            "id": f"p{i}", "name": f"Slide {i}", "background": p["light"],
            "elements": [
                _text(f"n{i}", f"{i - 1:02d}", 80, 100, 300, 120, 96, p["accent"],
                      p["heading_font"], "bold"),
                _text(f"t{i}", title, 80, 300, 920, 260, 84, p["ink"], p["heading_font"], "bold"),
                _text(f"b{i}", body, 80, 620, 920, 500, 46, p["ink"], p["body_font"]),
            ],
        }  # fmt: skip

    return {
        "kind": "carousel", "width": 1080, "height": 1350,
        "pages": [
            {
                "id": "p1", "name": "Cover", "background": p["primary"],
                "elements": [
                    _text("cover", "3 things to know", 80, 420, 920, 400, 120, p["on_primary"],
                          p["heading_font"], "bold"),
                    _text("swipe", "Swipe →", 80, 1160, 920, 80, 44, p["on_primary"],
                          p["body_font"]),
                ],
            },
            page(2, "First point", "Explain it in one or two short sentences."),
            page(3, "Second point", "Keep one idea per slide."),
            page(4, "Third point", "Make it practical and specific."),
            {
                "id": "p5", "name": "Call to action", "background": p["accent"],
                "elements": [
                    _text("end", "Follow for more", 80, 500, 920, 300, 110, p["ink"],
                          p["heading_font"], "bold", "center"),
                ],
            },
        ],
    }  # fmt: skip


BUILT_IN: list[tuple[str, str, str, Any]] = [
    ("builtin-announcement", "Announcement", "Square post with a bold headline.", _announcement),
    ("builtin-tip", "Tip card", "Portrait 4:5 educational post.", _tip),
    ("builtin-story", "Story promo", "9:16 story with a call-to-action button.", _story),
    ("builtin-carousel", "Tips carousel", "Cover, three points, and a closing slide.", _carousel),
]


def built_in_templates(guideline: BrandGuideline | None) -> list[dict[str, Any]]:
    palette = _palette(guideline)
    out = []
    for key, name, description, build in BUILT_IN:
        doc = {"schema_version": 1, **build(palette)}
        out.append(
            {
                "id": key,
                "name": name,
                "description": description,
                "kind": doc["kind"],
                "built_in": True,
                "document": doc,
            }
        )
    return out

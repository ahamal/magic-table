"""Printable ArUco markers for the game board and the gantry head.

Usage: python markers.py   (needs: pip install opencv-contrib-python-headless pillow)
Writes markers.pdf (US Letter) next to this file. Print at 100% / actual size.

Dictionary DICT_4X4_50. IDs 0-3 go on the board corners, ID 10 on the head plate,
ID 20 on top of Mate (its top edge toward Mate's face, so the marker gives its heading).
The white border is part of each marker: cut along the grey line, not the black.
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 300
PAGE = (8.5, 11)              # inches, US Letter
DICT = cv2.aruco.DICT_4X4_50

# Sizes from a test on the black board: cam 1 still found the far corners when they were
# simulated down to 15 mm; these keep a margin for worse light and angles.
CORNER_BLACK, CORNER_BORDER = 30, 5   # mm: 40 mm cut size
HEAD_BLACK, HEAD_BORDER = 25, 4       # mm: 33 mm cut size, fits the head plate
MATE_BLACK, MATE_BORDER = 30, 5       # mm: 40 mm cut size, on top of Mate
MATE_TAB = 9                          # mm: extra strip above Mate's marker for the arrow
CORNERS = (0, 1, 2, 3)
HEAD_ID = 10
MATE_ID = 20


def px(mm):
    return round(mm / 25.4 * DPI)


def marker(id_, black, border):
    """Marker with its white border, as a PIL image at DPI."""
    size = px(black)
    img = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(DICT), id_, size)
    img = cv2.copyMakeBorder(img, px(border), px(border), px(border), px(border), cv2.BORDER_CONSTANT, value=255)
    return Image.fromarray(img).convert("RGB")


def font(size_mm):
    for name in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, px(size_mm))
        except OSError:
            pass
    return ImageFont.load_default()


def sheet():
    page = Image.new("RGB", (round(PAGE[0] * DPI), round(PAGE[1] * DPI)), "white")
    d = ImageDraw.Draw(page)
    f, small = font(4), font(3)

    def place(img, x_mm, y_mm, label):
        x, y = px(x_mm), px(y_mm)
        page.paste(img, (x, y))
        d.rectangle([x, y, x + img.width - 1, y + img.height - 1], outline=(170, 170, 170), width=2)
        d.text((x, y + img.height + px(2)), label, fill="black", font=small)

    d.text((px(15), px(10)), "Magic Table markers  ·  ArUco 4x4_50  ·  print at 100% (actual size)", fill="black", font=f)
    d.text((px(15), px(16)), "Cut along the grey lines. Glue flat on matte paper; no glossy tape over them.",
           fill="black", font=small)

    cut = CORNER_BLACK + 2 * CORNER_BORDER
    for i, id_ in enumerate(CORNERS):
        place(marker(id_, CORNER_BLACK, CORNER_BORDER), 20 + i * (cut + 10), 28, f"ID {id_} · board corner")
    d.text((px(20), px(28 + cut + 8)), "Any corner each, black board all around (a white border touching white "
           "cloth hides it).", fill="black", font=small)

    hcut = HEAD_BLACK + 2 * HEAD_BORDER
    y = 28 + cut + 30
    for i in range(2):
        place(marker(HEAD_ID, HEAD_BLACK, HEAD_BORDER), 20 + i * (hcut + 16), y,
              f"ID {HEAD_ID} · head" + (" (spare)" if i else ""))

    # Mate: the marker plus a strip above it with an arrow; that edge goes toward Mate's face
    mate = marker(MATE_ID, MATE_BLACK, MATE_BORDER)
    tab = Image.new("RGB", (mate.width, mate.height + px(MATE_TAB)), "white")
    tab.paste(mate, (0, px(MATE_TAB)))
    t = ImageDraw.Draw(tab)
    cx, top = tab.width // 2, px(1.5)
    t.polygon([(cx, top), (cx - px(3.5), top + px(4)), (cx + px(3.5), top + px(4))], fill="black")
    t.text((cx + px(5), top), "face", fill="black", font=small)
    place(tab, 20 + 2 * (hcut + 16) + 10, y - MATE_TAB, f"ID {MATE_ID} · top of Mate, arrow to its face")

    # 100 mm check ruler
    y = px(28 + cut + 30 + max(hcut, MATE_BLACK + 2 * MATE_BORDER) + 22)
    x0, x1 = px(20), px(120)
    d.line([x0, y, x1, y], fill="black", width=3)
    for mm in range(0, 101, 10):
        x = px(20 + mm)
        d.line([x, y - px(3 if mm % 50 else 5), x, y], fill="black", width=3)
    d.text((x0, y + px(2)), "This line should measure exactly 100 mm. If not, the printer scaled the page.",
           fill="black", font=small)
    return page


if __name__ == "__main__":
    path = Path(__file__).parent / "markers.pdf"
    sheet().save(path, resolution=DPI)
    print(path.name)

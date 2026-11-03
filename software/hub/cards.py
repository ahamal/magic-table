"""Reading face-up cards for free: cam 1 sees a lying card at an angle; its known rectangle
(63 x 88 mm at the scene's x, y, angle) projects to four corners in the picture, and warping those
straight gives the card as if from directly above. That face is compared with the faces of cards
already read (a cache on the Pi, cards/, not in git): a clear best match names it in a few ms, no
API. A card the cache can't name is Muse Spark's (read()), once; a sure answer is cached.

A card that hasn't moved keeps its name without looking again (the scene finds it every frame).
Face-down cards all look alike: they're never named here."""
import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from vision import CARD, project

LIB = Path(__file__).parent / "cards"   # <n>.png faces and index.json {file: name}
PX = 3            # px per mm of a flattened face (cam 1 sees cards at 2.3-3 px/mm)
SHIFT_MM = 4      # how far a face may sit off where the scene says (its corners jitter) when compared
SURE = 0.75       # a match this good...
MARGIN = 0.08     # ...and this far ahead of the next-best other card names it
KEEP = 4          # faces kept per card (different light, places)
STILL_MM, STILL_DEG = 3.0, 4.0   # a card within this of where it was named is the same card
ASK = ('This is a playing card seen from straight above. Which card is it? Look at the corner index and the pips. '
       'Reply with JSON only: {"card": "5♣", "confidence": 0.9}, or {"card": "face down", "confidence": 0.9}.')
CACHE_SURE = 0.9  # Muse's own confidence needed to add its answer to the cache
BACK_LEARN = 0.4  # a card this blue (share of its pixels) is surely a back: the first one teaches the back's look
BACK_SURE = 0.6   # a card matching the back this well is face down (all backs look alike)


def corners(c, tz):
    """A lying card's four corners on the board (mm), in face order: the face's top left, top
    right, bottom right, bottom left, with its long side running down."""
    a = np.radians(c["angle"])
    u = np.array([np.cos(a), np.sin(a)]) * CARD[1] / 2     # along the long side
    v = np.array([-np.sin(a), np.cos(a)]) * CARD[0] / 2
    m = np.array([c["x"], c["y"]])
    return [(*p, tz) for p in (m - u + v, m - u - v, m + u - v, m + u + v)]


def flatten(img, P, tz, c, unfix=None):
    """The card as if seen from straight above: CARD at PX px/mm, portrait. unfix: calibrated
    camera pixels -> this picture's (the scene's bump correction, undone)."""
    src = np.array([project(P, p) for p in corners(c, tz)], np.float32)
    if unfix is not None:
        src = unfix(src).astype(np.float32)
    w, h = CARD[0] * PX, CARD[1] * PX
    dst = np.array([(0, 0), (w, 0), (w, h), (0, h)], np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (int(w), int(h)))


def _prep(face):
    return cv2.GaussianBlur(face, (0, 0), 1.2)


def _inner(face):
    s = SHIFT_MM * PX
    return face[s:-s, s:-s]


class Cards:
    def __init__(self):
        self.lock = threading.Lock()
        self.faces = {}          # file: (name, prepared face, its middle)
        self.named = []          # [{x, y, angle, card, score, by}]: cards named, where they lie
        self.last = None         # the scene's last look: (img, P, tz, unfix, cards)
        self.back = None         # the card back, flattened and prepared (cards/back.png)
        self.faced = []          # [{x, y, angle, face, back}]: face decided by the back, where cards lie
        if (LIB / "back.png").exists():
            self.back = _prep(cv2.imread(str(LIB / "back.png")))
        LIB.mkdir(exist_ok=True)
        idx = LIB / "index.json"
        self.index = json.loads(idx.read_text()) if idx.exists() else {}
        for f, name in self.index.items():
            img = cv2.imread(str(LIB / f))
            if img is not None:
                self._add(f, name, img)

    def _add(self, f, name, face):
        p = _prep(face)
        self.faces[f] = (name, p, _inner(p))

    def match(self, face):
        """The cached card this face is: (name, score, margin) or (None, best score, margin)."""
        p = _prep(face)
        best = {}
        for name, _, mid in list(self.faces.values()):
            for f in (p, cv2.rotate(p, cv2.ROTATE_180)):        # a card looks the same either way up
                s = float(cv2.matchTemplate(f, mid, cv2.TM_CCOEFF_NORMED).max())
                best[name] = max(best.get(name, -1.0), s)
        if not best:
            return None, 0.0, 0.0
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        name, s = ranked[0]
        margin = s - (ranked[1][1] if len(ranked) > 1 else 0.0)
        return (name if s >= SURE and margin >= MARGIN else None), round(s, 3), round(margin, 3)

    def learn(self, name, face):
        """Keep this face as one of `name`'s (up to KEEP, the oldest dropped)."""
        with self.lock:
            mine = [f for f, n in self.index.items() if n == name]
            for f in mine[:max(0, len(mine) - KEEP + 1)]:
                del self.index[f]
                self.faces.pop(f, None)
                (LIB / f).unlink(missing_ok=True)
            f = f"{int(time.time() * 1000)}.png"
            cv2.imwrite(str(LIB / f), face)
            self.index[f] = name
            (LIB / "index.json").write_text(json.dumps(self.index, ensure_ascii=False, indent=1))
            self._add(f, name, face)

    def _still(self, c, among=None):
        for n in (self.named if among is None else among):
            d = abs((n["angle"] - c["angle"] + 90) % 180 - 90)
            if np.hypot(n["x"] - c["x"], n["y"] - c["y"]) < STILL_MM and d < STILL_DEG:
                return n
        return None

    def _back_score(self, face):
        p = _prep(face)
        mid = _inner(self.back)
        return max(float(cv2.matchTemplate(f, mid, cv2.TM_CCOEFF_NORMED).max()) for f in (p, cv2.rotate(p, cv2.ROTATE_180)))

    def face_up(self, img, P, tz, cards, unfix=None):
        """Face up or down by the card back's look (more sure than how blue a card is): learns the back
        from the first clearly blue card, then each card is matched against it; one that hasn't moved
        keeps its answer. Sets face and back (the match, 0-1) in place."""
        if self.back is None:
            blue = max((c for c in cards if c.get("blue", 0) >= BACK_LEARN), key=lambda c: c["blue"], default=None)
            if blue is None:
                return
            f = flatten(img, P, tz, blue, unfix)
            cv2.imwrite(str(LIB / "back.png"), f)
            self.back = _prep(f)
        faced = []
        for c in cards:
            was = self._still(c, self.faced)
            if was:
                c["face"], c["back"] = was["face"], was["back"]
            else:
                c["back"] = round(self._back_score(flatten(img, P, tz, c, unfix)), 2)
                c["face"] = "down" if c["back"] >= BACK_SURE else "up"
            faced.append({"x": c["x"], "y": c["y"], "angle": c["angle"], "face": c["face"], "back": c["back"]})
        self.faced = faced

    def label(self, img, P, tz, cards, unfix=None):
        """Names the scene's face-up cards in place: card, score (and by: "cache"), from the
        cache; one that hasn't moved since it was named keeps its name without looking."""
        self.last = (img, P, tz, unfix, cards)
        self.face_up(img, P, tz, cards, unfix)
        named = []
        for c in cards:
            if c.get("face") != "up":
                continue
            was = self._still(c)
            if was:
                c.update(card=was["card"], score=was["score"], margin=was.get("margin"), by=was["by"])
                named.append({**was, "x": c["x"], "y": c["y"], "angle": c["angle"]})
                continue
            if not self.faces:
                continue
            name, score, margin = self.match(flatten(img, P, tz, c, unfix))
            c["score"], c["margin"] = score, margin
            if name:
                c.update(card=name, by="cache")
                named.append({"x": c["x"], "y": c["y"], "angle": c["angle"], "card": name, "score": score, "margin": margin, "by": "cache"})
        self.named = named

    def remember(self, c, name, score, by):
        """A card named elsewhere (Muse) keeps its name where it lies."""
        self.named.append({"x": c["x"], "y": c["y"], "angle": c["angle"], "card": name, "score": score, "by": by})

    async def read(self, ask, effort="minimal"):
        """The face-up cards of the scene's last look, each named: from the cache, or else by Muse
        Spark (ask: eyes.ask) from its flattened face, all at once. A sure answer (CACHE_SURE)
        is cached. [{x, y, angle, card, score, by, confidence?}]"""
        import asyncio
        if not self.last:
            return []
        img, P, tz, unfix, cards = self.last
        up = [dict(c) for c in cards if c.get("face") == "up"]
        todo = [c for c in up if not c.get("card")]
        faces = [flatten(img, P, tz, c, unfix) for c in todo]
        jpgs = [cv2.imencode(".jpg", cv2.resize(f, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))[1].tobytes()
                for f in faces]
        answers = await asyncio.gather(*(ask(j, ASK, effort) for j in jpgs), return_exceptions=True)
        for c, f, a in zip(todo, faces, answers):
            c["by"] = "muse"
            try:
                got = json.loads(a[a.index("{"):a.rindex("}") + 1])
                name, conf = str(got["card"]).strip(), float(got.get("confidence", 0))
            except Exception:
                c["card"], c["error"] = None, str(a)[:200]
                continue
            c["card"], c["confidence"] = name, conf
            if conf >= CACHE_SURE and name.lower() != "face down":
                self.learn(name, f)
                self.remember(c, name, conf, "muse")
        return [{k: (round(v, 1) if isinstance(v, float) and k in ("x", "y", "angle") else v)
                 for k, v in c.items() if k in ("x", "y", "angle", "card", "score", "margin", "by", "confidence", "error")}
                for c in up]

    async def watch(self, ask, every=1.0):
        """Forever: a face-up card the cache can't name, lying still since the last look, is read
        by Muse (read) in the background, once per place it lies (not again unless it moves)."""
        import asyncio
        seen, asked = [], []
        same = lambda a, b: np.hypot(a["x"] - b["x"], a["y"] - b["y"]) < STILL_MM and \
            abs((a["angle"] - b["angle"] + 90) % 180 - 90) < STILL_DEG
        while True:
            await asyncio.sleep(every)
            try:
                up = [c for c in (self.last[4] if self.last else []) if c.get("face") == "up" and not c.get("card")]
                new = [c for c in up if any(same(c, o) for o in seen) and not any(same(c, o) for o in asked)]
                seen = up
                if new:
                    asked = [a for a in asked if any(same(a, c) for c in up)] + new
                    await self.read(ask)
            except Exception:
                pass                                   # Muse down: try again when a card moves

    def forget(self):
        with self.lock:
            (LIB / "back.png").unlink(missing_ok=True)
            self.back, self.faced = None, []
            for f in self.index:
                (LIB / f).unlink(missing_ok=True)
            self.index, self.faces, self.named = {}, {}, []
            (LIB / "index.json").write_text("{}")

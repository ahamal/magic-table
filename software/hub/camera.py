"""The table's cameras on the Pi 5's two CSI ports, via picamera2.

Each camera is opened once and keeps streaming, so a snapshot is just the next
frame (about 0.1 s) instead of a 1 s cold start, and exposure and white balance
have already settled. picamera2 is a system package, so the hub's venv is
created with --system-site-packages.
"""

import io
import threading

SIZE = (1640, 1232)  # full field of view on both the imx219 and the ov5647
STREAM_WIDTH = 820   # the live view is scaled down to keep Wi-Fi traffic low


class Camera:
    def __init__(self, num=0, model="", size=SIZE):
        self.num, self.model, self.size = num, model, size
        self.cam = None
        self.error = None
        self._lock = threading.Lock()

    @property
    def info(self):
        return {"cam": self.num, "model": self.model, "ok": self.cam is not None, "error": self.error}

    def start(self):
        try:
            from picamera2 import Picamera2
            cam = Picamera2(self.num)
            cam.configure(cam.create_still_configuration(main={"size": self.size}, buffer_count=2))
            cam.options["quality"] = 90
            cam.start()
            self.cam = cam
        except Exception as e:
            self.error = str(e)

    def capture(self):
        """One JPEG of the current frame, or None if the camera isn't running."""
        if self.cam is None:
            return None
        with self._lock:
            buf = io.BytesIO()
            self.cam.capture_file(buf, format="jpeg")
            return buf.getvalue()

    def frame(self, width=STREAM_WIDTH, quality=75):
        """A smaller JPEG of the current frame for the live view (~50 KB)."""
        if self.cam is None:
            return None
        with self._lock:
            img = self.cam.capture_image("main")
        if width < img.width:
            img = img.resize((width, round(img.height * width / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


def start_all():
    """Open every camera the Pi found at boot. Empty off a Pi or with none plugged in."""
    try:
        from picamera2 import Picamera2
        found = Picamera2.global_camera_info()
    except Exception:
        return []
    cams = [Camera(i, c.get("Model", "")) for i, c in enumerate(found)]
    for c in cams:
        c.start()
    return cams

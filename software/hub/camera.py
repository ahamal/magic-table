"""Overhead camera (Camera v2 on the Pi 5's CSI port), via picamera2.

The camera is opened once and keeps streaming, so a snapshot is just the next
frame (about 0.1 s) instead of a 1 s cold start, and exposure and white balance
have already settled. picamera2 is a system package, so the hub's venv is
created with --system-site-packages.
"""

import io
import threading

SIZE = (1640, 1232)  # full field of view, 2x2 binned


class Camera:
    def __init__(self, size=SIZE):
        self.size = size
        self.cam = None
        self.error = None
        self._lock = threading.Lock()

    def start(self):
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            cam.configure(cam.create_still_configuration(main={"size": self.size}, buffer_count=2))
            cam.options["quality"] = 90
            cam.start()
            self.cam = cam
        except Exception as e:  # no camera, or not on a Pi
            self.error = str(e)

    def capture(self):
        """One JPEG of the current frame, or None if there's no camera."""
        if self.cam is None:
            return None
        with self._lock:
            buf = io.BytesIO()
            self.cam.capture_file(buf, format="jpeg")
            return buf.getvalue()

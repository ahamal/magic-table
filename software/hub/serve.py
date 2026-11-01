"""Run the hub on HTTP :8000 and HTTPS :8443 in one process.

Browsers only allow the microphone on HTTPS pages, so the talk page needs
:8443; everything else keeps working on plain :8000. One process, because
only one thing may own the GRBL serial port and the cameras. The HTTPS
server skips the app's startup (lifespan), which the HTTP server already ran.

Run on the Pi:  python serve.py   (hub.service does this)
The certificate is self-signed (see README); without it only :8000 starts.
"""

import asyncio
import contextlib
import signal
from pathlib import Path

import uvicorn

from server import app

HERE = Path(__file__).parent
CERT, KEY = HERE / "certs" / "hub.crt", HERE / "certs" / "hub.key"


class Server(uvicorn.Server):
    # two servers in one loop: signals are handled once, below, for both
    def capture_signals(self):
        return contextlib.nullcontext()


async def main():
    servers = [Server(uvicorn.Config(app, host="0.0.0.0", port=8000))]
    if CERT.exists() and KEY.exists():
        servers.append(Server(uvicorn.Config(app, host="0.0.0.0", port=8443, lifespan="off",
                                             ssl_certfile=str(CERT), ssl_keyfile=str(KEY))))

    def stop():
        for s in servers:
            s.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())

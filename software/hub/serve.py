"""Run the hub on port 8000, for both HTTP and HTTPS, in one process.

Browsers only allow the microphone on HTTPS pages, so the talk page needs HTTPS; everything
else is fine on plain HTTP. Both come in on :8000: the first byte of a connection says which
(a TLS handshake always starts with 0x16), and it's passed to the plain server or the TLS
one, which listen on this machine only. One process, because only one thing may own the GRBL
serial port and the cameras. The TLS server skips the app's startup (lifespan), which the
plain server already ran.

Run on the Pi:  python serve.py   (hub.service does this)
The certificate is self-signed (see README); without it :8000 is plain HTTP only.
"""

import asyncio
import contextlib
import signal
from pathlib import Path

import uvicorn

from server import app

HERE = Path(__file__).parent
CERT, KEY = HERE / "certs" / "hub.crt", HERE / "certs" / "hub.key"
PORT = 8000
PLAIN, TLS = 18000, 18443          # internal, 127.0.0.1 only
TLS_HANDSHAKE = 0x16


class Server(uvicorn.Server):
    # several servers in one loop: signals are handled once, below, for all
    def capture_signals(self):
        return contextlib.nullcontext()


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        with contextlib.suppress(Exception):
            writer.close()


async def front(reader, writer):
    """Peek at the first byte, then splice the connection to the plain or the TLS server."""
    try:
        first = await asyncio.wait_for(reader.read(1), 30)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        writer.close()
        return
    if not first:
        writer.close()
        return
    port = TLS if first[0] == TLS_HANDSHAKE and CERT.exists() else PLAIN
    try:
        up_r, up_w = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        writer.close()
        return
    up_w.write(first)
    await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))


async def main():
    tls = CERT.exists() and KEY.exists()
    servers = [Server(uvicorn.Config(app, host="127.0.0.1", port=PLAIN, proxy_headers=False))]
    if tls:
        servers.append(Server(uvicorn.Config(app, host="127.0.0.1", port=TLS, lifespan="off",
                                             ssl_certfile=str(CERT), ssl_keyfile=str(KEY))))
    door = await asyncio.start_server(front, "0.0.0.0", PORT)

    def stop():
        for s in servers:
            s.should_exit = True
        door.close()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())

"""Background CDP WebSocket holder. Listens on Unix socket for commands.

Run: python3 daemon.py &
Stop: pkill -f harnesless/daemon.py  (or send {"meta": "shutdown"})

The daemon owns ONE persistent WebSocket to Chrome. Short-lived helper
processes connect to the Unix socket, send one JSON request, get one
JSON response. WebSocket stays alive across all of them.
"""
import asyncio
import json
import os
import sys
import urllib.request
from collections import deque

from cdp_use.client import CDPClient

SOCK_PATH = "/tmp/harnesless.sock"
LOG_PATH = "/tmp/harnesless.log"
CDP_HTTP = "http://127.0.0.1:9222"
EVENT_BUFFER_MAX = 500


def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(f"{msg}\n")


def get_browser_ws_url():
    with urllib.request.urlopen(f"{CDP_HTTP}/json/version", timeout=3) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


class Daemon:
    def __init__(self):
        self.cdp: CDPClient | None = None
        self.default_session: str | None = None
        self.events: deque = deque(maxlen=EVENT_BUFFER_MAX)

    async def start(self):
        url = get_browser_ws_url()
        log(f"connecting to {url}")
        self.cdp = CDPClient(url)
        await self.cdp.start()

        # Attach to the first page target so helpers have a default session.
        targets = await self.cdp.send_raw("Target.getTargets")
        pages = [t for t in targets["targetInfos"] if t["type"] == "page"]
        if pages:
            attach = await self.cdp.send_raw(
                "Target.attachToTarget",
                {"targetId": pages[0]["targetId"], "flatten": True},
            )
            self.default_session = attach["sessionId"]
            log(f"attached to {pages[0]['targetId']} session={self.default_session}")
            # Enable common domains so events flow.
            for d in ("Page", "DOM", "Runtime", "Network"):
                try:
                    await self.cdp.send_raw(f"{d}.enable", session_id=self.default_session)
                except Exception as e:
                    log(f"enable {d} failed: {e}")

        # Buffer every event we see.
        original = self.cdp._event_registry.handle_event

        async def tap(method, params, session_id=None):
            self.events.append({"method": method, "params": params, "session_id": session_id})
            return await original(method, params, session_id)

        self.cdp._event_registry.handle_event = tap

    async def handle(self, req: dict) -> dict:
        meta = req.get("meta")
        if meta == "drain_events":
            out = list(self.events)
            self.events.clear()
            return {"events": out}
        if meta == "session":
            return {"session_id": self.default_session}
        if meta == "set_session":
            self.default_session = req.get("session_id")
            return {"session_id": self.default_session}
        if meta == "shutdown":
            return {"ok": True, "_shutdown": True}

        method = req["method"]
        params = req.get("params") or {}
        session_id = req.get("session_id") or self.default_session
        try:
            result = await self.cdp.send_raw(method, params, session_id=session_id)
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}


async def serve(daemon: Daemon):
    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)

    async def on_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await reader.readline()
            if not line:
                return
            req = json.loads(line)
            resp = await daemon.handle(req)
            writer.write((json.dumps(resp, default=str) + "\n").encode())
            await writer.drain()
            if resp.get("_shutdown"):
                log("shutdown requested")
                asyncio.get_event_loop().stop()
        except Exception as e:
            log(f"conn error: {e}")
            try:
                writer.write((json.dumps({"error": str(e)}) + "\n").encode())
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()

    server = await asyncio.start_unix_server(on_conn, path=SOCK_PATH)
    os.chmod(SOCK_PATH, 0o600)
    log(f"listening on {SOCK_PATH}")
    async with server:
        await server.serve_forever()


async def main():
    d = Daemon()
    await d.start()
    await serve(d)


if __name__ == "__main__":
    open(LOG_PATH, "w").close()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"fatal: {e}")
        sys.exit(1)

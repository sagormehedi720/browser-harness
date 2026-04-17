"""Helpers for controlling the browser. Read me. Edit me. Add new functions.

Every function is a thin wrapper around CDP. If a pattern is repetitive,
add a new helper here — this file is yours.

The only function that isn't a direct CDP call is `cdp()` itself, which
talks to the daemon over a Unix socket. The daemon forwards to Chrome.
"""
import base64
import json
import socket
import time

SOCK_PATH = "/tmp/harnesless.sock"


# ----- transport -----
def _send(req: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK_PATH)
    s.sendall((json.dumps(req) + "\n").encode())
    data = b""
    while True:
        chunk = s.recv(1 << 20)
        if not chunk:
            break
        data += chunk
        if data.endswith(b"\n"):
            break
    s.close()
    resp = json.loads(data.decode())
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return resp


def cdp(method: str, session_id: str | None = None, **params):
    """Raw CDP call. Examples:
        cdp("Page.navigate", url="https://example.com")
        cdp("DOM.getDocument", depth=-1, pierce=True)
    """
    return _send({"method": method, "params": params, "session_id": session_id}).get("result", {})


def drain_events():
    """Return all CDP events since last call, then clear the buffer."""
    return _send({"meta": "drain_events"})["events"]


def get_session():
    return _send({"meta": "session"})["session_id"]


def set_session(session_id: str):
    return _send({"meta": "set_session", "session_id": session_id})


def shutdown():
    return _send({"meta": "shutdown"})


# ----- navigation -----
def goto(url: str):
    return cdp("Page.navigate", url=url)


def reload():
    return cdp("Page.reload")


def back():
    h = cdp("Page.getNavigationHistory")
    i = h["currentIndex"]
    if i > 0:
        cdp("Page.navigateToHistoryEntry", entryId=h["entries"][i - 1]["id"])


def page_info():
    """url, title, viewport, scroll position."""
    r = cdp(
        "Runtime.evaluate",
        expression="JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY,pw:document.documentElement.scrollWidth,ph:document.documentElement.scrollHeight})",
        returnByValue=True,
    )
    return json.loads(r["result"]["value"])


# ----- input -----
def click(x: float, y: float, button: str = "left", clicks: int = 1):
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=clicks)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=clicks)


def double_click(x: float, y: float):
    click(x, y, clicks=2)


def right_click(x: float, y: float):
    click(x, y, button="right")


def move_mouse(x: float, y: float):
    cdp("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)


def type_text(text: str):
    """Insert text at the current focus. Simple unicode, no special keys."""
    cdp("Input.insertText", text=text)


def press_key(key: str, modifiers: int = 0):
    """Key is a KeyboardEvent.key string like 'Enter', 'Tab', 'ArrowDown', 'a'.
    Modifiers: 1=Alt, 2=Ctrl, 4=Meta, 8=Shift (bitfield, sum them).
    """
    cdp("Input.dispatchKeyEvent", type="keyDown", key=key, modifiers=modifiers)
    cdp("Input.dispatchKeyEvent", type="keyUp", key=key, modifiers=modifiers)


def scroll(x: float, y: float, dy: float = -300, dx: float = 0):
    cdp("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)


# ----- visual -----
def screenshot(path: str = "/tmp/shot.png", fmt: str = "png"):
    r = cdp("Page.captureScreenshot", format=fmt)
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return path


def screenshot_full(path: str = "/tmp/full.png"):
    r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return path


# ----- DOM (for forms, scraping, element targeting) -----
_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "label", "option", "summary"}
_INTERACTIVE_ATTRS = {"onclick", "role", "tabindex", "contenteditable", "aria-label"}


def get_dom(max_chars: int = 20000):
    """Flattened DOM filtered to interactive + text-bearing elements.
    Returns: list of "[backendNodeId] <tag attr=val ...> text" strings.
    Use click_element(id) / type_in(id, text) to act on them, or raw CDP.
    """
    doc = cdp("DOM.getFlattenedDocument", depth=-1, pierce=True)
    out = []
    total = 0
    for n in doc["nodes"]:
        if n.get("nodeType") != 1:
            continue
        tag = (n.get("nodeName") or "").lower()
        attrs = dict(zip(n.get("attributes", [])[::2], n.get("attributes", [])[1::2]))
        interactive = tag in _INTERACTIVE_TAGS or any(a in attrs for a in _INTERACTIVE_ATTRS)
        if not interactive:
            continue
        text = (n.get("nodeValue") or "")[:80].replace("\n", " ").strip()
        # Pull one level of inner text for buttons/links.
        if not text and n.get("children"):
            for c in n["children"]:
                if c.get("nodeType") == 3 and c.get("nodeValue"):
                    text = c["nodeValue"][:80].replace("\n", " ").strip()
                    break
        attr_str = " ".join(f'{k}="{v[:40]}"' for k, v in attrs.items() if k in ("id", "name", "type", "placeholder", "aria-label", "href", "value", "role"))
        line = f"[{n['backendNodeId']}] <{tag} {attr_str}> {text}".rstrip()
        total += len(line) + 1
        if total > max_chars:
            out.append(f"... (truncated, raise max_chars)")
            break
        out.append(line)
    return out


def element_pos(backend_node_id: int):
    """Return (center_x, center_y) for an element. Scrolls into view first."""
    cdp("DOM.scrollIntoViewIfNeeded", backendNodeId=backend_node_id)
    box = cdp("DOM.getBoxModel", backendNodeId=backend_node_id)
    q = box["model"]["content"]  # [x1,y1,x2,y2,x3,y3,x4,y4]
    return (q[0] + q[4]) / 2, (q[1] + q[5]) / 2


def click_element(backend_node_id: int):
    x, y = element_pos(backend_node_id)
    click(x, y)
    return x, y


def type_in(backend_node_id: int, text: str, clear: bool = True):
    click_element(backend_node_id)
    if clear:
        press_key("a", modifiers=4)  # Cmd+A (macOS); change to 2 for Ctrl+A
        press_key("Backspace")
    type_text(text)


# ----- tabs -----
def list_tabs():
    r = cdp("Target.getTargets")
    return [
        {"targetId": t["targetId"], "title": t.get("title", ""), "url": t.get("url", "")}
        for t in r["targetInfos"]
        if t["type"] == "page"
    ]


def switch_tab(target_id: str):
    r = cdp("Target.attachToTarget", targetId=target_id, flatten=True)
    set_session(r["sessionId"])
    return r["sessionId"]


def new_tab(url: str = "about:blank"):
    r = cdp("Target.createTarget", url=url)
    switch_tab(r["targetId"])
    return r["targetId"]


def close_tab(target_id: str):
    cdp("Target.closeTarget", targetId=target_id)


# ----- dialogs -----
def handle_dialog(accept: bool = True, text: str = ""):
    cdp("Page.handleJavaScriptDialog", accept=accept, promptText=text)


# ----- state -----
def save_cookies(path: str):
    cookies = cdp("Network.getCookies")["cookies"]
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
    return len(cookies)


def load_cookies(path: str):
    with open(path) as f:
        cookies = json.load(f)
    cdp("Network.setCookies", cookies=cookies)
    return len(cookies)


# ----- emulation -----
def set_viewport(w: int, h: int, scale: float = 1.0, mobile: bool = False):
    cdp("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=scale, mobile=mobile)


# ----- utility -----
def wait(seconds: float = 1.0):
    time.sleep(seconds)


def js(expression: str):
    """Run JavaScript, return the value (JSON-serialized)."""
    r = cdp("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
    return r.get("result", {}).get("value")

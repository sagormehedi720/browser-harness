# AGENTS.md

Context for future-me maintaining this codebase. Read `SKILL.md` first if you just want to use harnesless.

## Why this exists

Both `agent-browser` (Rust, 60+ commands) and the existing `browser-use` CLI (~20 commands) are walled gardens — the LLM is forced through a fixed verb list that can't express things the author didn't anticipate. Harnesless inverts this: almost no API, maximum freedom, LLM edits the helpers on the fly.

## Design decisions worth preserving

- **Coordinate clicks are the default, not the fallback.** `Input.dispatchMouseEvent` happens at the compositor level and goes through iframes, shadow DOM, cross-origin frames, canvas, SVG — in one call. DOM-based clicking requires per-frame CDP sessions and target juggling; coordinate clicking doesn't.
- **Daemon connects to user's running Chrome (`127.0.0.1:9222`), never launches one.** User sees what's happening in real time; cookies and logins are theirs.
- **We use `cdp-use` only for `CDPClient.send_raw`** — ignoring the 36k lines of generated typed wrappers. Typed wrappers (`cdp.send.DOM.getDocument(params={...})`) cost more tokens than raw `cdp("DOM.getDocument", ...)` and the LLM already knows method names from training.
- **`run.py` is 3 lines on purpose.** The LLM writes Python; we don't parse anything. No argparse, no subcommands.
- **helpers.py is explicitly editable at runtime.** The LLM is told "add a helper if you want one." This is the whole philosophy — don't add features that erode it.

## Architecture

```
Chrome (127.0.0.1:9222) ── CDP WebSocket ──▶ daemon.py  ── /tmp/harnesless.sock ──▶ run.py (one per tool call)
                                              (long-running)                         (from helpers import *; exec(stdin))
```

Protocol: one JSON line req, one JSON line resp. Request has either `{method, params, session_id}` (CDP passthrough) or `{meta: "..."}` (drain_events / session / set_session / shutdown). Response: `{result}` or `{error}` or `{events}` or `{session_id}`.

Daemon attaches to first page target at startup, stores `default_session`. Event buffer is a `deque(maxlen=500)`; `drain_events` flushes it. Logs go to `/tmp/harnesless.log`.

## Rules when extending

- Every helper ≤ 15 lines. If bigger, it doesn't belong.
- No new deps beyond stdlib + cdp-use + websockets.
- No classes in helpers.py. Module-level functions only.
- Don't add meta verbs lightly — if it can be a helper calling `cdp()`, it's a helper.
- Don't add: CLI argparse, tests, logging framework, config files, session manager, retries, multi-daemon.
- Taste test: "Could the LLM rewrite this from scratch after reading it once?" If no, it's too clever.

## Known gotchas

- `type_in` uses `modifiers=4` (Cmd+A) to clear — Linux/Windows need `2` (Ctrl+A).
- If daemon crashed and left `/tmp/harnesless.sock`, next start calls `os.unlink` on it; but if two daemons race, manual `rm` needed.
- `send_raw` has no timeout — a stuck CDP call hangs forever. Acceptable for now; add a wrapper if it becomes a problem.
- Daemon's default session can go stale if user navigates/closes tabs manually. `switch_tab(list_tabs()[0]["targetId"])` re-attaches.

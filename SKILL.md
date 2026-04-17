---
name: harnesless
description: Direct browser control via CDP. Use when the user wants to automate, scrape, test, or interact with web pages. Connects to the user's already-running Chrome.
allowed-tools: Bash, Read, Edit, Write
---

# Harnesless

Project: `/Users/greg/Documents/browser-use/hackathons/harnesless/`

Every action is one Bash call:
```bash
cd /Users/greg/Documents/browser-use/hackathons/harnesless && uv run run.py <<'PY'
# any python. helpers pre-imported.
PY
```

Setup (if daemon not running): user enables `chrome://inspect/#remote-debugging` → `uv sync` → `uv run daemon.py &`. Errors in `/tmp/harnesless.log`.

**The code is the documentation.** To see what helpers exist: `Read helpers.py` or `grep '^def ' helpers.py`. To see what the daemon speaks: `Read daemon.py`. To see design rationale: `Read AGENTS.md`. Don't guess — read.

You can edit `helpers.py` at any time. Adding a helper is expected, not exceptional.

Default workflow: screenshot → `click(x,y)`. For forms: `get_dom()` → `click_element(id)` / `type_in(id, text)`. For anything else: `cdp("Domain.method", ...)`.

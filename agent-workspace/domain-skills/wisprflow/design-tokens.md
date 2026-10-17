---
name: wisprflow-design-tokens
description: wisprflow.ai (Webflow) — where the full design-token set lives, how to read it with one HTTP fetch, and which computed styles to pull from the live page.
---

# Wispr Flow — design tokens

wisprflow.ai is a Webflow site. Everything a "match their look" task needs is in **one shared stylesheet** plus a handful of computed styles — no scrolling or DOM scraping required for tokens.

## The stylesheet (no browser needed)

The homepage HTML links a single shared CSS file on Webflow's CDN:

```python
html = http_get("https://wisprflow.ai")
import re
css_url = re.search(r'href="(https://cdn\.prod\.website-files\.com/[^"]+\.webflow\.shared\.[^"]+\.css)"', html).group(1)
css = http_get(css_url)   # ~700 KB minified
```

The hash in the filename changes on every publish — always resolve it from the HTML, never hard-code it.

Tokens are CSS custom properties with Webflow's variable-collection naming:

| Prefix | Holds |
|---|---|
| `--base-color--*` | brand palette, named (e.g. lumen, vast, dawn, fathom, glow, flare, signal, pulse) |
| `--base-color-neutral--*`, `--base-color-system--*` | greys and success/warning/error pairs |
| `--background-color--*`, `--text-color--*`, `--border-color--*`, `--link-color--*` | semantic aliases pointing at base colors |
| `--alpha--light--NN`, `--alpha--dark--NN` | the cream and ink at fixed alphas |
| `--_text-collection---font--*` | font stacks (primary/display vs body) |
| `--_text-collection---heading--h1..h6`, `---body--*` | type scale in rem |
| `--_spacing---section-radius--*`, `---section-paddings--*` | section corner radii and paddings |

Each collection appears more than once (breakpoint overrides); the first occurrence is desktop.

`@font-face` blocks in the same file name the families actually shipped (`grep -oE '@font-face\{[^}]*\}' | grep -oE 'font-family:[^;]+'`).

## What to read from the live page

Some values only resolve at runtime. Pull these with `js()` and `getComputedStyle` after `new_tab` + `wait_for_load()`:

- The primary CTA: find the anchor by its text ("Get started…"), then read background, border, border-radius, padding and font.
- `h1` font, letter-spacing and line-height, plus the `em`/italic span inside it (the payoff half of each headline is italic).
- `document.body` background and font.

## Traps

- The dark-green section colour can look different in screenshots than in CSS, because of the screenshot colour profile. Trust the token value, not the pixels.
- The nav is a floating card inside a transparent `nav` element, so `getComputedStyle(nav)` returns transparent. Read `.nav_container-*` for the card instead.
- The page is about 20k px tall with heavy scroll-driven video. Screenshots taken right after `scrollTo` can catch sections mid-animation, so wait about 1s between steps.

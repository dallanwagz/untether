# Untether — Brand & Identity Guide

> Local control. No cloud. No leash.

Untether takes a Bluetooth/BLE gadget that's locked to its vendor phone app and
**frees it** — decode the radio protocol, rebuild it as a local, cloud-free Home
Assistant integration. The identity has to say that in one glance: *snap the
tether, run it local.*

---

## 1 · Concept & rationale

The emblem is a **Bluetooth rune breaking free of its chain**. The classic
Bluetooth glyph stands for the device. A short **chain** hangs from its base —
the tether to the vendor app — and it has just **snapped**: the break glows in
the electric accent (magenta), and the dead lower fragment falls away as a
dashed, severed leash. The freed device immediately does what a liberated device
does: it **broadcasts**, shown by the symmetric **radio / advertisement arcs**
radiating from both sides. The leash is cut; the signal is ours now.

Running underneath is a **byte row** — a real BLE advertisement header,
`[ 02 01 06 FF 39 14 ]` — with one byte (`FF`) lit in the accent color. That's
the **"golden frame"**: the single captured-and-decoded frame that anchors every
decode in this project, the moment the protocol stops being a guess and becomes
ground truth. (`39 14` is a wink at `#39FF14`, the phosphor green.) The whole
thing sits on near-black with faint **CRT scanlines** and a phosphor glow: a
terminal, late at night, watching packets come off the radio.

The tone is **DEF CON badge / phrack / 2600** — a confident hacker emblem, not a
corporate logo and not a busy illustration. Medium complexity on purpose: rich
enough to reward a close look on a sticker or a conference slide, simple enough
to survive being shrunk to a 16px favicon, where it collapses cleanly to "a
Bluetooth glyph cutting its leash and broadcasting."

---

## 2 · Color palette

| Role | Name | Hex | Use |
|---|---|---|---|
| Background | Terminal Black | `#0A0E12` | canvas; everything sits on it. A subtle radial lift to `#10161C` at center is allowed. |
| Primary | Phosphor Green | `#39FF14` | the Bluetooth glyph, radio arcs, wordmark, frames, the bulk of the mark. |
| Primary (light) | Phosphor Tint | `#7CFFD0` | top highlight of the glyph gradient only; gives the "lit CRT" sheen. |
| Primary (deep) | Phosphor Shade | `#16C24F` | bottom of the glyph gradient; adds depth, never used for text. |
| Accent | Cut Magenta | `#FF2E97` | **one job:** the break/snap, the lit golden-frame byte, the terminal caret. Scarce by design. |
| Tagline text | Mint | `#9FFFC8` | secondary/tagline lines so they read as quieter than the wordmark. |

**Accent discipline:** magenta marks *the cut and the truth* — the snapped link,
the golden byte, the cursor. If a second magenta element doesn't mean "this is
where the leash breaks" or "this is the proven byte," it shouldn't be magenta.

**Approved alternates** (if a build needs a cooler accent): primary may be
`#00FF9C`; accent may be cyan `#00E5FF`. Never run magenta *and* cyan accents in
the same lockup — pick one electric accent.

---

## 3 · Type treatment

- **Wordmark:** `untether`, all lowercase, drawn as a custom **stencil monospace**
  built from stroked vector paths in `untether-logo.svg` (rounded caps/joins,
  even stem weight). It is shipped as paths so it needs **no font install** and
  renders identically under `rsvg-convert` / `cairosvg`.
- **Supporting text** (byte rows, taglines, CLI): a **monospace** stack —
  `'DejaVu Sans Mono', 'Menlo', 'Consolas', monospace`. Always lowercase for the
  wordmark; taglines may be UPPERCASE with generous letter-spacing for the
  terminal feel.
- **Caret:** a solid magenta block `▮` after the wordmark evokes a live terminal
  prompt. Optional, but on-brand.
- Don't pair the mark with a serif or a humanist sans. Mono or nothing.

---

## 4 · Usage — do / don't

**Do**
- Keep clear space around the lockup ≥ the height of the "u" on all sides.
- Put the mark/emblem on near-black or a genuinely dark surface.
- Use the square **mark** for avatars, favicons, app tiles, sticker die-cuts.
- Use the **lockup** for README headers, slide title cards, docs banners.
- Let the magenta stay rare. One accent moment per composition is plenty.

**Don't**
- Don't recolor the glyph to brand-blue Bluetooth — the green *is* the point.
- Don't place it on white/light backgrounds (phosphor green dies on white). If
  you must, use the all-green knockout on a dark plate, not on bare white.
- Don't add a second electric accent, gradients on the text, or drop shadows
  beyond the built-in phosphor glow.
- Don't stretch, skew, or rotate the emblem; don't separate the arcs from the
  glyph; don't "fix" the broken chain — the break is the brand.
- Don't swap in a real installed font for the wordmark and re-space it; use the
  shipped SVG so the stencil proportions hold.

---

## 5 · Assets & where they're used

| File | viewBox | What it is | Use it for |
|---|---|---|---|
| `untether-logo.svg` | `0 0 1200 400` | Primary horizontal lockup: emblem + `untether` wordmark + caret + golden-frame byte row + tagline slot. | README header, docs/site banner, slide title card, social card. |
| `untether-mark.svg` | `0 0 512 512` | Square emblem only (glyph + arcs + snapped chain + byte-row footer). | Favicon, GitHub/org avatar, app tile, stickers, embroidery. |
| `untether-banner.txt` | ~70 cols | ASCII-art banner of `UNTETHER` + tagline + golden-frame line. | CLI splash / `--version` art, README top fence, MOTD. |
| `BRANDING.md` | — | This guide. | Anyone touching the brand. |

**Rendering:** both SVGs are valid, self-contained, and verified with
`rsvg-convert` (no JS, no external fonts, inline styling only). To rasterize:

```sh
rsvg-convert -w 1200 untether-logo.svg -o untether-logo.png
rsvg-convert -w 512  untether-mark.svg  -o untether-mark.png   # favicon: -w 32/64/128
```

`cairosvg` works equally well. The mark stays legible down to ~16px; below that,
prefer a hand-tuned favicon export at 32px.

---

## 6 · Voice (so the visuals don't stand alone)

Terse, confident, evidence-first. Taglines, interchangeable:

- **Local control. No cloud. No leash.**
- Free your devices from their apps.
- Static is the spec. Dynamic is the truth.

*Static gives the spec. Dynamic gives the truth. The operator gives the ground.
The library remembers.*

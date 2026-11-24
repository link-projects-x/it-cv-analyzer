# UI reference

Collected on 2026-10-31 from public pages. We take a palette and layout patterns; no logos, names, illustrations or
copy from these products.

## Palette (taken from tealhq.com computed styles)

| Token | Value | Use |
|---|---|---|
| `--color-primary` | `#005149` | primary actions, active slider track, headings accent |
| `--color-primary-soft` | `#E9F3F3` | selected rows, chips, rail background |
| `--color-accent` | `#F5B501` | the one main call to action per screen (Upload CV), "fits" badge |
| `--color-accent-soft` | `#F9D367` | accent hover / highlight |
| `--color-secondary` | `#791E3F` | "above what the CV shows" state, missing required skill |
| `--color-info` | `#5A6FEC` | links, focus ring |
| `--color-bg` | `#F7F7F7` | page background |
| `--color-surface` | `#FFFFFF` | cards |
| `--color-border` | `#F1F2F2` | hairlines |
| `--color-text` | `#333333` | body text |
| `--color-text-strong` | `#222222` | headings |
| `--color-text-muted` | `#6E7272` (reference `#9EA1A1` fails AA: 2.4:1) | captions, "was X" |
| `--color-positive` | `#005149` | positive deltas (same as primary) |
| `--color-negative` | `#791E3F` | negative deltas |

Dark mode: derive by keeping hue and inverting lightness (background ≈ `#121615`, surface ≈ `#1B2120`, text ≈ `#E6EAE9`,
primary lightened to ≈ `#4FB3A8` for contrast). Check WCAG AA contrast for text on every surface in both modes.

Font: Teal uses Roobert (commercial) — do not use it. Use `Manrope` from Google Fonts (or the system stack as fallback);
numbers in `tabular-nums`.

Shape: cards with 12px radius, buttons fully rounded (pill), 8px spacing grid, no heavy shadows (1px border + very soft
shadow at most).

## Patterns to borrow

| Source | Pattern | Our use |
|---|---|---|
| Jobscan match report | large match-rate number per document; table of hard skills found / missing | per vacancy: coverage ring + chips of required skills, green = covered, maroon = missing, outlined = partial |
| Teal "Matching Mode" | keyword checklist next to the resume | in the expanded vacancy card: requirement list with evidence quotes and a check per item |
| Djinni salary stats | stat cards: big number with a coloured delta, filters as chips | top bar: "Fits", "Mean coverage", "Salary estimate", each with delta vs opening |
| Innovera RQASim (ideas only, no code) | control rail on the right, `was X` under moved values, Reset greyed until touched, ticks for the supported band | slider rail; CV-supported level as a tick |

## Screens

1. **Upload** — drop zone for PDF / DOCX / TXT, privacy note (CV deleted after parsing), states: idle, uploading,
   parsing, matching, error.
2. **Results** — stat cards on top, vacancy list in the main column, slider rail on the right (bottom sheet on mobile),
   hints under the stat cards.

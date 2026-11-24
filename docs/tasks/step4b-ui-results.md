# Step 4b — results screen design

Branch `feat/ui-results`. Work in `web/` only, and only in presentation: components, styles, layout. Read
`docs/tasks/README.md`, `docs/tasks/ui-reference.md` and `web/README.md` first.

## Goal

Restyle and re-lay out the results screen built in step 4 to the palette and patterns in `ui-reference.md`, without
changing behaviour. The logic modules (`src/coverage.ts`, `src/state.ts` and the selectors) and their tests stay as they
are; if a component needs a value the selectors do not expose, add a new selector with a test rather than computing in
the component.

## Must have

- `src/styles/tokens.css` already exists on main with every token from `ui-reference.md`, light and dark. Import it
  once, use only its variables (no raw hex values anywhere else), and adjust the dark values only if the contrast check
  below fails, saying which and why. A theme toggle (system / light / dark) via `data-theme` on `<html>`.
- Slider rail that stays usable with many skills: with the two example vacancies there are already 31 sliders, and
  50 vacancies will give more. Group skill sliders by `group` from `skills.json`; show child skills (`parent` set)
  indented under their parent inside the group; show the 8 sliders with the largest effect expanded and the rest behind
  "Show all N"; a search field filters by skill name. Experience and English stay pinned at the top of the rail.
- Experience slider opens at `floor(experience_years + 0.5)` clamped to 0–15 and the salary grid is read with the same
  key (`contracts/README.md -> Salary grid`). Today a non-integer experience shows a dash; fix that in `state.ts` with a
  test.
- Layout: stat cards row (Fits, Mean coverage, Salary estimate, each with a delta vs opening, coloured by sign);
  hints block; vacancy list in the main column; slider rail on the right at ≥ 1024px, a bottom sheet with a toggle
  below that. No horizontal scroll at 375px.
- Vacancy card: title (link), company, location/remote, coverage ring with the percentage, "fits" badge, delta vs
  opening; required skills as chips (covered / partial / missing, with a legend), expandable list of all requirements
  with their evidence quotes.
- Slider row: label, value as level name, `was X` when moved, tick at the CV-supported level, maroon state above it,
  keyboard operable, visible focus ring.
- Reset button: pill, disabled until touched.
- Font Manrope via Google Fonts with a system fallback; `tabular-nums` on numbers.
- Respect `prefers-reduced-motion` for any transition.

## Checks

- Existing tests still pass; add component tests for the chip states and delta colouring (Testing Library).
- `npm run lint`, `npm test`, `npm run build` pass.
- Check contrast (AA) of text tokens on `--color-bg` and `--color-surface` in both modes with a small script or test
  and report the ratios.
- Run the dev server, take screenshots at 1440px and 375px in light and dark (Playwright is fine, install it as a dev
  dependency), save them under `web/docs/screenshots/` and commit them.

## Done when

The checks pass and the report lists the screenshots, contrast ratios and any behaviour that changed (should be none).

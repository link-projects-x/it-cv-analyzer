# web: CV vs vacancies, with sliders

React + TypeScript page for step 4. It reads one API response (`contracts/match-response.schema.json`) and
recomputes, in the browser and without network calls, on every slider move:

- coverage of each vacancy (formula: `contracts/README.md -> Coverage formula`, code: `src/coverage.ts`);
- how many vacancies fit (`coverage >= fits_threshold`);
- the salary estimate from `salary.point` / `salary.grid`;
- the top 5 hints (effect of one step up on one slider).

The first screen uploads a CV through `MatchApi` (`src/api/types.ts`). With `VITE_API_URL` unset the app uses the
mock (`src/api/mock.ts`), which returns `contracts/examples/match-response.example.json`; a file named `fail*.pdf` makes
the mock job fail. With `VITE_API_URL` set (`terraform output -raw api_url`) the app uses `src/api/http.ts`: the upload
screen asks for an access code (kept in this browser's localStorage), sends it as `Authorization: Bearer <code>`,
uploads the file with the presigned S3 POST and polls `GET /jobs/{id}`. The HTTP client is tested against a fake
`fetch` only; it has not been run against a deployed API.

## Run

```sh
cd web
npm install
npm run dev      # dev server
npm test         # vitest: golden parity, state, visibility, salary, hints, vacancy order, static render
npm run lint     # eslint
npm run build    # tsc (strict) + vite build into web/dist
npm run screenshots  # needs `npm run dev -- --port 5180` running and `npx playwright install chromium`
```

Screenshots of the results screen (1440px and 375px, light and dark, opening and moved state, mobile bottom sheet)
are in `docs/screenshots/`.

`contracts/*.json` is imported through the `@contracts` alias (`vite.config.ts`, `tsconfig.app.json`), not copied.

## Layout

| File | Role |
|---|---|
| `src/coverage.ts` | Coverage formula; mirrors `contracts/coverage_reference.py`. |
| `src/coverage.test.ts` | Asserts every case of `contracts/fixtures/coverage-golden.json` (coverage within 1e-9, `fits` equal). |
| `src/state.ts` | State = opening values + `touched`; transitions and selectors, including `salaryEstimate`. |
| `src/visibility.ts` | Which skill sliders are drawn, and their order. |
| `src/hints.ts` | One-step hints and their ranking. |
| `src/vacancies.ts` | Vacancy list order. |
| `src/summary.ts` | Stat card numbers (fits, mean coverage, salary) and their change against the opening state. |
| `src/rail.ts` | Slider rail: effect per skill slider, top 8, grouping by `skills.json` group, search. |
| `src/requirements.ts` | Per-requirement status (covered / partial / missing) for the vacancy card. |
| `src/theme.ts` | Theme preference (system / light / dark) on `<html data-theme>`, kept in localStorage. |
| `src/styles/tokens.css` | Colour, font, radius and spacing tokens; `src/styles.css` uses only these variables. |
| `src/styles/contrast.test.ts` | WCAG contrast of the text tokens on bg and surface, light and dark. |
| `src/components/` | Results screen: stat cards, hints, vacancy cards, slider rail / bottom sheet, theme toggle. |
| `src/api/` | `MatchApi` interface, mock, HTTP client with the access code, selection by `VITE_API_URL`. |
| `src/upload/` | Upload, progress and error views; file checks (`validate.ts`); screen state machine (`flow.ts`); polling (`runJob.ts`); `AppFlow.tsx` joins them with the results screen. |
| `scripts/screenshots-upload.mjs` | Playwright screenshots of the upload states into `docs/screenshots/upload-*`. |

## Rules as implemented

- **Skill sliders.** A skill from `skills.json` gets a slider if setting it to the slider minimum vs. maximum (0 vs. 3,
  from `coverage.json -> sliders.skill`) changes the coverage of at least one loaded vacancy. The other skills stay at
  the opening profile, so the set of sliders does not change while dragging. Order: number of vacancies the skill
  moves, then number of vacancies that list it in `any_of`, then name.
- **Slider rail.** Experience and English are pinned at the top. Skill sliders are grouped by `group` from
  `skills.json`; a child skill is drawn indented under its parent when the parent's slider is shown. Effect of a
  skill slider: sum over the loaded vacancies of the coverage change between level 0 and level 3, on the opening
  profile. The 8 sliders with the largest effect (ties: slider order above) and any moved slider are expanded; the
  rest are behind "Show all N". Search matches the skill name and its `skills.json` aliases and overrides "Show all".
  Groups are ordered by the largest effect inside them. Collapsed rows stay in the DOM with `hidden`.
  At 1024px and wider the rail is a sticky right column; below that it is a bottom sheet opened by a button.
- **Experience position.** The experience slider opens at `floor(experience_years + 0.5)` clamped to 0–15
  (`contracts/README.md -> Salary grid`), and the grid key is that position. Moving back to the opening position
  is not a move. Until the slider moves, coverage reads the parsed `experience_years` (3.5 stays 3.5).
- **CV tick.** Drawn at the opening level of a profile skill whose `evidence` is not null. A moved skill above that
  level (above 0 for skills without evidence or not in the profile) shows "Level is above what the CV shows."
- **Salary.** No salary input moved: `point` (and `low`–`high` when both are set). Exactly one of English / experience
  moved: `grid[input][new value]`. Both moved: a dash and "salary estimate changes one setting at a time". Missing
  grid key: a dash. Skill sliders never change the estimate.
- **Hints.** For each drawn skill slider plus experience and English that can go one step up: change in fits count,
  change in mean coverage (vacancies with `coverage: null` are left out of the mean), change in the displayed salary
  estimate (English / experience only; null when the estimate is a dash before or after the step). Steps with no
  change in all three are dropped. Ranked by fits change, mean coverage change, salary change (null as 0); ties keep
  the slider order.
- **Vacancies.** Sorted by coverage, then `similarity`; `coverage: null` shows a dash and sorts last.

## Contrast

`src/styles/contrast.test.ts` checks text tokens against `--color-bg` and `--color-surface`. Every pair passes AA
(4.5:1). Light `--color-text-muted` is `#6e7272` (4.55 on bg, 4.87 on surface) instead of the reference palette's
`#9EA1A1`, which gave 2.43 / 2.60.

## Not implemented yet

- Presets.

# Step 4 — web app with sliders

Branch `feat/step4-web`. Work in `web/` only. Read `docs/tasks/README.md` and `contracts/README.md` first.

## Goal

A React + TypeScript page that takes one API response (`contracts/match-response.schema.json`) and lets the user move
sliders for skills, experience and English. Every move recomputes, in the browser and without network calls, the
coverage of each vacancy, how many vacancies fit, the salary estimate, and the ranked hints.
There is no API yet: the page loads `contracts/examples/match-response.example.json`.

## Stack

Vite, React, TypeScript (`strict`), Vitest, ESLint. No UI component library is required; plain CSS or CSS modules.
Read `contracts/` files through a Vite alias (`@contracts`) so the JSON is imported, not copied.

## Coverage — must match the reference

- `src/coverage.ts` implements the formula in `contracts/README.md -> Coverage formula`, reading weights, threshold and
  CEFR order from `contracts/coverage.json` and the hierarchy (`parent`) from `contracts/skills.json`.
- `src/coverage.test.ts` loads `contracts/fixtures/coverage-golden.json` and asserts every case: `coverage` within
  `1e-9` (both `null` counts as equal) and `fits` equal. This parity test is the acceptance test for the formula.

## State — pure functions, tested without React

The state is the opening values plus what the user touched (`touched`), not a copy that drifts.

- `initialState(response)`: opening skill levels from `profile.skills`, `experience_years`, `english`; empty `touched`.
- `dragSkill(state, id, level)`, `setExperience(state, years)`, `setEnglish(state, cefr)`, `reset(state)`.
- Setting a value back to its opening value removes it from `touched`.
- Selectors: `currentProfile(state)`, `isTouched(state)`, `coverages(state, vacancies)`, `fitsCount(...)`,
  `salaryEstimate(state, salary)`, `hints(state, vacancies, salary)`.

Ranges for sliders come from `contracts/coverage.json -> sliders`, not literals in components.

## Which skill sliders to show

Show a slider for a skill only if moving it from 0 to 3 changes the coverage of at least one of the loaded vacancies
(hierarchy included: a profile `aws-bedrock` moves a vacancy that requires `aws`). A slider that moves nothing is not
drawn. Order: skills required by the most vacancies first. Label: `name` from `skills.json`.

## Slider row

- Label, current value as the level name (`skills.json -> levels`), and `was <opening>` once the value differs from the
  opening one.
- A tick on the track at the level the CV supports (the profile skill's opening level when its `evidence` is not null).
  Moving above it is allowed; the row then says the level is above what the CV shows.
- `aria-valuetext` with the level name.

## Salary

`salary.grid` varies one input at a time with the rest of the profile unchanged, so:

- nothing that affects salary moved → `salary.point` (and `low`–`high` when not null);
- exactly one of English / experience moved from its opening value → the grid value for the new position;
- both moved → show a dash and the note "salary estimate changes one setting at a time"; do not add deltas.
- a grid key missing for the position → a dash, never the opening value.

Skill sliders do not change the salary estimate (the salary model has no skill inputs); say so once under the estimate.

## Vacancy list

Title (link to `url`), company, coverage as a percentage, a "fits" badge at `coverage ≥ fits_threshold`, and the
change against the opening coverage (`+12 pp`) once anything moved. Sort by coverage, then by `similarity`.
`coverage: null` shows a dash and sorts last.

## Hints

For each visible slider that can go one step up, compute the effect of that single step from the current state:
change in fits count, change in mean coverage over the loaded vacancies, change in salary (only English / experience,
only when the grid allows it per the rules above). Rank by fits change, then mean coverage change, then salary change;
show the top 5 as "RAG: pet project → production: +3 vacancies, +4.1 pp". Hints are code; no LLM.

## Reset

A Reset button, disabled until something is touched, returns to the opening state.

## Deliverables

`web/` with `package.json` scripts `dev`, `build`, `test`, `lint`; `src/coverage.ts`, `src/state.ts`, components,
tests for coverage (golden), state transitions, slider visibility, salary rules, and hint ranking; `web/README.md`
with how to run and what is not implemented yet (CV upload, API calls, presets).

## Done when

`npm test`, `npm run lint` and `npm run build` pass in `web/`, and the PR description includes a screenshot or a short
description of the page with the example data.

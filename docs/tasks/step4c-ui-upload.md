# Step 4c — upload screen and API client

Branch `feat/ui-upload`. Work in `web/` only. Read `docs/tasks/README.md`, `docs/tasks/ui-reference.md`,
`contracts/match-response.schema.json` and `web/README.md` first.

## Goal

The first screen: the user uploads a CV and gets to the results screen. There is no backend yet, so the API is an
interface with a mock implementation; the real HTTP implementation is a later step.

## Must have

- `src/api/types.ts`: `MatchApi` interface — `uploadCv(file): Promise<{ jobId }>`, `getJob(jobId): Promise<JobStatus>`
  where `JobStatus` is `{ state: "uploading" | "parsing" | "matching" } | { state: "done", result: MatchResponse }
  | { state: "failed", error: string }`. `MatchResponse` typed from the contract (hand-written types are fine; keep them
  in one file).
- `src/api/mock.ts`: walks through the states with delays (configurable, 0 in tests) and returns
  `contracts/examples/match-response.example.json`; a file named `fail*.pdf` produces `failed` (for manual testing).
- `src/api/http.ts`: a stub that throws "not implemented" behind the same interface, plus `VITE_API_URL` read once;
  the app picks mock when it is unset.
- Upload screen: drop zone + file button; accepts `.pdf`, `.docx`, `.txt`, max 5 MB, rejects others with an inline
  message; privacy note ("Your CV is used only to build your profile and is deleted after parsing."); progress view with
  the three steps; error view with Retry. One accent-coloured call to action (`--color-accent`).
- App flow: upload → progress → results (the existing results screen receives the `MatchResponse`), with a "New CV"
  action on the results screen that returns to upload. No router library needed; a small state machine is enough.
  Keep the change to the existing results components to the one prop they need.
- Use only the variables from `src/styles/tokens.css` (already on main); do not edit that file — another task owns it.
  Put upload-screen styles in their own file.

## Checks

- Tests (Vitest + Testing Library): file type/size validation, mock state sequence, failed state and Retry, flow from
  upload to results with the example data.
- `npm run lint`, `npm test`, `npm run build` pass.
- Screenshots of the upload, progress and error states at 1440px and 375px (Playwright) in `web/docs/screenshots/upload-*`.

## Done when

The checks pass and the report lists what was verified.

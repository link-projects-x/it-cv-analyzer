# Tasks for parallel sessions

Each file is a self-contained brief for one Claude Code cloud session. Start a session on this repo with:

> Read docs/tasks/<file> and do the task.

| File | Branch | Touches |
|---|---|---|
| `step2-cv.md` | `feat/step2-cv` | `services/cv/`, `scripts/build_lambdas.sh`, `infra/` |
| `step4-web.md` | `feat/step4-web` | `web/` |
| `step5-salary.md` | `feat/step5-salary` | `ml/salary/` |
| `step3-api.md` | `feat/step3-api` | `services/api/`, `services/indexer/`, `ml/salary/` packaging, `scripts/`, `infra/` |
| `step4b-ui-results.md` | `feat/ui-results` | `web/` presentation |
| `step4c-ui-upload.md` | `feat/ui-upload` | `web/src/api/`, upload screen, app flow |

## Rules for every task

- Work only in the paths listed for your task. `contracts/` is read-only: if the task needs a contract change, stop
  and describe the change in the PR description instead of making it.
- Do not edit the root `README.md`; the step table there is updated when PRs merge.
- All files in English (code, comments, docs, messages). Data values copied from sources keep their original language.
- No calls to paid APIs (Anthropic, Bedrock, any AWS service) and no AWS resources. Tests use fakes.
- Do not commit data, model artifacts, `node_modules`, build output or caches (see `.gitignore`).
- Before opening the PR: tests pass, `python contracts/check.py` passes, and the PR description lists what was
  verified and what was not.
- Open one PR into `main` from the task's branch.

# Vacancy parsing eval

Measures how well the LLM turns a DOU vacancy into `contracts/vacancy.schema.json`, so model, prompt and effort
changes are judged by numbers.

## Workflow

1. `python eval/sample.py --data data --n 25` — picks 25 vacancies, writes empty templates to `eval/labels/` and the
   vacancy texts to `data/eval_texts/`.
2. Label each template by hand (rules below), then set `"_done": true`.
   Split the 25 between the four of us; a second person re-checks 5 of them to catch disagreements in the rules.
3. Parse the same vacancies: `cd services/parser && python -m parser --data ../../data --ids <ids>`.
4. `python eval/compare.py --data data`.

Label files are committed. Vacancy texts are not (DOU content, regenerate with step 1).

## Labelling rules

Same rules the LLM gets, from `contracts/README.md`:

- Skill IDs only from `contracts/skills.json`; anything else goes to `unmapped`.
- Alternatives ("AWS, Azure or GCP") → one item with `any_of`.
- `required: false` for nice to have / will be a plus / буде перевагою.
- `min_level`: 1 familiarity, 2 experience with / hands-on, 3 production / commercial / N years in X.
- `evidence`: copy the shortest supporting quote.
- Experience: "3+ years" → 3 / null, "3–5 years" → 3 / 5.
- English in CEFR: Upper-Intermediate → B2, Advanced / Fluent → C1.
- Skills that describe the company's product, not the candidate, are not requirements.

When a rule does not cover a case, write the case into `contracts/README.md` in the same PR, so the prompt and the
labels follow the same rule.

## What to compare

| Run | Change |
|---|---|
| baseline | `anthropic.claude-haiku-5-5`, effort `low` |
| effort | same model, effort `medium` |
| model | Claude Sonnet 5.5, effort `low` (take the Bedrock model ID from the model page in the Claude docs) |

Record token usage from the parser output next to the metrics: a better F1 at several times the cost may not be worth it.

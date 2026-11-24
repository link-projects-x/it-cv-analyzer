"""Reference implementation of the coverage formula (contracts/README.md -> Coverage formula).

Every other implementation (the TypeScript one in web/, the hint ranking) must reproduce
contracts/fixtures/coverage-golden.json, which this module writes:

  python contracts/coverage_reference.py --write-golden

The golden file holds inputs and expected outputs, so a consumer needs no Python to test against it.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config() -> dict:
    return json.loads((ROOT / "coverage.json").read_text(encoding="utf-8"))


def load_skills() -> list[dict]:
    return json.loads((ROOT / "skills.json").read_text(encoding="utf-8"))["skills"]


def effective_levels(profile_skills: dict[str, float], skills: list[dict]) -> dict[str, float]:
    """Profile skill years after the hierarchy rule: a parent's years are the max of its own and its descendants'."""
    parent_of = {s["id"]: s.get("parent") for s in skills}
    levels = dict(profile_skills)
    for sid, level in profile_skills.items():
        parent = parent_of.get(sid)
        seen = set()
        while parent is not None and parent not in seen:  # seen guards against a cycle in skills.json
            seen.add(parent)
            levels[parent] = max(levels.get(parent, 0), level)
            parent = parent_of.get(parent)
    return levels


def needed_years(req: dict, vacancy: dict, cfg: dict) -> float:
    """Years a requirement asks for: its own min_years, else the vacancy's experience (or the years typical for its
    grade, or default_years) times inherit_factor."""
    if req.get("min_years") is not None:
        return float(req["min_years"])
    sy = cfg["skill_years"]
    base = vacancy["experience"]["min_years"] or sy["grade_years"].get(vacancy.get("seniority") or "unknown") or sy["default_years"]
    return base * sy["inherit_factor"]


def skill_score(years: float, need: float) -> float:
    """0 without the skill; otherwise the share of the needed years, capped at 1."""
    if years <= 0:
        return 0.0
    return 1.0 if need <= 0 else min(1.0, years / need)


def coverage(profile: dict, vacancy: dict, cfg: dict, skills: list[dict]) -> dict:
    """Return {"coverage": float | None, "fits": bool, "parts": {...}}.

    profile: {"skills": {id: years}, "experience_years": number, "english": CEFR | None}
    vacancy: a contracts/vacancy.schema.json document (requirements, experience, english, seniority are read)

    coverage is None when the vacancy has nothing to score (no requirements, no experience, no English).
    """
    w = cfg["weights"]
    levels = effective_levels(profile["skills"], skills)

    skills_part = skills_max = 0.0
    for req in vacancy["requirements"]:
        weight = w["required"] if req["required"] else w["optional"]
        need = needed_years(req, vacancy, cfg)
        score = max(skill_score(levels.get(sid, 0), need) for sid in req["any_of"])
        skills_part += weight * score
        skills_max += weight

    exp_part = exp_max = 0.0
    min_years = vacancy["experience"]["min_years"]
    if min_years:  # None or 0: the vacancy asks for no experience, so the part is skipped
        exp_part = w["experience"] * min(1.0, profile["experience_years"] / min_years)
        exp_max = w["experience"]

    eng_part = eng_max = 0.0
    need = vacancy["english"]["min_level"]
    if need is not None:
        order = cfg["cefr_order"]
        have = profile["english"]
        have_i = order.index(have) + 1 if have else 0
        need_i = order.index(need) + 1
        eng_part = w["english"] * (1.0 if have_i >= need_i else have_i / need_i)
        eng_max = w["english"]

    total_max = skills_max + exp_max + eng_max
    if total_max == 0:
        return {"coverage": None, "fits": False, "parts": {"skills": 0.0, "experience": 0.0, "english": 0.0, "max": 0.0}}

    value = (skills_part + exp_part + eng_part) / total_max
    return {
        "coverage": value,
        "fits": value >= cfg["fits_threshold"] - 1e-12,
        "parts": {"skills": skills_part, "experience": exp_part, "english": eng_part, "max": total_max},
    }


# --- golden cases -----------------------------------------------------------


def _req(any_of, min_years=None, required=True):
    return {"any_of": any_of, "min_level": 2, "min_years": min_years, "required": required, "evidence": "x"}


def _vac(requirements, min_years=None, english=None, seniority="unknown"):
    return {
        "seniority": seniority,
        "requirements": requirements,
        "experience": {"min_years": min_years, "max_years": None},
        "english": {"min_level": english, "evidence": "x" if english else None},
    }


def golden_cases() -> list[dict]:
    example_profile = json.loads((ROOT / "examples" / "profile.example.json").read_text(encoding="utf-8"))
    match = json.loads((ROOT / "examples" / "match-response.example.json").read_text(encoding="utf-8"))
    ex = {
        "skills": {s["id"]: s["level"] for s in example_profile["skills"]},
        "experience_years": example_profile["experience_years"],
        "english": example_profile["english"],
    }
    base = {"skills": {"python": 2, "aws-bedrock": 2, "docker": 3}, "experience_years": 2, "english": "B2"}

    cases = [
        ("example profile vs example vacancy 1", ex, match["vacancies"][0]["vacancy"]),
        ("example profile vs example vacancy 2", ex, match["vacancies"][1]["vacancy"]),
        ("partial years: 2 of the skill's 3", base, _vac([_req(["python"], 3)])),
        ("over the needed years is capped at 1", base, _vac([_req(["docker"], 2)])),
        ("missing skill scores 0", base, _vac([_req(["pytorch"], 2)])),
        ("any_of takes the best option", base, _vac([_req(["azure", "docker", "gcp"], 3)])),
        ("hierarchy: child years lift the parent", base, _vac([_req(["aws"], 2)])),
        ("hierarchy does not flow down to children", {**base, "skills": {"aws": 3}}, _vac([_req(["aws-bedrock"], 1)])),
        ("optional weighs half of required", base, _vac([_req(["python"], 2), _req(["pytorch"], 2, required=False)])),
        ("no skill years: the vacancy's experience is inherited", base, _vac([_req(["python"])], min_years=4)),
        ("no years at all: the grade's typical years", base, _vac([_req(["python"])], seniority="senior")),
        ("no years and no grade: default years", base, _vac([_req(["python"])])),
        ("a skill asked with 0 years needs any years", base, _vac([_req(["python"], 0), _req(["pytorch"], 0)])),
        ("experience partial", base, _vac([], min_years=4)),
        ("experience zero is skipped", base, _vac([_req(["python"], 2)], min_years=0)),
        ("english below the bar", {**base, "english": "B1"}, _vac([], english="C1")),
        ("english missing in profile", {**base, "english": None}, _vac([], english="B2")),
        ("fits exactly at the threshold", {**base, "skills": {"python": 2}},
         _vac([_req(["python"], 2), _req(["python"], 2), _req(["python"], 2), _req(["python"], 2), _req(["pytorch"], 1)])),
        ("nothing to score", base, _vac([])),
    ]
    return [{"name": n, "profile": p, "vacancy": v} for n, p, v in cases]


def write_golden() -> Path:
    cfg, skills = load_config(), load_skills()
    out = []
    for case in golden_cases():
        result = coverage(case["profile"], case["vacancy"], cfg, skills)
        out.append({**case, "expected": {"coverage": result["coverage"], "fits": result["fits"]}})
    path = ROOT / "fixtures" / "coverage-golden.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def golden_is_current() -> list[str]:
    """Compare the stored golden file with a fresh computation; return differences."""
    path = ROOT / "fixtures" / "coverage-golden.json"
    if not path.exists():
        return ["fixtures/coverage-golden.json is missing; run coverage_reference.py --write-golden"]
    stored = json.loads(path.read_text(encoding="utf-8"))
    cfg, skills = load_config(), load_skills()
    diffs = []
    for case in stored:
        got = coverage(case["profile"], case["vacancy"], cfg, skills)
        exp = case["expected"]
        same_cov = (got["coverage"] is None and exp["coverage"] is None) or (
            got["coverage"] is not None and exp["coverage"] is not None and math.isclose(got["coverage"], exp["coverage"], abs_tol=1e-9)
        )
        if not same_cov or got["fits"] != exp["fits"]:
            diffs.append(f"coverage golden '{case['name']}': stored {exp}, computed {got['coverage']}, {got['fits']}")
    if len(stored) != len(golden_cases()):
        diffs.append("coverage golden: case list changed; run coverage_reference.py --write-golden")
    return diffs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-golden", action="store_true")
    args = ap.parse_args()
    if args.write_golden:
        print(write_golden())
    else:
        for c in golden_cases():
            r = coverage(c["profile"], c["vacancy"], load_config(), load_skills())
            print(f"{c['name']:<45} {r['coverage']!s:<22} fits={r['fits']}")

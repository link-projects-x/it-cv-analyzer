import json
from pathlib import Path

import pytest

from parser import contracts
from parser.assemble import InvalidVacancy, assemble
from parser.extract import ExtractError, extract
from parser.llm import LlmResult
from parser.pipeline import LocalStore, parse_raw
from parser.prompt import output_schema, system_prompt

FIXTURE = Path(__file__).parent / "fixtures" / "vacancy.html"

GOOD_LLM_OUTPUT = {
    "seniority": "middle",
    "role_type": "ai-engineer",
    "requirements": [
        {"any_of": ["python"], "min_level": 3, "required": True, "evidence": "3+ years of commercial Python development"},
        {"any_of": ["llm-api"], "min_level": 3, "required": True, "evidence": "Production experience with LLM-based systems"},
        {"any_of": ["rag"], "min_level": 2, "required": True, "evidence": "Hands-on experience with RAG"},
        {"any_of": ["pgvector", "qdrant", "pgvector"], "min_level": 2, "required": True, "evidence": "pgvector or Qdrant"},
        {"any_of": ["langgraph"], "min_level": 1, "required": False, "evidence": "LangGraph"},
    ],
    "experience": {"min_years": 3, "max_years": None},
    "english": {"min_level": "B2", "evidence": "Upper-Intermediate English"},
    "salary": {"from": 3000, "to": 4500, "currency": "USD", "period": "month"},
    "domains": ["Fintech / Banking / Insurance / Capital markets"],
    "unmapped": [{"text": "Pydantic", "required": False}],
}


class FakeLlm:
    model = "fake"

    def __init__(self, data):
        self.data = data
        self.calls = []

    def extract(self, system, user, schema):
        self.calls.append((system, user, schema))
        return LlmResult(data=self.data, model=self.model, input_tokens=100, output_tokens=50, cache_read_tokens=0)


# --- extract ---------------------------------------------------------------


def test_extract_fields():
    page = extract(FIXTURE.read_text(encoding="utf-8"))
    assert page.title == "Middle AI Engineer"
    assert page.company == "Example Co"
    assert page.cities == ["Київ", "Львів"]
    assert page.remote is True
    assert page.salary_text == "$3000–4500"


def test_extract_keeps_inline_tags_on_one_line():
    text = extract(FIXTURE.read_text(encoding="utf-8")).text
    assert "We build an AI assistant for accountants." in text
    assert "- 3+ years of commercial Python development" in text
    assert "Nice to have\nLangGraph\nPydantic" in text


def test_extract_rejects_page_without_body():
    with pytest.raises(ExtractError):
        extract("<html><h1 class='g-h2'>x</h1></html>")


# --- prompt / schema -------------------------------------------------------


def test_output_schema_lists_every_skill():
    enum = output_schema()["properties"]["requirements"]["items"]["properties"]["any_of"]["items"]["enum"]
    assert set(enum) == contracts.skill_ids()


def test_output_schema_uses_only_supported_keywords():
    """Structured outputs reject numeric/string length limits and oneOf; every object needs additionalProperties=false."""
    banned = {"minimum", "maximum", "minLength", "maxLength", "oneOf", "multipleOf"}

    def walk(node):
        if isinstance(node, dict):
            assert not banned & node.keys(), banned & node.keys()
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(output_schema())


def test_system_prompt_contains_every_skill_id():
    prompt = system_prompt()
    missing = [sid for sid in contracts.skill_ids() if f"- {sid}:" not in prompt]
    assert not missing


# --- assemble --------------------------------------------------------------


def _assemble(data):
    page = extract(FIXTURE.read_text(encoding="utf-8"))
    return assemble("dou-100001", "https://jobs.dou.ua/companies/example-co/vacancies/100001/",
                    "2026-10-31T06:00:00+00:00", page, data, "fake")


def test_assemble_produces_contract_valid_doc():
    doc = _assemble(GOOD_LLM_OUTPUT)
    assert contracts.validation_errors("vacancy", doc) == []
    assert doc["location"] == {"remote": True, "cities": ["Київ", "Львів"]}
    assert doc["requirements"][3]["any_of"] == ["pgvector", "qdrant"]  # deduped


def test_assemble_moves_unknown_skill_ids_to_unmapped():
    data = json.loads(json.dumps(GOOD_LLM_OUTPUT))
    data["requirements"].append({"any_of": ["rust-lang"], "min_level": 2, "required": True, "evidence": "Rust"})
    doc = _assemble(data)
    assert all("rust-lang" not in r["any_of"] for r in doc["requirements"])
    assert {"text": "rust-lang", "required": True} in doc["unmapped"]


def test_assemble_cuts_long_evidence():
    data = json.loads(json.dumps(GOOD_LLM_OUTPUT))
    data["requirements"][0]["evidence"] = "x" * 1000
    assert len(_assemble(data)["requirements"][0]["evidence"]) == 300


def test_assemble_rejects_contract_violation():
    data = json.loads(json.dumps(GOOD_LLM_OUTPUT))
    data["experience"]["min_years"] = -1  # structured outputs cannot enforce minimum; the contract does
    with pytest.raises(InvalidVacancy) as err:
        _assemble(data)
    assert any("experience/min_years" in e for e in err.value.errors)


# --- pipeline --------------------------------------------------------------


def _local_store(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "dou-100001.html").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (raw / "dou-100001.meta.json").write_text(json.dumps({
        "url": "https://jobs.dou.ua/companies/example-co/vacancies/100001/",
        "scraped-at": "2026-10-31T06:00:00+00:00",
    }), encoding="utf-8")
    return LocalStore(tmp_path)


def test_pipeline_writes_processed(tmp_path):
    llm = FakeLlm(GOOD_LLM_OUTPUT)
    outcome = parse_raw("raw/dou-100001.html", _local_store(tmp_path), llm)
    assert outcome.ok
    doc = json.loads((tmp_path / "processed" / "dou-100001.json").read_text(encoding="utf-8"))
    assert doc["id"] == "dou-100001"
    system, user, _ = llm.calls[0]
    assert "Salary line: $3000–4500" in user


def test_pipeline_writes_failed_on_invalid_output(tmp_path):
    bad = dict(GOOD_LLM_OUTPUT, seniority="mid")
    outcome = parse_raw("raw/dou-100001.html", _local_store(tmp_path), FakeLlm(bad))
    assert not outcome.ok
    failed = json.loads((tmp_path / "failed" / "dou-100001.json").read_text(encoding="utf-8"))
    assert failed["error_type"] == "InvalidVacancy"
    assert "seniority" in failed["error"]


def test_pipeline_rejects_non_raw_key(tmp_path):
    with pytest.raises(ValueError):
        parse_raw("processed/dou-1.json", _local_store(tmp_path), FakeLlm(GOOD_LLM_OUTPUT))


# --- relations -------------------------------------------------------------


def _broken(**patch):
    data = json.loads(json.dumps(GOOD_LLM_OUTPUT))
    for path, value in patch.items():
        node, *keys = path.split("__")
        target = data[node]
        for k in keys[:-1]:
            target = target[int(k)] if k.isdigit() else target[k]
        last = keys[-1] if keys else None
        if last is None:
            data[node] = value
        else:
            target[int(last) if last.isdigit() else last] = value
    return data


@pytest.mark.parametrize(
    "patch, relation",
    [
        ({"experience__min_years": 5, "experience__max_years": 2}, "rel.experience_range"),
        ({"salary__from": 4500, "salary__to": 3000}, "rel.salary_range"),
        ({"salary__from": None, "salary__to": None}, "rel.salary_range"),
        ({"requirements__0__evidence": "   "}, "rel.requirement_evidence"),
        ({"english__evidence": None}, "rel.english_evidence"),
    ],
)
def test_assemble_rejects_broken_relation(patch, relation):
    with pytest.raises(InvalidVacancy) as err:
        _assemble(_broken(**patch))
    assert any(e.startswith(relation) for e in err.value.errors), err.value.errors


def test_relations_allow_open_ranges_and_missing_values():
    doc = _assemble(_broken(
        experience__max_years=None,
        salary={"from": None, "to": 4000, "currency": "USD", "period": "month"},
        english={"min_level": None, "evidence": None},
    ))
    assert doc["experience"] == {"min_years": 3, "max_years": None}


def test_relation_failure_lands_in_failed(tmp_path):
    outcome = parse_raw("raw/dou-100001.html", _local_store(tmp_path), FakeLlm(_broken(salary__from=9000)))
    assert not outcome.ok
    failed = json.loads((tmp_path / "failed" / "dou-100001.json").read_text(encoding="utf-8"))
    assert "rel.salary_range" in failed["error"]

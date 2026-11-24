import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cv import contracts, handler
from cv.assemble import InvalidProfile, assemble
from cv.extract import MAX_TEXT_CHARS, ExtractError, extract
from cv.llm import BedrockClaude, LlmError, LlmResult
from cv.pipeline import LocalStore, S3Store, parse_cv
from cv.prompt import SALARY_FEATURES, output_schema, salary_feature_values, system_prompt
from cv.relations import experience_bound

FIXTURE = Path(__file__).parent / "fixtures" / "cv.txt"
CV_ID = "6f1c2b9e-3d4a-4f7b-9a10-2c5e8d7b1a01"
CV_TEXT = FIXTURE.read_text(encoding="utf-8")

# Strings from the synthetic CV that must never reach the logs
PRIVATE = ["Marta Example-Testova", "marta.example@example.com", "+380 00 000 0000", "RAG assistant for accountants"]

GOOD_LLM_OUTPUT = {
    "skills": [
        {"id": "python", "level": 3, "evidence": "4 years of commercial Python development"},
        {"id": "rag", "level": 3, "evidence": "Built a RAG assistant for accountants on Amazon Bedrock and pgvector"},
        {"id": "aws-bedrock", "level": 3, "evidence": "Built a RAG assistant for accountants on Amazon Bedrock"},
        {"id": "pgvector", "level": 3, "evidence": "Amazon Bedrock and pgvector, used by 3,000 customers"},
        {"id": "fastapi", "level": 3, "evidence": "FastAPI services deployed to AWS Lambda with Terraform"},
        {"id": "langgraph", "level": 2, "evidence": "LangGraph agent that triages GitHub issues (side project)"},
        {"id": "pytorch", "level": 1, "evidence": None},
    ],
    "experience_years": 4,
    "english": "B2",
    "seniority": "middle",
    "role_type": "ai-engineer",
    "salary_features": {
        "category": "DS / AI / ML / Data Engineering",
        "title": "Middle",
        "primary_language": "Python",
        "company_type": "Продуктова",
        "company_size": None,
        "domains": ["Fintech / Banking / Insurance / Capital markets", "AI / Data / Analytics",
                    "AI / Data / Analytics"],
        "residence": "В Україні",
    },
    "unmapped": [{"text": "Coursera"}],
}


def _copy(data):
    return json.loads(json.dumps(data))


class FakeLlm:
    model = "fake"

    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.calls = []

    def extract(self, system, user, schema):
        self.calls.append((system, user, schema))
        if self.error:
            raise self.error
        return LlmResult(data=self.data, model=self.model, input_tokens=100, output_tokens=50, cache_read_tokens=0)


def _docx_bytes(paragraphs, table_rows=()):
    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_rows:
        table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf_bytes(lines):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def _scanned_pdf_bytes():
    """A page with a drawn rectangle and no text layer, like a scan."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 400, 600, fill=1)
    c.showPage()
    c.save()
    return buf.getvalue()


# --- extract ---------------------------------------------------------------


def test_extract_txt():
    cv = extract(FIXTURE.read_bytes(), "txt")
    assert cv.format == "txt"
    assert "- Django backend and PostgreSQL for a fintech client" in cv.text
    assert not cv.truncated


def test_extract_txt_falls_back_to_cp1251():
    text = "Досвід: Python, 3 роки комерційної розробки. Англійська: B2. " * 2
    assert "Python, 3 роки" in extract(text.encode("cp1251"), "txt").text


def test_extract_docx_paragraphs_and_tables():
    data = _docx_bytes(
        ["AI Engineer", "Built a RAG assistant for accountants on Amazon Bedrock"],
        table_rows=[("Skills", "Python, FastAPI, pgvector"), ("English", "Upper-Intermediate")],
    )
    text = extract(data, "docx").text
    assert "Built a RAG assistant for accountants on Amazon Bedrock" in text
    assert "Skills | Python, FastAPI, pgvector" in text
    assert "English | Upper-Intermediate" in text


def test_extract_pdf_with_text_layer():
    data = _pdf_bytes(["AI Engineer, 4 years of commercial Python development", "Hands-on LangGraph side project"])
    text = extract(data, "pdf").text
    assert "4 years of commercial Python development" in text
    assert "LangGraph side project" in text


def test_extract_rejects_scanned_pdf():
    with pytest.raises(ExtractError, match="no extractable text.*OCR"):
        extract(_scanned_pdf_bytes(), "pdf")


@pytest.mark.parametrize(
    "data, fmt, message",
    [
        (b"%PDF-1.7 not really a pdf", "pdf", "pdf could not be read"),
        (b"PK not a docx", "docx", "docx could not be read"),
        (b"   \n\n  ", "txt", "no extractable text"),
        (b"hello", "rtf", "unsupported format"),
    ],
)
def test_extract_rejects_unreadable_files(data, fmt, message):
    with pytest.raises(ExtractError, match=message):
        extract(data, fmt)


def test_extract_rejects_empty_docx():
    with pytest.raises(ExtractError, match="no extractable text"):
        extract(_docx_bytes([""]), "docx")


def test_extract_caps_text_length():
    cv = extract(("Python developer. " * 3000).encode(), "txt")
    assert len(cv.text) == MAX_TEXT_CHARS
    assert cv.truncated and cv.chars > MAX_TEXT_CHARS


# --- prompt / schema -------------------------------------------------------


def test_output_schema_lists_every_skill():
    enum = output_schema()["properties"]["skills"]["items"]["properties"]["id"]["enum"]
    assert set(enum) == contracts.skill_ids()


def test_output_schema_salary_features_match_contract():
    contract = contracts.profile_schema()["properties"]["salary_features"]["properties"]
    schema = output_schema()["properties"]["salary_features"]["properties"]
    assert set(schema) == set(contract) == set(SALARY_FEATURES)
    for name in SALARY_FEATURES:
        if name == "domains":
            assert schema[name]["items"]["enum"] == contracts.common_defs()["domain"]["enum"]
        else:
            assert schema[name]["anyOf"][0]["enum"] + [None] == contract[name]["enum"]


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


def test_system_prompt_contains_every_skill_id_and_salary_value():
    prompt = system_prompt()
    assert not [sid for sid in contracts.skill_ids() if f"- {sid}:" not in prompt]
    assert not [v for name in SALARY_FEATURES if name != "domains" for v in salary_feature_values(name) if v not in prompt]


# --- assemble --------------------------------------------------------------

CREATED = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)


def _assemble(data):
    return assemble(CV_ID, data, "fake", created_at=CREATED)


def test_assemble_produces_contract_valid_doc():
    doc = _assemble(GOOD_LLM_OUTPUT)
    assert contracts.validation_errors("profile", doc) == []
    assert doc["id"] == CV_ID
    assert doc["created_at"] == "2026-10-31T09:00:00+00:00"
    assert doc["parse"] == {"model": "fake", "prompt_version": "profile-v1", "parsed_at": "2026-10-31T09:00:00+00:00"}
    assert doc["salary_features"]["domains"] == ["AI / Data / Analytics",
                                                 "Fintech / Banking / Insurance / Capital markets"]  # deduped


def test_assemble_moves_unknown_skill_ids_to_unmapped():
    data = _copy(GOOD_LLM_OUTPUT)
    data["skills"].append({"id": "made-up-tool", "level": 2, "evidence": "Made-up tool"})
    data["unmapped"].append({"text": "coursera "})
    doc = _assemble(data)
    assert all(s["id"] != "made-up-tool" for s in doc["skills"])
    assert doc["unmapped"] == [{"text": "Coursera"}, {"text": "made-up-tool"}]


def test_assemble_cuts_long_evidence_and_nulls_empty_one():
    data = _copy(GOOD_LLM_OUTPUT)
    data["skills"][0]["evidence"] = "x" * 1000
    data["skills"][6]["evidence"] = "  "
    doc = _assemble(data)
    assert len(doc["skills"][0]["evidence"]) == 300
    assert doc["skills"][6]["evidence"] is None


def test_assemble_rejects_contract_violation():
    data = _copy(GOOD_LLM_OUTPUT)
    data["experience_years"] = -1  # structured outputs cannot enforce minimum; the contract does
    with pytest.raises(InvalidProfile) as err:
        _assemble(data)
    assert any("experience_years" in e for e in err.value.errors)
    assert err.value.codes == ["experience_years: minimum"]


# --- relations -------------------------------------------------------------


@pytest.mark.parametrize(
    "patch, relation",
    [
        (lambda d: d["skills"][5].update(evidence=None), "rel.skill_evidence"),  # level 2
        (lambda d: d["skills"][0].update(evidence="   "), "rel.skill_evidence"),  # level 3, whitespace only
        (lambda d: d["skills"].append({"id": "python", "level": 2, "evidence": "Python"}), "rel.unique_skills"),
    ],
)
def test_assemble_rejects_broken_relation(patch, relation):
    data = _copy(GOOD_LLM_OUTPUT)
    patch(data)
    with pytest.raises(InvalidProfile) as err:
        _assemble(data)
    assert any(e.startswith(relation) for e in err.value.errors), err.value.errors


def test_relations_allow_level_1_without_evidence():
    data = _copy(GOOD_LLM_OUTPUT)
    data["skills"][6]["evidence"] = None
    assert _assemble(data)["skills"][6] == {"id": "pytorch", "level": 1, "evidence": None}


def test_experience_bound():
    """profile.schema.json already has maximum: 50, so in assemble the schema error comes first;
    the relation is checked on its own."""
    assert experience_bound({"experience_years": 50}) == []
    assert experience_bound({"experience_years": 51}) == ["experience_years 51 > 50"]
    data = _copy(GOOD_LLM_OUTPUT)
    data["experience_years"] = 51
    with pytest.raises(InvalidProfile) as err:
        _assemble(data)
    assert err.value.codes == ["experience_years: maximum"]


# --- pipeline --------------------------------------------------------------


def _local_store(tmp_path, data=None, ext="txt"):
    (tmp_path / "cv").mkdir()
    (tmp_path / "cv" / f"{CV_ID}.{ext}").write_bytes(data if data is not None else FIXTURE.read_bytes())
    return LocalStore(tmp_path)


def test_pipeline_writes_profile_and_deletes_cv(tmp_path):
    llm = FakeLlm(GOOD_LLM_OUTPUT)
    outcome = parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), llm)
    assert outcome.ok and outcome.key == f"profiles/{CV_ID}.json"
    doc = json.loads((tmp_path / "profiles" / f"{CV_ID}.json").read_text(encoding="utf-8"))
    assert doc["id"] == CV_ID
    assert not (tmp_path / "cv" / f"{CV_ID}.txt").exists()
    _, user, _ = llm.calls[0]
    assert "Example Co (product company), AI Engineer" in user


def test_pipeline_keeps_cv_when_delete_is_off(tmp_path):
    assert parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(GOOD_LLM_OUTPUT), delete_source=False).ok
    assert (tmp_path / "cv" / f"{CV_ID}.txt").exists()


def test_pipeline_parses_docx(tmp_path):
    store = _local_store(tmp_path, _docx_bytes(CV_TEXT.splitlines()), ext="docx")
    assert parse_cv(f"cv/{CV_ID}.docx", store, FakeLlm(GOOD_LLM_OUTPUT)).ok


def _failed(tmp_path):
    return json.loads((tmp_path / "failed-cv" / f"{CV_ID}.json").read_text(encoding="utf-8"))


def test_pipeline_writes_failed_on_invalid_output_and_keeps_cv(tmp_path):
    bad = dict(GOOD_LLM_OUTPUT, seniority="mid")
    outcome = parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(bad))
    assert not outcome.ok and outcome.key == f"failed-cv/{CV_ID}.json"
    failed = _failed(tmp_path)
    assert failed["error_type"] == "InvalidProfile"
    assert "seniority" in failed["error"]
    assert failed["cv_key"] == f"cv/{CV_ID}.txt"
    assert (tmp_path / "cv" / f"{CV_ID}.txt").exists()
    assert not (tmp_path / "profiles").exists()


def test_relation_failure_lands_in_failed(tmp_path):
    data = _copy(GOOD_LLM_OUTPUT)
    data["skills"][5]["evidence"] = None
    assert not parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(data)).ok
    assert "rel.skill_evidence" in _failed(tmp_path)["error"]


def test_scanned_pdf_lands_in_failed_without_llm_call(tmp_path):
    llm = FakeLlm(GOOD_LLM_OUTPUT)
    assert not parse_cv(f"cv/{CV_ID}.pdf", _local_store(tmp_path, _scanned_pdf_bytes(), "pdf"), llm).ok
    assert _failed(tmp_path)["error_type"] == "ExtractError"
    assert llm.calls == []


def test_llm_error_lands_in_failed(tmp_path):
    llm = FakeLlm(error=LlmError("output cut at max_tokens=8000"))
    assert not parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), llm).ok
    assert _failed(tmp_path)["error_type"] == "LlmError"


def test_missing_llm_field_lands_in_failed(tmp_path):
    data = _copy(GOOD_LLM_OUTPUT)
    del data["english"]
    assert not parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(data)).ok
    assert _failed(tmp_path)["error_type"] == "KeyError"


@pytest.mark.parametrize("key", ["profiles/x.json", f"cv/{CV_ID}.rtf", "cv/Marta_Example-Testova.pdf"])
def test_pipeline_rejects_non_cv_key_without_echoing_it(tmp_path, key):
    with pytest.raises(ValueError) as err:
        parse_cv(key, _local_store(tmp_path), FakeLlm(GOOD_LLM_OUTPUT))
    assert key not in str(err.value)


# --- privacy ---------------------------------------------------------------


def _leaks(log_text):
    return [s for s in PRIVATE if s in log_text]


def test_no_cv_text_in_logs_on_success(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    assert parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(GOOD_LLM_OUTPUT)).ok
    assert CV_ID in caplog.text and "tokens in=100" in caplog.text
    assert _leaks(caplog.text) == []


def test_no_cv_text_in_logs_on_schema_failure(tmp_path, caplog):
    """jsonschema messages quote the offending value; here the value is CV text."""
    caplog.set_level(logging.DEBUG)
    data = _copy(GOOD_LLM_OUTPUT)
    data["seniority"] = "Marta Example-Testova"
    data["salary_features"]["title"] = "marta.example@example.com"
    assert not parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(data)).ok
    assert "InvalidProfile" in caplog.text and "seniority: enum" in caplog.text
    assert _leaks(caplog.text) == []
    assert "Marta Example-Testova" in _failed(tmp_path)["error"]  # the reason is kept in failed-cv/, not in logs


def test_no_cv_text_in_logs_on_relation_failure(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    data = _copy(GOOD_LLM_OUTPUT)
    data["skills"].append({"id": "rag", "level": 3, "evidence": "RAG assistant for accountants"})
    assert not parse_cv(f"cv/{CV_ID}.txt", _local_store(tmp_path), FakeLlm(data)).ok
    assert "rel.unique_skills" in caplog.text
    assert _leaks(caplog.text) == []


def test_refusal_message_has_category_only():
    class Response:
        stop_reason = "refusal"
        stop_details = type("D", (), {"category": "general_harms", "explanation": "Marta Example-Testova"})()

    class Client:
        class messages:
            @staticmethod
            def create(**kwargs):
                return Response()

    with pytest.raises(LlmError) as err:
        BedrockClaude(model="fake", region="us-east-1", client=Client()).extract("s", "u", {})
    assert str(err.value) == "model refused: category=general_harms"


# --- handler ---------------------------------------------------------------


class FakeS3:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.put = {}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.put[Key] = json.loads(Body)

    def delete_object(self, Bucket, Key):
        del self.objects[Key]


@pytest.mark.parametrize("delete_env, deleted", [(None, True), ("false", False)])
def test_handler_decodes_key_and_honours_delete_cv(monkeypatch, delete_env, deleted):
    s3 = FakeS3({f"cv/{CV_ID}.txt": FIXTURE.read_bytes()})
    monkeypatch.setenv("BUCKET", "test-bucket")
    if delete_env is None:
        monkeypatch.delenv("DELETE_CV", raising=False)
    else:
        monkeypatch.setenv("DELETE_CV", delete_env)
    monkeypatch.setattr(handler, "S3Store", lambda bucket: S3Store(bucket, s3))
    monkeypatch.setattr(handler, "_llm", FakeLlm(GOOD_LLM_OUTPUT))

    event = {"Records": [{"s3": {"object": {"key": f"cv%2F{CV_ID}.txt"}}}]}
    assert handler.lambda_handler(event, None) == {"ok": 1, "failed": 0}
    assert f"profiles/{CV_ID}.json" in s3.put
    assert (f"cv/{CV_ID}.txt" not in s3.objects) is deleted

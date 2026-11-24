import base64
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api import contracts, handler, http
from api.access import AccessPolicy, hash_code
from api.embed import profile_text
from api.matcher import INDEX_KEY, TOP_K, InvalidMatch, assemble, cosine, match_profile, top_matches
from api.relations import grid_key_experience, relation_errors
from api.salary import FAKE_MODEL_VERSION, FakeSalary, SageMakerSalary, SalaryError, salary_input
from api.store import S3Store

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLES = CONTRACTS / "examples"
JOB_ID = "6f1c2b9e-3d4a-4f7b-9a10-2c5e8d7b1a01"  # the example profile ID, a valid UUID v4
NOW = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
CODE = "test-code-marta-0001"
OTHER_CODE = "test-code-oleh-0002"
ACCESS = AccessPolicy(codes=(("marta", hash_code(CODE)), ("oleh", hash_code(OTHER_CODE))), daily_per_code=3, daily_total=5)


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def copy(doc):
    return json.loads(json.dumps(doc))


PROFILE = load("profile.example.json")
VACANCY = load("vacancy.example.json")
# Evidence strings from the example profile that must never reach the logs
PRIVATE = [s["evidence"] for s in PROFILE["skills"]]


def vacancy(n):
    doc = copy(VACANCY)
    doc["id"] = f"dou-{n}"
    doc["url"] = f"https://jobs.dou.ua/companies/example-co/vacancies/{n}/"
    return doc


class MemoryStore:
    def __init__(self, objects=None):
        self.objects = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in (objects or {}).items()}
        self.presigned = []

    def exists(self, key):
        return key in self.objects

    def get_text(self, key):
        return self.objects.get(key)

    def get_json(self, key):
        text = self.objects.get(key)
        return None if text is None else json.loads(text)

    def put_json(self, key, doc):
        self.objects[key] = json.dumps(doc)

    def count(self, prefix):
        return sum(1 for k in self.objects if k.startswith(prefix))

    def presigned_post(self, key, content_type, max_bytes, expires_in):
        self.presigned.append((key, content_type, max_bytes, expires_in))
        return {"url": "https://bucket.s3.example/", "fields": {"key": key, "Content-Type": content_type}}


class FakeEmbedder:
    """The profile vector is fixed; vacancy vectors come from the index."""

    model_id = "fake-embed-v1"

    def __init__(self, vector=(1.0, 0.0)):
        self.vector = list(vector)
        self.calls = []

    def embed(self, texts, input_type):
        self.calls.append((texts, input_type))
        return [self.vector for _ in texts]


def index_text(entries):
    return "\n".join(json.dumps(e) for e in entries) + "\n"


def entry(n, embedding, model="fake-embed-v1"):
    return {"id": f"dou-{n}", "parsed_at": "2026-10-31T06:05:00Z", "embedding_model": model,
            "text_version": "embed-text-v1", "embedding": embedding, "vacancy": vacancy(n)}


def store_with(profile=PROFILE, entries=None):
    entries = entries if entries is not None else [entry(1, [1.0, 0.0]), entry(2, [0.0, 1.0])]
    return MemoryStore({f"profiles/{profile['id']}.json": profile, INDEX_KEY: index_text(entries)})


def test_format_checkers_are_active():
    """requirements.txt lists the date-time and uri validators instead of jsonschema[format-nongpl]."""
    profile = copy(PROFILE)
    profile["created_at"] = "yesterday"
    assert contracts.validation_codes("profile", profile) == ["created_at: format"]
    doc = {"schema_version": "1.0", "profile": PROFILE, "vacancies": [{"similarity": 0.5, "vacancy": {**vacancy(1), "url": "not a uri"}}],
           "salary": FakeSalary().estimate(salary_input(PROFILE))}
    assert contracts.validation_codes("match-response", doc) == ["vacancies/0/vacancy/url: format"]


# --- cosine / top 50 --------------------------------------------------------------------------------


def test_cosine():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([1, 0], [-2, 0]) == -1.0
    assert abs(cosine([1, 1], [1, 0]) - 0.7071067811865475) < 1e-12
    assert cosine([0, 0], [1, 0]) == 0.0


def test_top_50_ordered_by_cosine_descending():
    import math

    # 60 vectors at angles 0..59 degrees from the query, shuffled; the 50 closest are angles 0..49
    order = [37, 5, 59, 12, 0, 44, 21, 50, 3, 58] + [a for a in range(60) if a not in (37, 5, 59, 12, 0, 44, 21, 50, 3, 58)]
    entries = [entry(1000 + a, [math.cos(math.radians(a)), math.sin(math.radians(a))]) for a in order]
    top = top_matches([1.0, 0.0], entries)
    assert len(top) == TOP_K == 50
    assert [v["vacancy"]["id"] for v in top] == [f"dou-{1000 + a}" for a in range(50)]
    sims = [v["similarity"] for v in top]
    assert sims == sorted(sims, reverse=True)
    assert sims[0] == 1.0 and sims[-1] == round(math.cos(math.radians(49)), 6)


def test_top_matches_breaks_ties_by_id():
    entries = [entry(3, [1.0, 0.0]), entry(1, [2.0, 0.0]), entry(2, [1.0, 0.0])]
    assert [v["vacancy"]["id"] for v in top_matches([1.0, 0.0], entries)] == ["dou-1", "dou-2", "dou-3"]


# --- embedding text ---------------------------------------------------------------------------------


def test_profile_text_uses_the_vacancy_line_format():
    lines = profile_text(PROFILE, contracts.skill_names()).splitlines()
    assert lines[:3] == ["Seniority: middle", "Role: other", "Skills:"]
    assert "- TypeScript, level 3: 4 years of TypeScript in a SaaS backend" in lines
    assert "- Python, level 2: pet project: document classifier in Python" in lines
    assert lines.index("- TypeScript, level 3: 4 years of TypeScript in a SaaS backend") < lines.index(
        "- Python, level 2: pet project: document classifier in Python")  # highest level first


# --- fake salary and rel.grid_matches_point ---------------------------------------------------------


@pytest.mark.parametrize("years", [0, 0.3, 0.75, 1.2, 2.5, 3.5, 4.4, 4.5, 15.4, 15.5, 20, 50])
def test_fake_salary_satisfies_grid_matches_point(years):
    profile = copy(PROFILE)
    profile["experience_years"] = years
    doc = assemble(profile, [], FakeSalary().estimate(salary_input(profile)))
    assert relation_errors(doc) == []
    assert doc["salary"]["grid"]["experience_years"][grid_key_experience(years)] == doc["salary"]["point"]


@pytest.mark.parametrize(
    "patch",
    [
        lambda p: p.update(english=None),
        lambda p: p["salary_features"].update(company_type=None),
        lambda p: p["salary_features"].update(domains=[]),
        lambda p: p["salary_features"].update(domains=["GameDev", "Gambling"]),
        lambda p: p["salary_features"].update(domains=["Security / Cybersecurity"]),
        lambda p: p.update(english="C2"),
    ],
)
def test_fake_salary_valid_for_profile_variants(patch):
    profile = copy(PROFILE)
    patch(profile)
    salary = FakeSalary().estimate(salary_input(profile))
    assert salary["model_version"] == FAKE_MODEL_VERSION
    assert salary["low"] is None and salary["high"] is None
    assert salary["grid"]["english"]["C1"] == salary["grid"]["english"]["C2"]
    assert relation_errors(assemble(profile, [], salary)) == []


def test_fake_salary_is_deterministic():
    assert FakeSalary().estimate(salary_input(PROFILE)) == FakeSalary().estimate(salary_input(PROFILE))


def test_salary_input_has_no_skills_and_snaps_experience():
    profile = copy(PROFILE)
    profile["experience_years"] = 2.5
    data = salary_input(profile)
    assert set(data) == {"id", "experience_years", "english", "salary_features"}
    assert data["experience_years"] == 3.0
    assert not [s for s in PRIVATE if s in json.dumps(data)]


def test_grid_relation_catches_a_wrong_grid():
    salary = FakeSalary().estimate(salary_input(PROFILE))
    salary["grid"]["english"]["B2"] = salary["point"] + 100
    with pytest.raises(InvalidMatch) as err:
        assemble(PROFILE, [], salary)
    assert err.value.codes == [f"rel.grid_matches_point: grid.english['B2'] = {salary['point'] + 100}, point = {salary['point']}"]


# --- matcher ----------------------------------------------------------------------------------------


def test_match_writes_schema_valid_response():
    entries = [entry(n, [1.0, n / 100]) for n in range(1, 61)]
    store = store_with(entries=entries)
    embedder = FakeEmbedder()
    outcome = match_profile(f"profiles/{JOB_ID}.json", store, embedder, FakeSalary())
    assert outcome.ok and outcome.key == f"matches/{JOB_ID}.json" and outcome.vacancies == 50
    doc = store.get_json(f"matches/{JOB_ID}.json")
    assert contracts.validation_errors("match-response", doc) == []
    assert relation_errors(doc) == []
    assert doc["profile"] == PROFILE
    assert [v["vacancy"]["id"] for v in doc["vacancies"]] == [f"dou-{n}" for n in range(1, 51)]
    assert doc["salary"]["model_version"] == FAKE_MODEL_VERSION
    [(texts, input_type)] = embedder.calls
    assert input_type == "search_query" and texts[0].startswith("Seniority: middle")


def test_match_with_fewer_than_50_vacancies():
    store = store_with()
    assert match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), FakeSalary()).vacancies == 2


def failed(store):
    return store.get_json(f"failed-match/{JOB_ID}.json")


def test_missing_index_lands_in_failed_match():
    store = MemoryStore({f"profiles/{JOB_ID}.json": PROFILE})
    assert not match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), FakeSalary()).ok
    assert failed(store)["error_type"] == "IndexUnusable"
    assert f"matches/{JOB_ID}.json" not in store.objects


def test_index_from_another_embedding_model_lands_in_failed_match():
    store = store_with(entries=[entry(1, [1.0, 0.0], model="other-model")])
    assert not match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), FakeSalary()).ok
    assert "other-model" in failed(store)["error"]


class BrokenSalary:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def estimate(self, salary_input):
        if self.error:
            raise self.error
        return self.result


def test_salary_error_lands_in_failed_match():
    store = store_with()
    assert not match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), BrokenSalary(error=SalaryError("endpoint answered ModelError"))).ok
    assert failed(store)["error_type"] == "SalaryError"


def test_broken_relation_lands_in_failed_match():
    salary = FakeSalary().estimate(salary_input(PROFILE))
    salary["point"] += 10
    store = store_with()
    assert not match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), BrokenSalary(salary)).ok
    assert failed(store)["error_type"] == "InvalidMatch"
    assert "rel.grid_matches_point" in failed(store)["error"]


@pytest.mark.parametrize("key", ["cv/x.pdf", "profiles/Marta_Example.json", f"profiles/{JOB_ID}.txt"])
def test_rejects_non_profile_key_without_echoing_it(key):
    with pytest.raises(ValueError) as err:
        match_profile(key, store_with(), FakeEmbedder(), FakeSalary())
    assert key not in str(err.value)


# --- privacy ----------------------------------------------------------------------------------------


def leaks(text):
    return [s for s in PRIVATE if s in text]


def test_no_profile_evidence_in_logs_on_success(caplog):
    caplog.set_level(logging.DEBUG)
    assert match_profile(f"profiles/{JOB_ID}.json", store_with(), FakeEmbedder(), FakeSalary()).ok
    assert JOB_ID in caplog.text and "matched: 2 of 2 vacancies" in caplog.text
    assert leaks(caplog.text) == []
    assert "Seniority:" not in caplog.text  # the embedding text


def test_no_profile_evidence_in_logs_on_schema_failure(caplog):
    """jsonschema messages quote the offending value; here the value is profile evidence."""
    caplog.set_level(logging.DEBUG)
    profile = copy(PROFILE)
    profile["seniority"] = PRIVATE[0]
    profile["skills"][1]["evidence"] = PRIVATE[1] * 20  # over maxLength 300
    store = store_with(profile)
    assert not match_profile(f"profiles/{JOB_ID}.json", store, FakeEmbedder(), FakeSalary()).ok
    assert "InvalidMatch" in caplog.text and "profile/seniority: enum" in caplog.text
    assert leaks(caplog.text) == []
    assert PRIVATE[0] in failed(store)["error"]  # the reason is kept in failed-match/, not in logs


def test_no_profile_evidence_in_logs_on_http_poll(caplog):
    caplog.set_level(logging.DEBUG)
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker(), f"matches/{JOB_ID}.json": {"profile": PROFILE}})
    assert get_job(store)["state"] == "done"
    assert leaks(caplog.text) == []


# --- SageMaker client -------------------------------------------------------------------------------


class FakeRuntime:
    def __init__(self, body=None, error_code=None):
        self.body, self.error_code, self.calls = body, error_code, []

    def invoke_endpoint(self, **kwargs):
        from botocore.exceptions import ClientError

        self.calls.append(kwargs)
        if self.error_code:
            raise ClientError({"Error": {"Code": self.error_code, "Message": PRIVATE[0]}}, "InvokeEndpoint")
        return {"Body": io.BytesIO(self.body)}


def test_sagemaker_salary_sends_salary_fields_only():
    expected = FakeSalary().estimate(salary_input(PROFILE))
    runtime = FakeRuntime(json.dumps(expected).encode())
    assert SageMakerSalary("ep", "us-east-1", client=runtime).estimate(salary_input(PROFILE)) == expected
    [call] = runtime.calls
    assert call["EndpointName"] == "ep" and call["ContentType"] == "application/json"
    sent = json.loads(call["Body"])
    assert set(sent) == {"id", "experience_years", "english", "salary_features"}


@pytest.mark.parametrize("body, message", [(b"<html>", "not JSON"), (b"[1]", "is list")])
def test_sagemaker_salary_rejects_bad_body(body, message):
    with pytest.raises(SalaryError, match=message):
        SageMakerSalary("ep", "us-east-1", client=FakeRuntime(body)).estimate(salary_input(PROFILE))


def test_sagemaker_model_error_becomes_salary_error_without_message():
    with pytest.raises(SalaryError) as err:
        SageMakerSalary("ep", "us-east-1", client=FakeRuntime(error_code="ModelError")).estimate(salary_input(PROFILE))
    assert str(err.value) == "endpoint answered ModelError"


def test_sagemaker_throttling_is_raised_for_retry():
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        SageMakerSalary("ep", "us-east-1", client=FakeRuntime(error_code="ThrottlingException")).estimate(salary_input(PROFILE))


# --- HTTP: POST /uploads ----------------------------------------------------------------------------


def request(method, path, body=None, b64=False, code=CODE):
    raw = None if body is None else (body if isinstance(body, str) else json.dumps(body))
    if raw is not None and b64:
        raw = base64.b64encode(raw.encode()).decode()
    headers = {} if code is None else {"authorization": f"Bearer {code}"}
    return {
        "rawPath": path, "requestContext": {"http": {"method": method}}, "headers": headers,
        "body": raw, "isBase64Encoded": b64,
    }


def call(store, event, now=NOW, access=ACCESS):
    response = http.route(event, store, access, now=lambda: now)
    return response["statusCode"], json.loads(response["body"])


def upload(store, **body):
    payload = {"filename": "Marta Example CV.pdf", "size": 120_000, "content_type": "application/pdf", **body}
    return call(store, request("POST", "/uploads", payload))


def test_upload_returns_presigned_post_and_writes_marker():
    store = MemoryStore()
    status, body = upload(store)
    assert status == 201
    job_id = body["job_id"]
    assert http.JOB_ID_RE.match(job_id)
    assert body["upload"]["fields"]["key"] == f"cv/{job_id}.pdf" and body["expires_in"] == 600
    assert store.presigned == [(f"cv/{job_id}.pdf", "application/pdf", 120_000, 600)]
    assert store.get_json(f"jobs/{job_id}.json") == {
        "id": job_id, "created_at": "2026-10-31T09:00:00+00:00", "format": "pdf", "size": 120_000, "owner": "marta"}
    assert store.exists(f"quota/2026-10-31/marta/{job_id}.json")
    assert "Marta" not in json.dumps(store.objects)  # the file name is not stored


@pytest.mark.parametrize(
    "filename, content_type, ext, stored_type",
    [
        ("cv.PDF", "application/pdf", "pdf", "application/pdf"),
        ("cv.docx", "", "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("cv.docx", "application/octet-stream", "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("my.cv.txt", "text/plain;charset=utf-8", "txt", "text/plain"),
    ],
)
def test_upload_accepts_supported_files(filename, content_type, ext, stored_type):
    store = MemoryStore()
    status, body = upload(store, filename=filename, content_type=content_type)
    assert status == 201
    assert store.presigned[0][:2] == (f"cv/{body['job_id']}.{ext}", stored_type)


@pytest.mark.parametrize(
    "patch, status, code",
    [
        ({"filename": "cv.rtf"}, 400, "unsupported_extension"),
        ({"filename": "cv.doc"}, 400, "unsupported_extension"),
        ({"filename": "cv"}, 400, "invalid_filename"),
        ({"filename": None}, 400, "invalid_filename"),
        ({"size": 5 * 1024 * 1024 + 1}, 413, "file_too_large"),
        ({"size": 0}, 400, "invalid_size"),
        ({"size": "100"}, 400, "invalid_size"),
        ({"size": True}, 400, "invalid_size"),
        ({"size": 1.5}, 400, "invalid_size"),
        ({"content_type": "image/png"}, 400, "content_type_mismatch"),
        ({"content_type": 5}, 400, "invalid_content_type"),
    ],
)
def test_upload_validation(patch, status, code):
    store = MemoryStore()
    got_status, body = upload(store, **patch)
    assert (got_status, body["error"]) == (status, code) and body["message"]
    assert store.objects == {} and store.presigned == []


def test_upload_accepts_exactly_5_mb():
    assert upload(MemoryStore(), size=5 * 1024 * 1024)[0] == 201


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_upload_rejects_bad_json(body):
    assert call(MemoryStore(), request("POST", "/uploads", body))[1]["error"] == "invalid_json"


def test_upload_accepts_base64_body():
    payload = {"filename": "cv.txt", "size": 10, "content_type": "text/plain"}
    assert call(MemoryStore(), request("POST", "/uploads", payload, b64=True))[0] == 201


def test_routes_and_methods():
    store = MemoryStore()
    assert call(store, request("GET", "/uploads"))[0] == 405
    assert call(store, request("POST", f"/jobs/{JOB_ID}"))[0] == 405
    assert call(store, request("GET", "/"))[0] == 404
    assert call(store, request("GET", f"/jobs/{JOB_ID}/x"))[0] == 404


# --- HTTP: GET /jobs/{id} ---------------------------------------------------------------------------


def marker(created=NOW, fmt="pdf", owner="marta"):
    return {"id": JOB_ID, "created_at": created.isoformat(timespec="seconds"), "format": fmt, "size": 100, "owner": owner}


def get_job(store, now=NOW, job_id=JOB_ID):
    status, body = call(store, request("GET", f"/jobs/{job_id}"), now=now)
    assert status == 200, body
    return body


@pytest.mark.parametrize(
    "job_id",
    [
        "not-a-uuid",
        "6F1C2B9E-3D4A-4F7B-9A10-2C5E8D7B1A01",  # upper case
        "6f1c2b9e-3d4a-1f7b-9a10-2c5e8d7b1a01",  # version 1
        "6f1c2b9e-3d4a-4f7b-7a10-2c5e8d7b1a01",  # wrong variant
        "6f1c2b9e3d4a4f7b9a102c5e8d7b1a01",       # no dashes
        "..%2F..%2Findex",
    ],
)
def test_bad_job_id_is_rejected(job_id):
    status, body = call(MemoryStore(), request("GET", f"/jobs/{job_id}"))
    assert (status, body["error"]) == (400, "invalid_job_id")


def test_unknown_job_is_404():
    status, body = call(MemoryStore(), request("GET", f"/jobs/{JOB_ID}"))
    assert (status, body["error"]) == (404, "job_not_found")


def test_job_state_transitions():
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker()})
    assert get_job(store) == {"state": "uploading"}

    store.objects[f"cv/{JOB_ID}.pdf"] = "%PDF"
    assert get_job(store) == {"state": "parsing"}

    # services/cv writes the profile, then deletes the CV
    store.put_json(f"profiles/{JOB_ID}.json", PROFILE)
    assert get_job(store) == {"state": "matching"}
    del store.objects[f"cv/{JOB_ID}.pdf"]
    assert get_job(store) == {"state": "matching"}

    result = load("match-response.example.json")
    store.put_json(f"matches/{JOB_ID}.json", result)
    assert get_job(store) == {"state": "done", "result": result}


def test_uploading_until_15_minutes_then_failed():
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker()})
    assert get_job(store, now=NOW + timedelta(minutes=15)) == {"state": "uploading"}
    assert get_job(store, now=NOW + timedelta(minutes=15, seconds=1)) == {
        "state": "failed", "error": http.UPLOAD_TIMEOUT_MESSAGE}


def test_parsing_does_not_time_out_after_15_minutes():
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker(), f"cv/{JOB_ID}.pdf": "%PDF"})
    assert get_job(store, now=NOW + timedelta(hours=1)) == {"state": "parsing"}


def test_cv_with_another_extension_is_not_this_job():
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker(fmt="docx"), f"cv/{JOB_ID}.pdf": "%PDF"})
    assert get_job(store) == {"state": "uploading"}


@pytest.mark.parametrize(
    "failed_doc, message",
    [
        ({"error_type": "ExtractError", "error": "pdf has no extractable text; a scanned PDF needs OCR, which this step does not do"},
         "pdf has no extractable text; a scanned PDF needs OCR, which this step does not do"),
        ({"error_type": "LlmError", "error": "model refused: category=x"}, "The CV could not be parsed."),
        ({"error_type": "InvalidProfile", "error": f"seniority: '{PRIVATE[0]}' is not one of"}, "The CV could not be turned into a valid profile."),
        ({"error_type": "Surprise", "error": PRIVATE[0]}, "The CV could not be processed."),
    ],
)
def test_failed_cv_gives_short_error(failed_doc, message):
    # the CV stays in cv/ after a failed parse
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker(), f"cv/{JOB_ID}.pdf": "%PDF", f"failed-cv/{JOB_ID}.json": failed_doc})
    assert get_job(store) == {"state": "failed", "error": message}


def test_failed_match_gives_short_error():
    store = MemoryStore({
        f"jobs/{JOB_ID}.json": marker(),
        f"profiles/{JOB_ID}.json": PROFILE,
        f"failed-match/{JOB_ID}.json": {"error_type": "InvalidMatch", "error": PRIVATE[0]},
    })
    assert get_job(store) == {"state": "failed", "error": http.MATCH_FAILED_MESSAGE}


# --- presigned POST signed by real boto3, offline ---------------------------------------------------


def test_presigned_post_policy_is_limited_to_key_type_and_size(monkeypatch):
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3", region_name="eu-central-1", aws_access_key_id="AKIDEXAMPLE", aws_secret_access_key="secret",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    before = datetime.now(timezone.utc)
    post = S3Store("test-bucket", client).presigned_post(f"cv/{JOB_ID}.pdf", "application/pdf", 120_000, 600)
    assert post["url"] == "https://test-bucket.s3.eu-central-1.amazonaws.com/"
    assert post["fields"]["key"] == f"cv/{JOB_ID}.pdf" and post["fields"]["Content-Type"] == "application/pdf"
    policy = json.loads(base64.b64decode(post["fields"]["policy"]))
    conditions = policy["conditions"]
    assert {"bucket": "test-bucket"} in conditions
    assert {"key": f"cv/{JOB_ID}.pdf"} in conditions
    assert {"Content-Type": "application/pdf"} in conditions
    assert ["content-length-range", 1, 120_000] in conditions
    expires = datetime.strptime(policy["expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert timedelta(seconds=590) <= expires - before <= timedelta(seconds=610)


# --- handlers with a fake S3 ------------------------------------------------------------------------


class FakeS3:
    def __init__(self, objects):
        self.objects = {k: (v if isinstance(v, bytes) else (v if isinstance(v, str) else json.dumps(v)).encode())
                        for k, v in objects.items()}

    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))[:MaxKeys]
        return {"Contents": [{"Key": k} for k in keys]} if keys else {}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body


def test_match_handler_decodes_key_and_writes_match(monkeypatch):
    s3 = FakeS3({f"profiles/{JOB_ID}.json": PROFILE, INDEX_KEY: index_text([entry(1, [1.0, 0.0])])})
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("SALARY_ENDPOINT", raising=False)
    monkeypatch.setattr(handler, "S3Store", lambda bucket, region=None: S3Store(bucket, s3))
    monkeypatch.setattr(handler, "_embedder", FakeEmbedder())
    monkeypatch.setattr(handler, "_salary", None)
    event = {"Records": [{"s3": {"object": {"key": f"profiles%2F{JOB_ID}.json"}}}]}
    assert handler.match_handler(event, None) == {"ok": 1, "failed": 0}
    doc = json.loads(s3.objects[f"matches/{JOB_ID}.json"])
    assert doc["salary"]["model_version"] == FAKE_MODEL_VERSION


def test_salary_endpoint_env_selects_sagemaker(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(handler, "_salary", None)
    monkeypatch.setenv("SALARY_ENDPOINT", "dou-cv-analyzer-salary")
    assert isinstance(handler._get_salary(), SageMakerSalary)
    monkeypatch.setattr(handler, "_salary", None)
    monkeypatch.setenv("SALARY_ENDPOINT", "")
    assert isinstance(handler._get_salary(), FakeSalary)


def test_http_handler_reads_state_from_s3(monkeypatch):
    s3 = FakeS3({f"jobs/{JOB_ID}.json": marker(datetime.now(timezone.utc)), f"cv/{JOB_ID}.pdf": b"%PDF"})
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("ACCESS_CODES", f"marta:{hash_code(CODE)}")
    monkeypatch.setattr(handler, "_access", None)
    monkeypatch.setattr(handler, "S3Store", lambda bucket, region=None: S3Store(bucket, s3))
    response = handler.http_handler(request("GET", f"/jobs/{JOB_ID}"), None)
    assert response["statusCode"] == 200 and json.loads(response["body"]) == {"state": "parsing"}
    assert response["headers"]["Cache-Control"] == "no-store"


# --- access codes and quotas ----------------------------------------------------------------------------


@pytest.mark.parametrize("headers", [
    {},
    {"authorization": ""},
    {"authorization": f"Basic {CODE}"},
    {"authorization": "Bearer "},
    {"authorization": "Bearer wrong-code"},
])
def test_requests_without_a_valid_code_are_401(headers):
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker()})
    for event in (request("POST", "/uploads", {"filename": "a.pdf", "size": 10, "content_type": "application/pdf"}),
                  request("GET", f"/jobs/{JOB_ID}")):
        event["headers"] = headers
        status, body = call(store, event)
        assert (status, body["error"]) == (401, "unauthorized")
    assert not any(k.startswith("quota/") for k in store.objects)


def test_bearer_scheme_is_case_insensitive():
    event = request("GET", f"/jobs/{JOB_ID}")
    event["headers"] = {"authorization": f"bearer {CODE}"}
    assert call(MemoryStore({f"jobs/{JOB_ID}.json": marker()}), event)[0] == 200


def test_no_configured_codes_refuses_everything():
    closed = AccessPolicy.from_env({})
    assert closed.codes == ()
    status, body = call(MemoryStore(), request("POST", "/uploads", {"filename": "a.pdf", "size": 10}), access=closed)
    assert status == 401


def test_unknown_route_is_404_before_auth():
    assert call(MemoryStore(), request("GET", "/admin", code=None))[0] == 404


def test_job_of_another_code_is_404():
    store = MemoryStore({f"jobs/{JOB_ID}.json": marker(owner="marta"), f"cv/{JOB_ID}.pdf": "x"})
    assert call(store, request("GET", f"/jobs/{JOB_ID}", code=OTHER_CODE))[0] == 404
    assert call(store, request("GET", f"/jobs/{JOB_ID}", code=CODE))[0] == 200


def test_daily_limit_per_code():
    store = MemoryStore()
    for _ in range(ACCESS.daily_per_code):
        assert upload(store)[0] == 201
    status, body = upload(store)
    assert (status, body["error"]) == (429, "daily_limit")
    # the other code still has its own allowance
    assert call(store, request("POST", "/uploads", {"filename": "a.pdf", "size": 10, "content_type": "application/pdf"},
                               code=OTHER_CODE))[0] == 201


def test_daily_total_limit():
    store = MemoryStore({f"quota/2026-10-31/someone-{i}/x{i}.json": "{}" for i in range(ACCESS.daily_total)})
    status, body = upload(store)
    assert (status, body["error"]) == (429, "daily_limit")
    assert "service" in body["message"]


def test_quota_resets_next_utc_day():
    store = MemoryStore({f"quota/2026-10-31/marta/x{i}.json": "{}" for i in range(ACCESS.daily_per_code)})
    assert upload(store)[0] == 429
    assert call(store, request("POST", "/uploads", {"filename": "a.pdf", "size": 10, "content_type": "application/pdf"}),
                now=NOW + timedelta(days=1))[0] == 201


def test_access_codes_from_env_skip_malformed_entries(caplog):
    good = hash_code("x")
    policy = AccessPolicy.from_env({
        "ACCESS_CODES": f"marta:{good}, Bad Label:{good},oleh:nothex,,ira:{good}",
        "DAILY_UPLOADS_PER_CODE": "7", "DAILY_UPLOADS_TOTAL": "20",
    })
    assert [label for label, _ in policy.codes] == ["marta", "ira"]
    assert (policy.daily_per_code, policy.daily_total) == (7, 20)
    assert good not in caplog.text


def test_access_code_is_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    store = MemoryStore()
    upload(store)
    call(store, request("GET", f"/jobs/{JOB_ID}"))
    call(store, request("GET", f"/jobs/{JOB_ID}", code="wrong-code-123"))
    assert CODE not in caplog.text and "wrong-code-123" not in caplog.text and hash_code(CODE) not in caplog.text

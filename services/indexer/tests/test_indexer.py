import io
import json
from pathlib import Path

import pytest

from indexer import handler
from indexer.contracts import skill_names
from indexer.embed import BATCH, BedrockEmbedder, EmbeddingError, HashEmbedder, vacancy_text
from indexer.index import INDEX_KEY, LocalStore, S3Store, build_index, read_index

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLE = json.loads((CONTRACTS / "examples" / "vacancy.example.json").read_text(encoding="utf-8"))


def vacancy(n: int, parsed_at: str = "2026-10-31T06:05:00Z") -> dict:
    doc = json.loads(json.dumps(EXAMPLE))
    doc["id"] = f"dou-{n}"
    doc["url"] = f"https://jobs.dou.ua/companies/example-co/vacancies/{n}/"
    doc["title"] = f"AI Engineer {n}"
    doc["parse"]["parsed_at"] = parsed_at
    return doc


class FakeEmbedder:
    """Records every text it embeds; the vector encodes the call order so reuse is visible."""

    def __init__(self, model_id="fake-embed-v1"):
        self.model_id = model_id
        self.texts: list[str] = []

    def embed(self, texts, input_type):
        assert input_type == "search_document"
        out = []
        for text in texts:
            self.texts.append(text)
            out.append([float(len(self.texts)), 1.0])
        return out


def write_processed(root: Path, docs):
    (root / "processed").mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (root / "processed" / f"{doc['id']}.json").write_text(json.dumps(doc), encoding="utf-8")


def index_lines(root: Path) -> dict[str, dict]:
    return read_index(LocalStore(root))


# --- text ------------------------------------------------------------------------------------------


def test_vacancy_text_has_title_skill_names_levels_and_evidence():
    text = vacancy_text(EXAMPLE, skill_names())
    lines = text.splitlines()
    assert lines[:4] == ["Title: Middle AI Engineer", "Seniority: middle", "Role: ai-engineer", "Skills:"]
    assert "- Python, level 3, required: 3+ years of commercial Python development" in lines
    assert "- pgvector or Qdrant or Pinecone, level 2, required: experience with a vector store (pgvector, Qdrant or Pinecone)" in lines
    assert "- LangGraph, level 1, optional: LangGraph would be a plus" in lines
    # company, salary and location do not describe the work and stay out of the embedding
    assert "Example Co" not in text and "Kyiv" not in text


# --- incremental index -----------------------------------------------------------------------------


def test_first_run_embeds_every_vacancy(tmp_path):
    write_processed(tmp_path, [vacancy(1), vacancy(2), vacancy(3)])
    embedder = FakeEmbedder()
    result = build_index(LocalStore(tmp_path), embedder)
    assert result.total == 3 and sorted(result.embedded) == ["dou-1", "dou-2", "dou-3"] and result.reused == 0
    lines = index_lines(tmp_path)
    assert set(lines) == {"dou-1", "dou-2", "dou-3"}
    entry = lines["dou-2"]
    assert entry["vacancy"]["id"] == "dou-2" and entry["embedding_model"] == "fake-embed-v1"
    assert entry["parsed_at"] == "2026-10-31T06:05:00Z" and len(entry["embedding"]) == 2


def test_second_run_reembeds_only_changed_and_new_vacancies(tmp_path):
    write_processed(tmp_path, [vacancy(1), vacancy(2), vacancy(3)])
    build_index(LocalStore(tmp_path), FakeEmbedder())
    before = index_lines(tmp_path)

    # dou-2 re-parsed, dou-4 new, dou-3 gone from processed/
    (tmp_path / "processed" / "dou-3.json").unlink()
    write_processed(tmp_path, [vacancy(2, parsed_at="2026-11-01T06:05:00Z"), vacancy(4)])
    embedder = FakeEmbedder()
    result = build_index(LocalStore(tmp_path), embedder)

    assert sorted(result.embedded) == ["dou-2", "dou-4"]
    assert result.reused == 1 and result.removed == 1 and result.total == 3
    assert [t.splitlines()[0] for t in embedder.texts] == ["Title: AI Engineer 2", "Title: AI Engineer 4"]
    after = index_lines(tmp_path)
    assert after["dou-1"]["embedding"] == before["dou-1"]["embedding"]
    assert after["dou-2"]["parsed_at"] == "2026-11-01T06:05:00Z"
    assert "dou-3" not in after


def test_unchanged_index_makes_no_embedding_call(tmp_path):
    write_processed(tmp_path, [vacancy(1), vacancy(2)])
    build_index(LocalStore(tmp_path), FakeEmbedder())
    embedder = FakeEmbedder()
    result = build_index(LocalStore(tmp_path), embedder)
    assert embedder.texts == [] and result.reused == 2


def test_model_change_reembeds_everything(tmp_path):
    write_processed(tmp_path, [vacancy(1), vacancy(2)])
    build_index(LocalStore(tmp_path), FakeEmbedder("model-a"))
    result = build_index(LocalStore(tmp_path), FakeEmbedder("model-b"))
    assert sorted(result.embedded) == ["dou-1", "dou-2"]
    assert {e["embedding_model"] for e in index_lines(tmp_path).values()} == {"model-b"}


def test_invalid_vacancy_is_skipped_and_logged_by_id(tmp_path, caplog):
    bad = vacancy(2)
    bad["seniority"] = "mid"
    bad["requirements"][0]["evidence"] = "PRIVATE-EVIDENCE-TEXT"
    write_processed(tmp_path, [vacancy(1), bad])
    result = build_index(LocalStore(tmp_path), FakeEmbedder())
    assert result.invalid == ["dou-2"] and set(index_lines(tmp_path)) == {"dou-1"}
    assert "processed/dou-2.json skipped" in caplog.text and "seniority: enum" in caplog.text
    assert "'mid'" not in caplog.text


def test_empty_processed_writes_empty_index(tmp_path):
    result = build_index(LocalStore(tmp_path), FakeEmbedder())
    assert result.total == 0 and (tmp_path / INDEX_KEY).read_text() == ""


def test_hash_embedder_is_deterministic_and_normalised():
    a, b, c = HashEmbedder(64).embed(["python rag", "python rag", "react css"], "search_document")
    assert a == b and a != c
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9


# --- Bedrock client ---------------------------------------------------------------------------------


class FakeBedrock:
    def __init__(self, shape="list"):
        self.calls = []
        self.shape = shape

    def invoke_model(self, modelId, body, contentType, accept):
        req = json.loads(body)
        self.calls.append((modelId, req))
        vectors = [[float(i), 0.5] for i, _ in enumerate(req["texts"])]
        embeddings = vectors if self.shape == "list" else {"float": vectors}
        return {"body": io.BytesIO(json.dumps({"embeddings": embeddings, "response_type": "x"}).encode())}


@pytest.mark.parametrize("shape", ["list", "by_type"])
def test_bedrock_embedder_request_and_both_response_shapes(shape):
    client = FakeBedrock(shape)
    vectors = BedrockEmbedder("cohere.embed-v4:0", "us-east-1", 512, client=client).embed(["a", "b"], "search_document")
    assert vectors == [[0.0, 0.5], [1.0, 0.5]]
    model, req = client.calls[0]
    assert model == "cohere.embed-v4:0"
    assert req == {"texts": ["a", "b"], "input_type": "search_document", "embedding_types": ["float"],
                   "output_dimension": 512, "truncate": "RIGHT"}


def test_bedrock_embedder_batches_by_96():
    client = FakeBedrock()
    texts = [f"t{i}" for i in range(BATCH * 2 + 5)]
    assert len(BedrockEmbedder("m", "us-east-1", client=client).embed(texts, "search_document")) == len(texts)
    assert [len(req["texts"]) for _, req in client.calls] == [96, 96, 5]


def test_bedrock_embedder_rejects_count_mismatch():
    class Short(FakeBedrock):
        def invoke_model(self, **kw):
            return {"body": io.BytesIO(b'{"embeddings": [[1.0]]}')}

    with pytest.raises(EmbeddingError, match="asked for 2 embeddings, got 1"):
        BedrockEmbedder("m", "us-east-1", client=Short()).embed(["a", "b"], "search_document")


# --- handler with a fake S3 -------------------------------------------------------------------------


class FakeS3:
    def __init__(self, objects):
        self.objects = dict(objects)

    def get_paginator(self, name):
        s3 = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k} for k in sorted(s3.objects) if k.startswith(Prefix)]}

        return Paginator()

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body


def test_handler_builds_index_in_s3(monkeypatch):
    s3 = FakeS3({f"processed/dou-{n}.json": json.dumps(vacancy(n)).encode() for n in (1, 2)})
    s3.objects["processed/readme.txt"] = b"not a vacancy"
    monkeypatch.setenv("BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(handler, "S3Store", lambda bucket: S3Store(bucket, s3))
    monkeypatch.setattr(handler, "BedrockEmbedder", lambda **kw: FakeEmbedder(kw["model_id"]))
    assert handler.lambda_handler({}, None) == {"total": 2, "embedded": 2, "reused": 0, "invalid": 0, "removed": 0}
    lines = [json.loads(line) for line in s3.objects[INDEX_KEY].decode().splitlines()]
    assert [e["id"] for e in lines] == ["dou-1", "dou-2"]
    assert lines[0]["embedding_model"] == "cohere.embed-v4:0"
    # second run against the stored index
    assert handler.lambda_handler({}, None)["reused"] == 2


def test_s3_store_missing_key_is_none():
    assert S3Store("b", FakeS3({})).get_text(INDEX_KEY) is None

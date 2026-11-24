"""Embedding text for a profile and the Bedrock embedding call.

A copy of services/indexer/indexer/embed.py with profile_text in place of vacancy_text; services do not import each
other. Both texts use skill_line, so a vacancy requirement and a profile skill read the same way
("- Python, level 3: <evidence>"). Change both files together and bump TEXT_VERSION in both.

The profile text holds CV evidence: it is sent to Bedrock and never logged.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Protocol

TEXT_VERSION = "embed-text-v1"
BATCH = 96  # Cohere Embed v4 on Bedrock: max 96 texts per call


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    model_id: str

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]: ...


def skill_line(names: list[str], level: int, evidence: str | None, required: bool | None = None) -> str:
    """One skill line, shared format with services/indexer/indexer/embed.py."""
    tag = "" if required is None else (", required" if required else ", optional")
    line = f"- {' or '.join(names)}, level {level}{tag}"
    return f"{line}: {evidence.strip()}" if evidence and evidence.strip() else line


def profile_text(profile: dict, skill_names: dict[str, str]) -> str:
    """Seniority, role type and every skill with its name, level and evidence (highest level first)."""
    lines = [f"Seniority: {profile['seniority']}", f"Role: {profile['role_type']}", "Skills:"]
    for skill in sorted(profile["skills"], key=lambda s: (-s["level"], s["id"])):
        if skill["level"] > 0:
            lines.append(skill_line([skill_names.get(skill["id"], skill["id"])], skill["level"], skill["evidence"]))
    return "\n".join(lines)


class BedrockEmbedder:
    def __init__(self, model_id: str, region: str, dimension: int = 1024, client=None):
        if client is None:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=region)
        self._client = client
        self.model_id = model_id
        self.dimension = dimension

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            batch = texts[start : start + BATCH]
            body = {
                "texts": batch,
                "input_type": input_type,
                "embedding_types": ["float"],
                "output_dimension": self.dimension,
                "truncate": "RIGHT",
            }
            response = self._client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            got = _float_vectors(json.loads(response["body"].read()))
            if len(got) != len(batch):
                raise EmbeddingError(f"asked for {len(batch)} embeddings, got {len(got)}")
            vectors.extend(got)
        return vectors


def _float_vectors(data: dict) -> list[list[float]]:
    """Cohere returns `embeddings` as a list for one embedding type and as {"float": [...]} for several."""
    embeddings = data.get("embeddings")
    if isinstance(embeddings, dict):
        embeddings = embeddings.get("float")
    if not isinstance(embeddings, list):
        raise EmbeddingError(f"no float embeddings in response, response_type={data.get('response_type')}")
    return embeddings


class HashEmbedder:
    """Deterministic bag-of-words vectors for local runs without Bedrock. Same tokens -> same vector, so texts with
    shared skill names score higher. Not a semantic model."""

    model_id = "local-hash-v1"

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dimension
            for token in re.findall(r"[a-z0-9+#.]+", text.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                vec[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

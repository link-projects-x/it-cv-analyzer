"""Salary block of the match response: SageMaker endpoint (ml/salary/inference.py) or a deterministic fake.

The matcher sends the endpoint only the fields the salary model reads (id, experience_years, english,
salary_features), never skills or evidence. experience_years is first moved to the grid key the experience slider
opens at (nearest whole year, half up, clamped to 0..15; contracts/README.md -> Salary grid). Reason, measured on
2026-10-31 with the model trained by ml/salary/train.py: the gradient boosting model bins experience between the
survey's values, so the estimate at 2.5 years equals the one at 2 years while the grid key is "3"; 0.75, 2.5, 3.5
and 4.5 years broke rel.grid_matches_point. At the grid key the point and the grid row come from the same input row.
"""

from __future__ import annotations

import json
from typing import Protocol

from . import contracts
from .relations import grid_key_experience

FAKE_MODEL_VERSION = "fake-disabled"
CEFR_LEVEL = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 5}  # C1 and C2 are one survey level


class SalaryError(RuntimeError):
    """The endpoint answered, but not with a usable salary block. Logged by message; messages carry no profile data."""


class Salary(Protocol):
    def estimate(self, salary_input: dict) -> dict: ...


def salary_input(profile: dict) -> dict:
    return {
        "id": profile["id"],
        "experience_years": float(grid_key_experience(profile["experience_years"])),
        "english": profile["english"],
        "salary_features": profile["salary_features"],
    }


class SageMakerSalary:
    def __init__(self, endpoint_name: str, region: str, client=None):
        if client is None:
            import boto3
            from botocore.config import Config

            # Serverless endpoints start a container on the first call after idle; assumption: 70 s covers it.
            client = boto3.client(
                "sagemaker-runtime", region_name=region, config=Config(read_timeout=70, retries={"max_attempts": 2})
            )
        self._client = client
        self.endpoint_name = endpoint_name

    def estimate(self, salary_input: dict) -> dict:
        from botocore.exceptions import ClientError

        try:
            response = self._client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(salary_input, ensure_ascii=False).encode("utf-8"),
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("ModelError", "ValidationError"):
                # The container's message can quote the request; only the code goes on.
                raise SalaryError(f"endpoint answered {code}") from exc
            raise  # throttling, network, missing endpoint: the async invocation is retried by Lambda
        try:
            data = json.loads(response["Body"].read())
        except ValueError as exc:
            raise SalaryError("endpoint response is not JSON") from exc
        if not isinstance(data, dict):
            raise SalaryError(f"endpoint response is {type(data).__name__}, expected an object")
        return data


class FakeSalary:
    """Deterministic salary block for var.enable_salary_endpoint = false. Not a model: numbers come from a fixed
    formula so the chain works end to end without SageMaker. model_version is "fake-disabled"."""

    def __init__(self):
        self._company_types = [
            v
            for v in contracts.profile_schema()["properties"]["salary_features"]["properties"]["company_type"]["enum"]
            if v is not None
        ]
        self._domains = contracts.common_defs()["domain"]["enum"]

    def _value(self, years: float, english: str | None, company_type: str | None, domains: list[str]) -> float:
        value = 800 + 220 * years + 180 * CEFR_LEVEL[english or "B2"]
        if company_type is not None:
            value -= 60 * self._company_types.index(company_type)
        if domains:
            value += sum(40 * (self._domains.index(d) % 5) for d in domains) / len(domains)
        return float(round(value))

    def estimate(self, salary_input: dict) -> dict:
        years = salary_input["experience_years"]
        english = salary_input["english"]
        sf = salary_input["salary_features"]
        company_type, domains = sf["company_type"], list(sf["domains"])
        return {
            "currency": "USD",
            "period": "month",
            "point": self._value(years, english, company_type, domains),
            "low": None,
            "high": None,
            "model_version": FAKE_MODEL_VERSION,
            "grid": {
                "english": {c: self._value(years, c, company_type, domains) for c in CEFR_LEVEL},
                "experience_years": {str(y): self._value(y, english, company_type, domains) for y in range(16)},
                "company_type": {t: self._value(years, english, t, domains) for t in self._company_types},
                "domains": {d: self._value(years, english, company_type, [d]) for d in self._domains},
            },
        }

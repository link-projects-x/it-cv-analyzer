"""Generate an access code for the HTTP API.

  python scripts/new_access_code.py alice

Prints the code (give it to that person; it is shown once and stored nowhere) and the line to add to
infra/terraform.tfvars under access_code_hashes. Only the SHA-256 hash goes to AWS.
To revoke a code, delete its line from access_code_hashes and apply.
"""

import hashlib
import re
import secrets
import sys

LABEL_RE = re.compile(r"^[a-z0-9-]{1,32}$")  # same rule as services/api/api/access.py and infra/variables.tf


def main() -> None:
    if len(sys.argv) != 2 or not LABEL_RE.match(sys.argv[1]):
        sys.exit("usage: new_access_code.py <label>   (label: lowercase letters, digits, '-', up to 32 chars)")
    label = sys.argv[1]
    code = secrets.token_urlsafe(24)
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    print(f"access code for {label} (share privately, shown once):\n  {code}\n")
    print("add to infra/terraform.tfvars:")
    print(f'  access_code_hashes = {{\n    "{label}" = "{digest}"\n  }}')


if __name__ == "__main__":
    main()

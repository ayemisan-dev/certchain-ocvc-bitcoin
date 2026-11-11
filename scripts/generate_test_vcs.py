"""Generate a list of randomized full VCs for testing batch issuance.

Usage:
    python -m scripts.generate_test_vcs \
        --input /base_full_vc.json \
        --output /tmp/full_vc_list_10.json \
        --count 10
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

GRADE_POINTS = {
    "A": 4.00,
    "B+": 3.50,
    "B": 3.00,
    "C+": 2.50,
    "C": 2.00,
    "D+": 1.50,
    "D": 1.00,
    "F": 0.00,
}

STUDENT_NAMES = [
    "Aubriella Diaz", "Nathan Wilson", "Luna Dunlap", "Aries Page",
    "Cataleya Terry", "Armani Rhodes", "Tatum Johns", "Joziah Lu",
    "Emani Ray", "Arlo Yu", "Navy Underwood", "Reece Archer",
    "John Smith", "Annie Ruiz", "Austin Boyer", "Chaya Grant",
    "Leon Owens", "Amaya Bradley", "Richard Gonzalez",
]


def randomize_credential(base_vc: dict, credential_index: int, cred_count: int) -> dict:
    """Return a deep copy of ``base_vc`` with a random name and random grades."""
    cred = copy.deepcopy(base_vc)
    cred["id"] = f"cred/{credential_index}"

    transcript = cred["credentialSubject"]["transcriptRecord"]
    total_credits = 0
    total_points = 0

    for semester in transcript:
        semester_points = 0
        semester_credits = 0
        for course in semester["enrollmentRecord"]:
            credit = course["credit"]
            grade = random.choice(list(GRADE_POINTS))
            course["grade"] = grade
            semester_points += GRADE_POINTS[grade] * credit
            semester_credits += credit

        semester["GPA"] = round(semester_points / semester_credits, 2)
        total_credits += semester_credits
        total_points += semester_points
        semester["GPS"] = round(total_points / total_credits, 2)

    cred["credentialSubject"]["achievement"]["GPA"] = transcript[-1]["GPS"]

    first, last = random.choice(STUDENT_NAMES).split()
    cred["credentialSubject"]["givenName"] = first
    cred["credentialSubject"]["familyName"] = last

    # Assign a per-credential revocation index.
    cred["credentialStatus"]["revocationListIndex"] = [credential_index, cred_count + 1]
    return cred


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate randomized test VCs")
    parser.add_argument("--input", required=True, help="Path to a base full VC JSON")
    parser.add_argument("--output", required=True, help="Path to write the generated list")
    parser.add_argument("--count", type=int, default=10, help="Number of credentials to generate")
    args = parser.parse_args()

    base_vc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    vc_list = [randomize_credential(base_vc, i, args.count) for i in range(1, args.count + 1)]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(vc_list, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {len(vc_list)} credentials to {output_path}")


if __name__ == "__main__":
    main()
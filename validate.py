#!/usr/bin/env python3
"""Validate edition files against schema/edition.schema.json and the publish rules.

  python3 validate.py                       # every data/*.json; drafts checked as drafts, others must be publishable
  python3 validate.py data/2026-09-30.json  # specific files (same auto mode)
  python3 validate.py --strict [files]      # every file must be publishable (used before deploy)

Exit code 1 on any problem.
"""
import sys

from econ.render import ROOT
from econ.validate import validate_files


def main(argv):
    strict = "--strict" in argv
    files = [a for a in argv if not a.startswith("--")] or sorted(str(p) for p in (ROOT / "data").glob("*.json"))
    ok, lines = validate_files(files, mode="publish" if strict else "auto")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

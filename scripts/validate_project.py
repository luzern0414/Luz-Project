#!/usr/bin/env python3
"""Validate a Luz project and print machine-readable diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from project_core import validate_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 Luz 项目目录、开发矩阵、审批和 HTML 产物")
    parser.add_argument("project")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    errors = validate_project(Path(args.project), args.strict)
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())


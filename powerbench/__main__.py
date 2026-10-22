"""Portable CLI: python -m powerbench analyze request.json [--output result.json]."""
import argparse
import json
from pathlib import Path

from .api import analyze
from .capabilities import capabilities


def main() -> None:
    parser = argparse.ArgumentParser(description="PowerBench portable scientific interface")
    parser.add_argument("operation", choices=["analyze", "capabilities"])
    parser.add_argument("request", nargs="?")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.operation == "analyze" and not args.request:
        parser.error("analyze requires a request JSON file")
    result = capabilities() if args.operation == "capabilities" else analyze(json.loads(Path(args.request).read_text(encoding="utf-8")))
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

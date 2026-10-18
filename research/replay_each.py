"""Replay every project of a manifest in its own process and output directory.

One process per project keeps peak memory at one project's worth, and a crash
or a timeout in one repository leaves the others' results intact. Projects
that already have a runs.csv are skipped, so the script can be re-run to
resume. Merge the parts afterwards with merge_results.py.

    python research/replay_each.py --corpus research/corpus-v2.json --out results/corpus-v2
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--only", help="Comma-separated project names.")
    p.add_argument("--timeout", type=int, default=7200, help="Seconds per project (default 2 h).")
    args = p.parse_args(argv)

    manifest = json.load(open(args.corpus, encoding="utf-8"))
    wanted = set(args.only.split(",")) if args.only else None
    for project in manifest["projects"]:
        name = project["name"]
        if wanted and name not in wanted:
            continue
        out = os.path.join(args.out, name)
        if os.path.exists(os.path.join(out, "runs.csv")):
            print(f"{name}: already replayed", flush=True)
            continue
        os.makedirs(out, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump({"projects": [project]}, handle)
            single = handle.name
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(HERE, "replay.py"), "--corpus", single, "--out", out, "--quiet"],
                capture_output=True, text=True, timeout=args.timeout,
            )
            status = "ok" if result.returncode == 0 else f"exit {result.returncode}: {result.stderr.strip()[-300:]}"
        except subprocess.TimeoutExpired:
            status = f"timed out after {args.timeout}s"
        finally:
            os.unlink(single)
        with open(os.path.join(out, "status.txt"), "w", encoding="utf-8") as handle:
            handle.write(status + "\n")
        print(f"{name}: {status}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

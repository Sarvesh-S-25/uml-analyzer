"""Per-project corpus facts for Table II: language, window, size, score at both ends.

    python research/corpus_table.py --manifest research/corpus-v2.json --results results/corpus-v2 \
        --out results/v2/corpus_table.json

Reads each replayed project's runs.csv and the cached clone, so it needs the
clones under .corpus-cache (replay_each.py leaves them there).
"""
import argparse
import collections
import csv
import json
import os
import subprocess
from datetime import date

EXT = {".py": "Python", ".java": "Java", ".js": "JavaScript", ".jsx": "JavaScript",
       ".ts": "TypeScript", ".tsx": "TypeScript", ".cs": "C#", ".php": "PHP"}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default="research/corpus-v2.json")
    p.add_argument("--results", default="results/corpus-v2")
    p.add_argument("--cache", default=".corpus-cache")
    p.add_argument("--out", default="results/v2/corpus_table.json")
    args = p.parse_args(argv)

    rows = []
    for project in json.load(open(args.manifest, encoding="utf-8"))["projects"]:
        runs = os.path.join(args.results, project["name"], "runs.csv")
        if not os.path.exists(runs):
            continue
        oracle = [r for r in csv.DictReader(open(runs, encoding="utf-8")) if r["gate_strategy"] == "always"]
        clone = os.path.join(args.cache, project["source"].rstrip("/").split("/")[-1].removesuffix(".git"))
        spec = [project["subdirectory"]] if project.get("subdirectory") else []
        files = git(clone, "ls-tree", "-r", "--name-only", project["start"], *spec).split("\n")
        langs = collections.Counter(EXT[os.path.splitext(f)[1]] for f in files if os.path.splitext(f)[1] in EXT)
        start = git(clone, "log", "-1", "--format=%cs", project["start"]).strip()
        end = git(clone, "log", "-1", "--format=%cs", oracle[-1]["commit"]).strip()
        rows.append({
            "name": project["name"],
            "repository": project["source"],
            "lang": langs.most_common(1)[0][0] if langs else "?",
            "freeze": start,
            "commits": len(oracle),
            "days": (date.fromisoformat(end) - date.fromisoformat(start)).days if start and end else None,
            "files": int(oracle[0]["files"]),
            "changed": sum(r["conformance_changed"] == "True" for r in oracle),
            "score_start": oracle[0]["similarity_score"],
            "score_end": oracle[-1]["similarity_score"],
        })
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(rows, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"{len(rows)} projects -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

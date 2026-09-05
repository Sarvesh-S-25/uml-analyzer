"""Find projects whose UML diagram stopped being maintained while the code moved on.

This is the corpus problem solved from the other side. Reverse-engineering a
diagram from current code gives 100% conformance and measures nothing. But a
diagram that someone drew once and then abandoned is *already* the intended
design, and the code has already drifted away from it. The violations are real,
nobody planted them, and the drift window is measurable.

That this happens is established, not assumed. Romeo et al. (IEEE, 2025) deep-
cloned 13,152 GitHub repositories and found that fewer than one third of the
projects containing UML saw any activity in their UML files during 2022. The
diagram is drawn, and then it is left behind. This script measures how far
behind, for a specific repository.

    # one repository you have already cloned
    python research/find_stale_diagrams.py --repo ../some-project

    # several, and write a CSV
    python research/find_stale_diagrams.py --repo ../a --repo ../b --out results/

    # clone and scan in one step
    python research/find_stale_diagrams.py --clone https://github.com/owner/name.git

What it reports per diagram file:

    last_changed        when the diagram was last edited
    head_date           when the code was last edited
    stale_days          the gap, in days
    stale_commits       code commits that landed after the diagram stopped moving
    code_files_changed  distinct source files touched in that window

A diagram with a large `stale_commits` is a corpus candidate: the design is
genuine, the drift is genuine, and the size of the window is a number you can
put in the paper.
"""
import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Extensions that carry a design model. `.mdj` is StarUML's own format, which is
# what the analyser reads; the others are listed so the scan reports what a
# repository actually holds rather than silently ignoring it.
DIAGRAM_EXTENSIONS = {
    ".mdj": "StarUML",
    ".uml": "UML (Eclipse/Papyrus)",
    ".xmi": "XMI interchange",
    ".ecore": "Ecore",
    ".puml": "PlantUML",
    ".plantuml": "PlantUML",
    ".ucls": "ObjectAid class diagram",
    ".asta": "Astah",
}

# Files whose churn counts as "the code moved". Everything else -- docs, CI
# config, lockfiles -- would inflate the staleness window without meaning it.
CODE_EXTENSIONS = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".kt", ".scala",
    ".cs", ".cpp", ".cc", ".h", ".hpp", ".go", ".rb", ".php", ".swift",
}


def git(repo: str, *args: str) -> str:
    """Run git in `repo` and return stdout, or an empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=180, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_diagrams(repo: str) -> List[str]:
    """Every design-model file tracked by git, ignoring vendored trees."""
    listing = git(repo, "ls-files")
    if not listing:
        return []

    found = []
    for path in listing.splitlines():
        lowered = path.lower()
        if any(part in lowered for part in ("node_modules/", "/vendor/", "/venv/", "site-packages/")):
            continue
        if os.path.splitext(lowered)[1] in DIAGRAM_EXTENSIONS:
            found.append(path)
    return found


def scan(repo: str) -> Dict[str, Any]:
    """Measure how far each diagram in one repository has fallen behind."""
    name = os.path.basename(os.path.abspath(repo.rstrip("/\\")))

    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"project": name, "path": repo, "error": "not a git repository", "diagrams": []}

    head_sha = git(repo, "rev-parse", "--short", "HEAD")
    head_iso = git(repo, "log", "-1", "--format=%cI")
    head_date = parse_iso(head_iso)
    total_commits = git(repo, "rev-list", "--count", "HEAD") or "0"

    diagrams = []
    for path in find_diagrams(repo):
        last_iso = git(repo, "log", "-1", "--format=%cI", "--", path)
        last_sha = git(repo, "log", "-1", "--format=%h", "--", path)
        last_date = parse_iso(last_iso)
        if last_date is None or head_date is None:
            continue

        since = f"{last_sha}..HEAD" if last_sha else "HEAD"

        # Commits that landed after the diagram stopped moving, counting only
        # those that touched source. A hundred documentation commits do not mean
        # the architecture drifted.
        changed = git(repo, "log", "--name-only", "--format=", since)
        code_files = {
            line for line in changed.splitlines()
            if line and os.path.splitext(line.lower())[1] in CODE_EXTENSIONS
        }
        stale_commits = int(git(repo, "rev-list", "--count", since) or 0)

        diagrams.append({
            "project": name,
            "diagram": path,
            "kind": DIAGRAM_EXTENSIONS[os.path.splitext(path.lower())[1]],
            "size_bytes": _size(repo, path),
            "last_changed": last_date.date().isoformat(),
            "last_commit": last_sha,
            "head_date": head_date.date().isoformat(),
            "head_commit": head_sha,
            "stale_days": (head_date - last_date).days,
            "stale_commits": stale_commits,
            "code_files_changed_since": len(code_files),
            "total_commits": int(total_commits),
        })

    diagrams.sort(key=lambda d: -d["stale_commits"])
    return {"project": name, "path": repo, "head": head_sha, "diagrams": diagrams}


def _size(repo: str, path: str) -> int:
    full = os.path.join(repo, path)
    try:
        return os.path.getsize(full)
    except OSError:
        return 0


def clone(url: str, cache: str) -> Optional[str]:
    os.makedirs(cache, exist_ok=True)
    name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    target = os.path.join(cache, name)
    if os.path.isdir(os.path.join(target, ".git")):
        print(f"  {name}: already cloned")
        return target

    print(f"  {name}: cloning…", flush=True)
    result = subprocess.run(
        ["git", "clone", "--quiet", url, target],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"  {name}: clone failed — {result.stderr.strip()[:120]}", file=sys.stderr)
        return None
    return target


# A diagram this far behind is worth analysing: the design is real and the code
# has demonstrably moved without it. Below this the repository is either well
# maintained or too young to have drifted.
INTERESTING_STALE_COMMITS = 30


def verdict(diagram: Dict[str, Any]) -> str:
    if diagram["stale_commits"] == 0:
        return "current — diagram moves with the code, no drift to measure"
    if diagram["stale_commits"] < INTERESTING_STALE_COMMITS:
        return "recent — too little drift to be worth a corpus slot"
    if diagram["code_files_changed_since"] == 0:
        return "stale, but no source changed — nothing to detect"
    return "CANDIDATE — real design, real drift"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", action="append", default=[],
                        help="Path to a cloned repository. Repeatable.")
    parser.add_argument("--clone", action="append", default=[],
                        help="Clone URL to fetch and scan. Repeatable.")
    parser.add_argument("--cache", default=".corpus-cache", help="Where clones are kept.")
    parser.add_argument("--out", help="Directory to write stale-diagrams.csv into.")
    args = parser.parse_args(argv)

    if not args.repo and not args.clone:
        parser.error("give at least one --repo or --clone")

    repos = list(args.repo)
    for url in args.clone:
        path = clone(url, args.cache)
        if path:
            repos.append(path)

    every: List[Dict[str, Any]] = []
    for repo in repos:
        result = scan(repo)
        if result.get("error"):
            print(f"\n{result['project']}: {result['error']}")
            continue

        print(f"\n{result['project']}  (HEAD {result['head']})")
        if not result["diagrams"]:
            print("  no design-model files found")
            continue

        for diagram in result["diagrams"]:
            print(f"  {diagram['diagram']}")
            print(f"    {diagram['kind']}, last changed {diagram['last_changed']}, "
                  f"code at {diagram['head_date']}")
            print(f"    {diagram['stale_commits']} commits and {diagram['stale_days']} days behind; "
                  f"{diagram['code_files_changed_since']} source files changed since")
            print(f"    -> {verdict(diagram)}")
            every.append({**diagram, "verdict": verdict(diagram)})

    if not every:
        print("\nNo design-model files found in any repository scanned.")
        return 1

    candidates = [d for d in every if d["verdict"].startswith("CANDIDATE")]
    print(f"\n{len(every)} diagram(s) across {len(repos)} repositor(y/ies); "
          f"{len(candidates)} are corpus candidates.")

    if candidates:
        print("\nUse these. For each, in research/corpus.json set `uml` to the diagram's")
        print("path and check out the commit where it was last touched, so the analysis")
        print("starts from the design as its author last left it:")
        for d in candidates:
            print(f"  {d['project']:<24} {d['diagram']:<44} checkout {d['last_commit']}")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "stale-diagrams.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(every[0].keys()), lineterminator="\n")
            writer.writeheader()
            writer.writerows(every)
        print(f"\nWrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

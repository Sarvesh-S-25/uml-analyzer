"""Turn a candidate screen into a corpus manifest, by a rule fixed in advance.

The screen (see docs/CORPUS-AND-SUBMISSION.md) records, for every StarUML
model found on GitHub, where its designed classes live in the code at the
diagram's last edit (the freeze), how many first-parent commits touched that
code afterwards, and the deterministic findings at the freeze and at HEAD.
This script applies the inclusion rule and writes `corpus.json` entries plus
the frozen models. It never looks at whether a project drifted: every project
that meets the rule is included, drifting or not, so the drift rate is not
selected for.

Inclusion rule
--------------
1. a StarUML class model committed by the project's own authors;
2. at least 5 designed classes, at least 3 of them declared in the code at the
   freeze;
3. at least 3 first-parent commits after the freeze touching the analysed
   directory;
4. the analysed directory has between 1 and 1,500 source files at the freeze
   and still exists at HEAD (a moved directory would read as total erosion);
5. one model per repository (the one with most designed classes found), and a
   fork is dropped when its upstream also qualifies.

    python research/build_corpus.py --screen screen.json --out research/corpus.json \
        --models research/models --keep-existing
"""
import argparse
import json
import os
import re
import shutil

FORKS = {
    # fork -> upstream, where both appeared in the search results
    "Jinksi/vars-annotation": "mbari-org/vars-annotation",
    "tasyiann/2Dto3DMotion": "CMU-Perceptual-Computing-Lab/openpose_unity_plugin",
    "aidarbek/openpose_unity_plugin": "CMU-Perceptual-Computing-Lab/openpose_unity_plugin",
    "dineshKumar777/vscode-rf-language-server": "Snooz82/vscode-rf-language-server",
    "reakaleek/MK-Design-Pattern": "ksatria/MK-Design-Pattern",
}
MAX_FILES = 1500


def qualifies(row):
    if row.get("error") or not row.get("drift"):
        return False, row.get("verdict") or row.get("error", "not analysed")
    if row["designed"] < 5 or row["found_in_code"] < 3:
        return False, "too few designed classes in code"
    if row.get("fp_touching_subdir", 0) < 3:
        return False, "fewer than 3 commits touching the analysed code"
    files, head_files = row["freeze_run"]["files"], row["head_run"]["files"]
    if not 1 <= files <= MAX_FILES:
        return False, f"{files} files at the freeze (limit {MAX_FILES})"
    if head_files == 0:
        return False, "analysed directory gone at HEAD"
    return True, "included"


def slug(repo):
    return re.sub(r"[^a-z0-9]+", "-", repo.split("/", 1)[1].lower()).strip("-")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--screen", action="append", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--models", default="research/models")
    p.add_argument("--keep-existing", action="store_true", help="Keep projects already in --out.")
    p.add_argument("--max-commits", type=int, default=150)
    p.add_argument("--decisions", help="Write every candidate's decision here (CSV).")
    args = p.parse_args(argv)

    rows = []
    for path in args.screen:
        rows.extend(json.load(open(path, encoding="utf-8")))
    decisions, best = [], {}
    for row in rows:
        repo = row["repo"].removeprefix("github.com/")
        ok, why = qualifies(row)
        decisions.append((repo, row["mdj"], why))
        if ok and (repo not in best or row["found_in_code"] > best[repo]["found_in_code"]):
            best[repo] = row
    for fork, upstream in FORKS.items():
        if fork in best and upstream in best:
            del best[fork]
            decisions.append((fork, "", f"fork of {upstream}"))
        elif fork in best:
            # Only the fork qualified; keep it but say so.
            best[fork]["fork_of"] = upstream

    existing = {"projects": []}
    if args.keep_existing and os.path.exists(args.out):
        existing = json.load(open(args.out, encoding="utf-8"))
    names = {p["name"] for p in existing["projects"]}
    os.makedirs(args.models, exist_ok=True)
    for repo, row in sorted(best.items()):
        name = slug(repo)
        if name in names:
            continue
        model = os.path.join(args.models, name + ".mdj")
        shutil.copyfile(row["model_file"], model)
        f, h = row["freeze_run"], row["head_run"]
        existing["projects"].append({
            "name": name,
            "source": f"https://github.com/{repo}.git",
            "uml": model.replace("\\", "/"),
            "start": row["freeze"],
            "commits": args.max_commits,
            "subdirectory": row["subdir"] or None,
            "provenance": "found",
            "notes": (f"{row['mdj']} last edited {row['freeze_date']}; code to {row['head_date']}; "
                      f"{row['fp_touching_subdir']} first-parent commits touch the analysed code. "
                      f"Screen: {row['designed']} designed, {row['found_in_code']} found in code, "
                      f"{f['files']} files at freeze.") + (f" Fork of {row['fork_of']}." if row.get("fork_of") else ""),
        })
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, indent=2)
    if args.decisions:
        import csv
        with open(args.decisions, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["repo", "model", "decision"])
            writer.writerows(decisions)
    print(f"{len(best)} included of {len(rows)} screened; manifest has {len(existing['projects'])} projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

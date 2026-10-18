"""Screen candidate repos: blobless clone, find .mdj class models, measure the drift window."""
import json, os, subprocess, sys, collections

CACHE = r"C:\Users\sarve\Desktop\uml-analyzer-final\.corpus-cache\screen"
CODE = {".py": "Python", ".java": "Java", ".js": "JavaScript", ".ts": "TypeScript",
        ".cs": "C#", ".php": "PHP", ".jsx": "JavaScript", ".tsx": "TypeScript"}


def git(repo, *args, timeout=600):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf8", errors="replace", timeout=timeout).stdout


def count_classes(text):
    try:
        data = json.loads(text)
    except Exception:
        return None
    counts = collections.Counter()
    def walk(n):
        if isinstance(n, dict):
            t = n.get("_type")
            if t in ("UMLClass", "UMLInterface", "UMLEnumeration"):
                counts["classes"] += 1
            if t in ("UMLAttribute",): counts["attrs"] += 1
            if t in ("UMLOperation",): counts["ops"] += 1
            if t in ("UMLGeneralization", "UMLInterfaceRealization", "UMLAssociation", "UMLDependency"):
                counts["rels"] += 1
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(data)
    return dict(counts)


def screen(full):
    name = full.split("/", 1)[1].replace("/", "__")
    dest = os.path.join(CACHE, name)
    url = "https://" + full + ".git"
    if not os.path.isdir(dest):
        r = subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", url, dest],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode:
            return [{"repo": full, "error": r.stderr.strip()[:200]}]
    out = []
    head = git(dest, "rev-parse", "HEAD").strip()
    mdjs = [p for p in git(dest, "ls-tree", "-r", "--name-only", "HEAD").splitlines() if p.lower().endswith(".mdj")]
    # Language mix of HEAD
    langs = collections.Counter()
    for p in git(dest, "ls-tree", "-r", "--name-only", "HEAD").splitlines():
        ext = os.path.splitext(p)[1].lower()
        if ext in CODE: langs[CODE[ext]] += 1
    for path in mdjs:
        last = git(dest, "log", "-1", "--format=%H %cs", "--", path).split()
        if not last: continue
        sha, date = last
        blob = git(dest, "show", f"{sha}:{path}", timeout=300)
        counts = count_classes(blob) or {}
        # first-parent source commits after the freeze
        after = git(dest, "rev-list", "--first-parent", f"{sha}..HEAD").split()
        code_after = git(dest, "log", "--first-parent", "--format=%H", f"{sha}..HEAD", "--",
                         *[f"*{e}" for e in CODE]).split()
        head_date = git(dest, "log", "-1", "--format=%cs", "HEAD").strip()
        out.append({"repo": full, "mdj": path, "freeze": sha[:10], "freeze_date": date,
                    "head_date": head_date, "fp_commits_after": len(after),
                    "fp_code_commits_after": len(code_after), "langs": dict(langs.most_common(3)),
                    **counts})
    if not mdjs:
        out.append({"repo": full, "error": "no .mdj at HEAD"})
    return out


def safe(r):
    try:
        return screen(r)
    except Exception as e:
        return [{"repo": r, "error": repr(e)[:200]}]


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    repos = [r for r in json.load(open(sys.argv[1])) if r.startswith("github.com/")]
    os.makedirs(CACHE, exist_ok=True)
    results = []
    with ThreadPoolExecutor(6) as pool:
        for rows in pool.map(safe, repos):
            for row in rows:
                results.append(row)
                print(json.dumps(row), flush=True)
    json.dump(results, open(sys.argv[2], "w"), indent=1)

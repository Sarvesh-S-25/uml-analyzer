"""Second-pass screen: does the diagram describe the code, and did conformance move?

For each (repo, mdj) candidate: full clone, take the model at its last edit (the
freeze), locate the designed classes in the code at the freeze to choose the
analysed subdirectory, count first-parent commits after the freeze that touch
that subdirectory, and run the real deterministic checker at freeze and HEAD.
"""
import json, os, re, subprocess, sys, shutil, collections, traceback

REPO_ROOT = r"C:\Users\sarve\Desktop\uml-analyzer-final"
sys.path.insert(0, os.path.join(REPO_ROOT, "research"))
os.environ["LLM_MODE"] = "offline"
from harness import Sandbox, checkout_worktree, copy_source, install_uml, designed_element_names  # noqa
from core.pipeline import run_analysis  # noqa

CACHE = os.path.join(REPO_ROOT, ".corpus-cache", "screen-full")
SCRATCH = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(SCRATCH, "models")
EXTS = (".py", ".java", ".js", ".ts", ".cs", ".php", ".jsx", ".tsx")


def git(repo, *args, binary=False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=600)
    return r.stdout if binary else r.stdout.decode("utf8", "replace")


def full_clone(full):
    name = full.split("/", 1)[1].replace("/", "__")
    dest = os.path.join(CACHE, name)
    if not os.path.isdir(os.path.join(dest, ".git")):
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:limit=512k", "--no-checkout",
                        "https://" + full + ".git", dest], capture_output=True, timeout=600)
    return dest


def designed_names(mdj_bytes):
    data = json.loads(mdj_bytes)
    names = []
    def walk(n):
        if isinstance(n, dict):
            if n.get("_type") in ("UMLClass", "UMLInterface", "UMLEnumeration") and n.get("name"):
                names.append(n["name"])
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(data)
    return sorted(set(names))


def locate(repo, sha, names):
    """Code files at the freeze declaring a designed class; returns (subdir, hits)."""
    files = [p for p in git(repo, "ls-tree", "-r", "--name-only", sha).splitlines() if p.endswith(EXTS)]
    hits = {}
    # One git grep for all names at once.
    pattern = r"(class|interface|enum|struct)\s+(" + "|".join(re.escape(n) for n in names) + r")\b"
    out = git(repo, "grep", "-E", "-o", pattern, sha, "--", *[f"*{e}" for e in EXTS])
    for line in out.splitlines():
        # sha:path:match
        try:
            _, path, match = line.split(":", 2)
        except ValueError:
            continue
        name = match.split()[-1]
        hits.setdefault(name, set()).add(path)
    if not hits:
        return None, {}, len(files)
    dirs = [os.path.dirname(p) for ps in hits.values() for p in ps]
    common = os.path.commonpath(dirs) if dirs else ""
    common = common.replace("\\", "/")
    return common, {k: sorted(v) for k, v in hits.items()}, len(files)


def analyse(repo, sha, subdir, mdj_path, sandbox, label):
    tree = os.path.join(sandbox.root, "__tree__" + label)
    proj = sandbox.reset(label)
    install_uml(proj, mdj_path)
    checkout_worktree(repo, sha, tree, subdir or None)
    n = copy_source(tree, proj, subdir or None)
    res = run_analysis(proj, gate_strategy="always", force=True)
    rf = res.get("reflexion") or {}
    return {"files": n, "score": res.get("similarity_score_rule_based"),
            "conv": rf.get("convergences"), "div": rf.get("divergences"), "abs": rf.get("absences")}


def one(c, sandbox_root):
    from harness import Sandbox
    sandbox = Sandbox.create(os.path.join(sandbox_root, str(abs(hash(c["repo"]+c["mdj"])))))
    row = {"repo": c["repo"], "mdj": c["mdj"]}
    try:
        repo = full_clone(c["repo"])
        sha = git(repo, "log", "-1", "--format=%H", "--", c["mdj"]).strip()
        blob = git(repo, "show", f"{sha}:{c['mdj']}", binary=True)
        names = designed_names(blob)
        tag = (c["repo"].split("/")[-1] + "__" + c["mdj"].replace("/", "_")).replace(" ", "_")[-120:]
        mdj_path = os.path.join(MODELS, tag)
        open(mdj_path, "wb").write(blob)
        subdir, hits, nfiles = locate(repo, sha, names)
        row.update(freeze=sha[:10], freeze_date=git(repo, "log", "-1", "--format=%cs", sha).strip(),
                   head_date=git(repo, "log", "-1", "--format=%cs", "HEAD").strip(),
                   designed=len(names), found_in_code=len(hits), subdir=subdir, model_file=mdj_path)
        if len(names) < 5 or len(hits) < 3:
            row["verdict"] = "too few designed classes found in code"
            return row
        spec = [subdir] if subdir else []
        after = git(repo, "rev-list", "--first-parent", "--ancestry-path", f"{sha}..HEAD").split()
        touching = git(repo, "rev-list", "--first-parent", "--ancestry-path", f"{sha}..HEAD", "--", *spec).split()
        row.update(fp_after=len(after), fp_touching_subdir=len(touching))
        if len(touching) < 3:
            row["verdict"] = "code under the diagram barely changed"
            return row
        row["freeze_run"] = analyse(repo, sha, subdir, mdj_path, sandbox, "f")
        row["head_run"] = analyse(repo, "HEAD", subdir, mdj_path, sandbox, "h")
        f, h = row["freeze_run"], row["head_run"]
        row["drift"] = (f["div"], h["div"], f["abs"], h["abs"])
    except Exception as e:
        row["error"] = repr(e)[:300]
    finally:
        sandbox.cleanup()
    return row


def main():
    from concurrent.futures import ProcessPoolExecutor
    cands = json.load(open(sys.argv[1]))
    out_path = sys.argv[2]
    os.makedirs(MODELS, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    done = {}
    if os.path.exists(out_path):
        for r in json.load(open(out_path)):
            done[(r["repo"], r["mdj"])] = r
    todo = [c for c in cands if (c["repo"], c["mdj"]) not in done]
    results = list(done.values())
    root = os.path.join(SCRATCH, "sandboxes")
    from concurrent.futures import as_completed
    with ProcessPoolExecutor(2) as pool:
        futures = [pool.submit(one, c, root) for c in todo]
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(json.dumps(row), flush=True)
            json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()

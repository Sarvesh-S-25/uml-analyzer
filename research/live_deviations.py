"""The seeded-deviation set with a real local model in the loop.

evaluate_deviations.py asks whether each gate *fires* on each mutation. This
asks what the user is then shown. For every mutation and gate it analyses the
pristine project, applies the mutation, analyses again with a real Ollama model
behind the gate, and scores the explanation served after the mutation against
the deterministic findings:

* changed_elements -- designed or undocumented elements whose findings the
  mutation changed (from the forced, model-free oracle);
* changed_coverage -- the share of those the served explanation names. A gate
  that reuses serves the pre-mutation explanation, so this is what a skip costs
  in what the reader is told;
* ungrounded -- identifiers the explanation names that exist in neither the
  design nor the code.

Calls are cached by prompt (see live_llm.py), so the pristine project's prompt,
identical across all mutations, is sent once per gate prompt shape.

    python research/live_deviations.py --out results/live --model qwen2.5-coder:7b
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="results/live")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--num-ctx", type=int, default=32768)
    p.add_argument("--num-predict", type=int, default=2048)
    p.add_argument("--fit-margin", type=float, default=0.85)
    p.add_argument("--strategies", default="always,content,structural,isomorphism")
    p.add_argument("--timeout", type=float, default=3600.0)
    p.add_argument("--tag", default="", help="Suffix for output files, e.g. the model name.")
    p.add_argument("--mutations", help="Comma-separated mutation ids to run (default all).")
    p.add_argument("--repeat", action="store_true",
                   help="Re-send every prompt instead of reading the cache (repeatability check).")
    return p.parse_args(argv)


def project_vocabulary_dir(root):
    from live_llm import WORD
    words = set()
    for current, _, files in os.walk(root):
        for filename in files:
            with open(os.path.join(current, filename), encoding="utf-8", errors="replace") as handle:
                words.update(WORD.findall(handle.read()))
    return words


def finding_map(result):
    difference = result["difference"]
    entries = {}
    for name in difference.get("missing_classes", []) or []:
        entries[name] = "missing"
    for name in difference.get("extra_classes", []) or []:
        entries[name] = "extra"
    for item in difference.get("element_differences", []) or []:
        entries[item["element_name"]] = json.dumps(
            {k: sorted(item.get(k, []) or []) for k in
             ("missing_methods", "missing_attributes", "extra_methods", "extra_attributes")},
            sort_keys=True)
    relations = (difference.get("missing_relations", []) or []) + (difference.get("unimplemented_associations", []) or [])
    for relation in relations:
        text = relation if isinstance(relation, str) else json.dumps(relation, sort_keys=True)
        for part in re.split(r"[^\w]+", text):
            if part[:1].isupper():
                entries[part] = entries.get(part, "") + "|rel:" + text
    # Layer-rule violations (a controller calling persistence directly) are
    # findings too; the element is the class in the offending file.
    for item in result.get("rule_violations", []) or []:
        stem = os.path.splitext(os.path.basename(str(item.get("file", ""))))[0]
        names = [n for n in re.split(r"[^\w]+", json.dumps(item)) if n[:1].isupper()] or [stem]
        for name in names:
            entries[name] = entries.get(name, "") + "|rule:" + str(item.get("rule"))
    return entries


def main(argv=None) -> int:
    args = parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    os.environ["LLM_MODE"] = "auto"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["LLM_MODEL"] = args.model

    import evaluate_deviations as ed
    from harness import Sandbox, copy_source, finding_signature, install_uml, signatures_differ, write_csv
    from live_llm import LiveModel, grounded_names, mentioned_identifiers, project_vocabulary
    from core.pipeline import run_analysis

    args.always_sample = 0
    live = LiveModel(args)
    strategies = [s for s in args.strategies.split(",") if s]
    sandbox = Sandbox.create()
    rows = []
    try:
        chosen = set(args.mutations.split(",")) if args.mutations else None
        for mutation in ed.MUTATIONS:
            if chosen and mutation.id not in chosen:
                continue
            tree = os.path.join(sandbox.root, "__tree__" + mutation.id)
            oracle = sandbox.reset("oracle--" + mutation.id)
            install_uml(oracle, ed.UML_PATH)
            live.before_run("oracle", 0, None)
            ed.stage_base(tree)
            copy_source(tree, oracle)
            before = run_analysis(oracle, gate_strategy="always", force=True)
            mutation.apply(tree)
            copy_source(tree, oracle)
            after = run_analysis(oracle, gate_strategy="always", force=True)
            findings_changed = bool(signatures_differ(finding_signature(before), finding_signature(after)))
            fb, fa = finding_map(before), finding_map(after)
            changed = {n for n in set(fb) | set(fa) if fb.get(n) != fa.get(n)}

            for strategy in strategies:
                project = sandbox.reset(f"{mutation.id}--{strategy}")
                install_uml(project, ed.UML_PATH)
                ed.stage_base(tree)
                copy_source(tree, project)
                live.before_run(strategy, 0, None)
                base = run_analysis(project, gate_strategy=strategy)
                base_status = dict(live.last)
                mutation.apply(tree)
                copy_source(tree, project)
                live.before_run(strategy, 1, findings_changed)
                result = run_analysis(project, gate_strategy=strategy)
                status = dict(live.last)
                texts = (result.get("ai_gaps") or []) + (result.get("recommendations") or [])
                mentioned = mentioned_identifiers(texts)
                # Grounded: anything named in the design, or present anywhere in
                # the code before or after the mutation.
                grounded = grounded_names(result) | grounded_names(base) | project_vocabulary(project)
                pristine = os.path.join(sandbox.root, "__pristine__")
                ed.stage_base(pristine)
                grounded |= project_vocabulary_dir(pristine)
                fired = bool(result["gate"]["should_invoke_llm"])
                rows.append({
                    "mutation": mutation.id,
                    "category": mutation.category,
                    "strategy": strategy,
                    "findings_changed": findings_changed,
                    "gate_fired": fired,
                    "llm_status": status.get("llm_status"),
                    "llm_invoked": bool(result["llm"].get("invoked")),
                    "base_llm_status": base_status.get("llm_status"),
                    "scoped": fired and bool(result["gate"].get("impact_node_count")),
                    "est_prompt_tokens": status.get("est_prompt_tokens"),
                    "ollama_prompt_tokens": status.get("prompt_eval_count"),
                    "ollama_completion_tokens": status.get("eval_count"),
                    "prompt_eval_s": status.get("prompt_eval_s"),
                    "eval_s": status.get("eval_s"),
                    "llm_wall_s": status.get("wall_s"),
                    "cache_hit": status.get("cache_hit"),
                    "json_ok": status.get("json_ok"),
                    "changed_elements": ";".join(sorted(changed)),
                    "changed_named": len(changed & mentioned),
                    "changed_coverage": round(len(changed & mentioned) / len(changed), 4) if changed else None,
                    "served_gaps": len(result.get("ai_gaps") or []),
                    "mentions": len(mentioned),
                    "ungrounded": len(mentioned - grounded),
                    "ungrounded_names": ";".join(sorted(mentioned - grounded))[:300],
                    "model_score": result.get("model_score"),
                    "rule_score": result.get("similarity_score_rule_based"),
                    "mentioned": ";".join(sorted(mentioned))[:600],
                    "gaps_text": json.dumps(result.get("ai_gaps") or [])[:2000],
                })
                r = rows[-1]
                print(f"{mutation.id:<26} {strategy:<11} fired={fired!s:<5} {r['llm_status']:<14} "
                      f"cov={r['changed_coverage']} ungrounded={r['ungrounded']} "
                      f"tok={r['ollama_prompt_tokens']} wall={r['llm_wall_s']}", flush=True)
                write_csv(os.path.join(args.out, f"deviations-live{args.tag}.csv"), rows)
    finally:
        sandbox.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

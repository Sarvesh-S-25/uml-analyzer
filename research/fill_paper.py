"""Fill paper/paper-revised.template.md from the results, so no number is typed by hand.

    python research/fill_paper.py --v2 results/v2 --live results/live \
        --template paper/paper-revised.template.md --out paper/paper-revised.md

Every ⟦NAME⟧ marker in the template is replaced by a value computed here from
statistics.json, drift.json, runs.csv (the merged offline replay) and the live
results. A marker left unfilled is reported and the script exits non-zero.
"""
import argparse
import csv
import glob
import io
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from stats.core import wilson_interval  # noqa: E402

GATES = ("always", "content", "structural", "isomorphism")


def pct(x, places=0):
    return f"{x * 100:.{places}f}%"


def ci(k, n):
    lo, hi = wilson_interval(k, n)
    return f"{lo * 100:.1f}–{hi * 100:.1f}%"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--v2", default="results/v2")
    p.add_argument("--live", default="results/live")
    p.add_argument("--template", default="paper/paper-revised.template.md")
    p.add_argument("--out", default="paper/paper-revised.md")
    p.add_argument("--manifest", default="research/corpus-v2.json")
    args = p.parse_args(argv)

    stats = json.load(open(os.path.join(args.v2, "statistics.json"), encoding="utf-8"))
    drift = json.load(open(os.path.join(args.v2, "drift.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(args.v2, "runs.csv"), encoding="utf-8")))
    table = json.load(open(os.path.join(args.v2, "corpus_table.json"), encoding="utf-8"))
    manifest = json.load(open(args.manifest, encoding="utf-8"))["projects"]
    V = {}

    projects = drift["projects"]
    oracle = [r for r in rows if r["gate_strategy"] == "always"]
    judged = [r for r in oracle if r["conformance_changed"] in ("True", "False")]
    changed = sum(r["conformance_changed"] == "True" for r in judged)
    V["N_PROJECTS"] = str(len(projects))
    V["N_COMMITS"] = f"{len(oracle):,}"
    V["N_TRANS"] = f"{len(judged):,}"
    V["N_CHANGED"] = f"{changed:,}"
    V["N_UNCHANGED"] = f"{len(judged) - changed:,}"
    V["CHANGED_PCT"] = pct(changed / len(judged), 1)
    V["CHANGED_CI"] = ci(changed, len(judged))
    drifted = sum(1 for x in projects if x["conformance_changing_commits"])
    V["DRIFTED"] = str(drifted)
    V["DRIFTED_PCT"] = pct(drifted / len(projects))
    direction = Counter(x["direction"] for x in projects)
    V["DIV_LED"] = str(direction["divergence-led"])
    V["ABS_LED"] = str(direction["absence-led"])
    V["CONV"] = str(direction["converging"])
    V["STABLE"] = str(direction["stable"])
    V["ERODING"] = str(sum(x["eroding_commits"] for x in projects))
    V["REPAIRING"] = str(sum(x["repairing_commits"] for x in projects))
    V["NET_DIV"] = f"{sum(x['net_divergence'] for x in projects):,}"
    V["NET_ABS"] = f"{sum(x['net_absence'] for x in projects):,}"
    surv = drift["pooled_survival"]
    V["SURV_AT_RISK"] = str(surv["at_risk"])
    V["SURV_EVENTS"] = str(surv["events"])
    V["SURV_END"] = f"{surv['survival_at_end']:.2f}"

    langs = Counter(t["lang"] for t in table)
    V["LANG_COUNTS"] = ", ".join(f"{lang} {n}" for lang, n in langs.most_common())
    years = sorted(int(t["freeze"][:4]) for t in table if t.get("freeze"))
    V["MED_YEAR"] = str(int(statistics.median(years)))
    V["YEAR_RANGE"] = f"{years[0]}–{years[-1]}"
    for key, field in (("COMMITS", "commits"), ("DAYS", "days"), ("FILES", "files")):
        values = [t[field] for t in table if t.get(field) is not None]
        V[key + "_MED"] = f"{statistics.median(values):,.0f}"
        V[key + "_RANGE"] = f"{min(values):,}–{max(values):,}"
    missing = [m["name"] for m in manifest if not os.path.exists(os.path.join("results", "corpus-v2", m["name"], "runs.csv"))]
    others = [n for n in missing if n != "city-sim"]
    V["N_REPLAYED_NOTE"] = (f"{len(projects)} were replayed" if not others else
                            f"{', '.join(others)} did not finish in time; {len(projects)} were replayed")

    by_gate = {g["gate"]: g for g in stats["gates"]["rows"]}
    lines = []
    for gate in GATES:
        g = by_gate[gate]
        rec = f"{pct(g['recall'])} [{pct(g['recall_low'])}–{pct(g['recall_high'])}]"
        spe = f"{pct(g['specificity'])} [{pct(g['specificity_low'])}–{pct(g['specificity_high'])}]"
        saved = "—" if gate == "always" else pct(g["counterfactual_percent_saved"])
        lines.append(f"| {gate} | {g['reanalysed']:,} | {pct(g['skip_rate'])} [{pct(g['skip_low'])}–{pct(g['skip_high'])}] | "
                     f"{rec} | {spe} | {g['missed']} | {saved} |")
    V["GATE_ROWS"] = "\n".join(lines)
    V["STRUCT_SKIP"] = pct(by_gate["structural"]["skip_rate"])
    V["STRUCT_SAVED"] = pct(by_gate["structural"]["counterfactual_percent_saved"])
    V["ISO_SKIP"] = pct(by_gate["isomorphism"]["skip_rate"])
    comp = stats.get("comparison") or {}
    V["DISCORDANT"] = str(comp.get("discordant"))
    content = [r for r in rows if r["gate_strategy"] == "content"]
    struct_fired = {(r["project"], r["commit_index"]) for r in rows if r["gate_strategy"] == "structural" and r["gate_allowed_llm"] == "True"}
    waste = sum(1 for r in content if r["gate_allowed_llm"] == "True" and r["conformance_changed"] == "False"
                and (r["project"], r["commit_index"]) not in struct_fired and r["commit_index"] != "0")
    V["CONTENT_WASTE"] = f"{waste:,} commits"

    iso = [r for r in rows if r["gate_strategy"] == "isomorphism"]
    stale = [r for r in iso if r["missed_change"] == "True"]
    V["ISO_STALE"] = str(len(stale))
    V["ISO_STALE_PCT"] = pct(len(stale) / len(iso), 1)
    V["ISO_STARTS"] = str(sum(1 for r in stale if "isomorphic" in r["reason"]))
    member = 0
    for path in glob.glob(os.path.join("results", "corpus-v2", "*", "summary.json")):
        for m in json.load(open(path, encoding="utf-8")).get("missed_changes", []):
            if "isomorphism" == m.get("strategy") and "element_differences" in m["differing_fields"]:
                member += 1
    V["ISO_MEMBER"] = str(member)
    V["ISO_CENSORED"] = str(by_gate["isomorphism"]["recovery"].get("censored_count"))

    # Fit to the local window (fit_numbers.py logic, with the measured ratio).
    records = [json.load(open(p_, encoding="utf-8")) for p_ in glob.glob(os.path.join(args.live, "llm-cache", "*.json"))
               if not p_.endswith("-r.json")]
    ok = [r for r in records if r.get("ok")]
    ratios = [r["prompt_eval_count"] / r["est_prompt_tokens"] for r in ok if r.get("est_prompt_tokens") and r.get("prompt_eval_count")]
    ratio = statistics.median(ratios)
    V["CAL_RATIO"] = f"{ratio:.3f}"
    V["CAL_RANGE"] = f"{min(ratios):.3f}–{max(ratios):.3f}"
    V["N_CALIBRATION"] = str(len(ratios))
    V["TPS_PROMPT"] = f"{statistics.median(r['prompt_eval_count'] / r['prompt_eval_s'] for r in ok if r.get('prompt_eval_s')):,.0f}"
    V["TPS_GEN"] = f"{statistics.median(r['eval_count'] / r['eval_s'] for r in ok if r.get('eval_s')):.1f}"
    capped = [r for r in ok if r.get("done_reason") == "length"]
    V["TRUNC_OUT"] = f"{len(capped)} of {len(ok)}"
    limit = 32768 * 0.85
    fired = [r for r in rows if r["gate_allowed_llm"] == "True"]
    fit_lines, share = [], {}
    for gate in GATES:
        sizes = [int(r["counterfactual_prompt_tokens"] or 0) * ratio for r in fired if r["gate_strategy"] == gate]
        fit = sum(1 for x in sizes if x <= limit)
        lo, hi = wilson_interval(fit, len(sizes))
        q = statistics.quantiles(sizes, n=10)
        share[gate] = fit / len(sizes)
        fit_lines.append(f"| {gate} | {len(sizes):,} | {pct(fit / len(sizes))} [{lo * 100:.0f}–{hi * 100:.0f}] | "
                         f"{statistics.median(sizes):,.0f} | {q[8]:,.0f} |")
    V["FIT_ROWS"] = "\n".join(fit_lines)
    V["ALWAYS_FIT"] = pct(share["always"])
    V["STRUCT_FIT"] = pct(share["structural"])
    never = 0
    for project in {r["project"] for r in fired}:
        sizes = [int(r["counterfactual_prompt_tokens"] or 0) * ratio for r in fired if r["project"] == project and r["gate_strategy"] == "always"]
        if sizes and all(x > limit for x in sizes):
            never += 1
    V["NEVER_FIT"] = str(never)

    # Live corpus arm.
    live_rows = []
    for path in sorted(glob.glob(os.path.join(args.live, "runs-*.csv"))):
        live_rows += list(csv.DictReader(open(path, encoding="utf-8")))
    live_projects = sorted({r["project"] for r in live_rows})
    if live_rows:
        sent = {g: [r for r in live_rows if r["gate_strategy"] == g and r["llm_status"] in ("called", "bad_json")] for g in GATES}
        tok = {g: sum(int(r["ollama_prompt_tokens"] or 0) for r in sent[g]) for g in GATES}
        secs = {g: sum(float(r["llm_wall_s"] or 0) for r in sent[g]) for g in GATES}
        nofit = sum(1 for r in live_rows if r["llm_status"] == "no_fit")
        bad = {g: sum(1 for r in sent[g] if r["llm_status"] == "bad_json") for g in GATES}
        all_sent = sum(len(sent[g]) for g in GATES)
        V["LIVE_CORPUS"] = (
            f"In the live corpus arm ({len(live_projects)} project{'s' if len(live_projects) != 1 else ''}: "
            f"{', '.join(live_projects)}), the structural gate sent {len(sent['structural'])} real calls "
            f"({tok['structural']:,} measured prompt tokens, {secs['structural'] / 60:,.0f} minutes of model time) and the "
            f"isomorphism gate {len(sent['isomorphism'])}; every scoped prompt fitted the window, while {nofit} of the "
            f"sampled full-project prompts did not and were not sent. On this real project the small model often failed "
            f"to finish the answer format: {bad['structural']} of the structural gate's {len(sent['structural'])} answers, "
            f"and {sum(bad.values())} of all {all_sent} answers, were cut off or were not valid JSON, and the tool fell "
            "back to its deterministic findings for those runs. Because `always` was sampled, its measured total is not "
            "comparable, and Table IV keeps the counterfactual for the corpus-wide saving.")
        V["LIVE_TIME"] = (f"In the live corpus arm the structural gate's calls took {secs['structural'] / max(len(sent['structural']), 1) / 60:.1f} "
                          "minutes each on average.")
    else:
        V["LIVE_CORPUS"] = "The live corpus arm had not finished any project when these numbers were produced."
        V["LIVE_TIME"] = ""

    template = io.open(args.template, encoding="utf-8").read()
    out = template
    for key, value in V.items():
        out = out.replace("⟦" + key + "⟧", value)
    left = sorted(set(re.findall("⟦([A-Z0-9_]+)⟧", out)))
    io.open(args.out, "w", encoding="utf-8").write(out)
    json.dump(V, open(os.path.join(args.v2, "paper_values.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"filled {len(V)} values; unfilled: {left}")
    return 1 if left else 0


if __name__ == "__main__":
    raise SystemExit(main())

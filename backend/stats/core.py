"""The four statistical operations this project actually needs.

Deliberately small. An earlier version of this file was 763 lines and offered a
dozen tests; it was harder to read than the data it described, which defeats the
point. What survives is the minimum that lets the paper's four tables be
defended:

* **median / mean** -- token counts and latencies are right-skewed, so the
  median leads and the mean follows for readers who expect it.
* **Wilson interval** -- a skip rate of 40% from 200 runs and one from 8 runs
  are not the same claim, and the interval is what says so. Wilson rather than
  the textbook normal approximation because these rates sit near 0 and 1, where
  the naive interval runs outside [0, 1] and stops being an interval.
* **McNemar's exact test** -- the one significance test kept. Every commit is
  analysed by every gate, so comparing two gates is a *paired* problem, and only
  the commits where they disagreed carry information.
* **percent / plain formatting** -- so a number is written the same way in the
  UI, the CSV and the LaTeX, and cannot drift apart between them.

Pure Python throughout. A dependency that might be missing in a reviewer's
environment is a reproducibility problem, not a convenience.
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Below this many observations a rate is reported with a loud warning: it is not
# that the arithmetic changes, it is that 2/5 and 80/200 both print as "40%" and
# only one of them is worth quoting.
MIN_RUNS_FOR_A_TRUSTWORTHY_RATE = 10

# McNemar needs disagreements to work with. With *five* or fewer, the exact test
# cannot reach significance at all: the most lopsided possible split at five
# discordant pairs is 5-0, giving 2 * 0.5**5 = 0.0625, which never clears the
# 0.05 the rest of this file reports against. Six is the first count at which a
# significant result is even reachable (2 * 0.5**6 = 0.03125). Reporting a
# p-value below that invites the reader to treat "not significant" as evidence
# of no difference, when in fact no outcome could have been significant.
MIN_DISCORDANT_PAIRS = 6


# --- basic descriptive -------------------------------------------------------


def mean(values: Sequence[float]) -> Optional[float]:
    clean = _clean(values)
    return sum(clean) / len(clean) if clean else None


def median(values: Sequence[float]) -> Optional[float]:
    clean = sorted(_clean(values))
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return float(clean[middle])
    return (clean[middle - 1] + clean[middle]) / 2


def _clean(values: Sequence[float]) -> List[float]:
    out: List[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number):
            continue
        out.append(number)
    return out


def describe(values: Sequence[float]) -> Dict[str, Any]:
    """Median first, mean second, and the count so a reader can weigh both."""
    clean = _clean(values)
    if not clean:
        return {"n": 0, "median": None, "mean": None, "min": None, "max": None, "total": 0}
    return {
        "n": len(clean),
        "median": round2(median(clean)),
        "mean": round2(mean(clean)),
        "min": round2(min(clean)),
        "max": round2(max(clean)),
        "total": round2(sum(clean)),
    }


def round2(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    rounded = round(float(value), 2)
    return int(rounded) if rounded == int(rounded) else rounded


# --- rates and their intervals -----------------------------------------------


def rate(successes: int, total: int) -> Optional[float]:
    return successes / total if total else None


def wilson_interval(successes: int, total: int) -> Tuple[Optional[float], Optional[float]]:
    """95% interval for a proportion, Wilson score method.

    Read it as: if the study were repeated, the true rate would very likely fall
    in this range. It is wide when the run count is small, which is exactly the
    signal a reader needs.
    """
    if total <= 0:
        return None, None
    z = 1.959963984540054
    observed = successes / total
    denominator = 1 + z * z / total
    centre = (observed + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(observed * (1 - observed) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


# --- the one significance test -----------------------------------------------


def mcnemar_exact(left: Sequence[bool], right: Sequence[bool]) -> Dict[str, Any]:
    """Did two gates really behave differently, or could it be chance?

    The design is paired: the *same* commits are put through both gates, so the
    two columns are not independent samples and a two-sample proportion test
    would be the wrong instrument. McNemar looks only at the commits where the
    gates disagreed -- gate A re-analysed and gate B skipped, or the reverse --
    and asks whether the split between those two kinds of disagreement is
    lopsided enough to be more than a coin flip.

    Exact binomial rather than the chi-square approximation: with a few dozen
    disagreements the approximation is not reliable and the exact version costs
    nothing.
    """
    pairs = [(bool(a), bool(b)) for a, b in zip(left, right)]
    a_only = sum(1 for a, b in pairs if a and not b)
    b_only = sum(1 for a, b in pairs if b and not a)
    discordant = a_only + b_only

    result: Dict[str, Any] = {
        "paired_observations": len(pairs),
        "left_only": a_only,
        "right_only": b_only,
        "discordant": discordant,
        "agreed": len(pairs) - discordant,
        "p_value": None,
        "usable": False,
        "reason": "",
    }

    if not pairs:
        result["reason"] = "No commits were analysed by both gates."
        return result
    if discordant == 0:
        result["reason"] = "The two gates made the same decision on every commit."
        return result
    if discordant < MIN_DISCORDANT_PAIRS:
        result["reason"] = (
            f"Only {discordant} commit(s) where the gates disagreed; at least "
            f"{MIN_DISCORDANT_PAIRS} are needed before a p-value means anything."
        )
        return result

    smaller = min(a_only, b_only)
    tail = sum(_binomial_pmf(k, discordant, 0.5) for k in range(smaller + 1))
    p_value = min(1.0, 2 * tail)

    result["p_value"] = p_value
    result["usable"] = True
    return result


def _binomial_pmf(successes: int, trials: int, probability: float) -> float:
    return (
        math.comb(trials, successes)
        * probability ** successes
        * (1 - probability) ** (trials - successes)
    )


# --- shared formatting -------------------------------------------------------
# One implementation, used by the page, the CSVs and the LaTeX, so the same
# number is never written two different ways in two different places.


def percent(value: Optional[float], places: int = 1) -> str:
    if value is None:
        return "not measured"
    return f"{value * 100:.{places}f}%"


def count(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{int(round(float(value))):,}"


def p_value_text(value: Optional[float]) -> str:
    """p is never exactly zero, and an exponent in a results table is noise."""
    if value is None:
        return "not computed"
    return "below 0.001" if value < 0.001 else f"{value:.3f}"


def interval_text(low: Optional[float], high: Optional[float]) -> str:
    if low is None or high is None:
        return ""
    return f"between {percent(low, 0)} and {percent(high, 0)}"


# --- how long a missed change stays missed -----------------------------------


def km_median_horizon(durations: Sequence[Optional[int]]) -> Dict[str, Any]:
    """Median commits from a missed change to the run that corrects it.

    Some misses are still uncorrected when a project's replay ends. Dropping
    those would bias the median downwards (the longest gaps are exactly the ones
    most likely to run past the end), and counting them as some finite number
    would be inventing data. They are therefore treated as **censored**: known
    to be at least this long, exact length unknown -- which is what the
    Kaplan-Meier estimator is for.

    Pass an integer commit distance for each corrected miss and ``None`` for
    each one still outstanding at the end of its project's history.

    ``median_commits`` is ``None`` when the survival curve never falls to 0.5 --
    that is, when so many misses were still outstanding that the median is not
    identified. ``censored_beyond`` then carries the longest observed
    outstanding gap, so the text can honestly say "more than N commits" instead
    of inventing a midpoint.
    """
    resolved = sorted(value for value in durations if value is not None)
    censored = [value for value in durations if value is None]

    result: Dict[str, Any] = {
        "misses_tracked": len(durations),
        "resolved_count": len(resolved),
        "censored_count": len(censored),
        "median_commits": None,
        "censored_beyond": None,
        "max_resolved": resolved[-1] if resolved else None,
    }
    if not durations:
        return result

    # Kaplan-Meier over the corrected gaps, with the outstanding ones removed
    # from the risk set at the end (they survived at least as long as any
    # observed correction).
    at_risk = len(durations)
    survival = 1.0
    for moment in sorted(set(resolved)):
        events = sum(1 for value in resolved if value == moment)
        if at_risk <= 0:
            break
        survival *= 1 - events / at_risk
        if survival <= 0.5 and result["median_commits"] is None:
            result["median_commits"] = float(moment)
        at_risk -= events

    if result["median_commits"] is None and censored:
        result["censored_beyond"] = resolved[-1] if resolved else 0
    return result

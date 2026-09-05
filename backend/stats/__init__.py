"""Four tables, one significance test, two charts.

The whole package is roughly 700 lines of pure Python and computes only what the
paper needs:

    Table 1  What was studied
    Table 2  How each gate performed        <- the headline result
    Table 3  Did it work on every project?
    Table 4  The controlled test (seeded deviations)
    +        McNemar's exact test on the one comparison that matters
    +        Skip rate by gate, and design violations accumulating over commits

Two principles:

1. **No number without a sentence.** Every table carries a plain-English reading
   generated from its own figures. A reader should never have to work out what a
   column means, and a sentence generated from the data cannot go stale or
   overstate what the data shows.

2. **Refuse rather than mislead.** Miss rate is reported as "not measured" when
   no forced-comparison run exists, never as zero. A rate from fewer than ten
   runs is flagged. Nothing is printed that a reader would take as evidence and
   that is not.

An earlier version of this package had regression models, cross-validated
classifiers, survival analysis, cluster bootstrapping and six corrected pairwise
tests. All of it was correct and none of it was readable. It was removed
deliberately; if a reviewer asks for a specific test, add that one test back.
"""
from stats.core import (  # noqa: F401
    mcnemar_exact,
    mean,
    median,
    percent,
    rate,
    wilson_interval,
)

__all__ = ["mcnemar_exact", "mean", "median", "percent", "rate", "wilson_interval"]

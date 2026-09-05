# Documentation index

Six documents. Each answers one question — start with the one that matches
what you are trying to do.

| Read this | When you want to |
|---|---|
| **[START-HERE.md](START-HERE.md)** | Know what to do next. Steps 0–9, each with the exact command and what you should see. **Start here.** |
| **[UNDERSTANDING.md](UNDERSTANDING.md)** | Understand what you are looking at — every screen, table, word, and what a good result looks like versus a broken one |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Change the code. One analysis run end to end, every module, and the six invariants that must not break |
| **[CORPUS-AND-SUBMISSION.md](CORPUS-AND-SUBMISSION.md)** | Choose projects to evaluate on, and submit the paper |
| **[STATISTICS.md](STATISTICS.md)** | Know what the four tables are and where each number comes from |
| **[LITERATURE.md](LITERATURE.md)** | Write the related-work section. Citations, positioning, novelty |
| **[API.md](API.md)** | Call the backend directly |

## The shortest possible orientation

The tool checks whether your code still matches your UML diagram. That check
costs money because it calls a language model, and it has to be repeated on
every commit. A **gate** decides, before spending anything, whether enough
changed to be worth re-checking.

The paper measures one thing: **how much each gate saves, and what that saving
costs in missed problems.**

Everything in this repository exists to produce that measurement.

## What is done and what is not

| | State |
|---|---|
| Parser, UML reader, comparator, four gates, versioning | Done |
| Statistics: four tables, McNemar, two charts, per-project breakdown | Done |
| Static layered graph, SVG export, replication packaging | Done |
| Paper draft (`paper/IEEE-Access-draft.docx`) | Written, 21 numbers to fill |
| **A corpus** | **Not started — the only blocker** |

Everything except the corpus is an afternoon. The corpus is the project.

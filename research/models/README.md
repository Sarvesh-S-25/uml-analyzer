# Frozen .mdj diagrams

One per project, named to match its entry in `research/corpus.json`.

**Freeze them.** Take each diagram from the commit where it was last edited,
record that commit as `start` in `corpus.json`, and never edit the file again.
If the diagram changes as the code changes, conformance is perfect by
construction and the study measures nothing.

## What is here, and where each file came from

| File | Repository | Taken from | Provenance | Changes |
|---|---|---|---|---|
| `discordbotrpg.mdj` | FightRPG-DiscordBotRPG/DiscordBotRPG-Server | `UML.mdj` at `f2ab878` (2019-12-01) | found | Four string literals in the authors' file were missing their closing quote (`"idEntities/Monster,` and three like it), which made the file invalid JSON. Exactly those four quotes were added; the parsed model is otherwise identical to the original. Verified by line diff. |
| `sistema-bancario.mdj` | manoelcampos/sistema-bancario-java-junit | `sistema-bancario.staruml.mdj` at `16508fe` (2020-08-13) | found | None (byte-identical to `git show`). |
| `gamespark.mdj` | yusufkaraaslan/GameSpark | `UML/Game Spark UML.mdj` at `8902f40` (2022-02-25) | found | None (byte-identical to `git show`). |
| `_salvaged-user_controller.mdj` | — | — | — | Unused scratch model; not in the corpus. |

Regenerate any of them with, for example:

```bash
git -C .corpus-cache/GameSpark show "8902f40:UML/Game Spark UML.mdj" > research/models/gamespark.mdj
```

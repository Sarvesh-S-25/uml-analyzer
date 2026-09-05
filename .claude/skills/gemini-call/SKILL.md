---
name: gemini-call
description: Ask Gemini a single question via .claude/scripts/gemini.mjs instead of reading broadly yourself. Use this whenever answering would need more than about three files read, tracing a call path across modules, finding every usage of a symbol, or getting a second opinion on a design decision before implementation begins. For a whole task rather than one question, use the gemini-planner subagent instead.
when_to_use: Triggers include "how does X work", "where is X used", "what would break if", "ask Gemini", "get a second opinion", or any moment about to read a fourth file to answer one question.
argument-hint: "[--dirs a,b] your question"
allowed-tools: Bash(node .claude/scripts/gemini.mjs:*)
---

# Gemini delegation

`.claude/scripts/gemini.mjs` reads files itself and sends them to Gemini
(through the Antigravity CLI, `agy`) — its context is large and cheap, and
Claude's context stays free for editing. Gemini reads; you edit.

## Dispatch

```powershell
node .claude/scripts/gemini.mjs --dirs <relevant dirs> "your question"
```

`--dirs` is the point of the whole thing: name the directories that matter and
the wrapper embeds their contents in the prompt. Do not paste file contents
into the question when you can name a directory instead.

| Flag | |
|---|---|
| `--dirs a,b` | files under these paths are read and sent with the question |
| `--dry-context` | print exactly what would be sent, then stop — free, no API call |
| `--effort low` | quicker, cheaper. Default `high` |
| `--max-kb 400` | raise the 250KB payload cap |
| `--timeout 900` | default 600s |
| `--raw` | full JSON response instead of just the answer |

See `.claude/README.md` for the full mechanism and why it's built this way
(headless permission issues, Windows command-line length limits, etc.).

## Writing the question

Each run is a fresh session with no memory of previous ones, and cost is
roughly 20-30k input tokens per call regardless of question size — `agy` loads
its own harness context before it sees anything.

- Name exact paths: `backend/core/graph_diff.py and backend/core/graph_builder.py`,
  not "the gate code".
- One question per call. Two unrelated asks gets a worse answer to both.
- State the shape you want back if you need something other than prose —
  numbered steps, a table, a list of file:line locations.
- Never phrase it as a task to perform. "What would break if `ComparisonEngine`
  started scoring associations by default?" is fine; "make associations count
  by default" invites Gemini to propose an implementation it cannot verify runs.

Good: `--dirs backend/core "read graph_diff.py. list every place decide_gate reads a graph attribute, with file:line, and which of the four gate strategies each read is used by"`

Bad: `"tell me about the gate and how to make it faster"`

## Acting on the output

Treat it as claims, not truth. It's a different model reading the same repo
and it can be confidently wrong about specifics — it has not read
`docs/ARCHITECTURE.md` §4's invariants unless you point `--dirs` at `docs/` or
quote them in the question.

- Before editing a file it named, open the cited lines and confirm they say
  what it claimed.
- If a claim contradicts the file, the file wins. Say the plan was wrong.
- Do not relay its findings to the user as established fact without checking
  the part you're about to act on.

## Failure handling

Exit codes from `gemini.mjs`:

- **0** — answered.
- **1** — the engine returned an error, or the call timed out. Transient: say
  so in one line and either retry once with `--effort low` or proceed without
  it.
- **2** — setup problem: nothing installed, or authentication failed. Stop and
  tell the user; retrying will not fix it. `agy` signs in through the browser
  and stores the token in Windows Credential Manager — re-run `agy` on its own
  to sign in again.

Always name the failure. Silently switching to reading files yourself hides a
broken setup for days.

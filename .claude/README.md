# Consulting Gemini from this repo

One command, from the project root:

```powershell
node .claude\scripts\gemini.mjs --dirs backend/core "what does decide_gate do?"
```

`--dirs` is the point of the whole thing: the wrapper reads those files itself and
sends them to Gemini, so Gemini gets the code and **Claude's context stays free**.

```
[context]   6 files · 49KB from backend/core        what was collected
[transport] 47KB prompt sent over stdin             how it was sent
<the answer>
[agy · 19476 in / 811 out · 13s · 1 turns]          what it cost
```

| Flag | |
|---|---|
| `--dirs a,b` | files under these paths are read and sent with the question |
| `--dry-context` | print exactly what would be sent, then stop — free, no API call |
| `--effort low` | quicker, cheaper. Default `high` |
| `--max-kb 400` | raise the 250KB payload cap |
| `--timeout 900` | default 600s |
| `--raw` | full JSON response instead of just the answer |

Exit codes matter to the agent: **2 = setup problem, stop**; 1 = transient
(quota, timeout); 0 = answered.

---

## How this was made to work

Five things blocked it. Each one is worth knowing, because each will bite again.

**1. Google sign-in is dead in the `gemini` CLI.** For individual accounts it fails
with *"this client is no longer supported for Gemini Code Assist for individuals"*
([gemini-cli#28229](https://github.com/google-gemini/gemini-cli/issues/28229)) —
open, unresolved. The fix was to switch engines entirely to the **Antigravity CLI
(`agy`)**, where OAuth still works. `agy` signs in through the browser and stores
the token in Windows Credential Manager. The old CLI is kept as an API-key fallback.

**2. `agy` isn't reliably on PATH.** The installer adds `%LOCALAPPDATA%\agy\bin`,
but that only reaches terminals opened afterwards. The wrapper now looks in the
known install location first — an absolute path that exists is proof, a PATH probe
is a guess. (`agy` on its own still needs PATH fixed; the wrapper doesn't.)

**3. Letting Gemini read the files itself doesn't work headlessly.** `agy -p`
ignores permission allowlists
([antigravity-cli#548](https://github.com/google-antigravity/antigravity-cli/issues/548)),
so its file tools get refused and you get an empty answer with a note that a tool
was denied. The only documented workaround is `--dangerously-skip-permissions`,
which also unlocks writes and shell. So **the wrapper reads the files instead**.
Deterministic, needs no permissions, and Gemini genuinely can't modify anything
because it never needs a tool.

**4. A 49KB prompt won't fit in a command line.** Windows caps it at 32,767
characters — `spawn` fails with `ENAMETOOLONG`. Anything over ~7KB now goes over
**stdin**, which for `agy` means stream-json: `--input-format stream-json` requires
`--output-format stream-json`, so the reply arrives as newline-delimited
`init`/`step_update`/`result` events and the answer is read from the `result` event.
Short prompts still use the plain argument form.

**5. Small mismatches that fail loudly.** `agy` reports `status: "SUCCESS"` in caps
and `error` as a plain string (the old CLI used an object); spawning a `.exe` with
`shell: true` triggers Node's DEP0190 warning and, worse, concatenates the prompt
into a command line unescaped, so a question containing `&` or a quote breaks it.

---

## Cost

Roughly **20–30k input tokens per consult** — `agy` loads its own harness context
before it sees your question, so even "say ok" costs ~14k. Two consequences:

- Skip it for typos and renames. That rule saves tokens, not just time.
- Batch. One question naming three directories beats three separate calls.

`--dry-context` costs nothing and shows you the payload before you spend anything.

---

## If it breaks

```powershell
node .claude\scripts\gemini.mjs --help
node .claude\scripts\gemini.mjs --dirs backend/core --dry-context   # collector only
& "$env:LOCALAPPDATA\agy\bin\agy.exe" -p "say ok" --output-format json # engine only
```

Those three isolate which half is broken. Exit code 2 means auth or install —
re-run `agy` on its own to sign in again.

See `skills/gemini-call/SKILL.md` for when to consult it, and
`agents/gemini-planner.md` for the whole-task version.

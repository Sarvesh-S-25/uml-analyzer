# How to run CompX

Commands for Windows PowerShell, which is what this machine uses. Where a
POSIX shell differs, the alternative is given underneath.

Two things run: a **backend** on port 8000 and a **frontend** on port 5173.
You need both, in two separate terminals.

---

## TL;DR — every day, once set up

Open two terminals.

**Terminal 1 — backend**

```powershell
cd C:\Users\sarve\uml-analyzer\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```

**Terminal 2 — frontend**

```powershell
cd C:\Users\sarve\uml-analyzer\frontend
npm run dev
```

Then open **http://localhost:5173**. Sign in, or create an account on the same
screen the first time.

Stop either with `Ctrl+C`.

---

## First-time setup

You only do this once.

### Backend

```powershell
cd C:\Users\sarve\uml-analyzer\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell refuses to run the activate script, it is the execution policy,
not the project:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then create your settings file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and set at least `SECRET_KEY`. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Everything else in `.env` is optional — the app runs with all of it blank, in
which case it does the structural comparison with no model at all. That is a
complete, usable system, and it is what the experiments use.

### Frontend

```powershell
cd C:\Users\sarve\uml-analyzer\frontend
npm install
```

There is nothing to configure. If your backend is not on
`http://localhost:8000`, create `frontend\.env` with:

```
VITE_API_BASE=http://localhost:8000
```

---

## Using a local model with Ollama

The comparison can run against a model on your own machine, with no API key and
nothing leaving the computer. This is the cheapest way to work, and for the
replay experiments it removes rate limits entirely.

### 1. Install and start Ollama

Download from [ollama.com](https://ollama.com/download), then:

```powershell
ollama pull qwen2.5-coder:7b
ollama serve
```

`ollama serve` runs in its own terminal (on Windows the installer usually starts
it as a background service already — if `ollama list` works, it is running).

**Which model.** This task asks for structured JSON about code, so a
code-tuned instruct model does far better than a general chat model of the same
size:

| Model | Pull | Notes |
|---|---|---|
| `qwen2.5-coder:7b` | `ollama pull qwen2.5-coder:7b` | Best small default. Reliable JSON. |
| `qwen2.5-coder:14b` | `ollama pull qwen2.5-coder:14b` | Better, if you have the VRAM. |
| `llama3.1:8b` | `ollama pull llama3.1:8b` | Fine, slightly weaker on JSON. |
| `deepseek-coder-v2:16b` | `ollama pull deepseek-coder-v2:16b` | Strong, heavier. |

Avoid models below about 7B. They produce prose where JSON was asked for, and
while CompX degrades gracefully when that happens (see below), you get nothing
useful out of the model half of the pipeline.

### 2. Point CompX at it

In `backend\.env`:

```
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:7b
LLM_MODE=auto
```

That is all. No API key. `OLLAMA_BASE_URL` defaults to
`http://localhost:11434/v1` and only needs setting if Ollama runs elsewhere:

```
OLLAMA_BASE_URL=http://192.168.1.50:11434/v1
```

Restart the backend. The sidebar will show `Model: qwen2.5-coder:7b` instead of
"No model configured".

### 3. The context window — read this one

This is the single most common way local models silently produce wrong answers.

Ollama defaults many models to a **2048-token context**, and when a prompt is
longer it **truncates it silently**. CompX sends the extracted structure of your
codebase, which is easily larger than that, so the model would be answering
about a fragment of your project while appearing to work perfectly normally.

**CompX handles this for you.** It sends an explicit context size with every
request, taken from `OLLAMA_NUM_CTX` in `.env`, which defaults to 16384. You do
not need a Modelfile.

If a prompt would still not fit, the Results screen says so on that run:

> This prompt is about 21,400 tokens but Ollama was asked for a 16,384-token
> context, so it may have been truncated…

If you see that, raise the value and restart the backend:

```
OLLAMA_NUM_CTX=32768
```

Bigger contexts cost VRAM. If Ollama starts failing or swapping after you raise
it, come back down and analyse a subdirectory instead of the whole repository.

The warning is about the model's half of the output only. The structural
findings on the same screen come from parsing and are unaffected either way.

### 4. What happens when a local model misbehaves

By design, the model is never trusted for the parts that matter. If it returns
prose, malformed JSON, or nothing at all:

- the **structural comparison still runs and is still exact** — missing classes,
  extra classes, missing inheritance and member differences all come from
  parsing the code and the `.mdj`, with no model involved;
- the result is marked **"Ran without the language model"** on the Results
  screen, with the reason;
- the model-authored parts — suggested tests, plain-English gaps,
  recommendations — are simply absent rather than fabricated;
- `llm_invoked` is recorded as false in the run ledger, separately from whether
  the gate *allowed* a call. The paper's numbers distinguish these two.

So a weak local model degrades the advisory half and leaves the measured half
untouched. That is deliberate.

---

## Using a hosted model instead

**OpenAI** — in `backend\.env`:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

**Anthropic** — also needs `pip install anthropic`:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-5
```

**Any other OpenAI-compatible endpoint** (Azure, OpenRouter, vLLM, LM Studio):

```
LLM_PROVIDER=compatible
LLM_BASE_URL=https://your-endpoint/v1
OPENAI_API_KEY=whatever-it-wants
LLM_MODEL=your-model
```

**No model at all** — leave everything blank, or set `LLM_MODE=offline`. The
structural comparison, the gate, versioning and all four statistics tables work
exactly the same. `offline` is what the replay experiments use, because it makes
the whole pipeline deterministic.

---

## Running the checks

From `backend\`, with the venv active:

```powershell
python -m unittest discover -s tests -t .    # 258 tests
python tools\check_imports.py
```

From `frontend\`:

```powershell
npx tsc -p tsconfig.app.json --noEmit        # must be clean
npm run build
```

The controlled test, which has known answers and runs in seconds — the fastest
way to know whether a change broke the gate:

```powershell
cd C:\Users\sarve\uml-analyzer
python research\evaluate_deviations.py --out results\
```

You should see `isomorphism` missing exactly one deviation
(`rename-class-consistently`) and nothing else missing anything.

---

## The research pipeline

This is what produces the paper's numbers.

**1. Pick projects.** See `link.md` for repositories with real StarUML diagrams
that have drifted from their code, and `docs/CORPUS-AND-SUBMISSION.md` for why
each one qualifies.

**2. Measure how stale a candidate's diagram is:**

```powershell
python research\find_stale_diagrams.py --clone https://github.com/owner/name.git --out results\
```

**3. Describe your corpus** in `research\corpus.json` (there is a worked example
in `research\corpus.recommended.json`).

**4. Replay the commits.** Every commit goes through every gate, plus a forced
full analysis as the oracle:

```powershell
python research\replay.py --corpus research\corpus.json --out results\
```

Or a single repository without a manifest:

```powershell
python research\replay.py --repo ..\MyDiary --uml research\models\mydiary.mdj --commits 40 --out results\
```

Run this with `LLM_MODE=offline` so it is deterministic and free.

**5. Build the tables and figures:**

```powershell
python research\analyze_statistics.py --runs results\runs.csv --out results\
```

This writes the four tables, the three figures and the LaTeX the paper
`\input`s. You can also see all of it in the app under **Statistics**, and
export from there.

---

## Troubleshooting

**"Backend unreachable" in the browser, but the backend is clearly running.**
Almost always CORS. The backend only accepts the origins listed in
`CORS_ORIGINS` in `.env`, which defaults to port 5173 only. If port 5173 was
busy, Vite quietly starts on 5174, 5175, 5176… and the backend then rejects it.

Look at the frontend terminal for the port it actually chose, then either free
5173, or widen the list:

```
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176
```

Restart the backend after changing `.env`.

**Port 8000 already in use.**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Stop-Process -Id <that-id> -Force
```

**"No model configured" when you have set one.** Check `LLM_MODE` is not
`offline`, and for Ollama that the daemon is up (`ollama list`). The sidebar
tells you which of the two it is.

**Ollama is running but every check reports "Ran without the language model".**
Usually the model name. `LLM_MODEL` must match `ollama list` exactly, tag
included — `qwen2.5-coder:7b`, not `qwen2.5-coder`. CompX checks this for you
and the note on the Results screen names the models it actually found:

> Ollama is running but has no model named 'qwen2.5-coder'. It has:
> qwen2.5-coder:7b, llama3.1:8b …

If instead it says it could not reach Ollama at all, the daemon is down — start
it with `ollama serve`, or set `OLLAMA_BASE_URL` if it runs on another machine.

**The suite is red.** Compare the *set* of failures against the note in
`.claude/CLAUDE.md` before assuming it is your environment. On a clean checkout
all 258 pass.

**Changes to `.env` do nothing.** It is read at startup only. Restart the
backend.

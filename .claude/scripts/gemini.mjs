#!/usr/bin/env node
/**
 * gemini.mjs — the single way this repo consults Gemini.
 *
 * The name is historical and kept deliberately: every skill, agent and doc
 * points here, and the job has not changed.
 *
 * ENGINES
 *   agy     Antigravity CLI. The default. Google-account OAuth works here,
 *           which it no longer does in the standalone gemini CLI for individual
 *           accounts (google-gemini/gemini-cli#28229).
 *   gemini  The older CLI, for anyone authenticating with GEMINI_API_KEY.
 *
 * HOW CONTEXT GETS IN — and why not the obvious way
 *
 * agy is an agent and can read files itself, so the obvious design is to name a
 * directory and let it go and look. That does not work headlessly: `agy -p`
 * ignores permission allowlists (antigravity-cli#548), so any tool call that
 * would normally prompt is denied or stalls, and you get an empty response with
 * a note that a tool was refused. The only documented workaround is
 * --dangerously-skip-permissions, which also unlocks writes and shell commands.
 *
 * So this wrapper reads the files itself and embeds them in the prompt. That is
 * better than it sounds:
 *
 *   · It is deterministic. You can see exactly what was sent.
 *   · It needs no tool permissions, so nothing stalls and nothing is refused.
 *   · Gemini genuinely cannot modify anything, because it never needs a tool.
 *   · Claude's context is still untouched — this process reads from disk, and
 *     the bytes go straight to Gemini. That was always the point of --dirs.
 *
 * --let-agent-read opts back into letting agy explore on its own, for the rare
 * case where you want that and will accept the caveats above.
 *
 * NEVER add --dangerously-skip-permissions. The value of a second opinion is
 * that it is an opinion, not a second agent editing your repo.
 *
 * Usage
 *   node .claude/scripts/gemini.mjs "your question"
 *   node .claude/scripts/gemini.mjs --dirs backend/core "your question"
 *   echo "your question" | node .claude/scripts/gemini.mjs
 *
 * Options
 *   --dirs a,b,c         files under these paths are read and sent with the question
 *   --max-kb <n>         cap on embedded source, default 250
 *   --let-agent-read     do not embed; let agy use its own tools (see caveats)
 *   -m, --model <name>   engine default if omitted
 *   --effort <level>     agy only: low | medium | high  (default high)
 *   --timeout <seconds>  default 600
 *   --engine <name>      auto | agy | gemini            (default auto)
 *   --raw                print the full JSON response
 *
 * Exit codes
 *   0  answered
 *   1  the engine returned an error, or the call timed out
 *   2  setup problem — nothing installed, or authentication failed.
 *      Retrying will not fix a 2. Stop and tell the user.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, extname, relative, resolve } from 'node:path';

const argv = process.argv.slice(2);

const opts = {
  model: '', effort: 'high', dirs: '', maxKb: 250,
  letAgentRead: false, timeout: 600, engine: 'auto', raw: false, dryContext: false, stream: false,
};
const promptParts = [];

for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '-m' || a === '--model') opts.model = argv[++i];
  else if (a === '--effort') opts.effort = argv[++i];
  else if (a === '--dirs') opts.dirs = argv[++i];
  else if (a === '--max-kb') opts.maxKb = Number(argv[++i]) || 250;
  else if (a === '--let-agent-read') opts.letAgentRead = true;
  else if (a === '--dry-context') opts.dryContext = true;
  else if (a === '--stream') opts.stream = true;
  else if (a === '--timeout') opts.timeout = Number(argv[++i]) || 600;
  else if (a === '--engine') opts.engine = argv[++i];
  else if (a === '--raw') opts.raw = true;
  else if (a === '-h' || a === '--help') { console.log(help()); process.exit(0); }
  else promptParts.push(a);
}

// These must be declared before the top-level code that calls collect(), or they
// sit in the temporal dead zone and the walk throws ReferenceError.
const SKIP_DIRS = new Set([
  'node_modules', '.git', 'dist', 'dist-ui', 'build', 'data', 'workspace',
  '__pycache__', '.venv', 'venv', '.next', 'coverage',
]);
const KEEP_EXT = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.json', '.md', '.sql', '.css',
  '.html', '.py', '.java', '.go', '.rs', '.yml', '.yaml', '.toml', '.txt', '.sh',
]);
const PER_FILE_MAX = 60_000;

const question = (promptParts.length > 0 ? promptParts.join(' ') : await readStdin()).trim();
if (opts.dryContext) {
  if (!opts.dirs) {
    console.error('gemini.mjs: --dry-context needs --dirs to collect anything.');
    process.exit(1);
  }
  const { text, files, bytes, skipped } = collect(splitDirs(opts.dirs));
  console.error(`[context] ${files} files · ${Math.round(bytes / 1024)}KB` + (skipped ? ` · ${skipped} skipped` : ''));
  if (files === 0) {
    console.error(`gemini.mjs: nothing readable under: ${opts.dirs}`);
    process.exit(1);
  }
  process.stdout.write(text + '\n');
  process.exit(0);
}

if (!question) {
  console.error('gemini.mjs: no prompt. Pass it as an argument or pipe it on stdin.');
  process.exit(1);
}

const WIN = process.platform === 'win32';

const runs = (bin) => {
  try {
    // Must be strict. On Windows, `cmd` exits 1 for a command it cannot find,
    // so accepting exit 1 here makes every probe succeed.
    const r = spawnSync(bin, ['--version'], { shell: WIN, encoding: 'utf8', timeout: 20000 });
    if (r.error) return false;
    if (/not recognized|command not found|no such file/i.test(`${r.stdout ?? ''}${r.stderr ?? ''}`)) return false;
    return r.status === 0;
  } catch {
    return false;
  }
};

/** An absolute path that exists is proof; a PATH probe is only a guess. */
function resolveBin(name) {
  const home = process.env.USERPROFILE || process.env.HOME || '';
  const local = process.env.LOCALAPPDATA || (home ? join(home, 'AppData', 'Local') : '');
  const candidates = name === 'agy'
    ? [
      local && join(local, 'agy', 'bin', WIN ? 'agy.exe' : 'agy'),
      home && join(home, '.local', 'bin', 'agy'),
      '/usr/local/bin/agy',
    ]
    : [
      home && join(home, 'AppData', 'Roaming', 'npm', 'gemini.cmd'),
      '/usr/local/bin/gemini',
    ];
  for (const c of candidates) if (c && existsSync(c)) return c;
  return runs(name) ? name : null;
}

let engine = null;
let bin = null;
for (const name of (opts.engine === 'agy' || opts.engine === 'gemini' ? [opts.engine] : ['agy', 'gemini'])) {
  const found = resolveBin(name);
  if (found) { engine = name; bin = found; break; }
}

if (!engine) {
  console.error(
    'gemini.mjs: no Gemini CLI is installed.\n' +
    '  Recommended — Antigravity CLI, which still supports Google-account sign-in:\n' +
    '    PowerShell:  irm https://antigravity.google/cli/install.ps1 | iex\n' +
    '    then run:    agy\n' +
    '  Already installed but not found? PATH has not been picked up. Either open a\n' +
    '  new terminal, or add the real directory (not the .exe) to PATH:\n' +
    '    C:\\Users\\<you>\\AppData\\Local\\agy\\bin\n' +
    '  This is a setup problem — do not work around it by answering the question yourself.',
  );
  process.exit(2);
}

// ── build the prompt ─────────────────────────────────────────────────────────

let prompt = question;

if (opts.dirs && opts.letAgentRead) {
  prompt = `Read these directories in the current repository before answering: ${opts.dirs}\n\n${question}`;
} else if (opts.dirs && engine === 'agy') {
  const { text, files, bytes, skipped } = collect(splitDirs(opts.dirs));
  if (files === 0) {
    console.error(`gemini.mjs: --dirs matched no readable source files under: ${opts.dirs}`);
    process.exit(1);
  }
  prompt =
    `You are being consulted about a codebase. The relevant files are included below.\n` +
    `Answer from them. Do not attempt to read, write or execute anything — you have\n` +
    `everything you need here, and tool calls will be refused.\n\n` +
    `${text}\n\n=== QUESTION ===\n${question}`;
  console.error(
    `[context] ${files} files · ${Math.round(bytes / 1024)}KB from ${opts.dirs}` +
    (skipped ? ` · ${skipped} skipped (over --max-kb)` : ''),
  );
}
// The older gemini CLI takes directories as a flag, so leave its prompt alone.

/**
 * A prompt carrying embedded source is far too big for a command-line argument:
 * Windows caps a command line at 32,767 characters, and `spawn` fails with
 * ENAMETOOLONG well before a 50KB payload. Anything large goes over stdin.
 *
 * For agy that means stream-json, which is a package deal — the docs are
 * explicit that `--input-format stream-json requires --output-format
 * stream-json`, so the response arrives as newline-delimited events rather than
 * one envelope. The older gemini CLI just reads a plain prompt from stdin.
 *
 * Short prompts keep using the argument form, which is the proven path.
 */
const ARG_LIMIT = 7000;
const overLimit = prompt.length > ARG_LIMIT;
const streaming = engine === 'agy' && (overLimit || opts.stream);
const pipePlain = engine === 'gemini' && overLimit;

const timeoutFlag = ['--print-timeout', `${Math.max(1, Math.round(opts.timeout / 60))}m`];
const tuning = [
  ...(opts.model ? ['--model', opts.model] : []),
  ...(opts.effort ? ['--effort', opts.effort] : []),
];

const args = engine === 'agy'
  ? (streaming
    ? ['--input-format', 'stream-json', '--output-format', 'stream-json', ...timeoutFlag, ...tuning]
    : ['-p', prompt, '--output-format', 'json', ...timeoutFlag, ...tuning])
  : [
    ...(pipePlain ? [] : ['--prompt', prompt]),
    '--output-format', 'json',
    ...(opts.model ? ['--model', opts.model] : []),
    ...(opts.dirs ? ['--include-directories', opts.dirs] : []),
  ];

if (streaming || pipePlain) {
  console.error(`[transport] ${Math.round(prompt.length / 1024)}KB prompt sent over stdin${streaming ? ' (stream-json)' : ''}`);
}

// A .exe needs no shell. Avoiding one removes Node's DEP0190 warning and the
// real hazard behind it: with a shell, the prompt is concatenated into a
// command line unescaped, so a question containing & | > or a quote breaks it.
const needsShell = WIN && !/\.exe$/i.test(bin);
const child = spawn(bin, args, {
  shell: needsShell,
  stdio: [streaming || pipePlain ? 'pipe' : 'ignore', 'pipe', 'pipe'],
});

if (streaming) {
  // One newline-delimited user event, then close stdin so the turn ends.
  child.stdin.write(JSON.stringify({ event: 'user', message: { content: prompt } }) + '\n');
  child.stdin.end();
} else if (pipePlain) {
  child.stdin.write(prompt);
  child.stdin.end();
}

let stdout = '';
let stderr = '';
let timedOut = false;

const timer = setTimeout(() => { timedOut = true; child.kill(); }, (opts.timeout + 45) * 1000);

child.stdout.on('data', (d) => { stdout += d; });
child.stderr.on('data', (d) => { stderr += d; });

child.on('error', (err) => {
  clearTimeout(timer);
  console.error(
    err.code === 'ENOENT'
      ? `gemini.mjs: "${bin}" could not be executed.`
      : `gemini.mjs: could not start ${engine} — ${err.message}`,
  );
  process.exit(2);
});

child.on('close', (code) => {
  clearTimeout(timer);

  if (timedOut) {
    console.error(`gemini.mjs: timed out after ${opts.timeout}s.\n  Narrow the question, or pass fewer directories to --dirs.`);
    process.exit(1);
  }

  // Streaming emits init / step_update / result as newline-delimited JSON; the
  // answer is in the single result event. Non-streaming is one envelope, and the
  // two share field names, so everything below is common.
  let parsed = null;
  if (streaming) {
    for (const line of stdout.split('\n')) {
      const s = line.trim();
      if (!s) continue;
      try {
        const ev = JSON.parse(s);
        if (ev.event === 'result' && ev.result) parsed = ev.result;
      } catch { /* a partial or non-JSON line is not fatal */ }
    }
  } else {
    try { parsed = JSON.parse(stdout); } catch { /* handled below */ }
  }

  // Only scan raw stdout for the auth-problem regex when it did NOT parse as a
  // successful envelope — a well-formed answer can legitimately discuss auth,
  // OAuth or credentials as its actual subject matter (e.g. "check if the CLI's
  // credential store exists on disk"), and matching against that would flag a
  // real, successful answer as an authentication failure. `stderr` has no such
  // ambiguity — a real CLI never explains authentication concepts there — so it
  // is always checked. `parsed.error` gets its own auth check below.
  if (looksLikeAuthProblem(stderr) || (!parsed && looksLikeAuthProblem(stdout))) {
    console.error(`gemini.mjs: ${engine} could not authenticate.\n  ${firstLines(stderr || stdout)}\n${AUTH_HINT}`);
    process.exit(2);
  }

  if (!parsed) {
    if (stdout.trim() && code === 0) {
      process.stdout.write(stdout.trim() + '\n');
      process.exit(0);
    }
    console.error(`gemini.mjs: ${engine} produced no usable output (exit ${code}).\n  ${firstLines(stderr)}`);
    process.exit(1);
  }

  if (parsed.error) {
    const detail = (typeof parsed.error === 'string'
      ? parsed.error
      : `${parsed.error.type ?? ''} ${parsed.error.message ?? ''}`).trim();
    if (looksLikeAuthProblem(detail)) {
      console.error(`gemini.mjs: authentication failed.\n  ${detail}\n${AUTH_HINT}`);
      process.exit(2);
    }
    console.error(`gemini.mjs: ${engine} returned an error: ${detail}`);
    process.exit(1);
  }

  const status = String(parsed.status ?? '').toLowerCase();
  if (status && status !== 'success' && status !== 'ok') {
    console.error(`gemini.mjs: ${engine} finished with status "${parsed.status}".\n  ${firstLines(stderr)}`);
    process.exit(1);
  }

  if (opts.raw) {
    process.stdout.write(JSON.stringify(parsed, null, 2) + '\n');
    process.exit(0);
  }

  const answer = String(parsed.response ?? '').trim();

  if (!answer) {
    console.error(
      `gemini.mjs: ${engine} returned an empty answer.\n` +
      (/soft-den|not allowed|requires approval|permission/i.test(stderr)
        ? '  It wanted a tool it cannot use headlessly. Pass the files instead:\n' +
          '    --dirs <the directories it needs>\n'
        : `  ${firstLines(stderr)}\n`),
    );
    process.exit(1);
  }

  process.stdout.write(answer + '\n');

  const bits = [engine];
  const u = parsed.usage ?? {};
  if (u.input_tokens || u.output_tokens) bits.push(`${u.input_tokens ?? '?'} in / ${u.output_tokens ?? '?'} out`);
  if (parsed.duration_seconds) bits.push(`${Math.round(parsed.duration_seconds)}s`);
  if (parsed.num_turns) bits.push(`${parsed.num_turns} turns`);
  console.error(`[${bits.join(' · ')}]`);

  process.exit(0);
});

// ── reading the repo ─────────────────────────────────────────────────────────

// A function declaration, not a const arrow: this is called from top-level code
// above, and a const would sit in the temporal dead zone exactly like SKIP_DIRS did.
function splitDirs(s) {
  return s.split(',').map((x) => x.trim()).filter(Boolean);
}

function collect(dirs) {
  const root = process.cwd();
  const budget = opts.maxKb * 1024;
  let bytes = 0;
  let files = 0;
  let skipped = 0;
  const chunks = [];

  const walk = (dir, depth = 0) => {
    if (depth > 8) return;
    let entries;
    try { entries = readdirSync(dir); } catch { return; }
    for (const name of entries.sort()) {
      if (SKIP_DIRS.has(name)) continue;
      const full = join(dir, name);
      let st;
      try { st = statSync(full); } catch { continue; }
      if (st.isDirectory()) { walk(full, depth + 1); continue; }
      if (!KEEP_EXT.has(extname(name))) continue;
      if (st.size > PER_FILE_MAX) { skipped++; continue; }
      if (bytes + st.size > budget) { skipped++; continue; }
      let body;
      try { body = readFileSync(full, 'utf8'); } catch { continue; }
      chunks.push(`--- ${relative(root, full).split('\\').join('/')} ---\n${body}`);
      bytes += st.size;
      files++;
    }
  };

  for (const d of dirs) {
    const abs = resolve(root, d);
    if (!existsSync(abs)) {
      console.error(`[context] warning: "${d}" does not exist, skipping`);
      continue;
    }
    statSync(abs).isDirectory() ? walk(abs) : walkFile(abs);
  }

  function walkFile(abs) {
    try {
      chunks.push(`--- ${relative(root, abs).split('\\').join('/')} ---\n${readFileSync(abs, 'utf8')}`);
      files++;
    } catch { /* unreadable */ }
  }

  return { text: `=== FILES ===\n\n${chunks.join('\n\n')}`, files, bytes, skipped };
}

// ── errors ───────────────────────────────────────────────────────────────────

/**
 * Auth failures are setup problems, not transient ones, so they exit 2 like a
 * missing binary. Retrying will not fix them, and answering the question
 * unreviewed while implying it was reviewed is worse than stopping.
 */
function looksLikeAuthProblem(text) {
  return /no longer supported|antigravity\.google\/?$|unauthenticated|failed to sign in|sign ?-?in failed|oauth|credential|api key not valid|GOOGLE_CLOUD_PROJECT|\b401\b|\b403\b/i
    .test(String(text || ''));
}

const AUTH_HINT = `
  If this is the standalone gemini CLI: Google-account sign-in no longer works
  for individual accounts (gemini-cli#28229). Use the Antigravity CLI instead:

    PowerShell:  irm https://antigravity.google/cli/install.ps1 | iex
    then run:    agy        (browser sign-in; token goes to Windows Credential Manager)

  Or use a key: copy .gemini/.env.example to .gemini/.env and set GEMINI_API_KEY
  from https://aistudio.google.com/apikey.

  Check nothing is hijacking the auth lane:
    echo %GEMINI_API_KEY% %GOOGLE_API_KEY% %GOOGLE_CLOUD_PROJECT%`;

function firstLines(text, n = 6) {
  return String(text || '').trim().split('\n').slice(0, n).join('\n  ');
}

function readStdin() {
  return new Promise((res) => {
    if (process.stdin.isTTY) return res('');
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { data += c; });
    process.stdin.on('end', () => res(data));
  });
}

function help() {
  return `gemini.mjs — consult Gemini through the local CLI (read-only).

  node .claude/scripts/gemini.mjs "question"
  node .claude/scripts/gemini.mjs --dirs backend/core "question"

  --dirs a,b,c         files under these paths are read and sent with the question
  --max-kb <n>         cap on embedded source, default 250
  --let-agent-read     let agy explore with its own tools instead (unreliable headlessly)
  --dry-context        print exactly what --dirs would send, then exit
  --stream             force the stdin stream transport (auto above ~7KB)
  -m, --model <name>   engine default if omitted
  --effort <level>     agy only: low | medium | high  (default high)
  --timeout <seconds>  default 600
  --engine <name>      auto | agy | gemini            (default auto)
  --raw                full JSON response

  Exit 2 means a setup problem — nothing installed, or auth failed. Stop.`;
}

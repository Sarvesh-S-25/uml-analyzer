---
name: frontend-design
description: Design UI through the Google Stitch MCP before writing any front-end code. Use this skill whenever the task touches a screen, page, view, component, layout, modal, form, dashboard, or design token in this project's frontend — including new UI, restyling existing UI, fixing spacing or visual hierarchy, or any "make this look better / this looks off" request. Use it even when Stitch is not mentioned and even when the request sounds like a small styling tweak.
when_to_use: Triggers include "build a page", "add a screen", "create a component", "design the UI", "restyle this", "the layout looks off", "make this look better", "add a modal/form/dashboard", or any work on files under frontend/src/.
paths: frontend/src/**, **/*.tsx, **/*.jsx, **/*.css
allowed-tools: mcp__stitch__*
---

# Front-end design via Stitch

UI in this project is designed in Stitch first, then translated into the
codebase. Do not hand-write layout or styling from scratch.

There are exactly three screens (`Dashboard`, `ProjectWorkspace`,
`StatisticsPage`) plus their sub-components — check whether the request is
really a fourth screen or a variant of one of these before generating anything
new.

## Procedure

1. Call `list_projects`. This repo's Stitch project is named after the repo
   (`uml-analyzer` or similar). If it does not exist, create it with
   `create_project`.
2. Call `list_screens`. If a screen already matches the request, use it — do
   not generate a duplicate.
3. If no screen matches, call `generate_screen_from_text` with a prompt
   covering: the screen's purpose, the key elements it must contain, and every
   constraint from the section below.
4. Retrieve the result with `fetch_screen_code`. Use `fetch_screen_image` when
   you need to describe the visual result back to the user.
5. Translate the output into this codebase's conventions. Never paste Stitch
   markup verbatim — map it onto existing components (`frontend/src/components/
   ui.tsx` has the shared primitives: Card, Button, Badge, Banner, EmptyState,
   Spinner) and existing Tailwind tokens, keep this codebase's file and prop
   naming.
6. Report the Stitch project and screen name so the user can open and iterate
   on the design directly.

## Constraints for every Stitch prompt

- Stack: **React 19 + TypeScript + Tailwind v4** (`@tailwindcss/vite`). Utility
  classes are the norm here — unlike a hand-rolled-CSS project, do not avoid
  them, but do prefer this project's existing token scale over arbitrary
  values.
- Match the design tokens already defined in `frontend/src/index.css` — no new
  colours, spacing values, or font sizes invented ad hoc.
- **Conformance status colour is never the only signal.** Status (convergence /
  divergence / absence, or pass/fail) must stay encoded three ways — border
  colour, a glyph, and a written label — per `frontend/src/lib/theme.ts`. The
  status palette puts green and red close together under deuteranopia, and a
  figure exported for the paper may be printed in greyscale.
- The dependency graph view (`components/GraphView.tsx`) renders from
  `lib/layout.ts`, a deterministic Sugiyama-style layout with **no physics and
  no randomness** — never propose a force-directed or animated layout for it;
  the same project must render pixel-identically every run because it's used
  as a paper figure.
- Reuse `components/ui.tsx` primitives and the layout patterns already in
  `components/`.
- Mobile-first is not a real constraint here (this is a research tool used at
  a desk), but WCAG AA contrast and keyboard accessibility (visible focus
  states, labelled inputs, escapable overlays) still apply.

## Iterating on an existing screen

For a change to UI that already has a Stitch screen, fetch that screen and
regenerate from it rather than starting a new one. Keep one screen per view so
the Stitch project stays a usable record of the design.

## When to skip Stitch

Bug fixes, state or data-fetching changes, copy edits, and single-property
tweaks (one padding value, one colour swap). Say that you are skipping Stitch
and why, then make the change directly.

## If Stitch is unavailable

Distinguish two failure modes and handle them differently.

**Quota or rate limit exhausted** — the error mentions quota, credits, limits,
`RESOURCE_EXHAUSTED`, or HTTP 429. Do not retry, and do not stop working. Say
in one line that Stitch credits are exhausted and you are designing directly,
then build the UI yourself. Every constraint in this file still applies: same
tokens, same `components/ui.tsx` patterns, same accessibility bar, same
determinism requirement for the graph view. Before writing code, state the
layout you intend in two or three sentences so the user can redirect you
cheaply. Assume Stitch stays unavailable for the rest of the session — do not
call it again unless asked.

**Broken connection or auth** — the tools are missing entirely, or the error
mentions authentication, credentials, an invalid API key, or dynamic client
registration. This is a configuration problem, not a credits problem. Stop and
tell the user, and do not fall back; they would rather fix the MCP setup than
merge design that bypassed it.

If you cannot tell which it is, quote the error and ask.

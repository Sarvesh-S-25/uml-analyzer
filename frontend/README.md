# Frontend

React 19 + Vite + Tailwind v4. Three screens, one dark theme, no chart library.

## Run it

```powershell
npm install
npm run dev
```

Opens on <http://localhost:5173> and expects the backend on
<http://localhost:8000>. To point elsewhere, copy `.env.example` to `.env.local`
and set `VITE_API_BASE`.

```powershell
npx tsc -p tsconfig.app.json --noEmit   # type check
npm run build                            # production build
```

## The three screens

| Screen | Component | Shows |
|---|---|---|
| Dashboard | `Dashboard.tsx` | Projects, GitHub import, create |
| Project | `ProjectWorkspace.tsx` | Three tabs: **Setup** (code + diagram + Run), **Results** (report + graph), **History** (versions, cost, repeatability) |
| Results | `StatisticsPage.tsx` | Four tables, two charts, the gate explainer |

## Layout

| Path | Does |
|---|---|
| `lib/api.ts` | Every backend call, typed |
| `lib/layout.ts` | **Deterministic graph layout** — Sugiyama-style, no physics |
| `lib/statsTypes.ts` | Mirrors `backend/stats/report.py` exactly |
| `lib/theme.ts` | Conformance status: colour, glyph, label |
| `components/GraphView.tsx` | The static graph, with SVG export |
| `components/charts/` | Hand-written SVG — `primitives`, `BarChart`, `DriftChart` |
| `index.css` | Every design token |
| `vite.config.ts` | Build config: React plugin, Tailwind v4, dev-server proxy |

## Two conventions worth knowing

**The graph never moves.** `lib/layout.ts` computes fixed positions from the
graph alone — longest-path layering, barycentre ordering, no randomness. The
same project produces the same picture every time, which is what makes it usable
as a paper figure. If nodes drift, you are running a cached old build: delete
`node_modules/.vite`.

**Colour never carries meaning alone.** Conformance status is encoded three ways
— border colour, a glyph on the node, and the written label in the legend —
because the status palette puts green and red close together under deuteranopia
and a printed figure may be greyscale. Three categorical hues clear the
colour-blindness separation floors on this surface; a fourth does not, so charts
distinguishing four gates use direct labels instead.

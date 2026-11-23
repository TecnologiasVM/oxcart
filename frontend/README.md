# First Issue · Knowledge Graph — Frontend

Next.js (App Router, TypeScript) explorer for the Costa Rica 1863 First Issue knowledge graph.
Talks to the First Issue GraphRAG backend at `http://localhost:8090`.

## Constraints (owner-mandated)

- **No direct LLM / OpenAI / Anthropic calls in the frontend.** All data comes from the
  READ-ONLY backend. There is no answer-generation phase — the sources are the answer.
- **No vector/embedding fields are ever surfaced.** The backend strips them; `lib/api.ts`
  strips any key matching `/embed|vector/i` again on the client (`stripVectors`).

## Stack

- Next.js (App Router) + React + TypeScript (manual scaffold, no `create-next-app`).
- Cytoscape.js core (not a React wrapper) mounted client-side in `app/components/GraphView.tsx`.
- Design system: **ink-cobalt-paper v2.0** — editorial, reductionist, flat. Palette tokens in
  `app/globals.css`; Cytoscape node styling in `lib/cytoscape-style.ts`.

## Run

```bash
npm ci               # install the locked dependencies
npm run dev          # http://localhost:3000, this machine only (expects backend on :8090)
npm run dev:lan      # same, reachable from other devices (set ALLOWED_DEV_ORIGINS)
npm run build
npm run start        # production build, this machine only (start:lan for all interfaces)
```

No env file is needed by default: the browser calls relative `/api/*` and Next.js proxies
those calls to the backend at `127.0.0.1:8090` (see `next.config.ts`). `.env.example`
lists the optional overrides.

## Routes

| Route               | File                             | Purpose                                         |
| ------------------- | -------------------------------- | ----------------------------------------------- |
| `/`                 | `app/page.tsx`                   | Redirects to `/research`.                       |
| `/research`         | `app/research/page.tsx`          | First Issue overview (health, totals, roster).  |
| `/research/explore` | `app/research/explore/page.tsx`  | Interactive graph + node detail.                |
| `/research/query`   | `app/research/query/page.tsx`    | Grounded retrieval evidence + subgraph.         |
| `/research/mena`    | `app/research/mena/page.tsx`     | Mena catalogue, Surface Mail issues by year.    |

The header and footer are presentation-only components (`app/components/AppHeader.tsx`,
`AppFooter.tsx`); data fetching lives in `lib/api.ts` and the view components.

## Backend contract

Endpoints consumed (see `lib/types.ts` + `lib/api.ts`):
`GET /api/health`, `/api/overview`, `/api/graph`, `/api/graph/stamp/{cno}`,
`/api/node?node_id=`, `/api/examples`, `/api/mena/*`, and `POST /api/query`.

## Pictures

The question page draws pictures from one figures host, named at build time by
`NEXT_PUBLIC_FIGURES_BASE` (https; unset, no picture is drawn). `lib/figures.ts` builds every address
as `<base>/<id>.png` from an id of 20 hex characters; nothing else in a response or a stored turn
becomes an address.

- **Figures of the cited pages.** The backend names a passage's figures by id, pixel size and class
  (`backend/README.md`, "Figures"). Under the newest answer, one group per cited page, no picture taller
  than 200 px; inside Evidence, at their own size under their passage. An older answer counts them.
- **The first screen's plate.** `<base>/first-screen.json`, a list of `{digest, width, height}` in order,
  read at run time: the set is changed on the host, with no build. Missing, malformed, or not there within
  two seconds: no plate, and the first screen is as it was.

The browser tests route the host `https://figures.invalid`: build with
`NEXT_PUBLIC_FIGURES_BASE=https://figures.invalid` before `npx playwright test` against a built site.

## Tests

```bash
npx playwright install chromium   # one-time browser download
npx playwright test               # smoke tests in tests-e2e/ (no backend needed)
npx playwright test --config=playwright.shadow.config.ts   # full suite in tests/ (needs both servers running)
```

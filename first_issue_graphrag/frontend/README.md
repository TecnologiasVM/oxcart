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
npm install          # already run during scaffold
npm run dev          # http://localhost:3000  (expects backend on :8090)
npm run build
npm run start
```

Set the backend origin in `.env.local`:

```
NEXT_PUBLIC_API_BASE=http://localhost:8090
```

## Routes

| Route       | File                          | Purpose                                            |
| ----------- | ----------------------------- | -------------------------------------------------- |
| `/`         | `app/page.tsx`                | First Issue overview (health, totals, roster).     |
| `/explore`  | `app/explore/page.tsx`        | Interactive graph + node detail.                   |
| `/query`    | `app/query/page.tsx`          | Grounded retrieval evidence + subgraph.            |

## Backend contract

Endpoints consumed (see `lib/types.ts` + `lib/api.ts`):
`GET /api/health`, `/api/overview`, `/api/graph`, `/api/graph/stamp/{cno}`,
`/api/node?node_id=`, `/api/examples`, and `POST /api/query`.

## Tests

```bash
npx playwright install   # one-time browser download
npx playwright test      # smoke tests in tests-e2e/ (degrade gracefully w/o backend)
```

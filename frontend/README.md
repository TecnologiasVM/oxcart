# Oxcart — Frontend

The page, in Next.js (App Router), React and TypeScript. Two parts:

- **The question page** (`/`) and **How it works** (`/how-it-works`): the hosted site. A question box, the
  evidence (catalogue cards and passages), the written answer with its sources, the Evidence panel, and the
  conversations, kept in the browser only. The page is built as a static site for the host (`npm run build:hosted`).
- **The First Issue explorer** (`/research`): a local research tool over the 1863 First Issue graph; the hosted
  site does not ship it. See [docs/EXPLORER.md](../docs/EXPLORER.md).

## What the page does and does not do

- **It calls no language model and holds no key.** Every answer comes from the backend (`POST /api/chat`), which
  writes it ([backend/README.md](../backend/README.md)). The page draws what the model wrote as text only: no
  markup and no link comes from it.
- **No vector or embedding field is shown.** The backend strips them; `lib/api.ts` strips any key matching
  `/embed|vector/i` again on the client (`stripVectors`).

## Stack

- Next.js (App Router) + React + TypeScript.
- Cytoscape.js core (not a React wrapper), for the explorer's graph, mounted client-side in
  `app/components/GraphView.tsx`. The Evidence panel's graph is SVG (`app/components/ask/EvidencePanel.tsx`,
  laid out by `lib/answer-graph.ts`).
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
| `/`                 | `app/page.tsx`                   | The question page (`app/components/Chat.tsx`).  |
| `/how-it-works`     | `app/how-it-works/page.tsx`      | How it works, and how it was measured.          |
| `/research`         | `app/research/page.tsx`          | First Issue overview (health, totals, roster).  |
| `/research/explore` | `app/research/explore/page.tsx`  | Interactive graph + node detail.                |
| `/research/query`   | `app/research/query/page.tsx`    | Grounded retrieval evidence + subgraph.         |
| `/research/mena`    | `app/research/mena/page.tsx`     | Mena catalogue, Surface Mail issues by year.    |

The header and footer are presentation-only components (`app/components/AppHeader.tsx`,
`AppFooter.tsx`); data fetching lives in `lib/api.ts` and the view components.

## Backend contract

The question page (`lib/ask.ts`, `lib/web.ts`): `GET /api/health`, `POST /api/session` (the human check, on the
hosted site), `POST /api/ask`, `POST /api/chat`, `POST /api/chat/web` (the web part).
The explorer (`lib/types.ts` + `lib/api.ts`): `GET /api/overview`, `/api/graph`, `/api/graph/stamp/{cno}`,
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

## The web part

With the build setting `NEXT_PUBLIC_WEB` on (`1`, `true`, `yes`, `on`), an answer whose sources cover part of the
question, or none of it, can get a part written from a web search (`lib/web.ts`; backend: `backend/README.md`,
"The web step"). The chat reply then carries a ticket; once the answer is on screen the page sends the question as
it was searched, the answer's text and the ticket to `POST /api/chat/web`, once, and draws what comes back last in
the turn: the block, the line "A web search found nothing to add." under "not covered", or nothing. Titles, hosts
and sentences are text; an address becomes a link only after the page checks it again (https, no user name), with
`rel="noopener noreferrer"`, in a new tab. The web part is kept with its turn; its ticket is not, so a turn read
back from storage never asks again. A follow-up never sends it. The privacy paragraph under "Details" names Tavily
only in such a build.

Off (the default) a ticket is ignored, no request is made, and the page is what it was. The browser tests are built
with `NEXT_PUBLIC_WEB=1` (CI, `playwright.config.ts`); build and run them with `NEXT_PUBLIC_WEB=` (empty) to test
the off build: `tests-e2e/web.spec.ts` then runs its off tests and skips the others.

## Tests

```bash
npx playwright install chromium   # one-time browser download
npx playwright test               # the question page's tests in tests-e2e/, the backend mocked; CI runs these
npx playwright test --config=playwright.shadow.config.ts   # the explorer's tests in tests/ (needs both servers running)
```

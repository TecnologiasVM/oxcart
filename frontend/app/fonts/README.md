# Fonts

The three type families of the pages, as files, so that a build needs nothing from a font service.

| Family | Cuts | Files |
|---|---|---|
| Newsreader | 300 and 400, upright and italic | `newsreader-latin-*.woff2` |
| Inter | 400 and 500 | `inter-latin-*.woff2` |
| JetBrains Mono | 400, 500 and 600 | `jetbrains-mono-latin-*.woff2` |

Each file is the Latin subset (it holds the Spanish letters and marks), copied unchanged from the npm packages
`@fontsource/newsreader`, `@fontsource/inter` and `@fontsource/jetbrains-mono`, version 5.3.0. The fonts are
under the SIL Open Font License 1.1; each family's licence, with its copyright line, is in `LICENSE-<family>.txt`.
`app/layout.tsx` loads them with `next/font/local`.

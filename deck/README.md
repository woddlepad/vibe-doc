# rsi-doc pitch deck

An 11-slide web deck about the self-improving diagnosis harness, in seven visual directions
(Specimen, Nocturne, Lightbox, and four Monograph variants). Built with Vite, React and
[Paper Shaders](https://github.com/paper-design/shaders).

```bash
npm install
npm run dev        # http://localhost:5173
npm run build && npm run preview
```

Open a direction from the landing page, then use the arrow keys. Keys 1–7 switch direction,
F toggles full screen, Esc returns to the landing page.

## Where things live

| Path | What |
|---|---|
| `src/data.ts` | Numbers from `runs/` and `harnesses/registry.json` (baseline, v001, candidates, flips) |
| `src/visit-mqx-104.json` | Before/after transcripts for the chat slide, exported from the dev eval results |
| `src/case-mqx-104.json` | The raw AgentClinic record shown on the dataset slide |
| `src/themes.ts` | The seven directions: palette, type, shader settings, portrait/hoop options |
| `src/slides*.tsx` | Slide content; `src/charts.tsx` holds the charts |
| `public/people/`, `public/hoop.webp` | Images used on slides (generated with Codex image generation) |
| `art-src/` | Full-size originals of those images |
| `public/agentclinic-figure.webp` | Figure from Schmidgall et al., *AgentClinic* (arXiv:2405.07960) |

To share a running preview, `vite.config.ts` allows `*.trycloudflare.com` hosts for
`cloudflared tunnel --url http://127.0.0.1:4173`.

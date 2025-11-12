# Environment Lock

- OS image: `node:20-bullseye-slim`
- Node: 20.x LTS (from base image)
- TypeScript: `5.6.3` (invoke via `npx -p typescript@5.6.3 tsc`)
- Package managers (corepack):
  - pnpm: `9.12.0`
  - yarn: `4.5.1`
  - npm: bundled with Node 20
- System tools: `git`, `/usr/bin/time`, `python3` + `requests`
- Node flags: `NODE_OPTIONS=--max-old-space-size=8192`
- Project structure: scripts under `scripts/`, repos under `projects/`, logs under `logs/`
- Repro commands:
  - Freeze corpus: `python3 scripts/freeze_corpus.py`
  - Run bench: `node scripts/bench.js` (ensure it uses `TS_VERSION` if calling `tsc`)
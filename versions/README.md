# Versions

Frozen snapshots of each autoresearch run. Each folder captures:

- `meta.yaml` — structured metadata (asset, dates, counts, peak metrics, known limitations)
- `results.tsv` — journal snapshot at the moment the run was declared done
- `strategy.final.py` (v0.1.0) OR `strategies/` (v0.2.0+, multi-strategy runs) — the final strategy file(s)
- `retrospective.md` — full post-mortem + interpretation
- `run.log` — (optional) the last backtest's raw output

The corresponding git state is preserved via a tag (e.g. `v0.1.0` → peak commit of that run). The original research branch is kept around too (e.g. `autoresearch/apr22`).

Versioning is loose — use semver spirit, not letter:
- **Major** (1.0, 2.0): significant harness / methodology change (new oracle, new loop architecture)
- **Minor** (0.2, 0.3): new asset, new timerange, new program.md, or otherwise distinct research question
- **Patch** (0.1.1, 0.1.2): minor reruns of the same setup (re-seed, small tweaks, reproducibility checks)

## Rules

**Archives are immutable.** Once a version folder is merged to master, do not
modify files inside `versions/<version>/`. If something in a past archive is
wrong or needs extension, write `versions/<version>/errata.md` or bump to a
patch version. The history is load-bearing — the whole point of this folder
is that we can read an archived retrospective a year from now and trust it
reflects what we thought at the time.

**Scaffold PRs and version-archive PRs are separate.** A PR that adds a new
`versions/<version>/` folder should touch nothing outside `versions/` (+
`.gitignore` if needed). A PR that changes `prepare.py`, `run.py`,
`config.json`, `program.md`, etc. should not touch `versions/`. This keeps
review surfaces distinct: scaffold PRs get real review, version PRs are
rubber-stamp.

## Index

| Version | Date | Asset | Experiments | Peak Sharpe | Headline |
|---|---|---|---|---|---|
| [0.1.0](0.1.0/) | 2026-04-22 | BTC/USDT + ETH/USDT @ 1h | 99 | 1.44 (true edge: 0.19) | Pattern validated; agent self-reversed Goodhart exploits |
| [0.2.0](0.2.0/) | 2026-04-23 | BTC/USDT + ETH/USDT @ 1h | 81 | 0.67 (clean, no gaming) | Multi-strategy architecture: 5 paradigms tested / 3 kept / zero Goodhart / 3.5× better true-edge than v0.1.0 |
| [0.3.0](0.3.0/) | 2026-04-24 | 5-pair crypto @ 1h+4h+1d | 39 | **1.07** (clean, no gaming) | MTF + 5-pair + per-pair reporting; first project-wide clean Sharpe > 1; first fork event with isolation experiment; cross-pair volume asymmetry + patient-exit paradigm asymmetry findings |

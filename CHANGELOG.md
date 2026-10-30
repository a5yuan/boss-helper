# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-22

### Highlights

- Stable release of BOSS-Helper as a CDP-based browser assistant
- Desktop GUI (pywebview) and CLI modes
- Vue component tree extraction for job card data
- Detail panel reader via `$data.currentJob` / `$data.jobDetail`
- Configurable browse pacing for natural interaction rhythm
- JSON + Markdown output with deduplication

### Architecture

- Pure CDP communication via `Runtime.evaluate` (single command pattern)
- Login state detection: `bst` cookie → `ka=header-username` DOM fallback
- Interruptible sleep for responsive stop handling
- Full-chain debug tracer (NDJSON + human-readable logs)
- Auto port discovery for dev mode (backend + Vite)

---

## [0.1.0] - 2026-01-01

- Initial release (BOSS 直聘 V14)

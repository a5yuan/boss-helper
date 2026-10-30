# BOSS-Helper

[简体中文](README.md) | English

> A **browser assistant** for zhipin.com.
> Reads job information from the **currently displayed page** in your browser.
> **Zero direct HTTP requests to zhipin.com.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What is this?

BOSS-Helper is a lightweight tool that runs in a **pywebview desktop window** or as a **CLI script**.

It connects to your existing Chrome/Edge browser via Chrome DevTools Protocol (CDP) and reads the job-card data that is already rendered on the page — without sending any requests to zhipin.com.

**Different from Traditional Tools:**
Traditional tools often rely on automated API requests to batch harvest data. In contrast, this tool is based on your real, physical browsing (you search, you login). The tool only reads the page you are currently viewing via local memory. You are in control; the tool is just your assistant.

---

## Design Principles

| Principle | What it means |
|---|---|
| **Local state reading only** | Reads data exclusively from the already rendered DOM |
| **Reuse user session** | Relies on authentic, user-initiated login sessions in the browser |
| **User-driven navigation** | Users handle key navigation (e.g., search); the tool assists with reading |
| **Native environment** | Preserves the pristine state of the browser without intrusive core injections |
| **Purely educational** | Focused on technical exploration with a minimalist architecture |

---

## Quick Start

### Desktop GUI

```powershell
# 1. Clone the repo
git clone https://github.com/yourusername/boss-helper.git
cd boss-helper

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install GUI dependencies
pip install "boss-helper[gui]"

# 4. Run
python run_gui.py
```

### CLI

```powershell
python main.py --new -b chrome -n 20
```

---

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  Your Browser (Chrome / Edge)                       │
│  ┌─────────────────────────────────────────────┐   │
│  │  https://www.zhipin.com/web/geek/jobs       │   │
│  │  (You logged in. You searched. You scrolled)│   │
│  └─────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────┘
                   │  Chrome DevTools Protocol (CDP)
                   │  ← WebSocket
┌──────────────────▼──────────────────────────────────┐
│  BOSS-Helper (CLI or pywebview)                     │
│   • VueExtractor    → reads job cards from DOM      │
│   • DetailPanelReader → reads detail panel state     │
│   • OutputWriter    → saves to jobs_*.json           │
└─────────────────────────────────────────────────────┘
```

No requests leave your machine to zhipin.com. All data exchange happens over a local WebSocket channel.

---

## Project Structure

```
boss-helper/
├── main.py                  # CLI entry point
├── run_gui.py               # Desktop GUI launcher (pywebview + uvicorn)
├── server/                  # FastAPI backend (serves webui + WebSocket)
│   ├── app.py
│   ├── session.py
│   └── tracer.py
├── webui/                   # Vue 3 + Vite + Tailwind frontend
│   └── src/
│       ├── components/       # Vue components
│       ├── stores/           # Pinia state (engine.ts)
│       └── api.ts            # API client
├── src/
│   ├── collector.py          # Main collection loop
│   ├── config.py             # Config loader
│   ├── core/
│   │   ├── browser.py        # CDP browser manager
│   │   ├── extractor.py      # VueExtractor + DetailPanelReader
│   │   └── js_loader.py      # JS script injector
│   ├── utils/
│   │   ├── salary.py         # Salary string parser
│   │   └── browser_behavior.py  # Browser interaction utilities
│   └── storage/
│       └── writer.py         # JSON / Markdown output
├── docs/
│   ├── zhipin-robots.md      # Official zhipin.com robots.txt reference
│   ├── prd.md                # Product requirements
│   └── visualize_prd.md      # Visual spec
├── CHANGELOG.md
├── LEGAL.md
├── LICENSE
├── SECURITY.md
└── CODE_OF_CONDUCT.md
```

---

## Known Limitations

1. **Salary Garbling**: Due to special CSS font rendering techniques used by the platform, the extracted salary text might occasionally be garbled. Please rely on what your human eyes see in the browser as the source of truth.
2. **Login required**: You must be logged into zhipin.com in your browser before starting.
3. **Rate Limiting**: Using the tool to assist browsing may still trigger the platform's frontend rate limiting. Please control your usage pace. Use at your own risk.

---

## Compliance

See [LEGAL.md](LEGAL.md) for the full legal disclaimer.

In short: This tool reads data already displayed in your browser via CDP. You are responsible for ensuring your use complies with zhipin.com's Terms of Service and applicable laws.

See [docs/zhipin-robots.md](docs/zhipin-robots.md) for the official `robots.txt` reference used in development.

---

## Contributing

Contributions are welcome. Please read our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License

MIT. See [LICENSE](LICENSE).

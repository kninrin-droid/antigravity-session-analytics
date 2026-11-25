<div align="center">

# Antigravity Session Analytics

**Live per-session cost, token, cache & context analytics right inside Antigravity's side panel.**

[![Python 3](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](#requirements)
[![Node.js](https://img.shields.io/badge/Sidecar-Node.js-339933?logo=nodedotjs&logoColor=white)](#how-it-works)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-10b981)](#how-it-works)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.md) · [Tiếng Việt](README.vi.md)

</div>

---

A standalone UI plugin for **Google Antigravity** that tracks **only the currently open conversation** in real time — zero extra ports, zero background scanning, zero external dependencies.

### What it shows

- **Optimum Score (0–100):** Live recommendation (*Just started / Continue / Near limit / Start fresh*) based on current context size, recent cache hit rate, uncached token creep, and conversation depth.
- **Cost & Cache Savings:** Exact USD + VND estimate broken down into **New Input**, **Cache Read**, and **Output**, plus total dollars saved by prompt caching.
- **Stacked Step Chart:** Interactive 3-color stacked cost chart (**New Input** · **Cache** · **Output**) overlaid with the **Context growth** curve. Click any bar to jump straight to that step's bill.
- **Step / Turn / Model & Tool Breakdown:** Inspect every step's `In / Cache / Out`, context delta (`Δ`), tools called, expandable per-step invoice, per-prompt cost summary, and 1-click **CSV export**.
- **Native Theme & Low Overhead:** Inherits Antigravity's Light/Dark theme automatically and caches parsed results by `transcript.jsonl` `mtime:size` (sub-2 ms when unchanged).

## Quick Install

Requires **Google Antigravity** and **Python 3** on `PATH` (`python`, `py`, or `python3`).

```bash
# macOS / Linux
git clone https://github.com/kninrin-droid/antigravity-session-analytics.git ~/.gemini/config/plugins/antigravity-session-analytics
```

```powershell
# Windows (PowerShell)
git clone https://github.com/kninrin-droid/antigravity-session-analytics.git "$HOME\.gemini\config\plugins\antigravity-session-analytics"
```

Then restart Antigravity (or toggle **Session Analytics** on under **Customizations → Installed**) and open **Session Analytics** from the right-hand side panel `+` menu.

## How it works

<details>
<summary>Architecture, files & testing</summary>

```text
antigravity-session-analytics/
├── plugin.json                    # Antigravity plugin manifest
├── assets/logo.svg                # Plugin icon
├── sidecars/stats/
│   ├── sidecar.json               # Registers SIDECAR_UI_ENTRYPOINT_AUX_PANE
│   ├── package.json               # ESM marker
│   ├── main.mjs                   # Node sidecar (caches by transcript mtime:size)
│   ├── session_analyzer.py        # Python stdlib-only transcript parser
│   └── index.html                 # Self-contained side panel UI
└── tests/
    └── test_session_analyzer.py   # Stdlib unittest suite
```

- Reads `~/.gemini/antigravity/brain/<conversationId>/.system_generated/logs/transcript.jsonl` (read-only; also checks `~/.gemini/antigravity-cli/brain/`).
- Never sends data over the network and never opens extra listening ports outside Antigravity's built-in sidecar bridge.

### Run tests

```bash
python -m unittest discover -s tests -v
```

</details>

## License

[MIT](LICENSE)

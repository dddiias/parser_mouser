# Parser mouser.com

A small CLI and interactive menu for looking up electronic parts on **Mouser** by Part Number (both **Mouser PN** and **Manufacturer PN**) using the official API. Outputs the key fields and can export to **CSV / JSON / XLSX (Excel)**.

## Features

- Search by **Mouser Part Number** (`579-...`, `667-...`) **and** by **Manufacturer Part Number** (via keyword fallback).
- Strict 5-column table:
  - `Product Category`
  - `Stock`
  - `Factory Lead Time`
  - `Unit Price` (price at the qty=1)
  - `Description`
- Exports to **CSV**, **JSON**, and **XLSX**.
- Interactive menu: enter PN(s), view a table, save results, optionally save RAW API responses.

## Installation

### Create and activate a virtual environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
```
### Install dependencies
```bash
pip install -r requirements.txt
```
### API Key setup
```bash
cp .env.example .env
```

## Quick Start

```bash
python mouser_menu.py
```
Follow the prompts: enter one or multiple PNs (space- or comma-separated), view the table, save to CSV/JSON/XLSX.

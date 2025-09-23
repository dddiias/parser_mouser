import os
import re
import sys
import json
import time
import csv
import argparse
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv, find_dotenv

API_PARTNUMBER = "https://api.mouser.com/api/v1.0/search/partnumber"
API_KEYWORD    = "https://api.mouser.com/api/v1.0/search/keyword"

load_dotenv(find_dotenv(), override=False)

def _get_api_key() -> str:
    key = os.getenv("MOUSER_API_KEY")
    if not key:
        print(
            "ERROR: MOUSER_API_KEY is not set. "
            "Create .env with MOUSER_API_KEY=YOUR_KEY (or export in shell).",
            file=sys.stderr,
        )
        sys.exit(2)
    return key

def _post_json(url: str, params: Dict[str, str], payload: Dict[str, Any],
               max_retries: int = 3, timeout: int = 20) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.post(url, params=params, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            if attempt <= max_retries:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"Network error: {e}") from e

        if resp.status_code == 429 and attempt <= max_retries:
            retry_after = int(resp.headers.get("Retry-After", "2") or "2")
            time.sleep(retry_after)
            continue

        if resp.status_code >= 400:
            raise RuntimeError(f"Mouser API error {resp.status_code}: {resp.text[:500]}")

        try:
            return resp.json()
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON: {resp.text[:200]}")

def fetch_by_partnumber(query: str, api_key: str, max_retries: int, timeout: int) -> Dict[str, Any]:
    params = {"apiKey": api_key}

    payload1 = {"SearchByPartNumberRequest": {"MouserPartNumber": query}}
    data = _post_json(API_PARTNUMBER, params, payload1, max_retries, timeout)
    if _has_parts(data):
        return data

    payload2 = {"SearchByPartNumberRequest": {"mouserPartNumber": query}}
    data2 = _post_json(API_PARTNUMBER, params, payload2, max_retries, timeout)
    return data2

def fetch_by_keyword(query: str, api_key: str, max_retries: int, timeout: int) -> Dict[str, Any]:
    params = {"apiKey": api_key}
    payload = {"SearchByKeywordRequest": {"keyword": query}}
    return _post_json(API_KEYWORD, params, payload, max_retries, timeout)

def _has_parts(api_response: Dict[str, Any]) -> bool:
    sr = api_response.get("SearchResults") or api_response.get("SearchByPartNumberResponse") or {}
    parts = sr.get("Parts") or []
    return len(parts) > 0

def extract_first_part(api_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sr = api_response.get("SearchResults") or api_response.get("SearchByPartNumberResponse") or {}
    parts = sr.get("Parts") or []
    return parts[0] if parts else None

def _parse_stock(avail: Optional[str]) -> Optional[int]:
    if not avail:
        return None
    m = re.search(r"([\d,]+)", avail)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None

def _first_price(price_breaks: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    if not price_breaks:
        return None
    for pb in price_breaks:
        try:
            if int(pb.get("Quantity", 0)) == 1:
                price = pb.get("Price")
                return (str(price).strip() if price is not None else None)
        except Exception:
            pass
    price = price_breaks[0].get("Price")
    return (str(price).strip() if price is not None else None)

def transform(part: Dict[str, Any]) -> Dict[str, Any]:
    category = part.get("Category") or part.get("CategoryName") or part.get("ProductLine")
    availability = part.get("Availability") or part.get("MultiAvailability")
    stock = _parse_stock(availability)
    lead_time = part.get("FactoryLeadTime") or part.get("LeadTime") or part.get("ManufacturerLeadTimeWeeks")
    unit_price = _first_price(part.get("PriceBreaks") or [])
    description = part.get("Description") or part.get("ProductDescription")
    return {
        "Product Category": category,
        "Stock": stock,
        "Factory Lead Time": lead_time,
        "Unit Price": unit_price,
        "Description": description,
        "Mouser Part Number": part.get("MouserPartNumber"),
        "Manufacturer Part Number": part.get("ManufacturerPartNumber"),
        "Product URL": part.get("ProductDetailUrl"),
        "Raw Availability": availability,
    }

def write_csv(rows: List[Dict[str, Any]], out_path: str) -> None:
    fields = list(rows[0].keys()) if rows else []
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def print_table(rows: List[Dict[str, Any]]) -> None:
    cols = [
        "Mouser Part Number",
        "Manufacturer Part Number",
        "Product Category",
        "Stock",
        "Factory Lead Time",
        "Unit Price",
        "Description",
    ]
    widths = {c: max(len(c), max((len(str(r.get(c) or "")) for r in rows), default=0)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header); print(sep)
    for r in rows:
        print(" | ".join(str(r.get(c) or "").ljust(widths[c]) for c in cols))

def main():
    parser = argparse.ArgumentParser(description="Mouser Search CLI: Mouser PN + fallback to keyword (manufacturer PN)")
    parser.add_argument("part_numbers", nargs="+", help="One or more PNs (Mouser or Manufacturer)")
    parser.add_argument("--format", choices=["table", "csv", "json"], default="table")
    parser.add_argument("--out", help="Output file path for csv/json")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON response(s)")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, default=3, help="Max retries for 429/network errors")
    args = parser.parse_args()

    api_key = _get_api_key()
    results: List[Dict[str, Any]] = []

    for q in args.part_numbers:
        data_pn = fetch_by_partnumber(q, api_key, args.retries, args.timeout)
        part = extract_first_part(data_pn)

        used_keyword = False
        if not part:
            data_kw = fetch_by_keyword(q, api_key, args.retries, args.timeout)
            part = extract_first_part(data_kw)
            used_keyword = True

        if args.raw:
            if used_keyword:
                print(f"=== RAW KEYWORD RESPONSE for {q} ===")
                print(json.dumps(data_kw, ensure_ascii=False, indent=2))
            else:
                print(f"=== RAW PARTNUMBER RESPONSE for {q} ===")
                print(json.dumps(data_pn, ensure_ascii=False, indent=2))

        if not part:
            print(f"WARNING: No parts found for {q}", file=sys.stderr)
            continue

        results.append(transform(part))

    if not results:
        print("No data produced.")
        return

    if args.format == "json":
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Wrote JSON -> {args.out}")
        else:
            print(output)
    elif args.format == "csv":
        out_path = args.out or "mouser_results.csv"
        write_csv(results, out_path)
        print(f"Wrote CSV -> {out_path}")
    else:
        print_table(results)

if __name__ == "__main__":
    main()

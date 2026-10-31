import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.crustdata.com"
DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)


def headers():
    key = os.getenv("CRUSTDATA_API_KEY")
    if not key:
        raise SystemExit("No CRUSTDATA_API_KEY found. Create a .env file with it.")
    return {
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "x-api-version": "2025-11-01",
    }


def post(path, body):
    wait = 3
    for _ in range(4):
        res = requests.post(BASE + path, json=body, headers=headers(), timeout=90)
        if res.status_code == 429 or res.status_code >= 500:
            print(f"  busy ({res.status_code}), retrying in {wait}s")
            time.sleep(wait)
            wait *= 2
            continue
        if not res.ok:
            print(f"  Crustdata said {res.status_code}")
            print(res.text[:1500])
            raise SystemExit(1)
        return res.json()
    raise SystemExit("Still rate limited. Wait a minute and run again.")


def records(reply):
    for key in ("companies", "profiles", "results", "data"):
        if isinstance(reply.get(key), list):
            return reply[key]
    for value in reply.values():
        if isinstance(value, list):
            return value
    return []


def save(name, payload):
    path = DATA / name
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  saved {path}")


def show_shape(item, depth=0, limit=3):
    if depth > limit:
        return
    pad = "  " * (depth + 1)
    if isinstance(item, dict):
        for key, value in item.items():
            kind = type(value).__name__
            preview = "" if isinstance(value, (dict, list)) else f" = {str(value)[:60]}"
            print(f"{pad}{key} ({kind}){preview}")
            if isinstance(value, dict):
                show_shape(value, depth + 1, limit)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                print(f"{pad}  [first item]")
                show_shape(value[0], depth + 2, limit)

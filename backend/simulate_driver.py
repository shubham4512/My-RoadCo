"""
Simple driver simulator:
- pushes GPS-like updates to backend every few seconds
- useful to demo live movement without real GPS hardware
"""

from __future__ import annotations

import argparse
import random
import time
from itertools import cycle

import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bus-id", type=int, default=1)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--api-key", default="dev-driver-key")
    args = parser.parse_args()

    # Demo loop for Haryana/Delhi corridor.
    route_paths = {
        1: [
            (30.7333, 76.7794),  # Chandigarh
            (29.9695, 76.8783),  # Kurukshetra
            (29.6857, 76.9905),  # Karnal
            (29.3909, 76.9635),  # Panipat
            (28.6675, 77.2273),  # Delhi ISBT
        ],
        2: [
            (29.1492, 75.7217),  # Hisar
            (28.7930, 76.1397),  # Bhiwani
            (28.1990, 76.6188),  # Rewari
            (28.4595, 77.0266),  # Gurugram
        ],
    }
    path = route_paths.get(args.bus_id, route_paths[1])

    for lat, lng in cycle(path):
        payload = {
            "lat": lat + random.uniform(-0.0006, 0.0006),
            "lng": lng + random.uniform(-0.0006, 0.0006),
            "speed_mps": random.uniform(6.0, 12.0),
            "heading_deg": random.choice([0, 90, 180, 270]),
            "delay_minutes": random.choice([0, 1, 2, 3]),
        }
        url = f"{args.base_url}/buses/{args.bus_id}/location"
        r = requests.post(url, json=payload, timeout=10, headers={"X-API-Key": args.api_key})
        print(r.status_code, r.text[:120])
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

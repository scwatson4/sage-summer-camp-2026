#!/usr/bin/env python3
"""What did the Sage nodes record during the nearby lightning-fire windows?

Keep windows narrow and per-node — broad fleet queries time out.
"""
import sage_data_client

CASES = [
    ("W06C", "Kitten Fire (0.3 ac, 6 km) discovered 2025-07-03", "2025-07-01", "2025-07-04"),
    ("W06C", "Signal Flat (7.7 ac, 12 km) discovered 2025-07-26", "2025-07-24", "2025-07-27"),
    ("W067", "Selma 4-fire bust (14-22 km) discovered 2025-07-08", "2025-07-06", "2025-07-09"),
    ("W045", "Maverick Assist (2 ac, 7 km) discovered 2023-07-27", "2023-07-25", "2023-07-28"),
]

for vsn, label, s, e in CASES:
    print("=" * 72)
    print(f"{vsn} | {label} | window {s} -> {e}")
    up = sage_data_client.query(start=s + "T00:00:00Z", end=e + "T00:00:00Z",
                                filter={"name": "upload", "vsn": vsn})
    if len(up):
        print("  uploads by task:")
        for task, cnt in up.groupby("meta.task").size().sort_values(ascending=False).items():
            print(f"    {task:<30} {cnt}")
    else:
        print("  uploads: NONE")
    met = sage_data_client.query(start=s + "T00:00:00Z", end=e + "T00:00:00Z",
                                 filter={"name": "env.temperature|env.pressure|wxt.*", "vsn": vsn})
    print(f"  met-ish records: {len(met)}")

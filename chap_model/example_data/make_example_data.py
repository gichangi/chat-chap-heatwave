"""Create deterministic weekly data for six synthetic locations."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
rng = np.random.default_rng(42)
dates = pd.date_range("2022-01-03", periods=108, freq="W-MON")
rows = []
for location_index in range(6):
    for index, date in enumerate(dates):
        phase = 2 * np.pi * (index % 52) / 52
        heat = max(0, 3 * np.sin(phase - 0.7) + rng.normal(0, 0.4))
        rng.normal(0, 1.5)  # Preserve the established deterministic climate series.
        rows.append({
            "time_period": f"{date.isocalendar().year}-W{date.isocalendar().week:02d}",
            "location": f"location_{location_index}",
            "heatwave": int(heat > 0),
            "population": 100000 + location_index * 10000,
            "rainfall": max(0, 80 + 50 * np.sin(phase + 1) + rng.normal(0, 8)),
            "mean_temperature": 27 + 4 * np.sin(phase - 0.5) + rng.normal(0, 0.5),
            "heatwave_days": min(7, round(heat)),
            "mean_heat_index": 82 + 3 * heat,
            "max_heat_index": 88 + 4 * heat,
            "heatwave_event_count": int(heat >= 2),
        })
frame = pd.DataFrame(rows)
historic = frame.groupby("location", group_keys=False).head(104)
future = frame.groupby("location", group_keys=False).tail(4).copy()
future["heatwave"] = np.nan
historic.to_csv(ROOT / "historic_data.csv", index=False)
future.to_csv(ROOT / "future_data.csv", index=False)


# heatwave_modelling_CHAP

**[Architecture diagram: Heatwave Detection Pipeline](https://claude.ai/code/artifact/f7dfd3f2-5a88-4f9f-b901-731128f0a801)** -- full walkthrough of credential resolution, ERA5-Land ingestion, Heat Index computation, the live Streamlit app, and the (built-but-unwired) climatology/heatwave-detection library, with every data source itemized.

A ward-level heatwave-detection pipeline for Nigeria. It ingests ERA5-Land climate data via Google Earth Engine, computes NOAA/NWS Heat Index per ward, detects heatwave days/events using a WMO/ETCCDI percentile-exceedance climatology, and produces a weekly covariate table for downstream disease-forecasting platforms (CHAP / chap-core / dhis2-chap). It does not forecast disease itself — it produces an upstream climate covariate.

## Development Status

This branch (`feature/heatwave-508110-phase-0-4-gsd`) reworks the project's original prototype through a structured plan → execute → verify pipeline, fixing several issues found along the way and adding the core heatwave-detection algorithm and its production batch pipeline. It supersedes an earlier, ad-hoc version of the same Phase 0-2 work ([PR #1](https://github.com/eHealthAfrica/heatwave_modelling_CHAP/pull/1)) and extends it through Phase 4.

### What changed from the original prototype

The original prototype (`main` branch) was a single-file Streamlit script (`gee.py` + `nigeria_heat_index.py`) that authenticated to Earth Engine inline, pulled a coarser ERA5 (not ERA5-Land) climate record for Northern Nigeria only, and computed Heat Index live on every map interaction. This rework replaces that with a tested `heatwave/` package and a nationwide, GRID3-based ward boundary (4,841 wards).

### Phase 1 — Foundation Rework

Re-verified and fixed four issues found during an independent audit of the initial rework:
- **Dewpoint/temperature join bug** — the original code matched each day's temperature image to its dewpoint image via a fragile `filterDate().first()` call. Fixed by restructuring ERA5-Land ingestion (`heatwave/data/ingest.py`) into a single multi-band collection, since both bands come from the same source data and are already aligned by day — no join needed at all.
- **Missing caching** — `heatwave/auth.py`'s Earth Engine initialization was re-run on every Streamlit interaction. Caching is now applied at the app layer only (`@st.cache_resource`), keeping the auth module itself reusable by non-Streamlit code (e.g. Phase 4's batch export).
- **Supply-chain issue** — `requirements.txt` pinned an unused package, `ee==0.2`, which turned out to be a namespace-colliding decoy package (not related to `earthengine-api`) and the actual source of a `blessings` import dependency. Removed.
- **Fragile path/import-order handling** — `heatwave/auth.py`'s credential file path and a `geemap` compatibility stub both depended on incidental call-order assumptions. Fixed with an explicit, CWD-independent path and an unconditional package-level stub.
- Added a live, credential-gated integration test suite (`tests/test_integration.py`) that runs against the real GCP project rather than mocks.

### Phase 2 — Heat Index Relocation

Moved the RH/Heat-Index math out of the Streamlit script and into `heatwave/science/heat_index.py`, so it's testable independent of the UI. The relative-humidity calculation is now clamped to a valid `[0, 100]` range (it previously had no bound). Tests validate the Heat Index formula against NOAA's own published reference table, not just internally-derived values.

### Phase 3 — Climatology & Heatwave Detection

The pipeline's core new scientific capability, not present in the original prototype at all:
- `heatwave/zonal.py` — reduces gridded ERA5-Land pixel data down to one Heat Index value per ward per day.
- `heatwave/science/climatology.py` — computes each ward's 90th-percentile Heat Index threshold for each calendar day of the year, from the 1991-2020 baseline, pooling a ±5-day window around each day (including correct handling of the wrap-around at the December/January boundary and Feb 29 in leap years).
- `heatwave/science/heatwave.py` — flags days where a ward's Heat Index exceeds its own climatological threshold, then groups consecutive hot days into heatwave events (3 or more consecutive days).
- Verified on small samples (a handful of test wards); running this across all 4,841 wards for the full 30-year baseline is Phase 4's job.

### Phase 4 — Batch Export & Covariate Table

The production deliverable: `scripts/run_batch_export.py` runs the full pipeline (ingest → Heat Index → climatology → detection → weekly aggregation) across all 4,841 wards and writes the CHAP-facing covariate table.

- **Asynchronous execution.** At this scale, Earth Engine's synchronous computation limits would be exceeded, so the script submits `ee.batch.Export.table` tasks and polls for completion, rather than blocking inline. Each run's progress is tracked in a resumable state file, keyed by a fingerprint of the parameters that built each chunk (so a differently-configured rerun can never silently reuse stale results).
- **Chunked by ward batch.** A live benchmark of the event-detection step suggested the full 35-year run could take on the order of 34-40 hours if attempted as a single computation, so the export is split into ~20 chunks of ~250 wards each, concatenated into one final CSV once every chunk completes.
- **Small-ward fallback.** `heatwave/zonal.py` gained a fallback path for wards too small relative to an ERA5-Land pixel to get a valid area-weighted value — it samples a representative in-polygon point instead, so every ward gets a real value in the final table (73 of the 4,841 real wards use this path), each one flagged for transparency, never silently dropped or defaulted to zero.
- **Human checkpoint before the real backfill.** Before any multi-hour production run, the pipeline surfaces a `--stage plan` preview (ward/chunk/small-ward counts, a quota-and-runtime warning) and a real small-scale smoke export for review — the actual full 1991-present backfill is a deliberate, separate operation the operator triggers when ready, not something that happens automatically.
- Research along the way caught two bugs before they shipped: pairing a calendar year with an ISO week number is wrong at the December/January boundary (needs the "Thursday of the same week" convention instead), and Earth Engine silently returns wrong values if you chain two `.group()` reducer calls instead of grouping by one composite key. A code review after execution found and fixed two critical issues (a task-tracking bug that could leave a failed export chunk permanently stuck as "in progress," and a resumability gap that could silently mix data from differently-configured runs), plus a follow-up regression the fixes themselves introduced (a scale bug that broke the `--stage plan` preview at full scale) — caught during phase verification and fixed before merge.

Phases 1-4 combined are covered by 90 tests that run live against the real Earth Engine project (`heatwave-508110`), plus two additional opt-in tests that submit real Earth Engine batch tasks (kept out of the default fast test loop since they take minutes, not seconds).

### What's next (Phases 5-7)

- **Phase 5 — Presentation Layer Rewrite:** the Streamlit app reads the precomputed table instead of computing live.
- **Phase 6 — Documentation:** full methodology write-up and a rewritten README covering setup, architecture, and usage end-to-end (this section will be superseded by that pass).
- **Phase 7 — Polish:** optional test/CI hardening.

See `.planning/PROJECT.md` and `.planning/ROADMAP.md` for full project context and phase-by-phase detail.

## Using with CHAP

This repository produces weekly heat and heatwave covariates and includes a
chapkit model service (`chap_model/`) that can be added to
[chap-core](https://github.com/dhis2-chap/chap-core) and used from the DHIS2
Modeling App.

### How the pieces fit

1. `scripts/run_batch_export.py` uses Earth Engine credentials to write the
   weekly ward covariate table. Never run its submit stage accidentally: inspect
   the plan and smoke stages first.
2. `scripts/chap_dataset.py` joins that table to health data and writes a CHAP
   dataset. This step is credential free.
3. `chap_model/` trains and predicts with lagged heat covariates. Its container
   never calls Earth Engine.

### Covariates and units

| Column | Meaning |
|---|---|
| `heatwave_days` | Mean count of days exceeding the ward and calendar-day 90th-percentile threshold, using a 1991–2020 baseline and ±5-day pooling window |
| `mean_heat_index` | Mean weekly NOAA/NWS Heat Index, **°F** |
| `max_heat_index` | Maximum weekly NOAA/NWS Heat Index, **°F** |
| `heatwave_event_count` | Mean count of qualifying events starting in the week; an event has at least three consecutive exceedance days |

The means above apply when several wards are mapped to one target location.
Heat index is not converted to Celsius.

### 1. Build a CHAP dataset

Health input must contain `time_period,location,disease_cases,population,rainfall,mean_temperature`.
The covariate export contains `time_period,location` and the four heat columns
above. Weekly periods are normalized to `YYYY-Www`.

```bash
python scripts/chap_dataset.py build \
  --covariates outputs/covariate_table.csv \
  --health health.csv \
  --geojson units.geojson \
  --crosswalk crosswalk.csv \
  --out outputs/chap_dataset.csv

python scripts/chap_dataset.py validate \
  --dataset outputs/chap_dataset.csv \
  --geojson units.geojson --strict
```

The optional crosswalk has `ward_id,location`. When multiple wards map to one
location, `mean_heat_index`, `heatwave_days`, and `heatwave_event_count` use an
unweighted mean; `max_heat_index` uses the maximum. Missing heat values remain
empty and are reported. They are never interpreted as zero. Extra export QA
fields are written to `<out>.qa.csv`.

### 2. Run the model locally

```bash
git clone https://github.com/gichangi/chat-chap-heatwave
cd chat-chap-heatwave/chap_model
uv sync
uv run python main.py
# In another terminal:
uv run chapkit test --period-type weekly
```

The service listens on port 9090 for local development. The committed synthetic
data and `chap_model/tests/` provide a credential-free model contract test.

### 3. Add it to chap-core

Docker Compose v2.20 or newer and a chap-core clone are required.

1. Copy `chap_model/compose.heatwave.yml` next to chap-core's `compose.yml`.
2. Pull `ghcr.io/gichangi/chat-chap-heatwave-model:latest`. New GHCR packages
   are private by default: make `chat-chap-heatwave-model` public in Package
   settings, or run `docker login ghcr.io` on every host that pulls it.
3. Start the combined stack:

   ```bash
   docker compose -f compose.yml -f compose.heatwave.yml up -d
   ```

4. Check `curl http://localhost:8000/v2/services` for
   `heatwave-covariate-model`, then open the DHIS2 Modeling App.

#### Add it to chap-core configured models

On current chap-core, service registration is sufficient. When
`heatwave-covariate-model` registers, chap-core reads its config schema and
creates a default configured model automatically. Confirm both layers:

```bash
# Registered chapkit service
curl http://localhost:8000/v2/services

# Runnable configured model used by the Modeling App
curl http://localhost:8000/v1/crud/configured-models
```

The configured model should use template `heatwave-covariate-model`, have
`uses_chapkit: true`, and list `heatwave_days`, `mean_heat_index`,
`max_heat_index`, and `heatwave_event_count` as additional continuous
covariates.

Some installations require configured models to be declared in files. For
those deployments, copy the supplied example into the chap-core checkout:

```bash
cp /path/to/chat-chap-heatwave/chap_model/chap-core.configured-models.yaml.example \
  config/configured_models/heatwave.yaml
```

Do not edit `config/configured_models/default.yaml`; chap-core updates replace
that file. The example uses `http://heatwave-model:8000`, which is the service
name and container port from `compose.heatwave.yml`. It is reachable from the
chap container on the shared Compose network. The `versions` field is required
by chap-core's configuration parser but is currently ignored for chapkit
services.

Rebuild the chap and worker images so the new configuration file is included,
then start the stack:

```bash
docker compose -f compose.yml -f compose.heatwave.yml build chap worker
docker compose -f compose.yml -f compose.heatwave.yml up -d
```

Inspect seeding and registration if it does not appear:

```bash
docker compose -f compose.yml -f compose.heatwave.yml logs chap | \
  grep -E "heatwave|configured model|chapkit"
docker compose -f compose.yml -f compose.heatwave.yml logs heatwave-model
curl http://localhost:8000/v1/crud/configured-models
```

File based seeding is idempotent. If a template version was already stored,
chap-core preserves it so existing backtests retain their provenance. Change
the configuration values or add a new version name when intentionally
publishing a new configuration or model version.

The literal `$$register` in the overlay is required Compose escaping. For a 401,
check that `SERVICEKIT_REGISTRATION_KEY` matches chap-core. Port 5010 must be
free. Apple Silicon may emit platform warnings for an amd64-only image.

For sidecar mode, mount a weekly covariate CSV read-only and set
`HEATWAVE_COVARIATE_TABLE` to its container path. To include the model in the
standard chap-core bundle, add its overlay to chap-core's `compose.chapkit.yml`.

### Limitations

- Reanalysis heat data has no future values. The model uses a four-week lag and
  rejects forecast horizons longer than `heat_lag_weeks` (default 4).
- The 4,841-ward dataset may be too large for some workflows; aggregate with a
  reviewed crosswalk when appropriate.
- The model is experimental and reports `AssessedStatus.red`.
- This repository currently has no LICENSE file. Add one before distributing
  the image or listing the repository as a community model.

### Origin and credit

The heatwave pipeline originates from
[eHealthAfrica/heatwave_modelling_CHAP](https://github.com/eHealthAfrica/heatwave_modelling_CHAP).
This repository was seeded from upstream branch
`feature/heatwave-508110-phase-0-4-gsd` at commit
`19556d92483f4702c41d6d456b61d22f9bbf38c1`; the CHAP adapter and chapkit
service were added here.

### Reference docs

- [Chapkit documentation](https://dhis2-chap.github.io/chapkit/)
- [Chapkit shell runner contract](https://dhis2-chap.github.io/chapkit/guides/shell-runner/)
- [Chap-core modeling documentation](https://chap.dhis2.org/chap-modeling-platform/)



# Qarizmi weekend technical assessment

## Atlas Fresh Daily Export Planner

This repository now contains a complete browser-based decision-support workspace for the supplied Atlas Fresh daily planning case. It uses a small standard-library Python API server, a deterministic planning engine, and a Next.js frontend styled with local shadcn-style components and Material Symbols icons.

### Quick Start (Makefile)

```bash
make install    # Install frontend dependencies
make backend    # Run Python API server (port 8080)
make frontend   # Run Next.js frontend dev server (port 3000)
make dev        # Run both backend & frontend concurrently
make test       # Run backend unit tests
```

### Manual Run

```bash
make install
make dev
```

Open `http://127.0.0.1:3000`, then select `Load Workbook` or `Recalculate Plan`.

The Next.js app proxies `/api/*` to the Python backend at `http://127.0.0.1:8080`. To use a different backend URL:

```bash
ATLAS_BACKEND_URL=http://127.0.0.1:8081 make frontend
```

### Test

```bash
make test
```

### API

- `GET /api/health`
- `POST /api/data/load`
- `POST /api/plan`
- `GET /api/plan`
- `POST /api/assistant`

The workbook remains the authoritative source. The frontend consumes server-generated validation, allocation, KPI, local residual, and assistant explanation results.

This pack contains a fully synthetic Production × Commercial planning case. It is the same for every candidate.

Atlas Fresh produces apples through 20 farms, classifies them into quality Segments A/B/C/D, conditions export fruit in one 500 t/day station and sells to 10 clients with different quality rules and prices. Before the season, Commercial sells a client program while Production sets an expected daily capacity and segment mix for each farm. The supplied data deliberately contains no farm-to-client mapping. Segment A, the hardest quality to produce, is below target in the daily snapshot.

Actual farm production differs from plan every day. Production and Commercial therefore meet to compare plan with actual receipts, decide which farm-segment volumes should serve which clients, and make visible what must fall back to the local market at only 10% of its segment reference export price. Creating and explaining that daily farm-to-client allocation is part of your assignment. Your task is to turn the manual preparation into one clear decision-support workspace while keeping final approval with the teams.

## Start here

1. Read `Qarizmi_Universal_Weekend_Technical_Assessment.pdf`.
2. Use `Atlas_Fresh_Production_Commercial_Data.xlsx` as the authoritative input.
3. Build the smallest complete product that satisfies the mandatory daily workflow.
4. Stop after 10–12 hours and document intentional omissions.

## Files

- `Qarizmi_Universal_Weekend_Technical_Assessment.pdf` — candidate brief.
- `Qarizmi_Universal_Weekend_Technical_Assessment.docx` — editable copy of the same brief.
- `Atlas_Fresh_Production_Commercial_Data.xlsx` — fictional input workbook and baseline checks.

## Submit

- repository URL;
- 3–5 minute walkthrough URL;
- optional live URL;
- approximate time spent and any access instructions.

Do not send credentials or use real client data. The core project must run without a paid service.

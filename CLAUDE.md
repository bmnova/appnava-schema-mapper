# appnava-schema-mapper — working rules

Interview prototype. The author must be able to explain every line:
prefer small, readable, boring code over clever code.

## Core principle
The LLM only PROPOSES a mapping. Deterministic code generates and runs SQL.
Anything uncertain is flagged `needs_human_review`.

## Rules
- Python 3.11+, type hints, Pydantic. Libraries: google-cloud-bigquery, anthropic. No web framework, no UI.
- All BigQuery access goes through `src/schema_mapper/bigquery/client.py`:
  SELECT-only, dry-run first, `maximum_bytes_billed` always set.
- Every query on `events_*` filters `_TABLE_SUFFIX` to a small date range.
- Config only via env vars: GCP_PROJECT, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, MAX_BYTES_BILLED.
- Small functions; docstrings explain WHY, not what.
- Never commit secrets. Before any commit, list the files and confirm nothing secret is included.
- Build one step at a time; run it and stop for review.

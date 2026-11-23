# appnava-schema-mapper

Maps a mobile game's raw Firebase / GA4 BigQuery events to a standard
analytics event schema (the kind a predictive LTV / churn product needs),
then turns that mapping into a BigQuery view and checks it on real data.

**Core idea:** the LLM only *proposes* a mapping. Deterministic code
generates and runs the SQL. Anything uncertain is flagged for a human.

```
profile (BigQuery) ──► agent proposes mapping (Claude) ──► validate (Pydantic + schema)
                                                              │
        report.md ◄── eval vs ground truth ◄── one-day run ◄──┘ SQL view generated (no LLM)
```

Data: the public Flood-It! dataset
`firebase-public-project.analytics_153293282.events_*`, 2018-08-01 to 08-03.

## Results

From [report.md](report.md):

| | |
|---|---|
| Events mapped | 17 / 33 |
| Rows mapped by the view (2018-08-01) | 12,208 / 50,000 (24.4%; most of the rest is `screen_view` / `user_engagement`) |
| Flagged for human review | 8 |
| Eval accuracy | 15 / 15 (small set; see caveats) |
| Agent cost per run | ≈ $0.09 (4 tool calls) |

The case worth looking at: `level_end` has no param that says win or lose,
and the game already sends `level_complete` / `level_fail`. The agent
leaves it unmapped and flags it instead of inventing a split.

### Phase 2: subscription data (SYNTHETIC)

`data/SYNTHETIC_adapty_events.csv` is a 30-row, hand-written, **synthetic**
Adapty-style export. As in a real Adapty setup, `purchase` is sent for both
a new subscription and a renewal, with no field that says which. Run with
`schema-mapper adapty` (CSV only, no BigQuery). The agent mapped `purchase`
with confidence 0.40 and flagged it ("likely mix of first and renewal
charges ... no split invented"), mapped cancel/expire directly, and left
`subscription_renewal_reactivated` unmapped and flagged because the schema
has no target for it. Details in report.md.

## How to run

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env    # set GCP_PROJECT, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
gcloud auth application-default login
```

```bash
.venv/bin/schema-mapper profile   # one BigQuery query -> cache/flood_it_profile.json
.venv/bin/schema-mapper map       # Claude agent -> output/mapping.json (costs ~$0.09)
.venv/bin/schema-mapper show      # print the saved mapping (offline, free)
.venv/bin/schema-mapper sql       # view SQL + dry-run + one-day validation
.venv/bin/schema-mapper eval      # score against eval/ground_truth.yaml
.venv/bin/schema-mapper report    # build report.md (offline)
.venv/bin/schema-mapper adapty    # Phase 2: agent on the synthetic Adapty CSV
.venv/bin/schema-mapper all       # everything except show and adapty
.venv/bin/pytest
```

The profile is committed, so `map` works without re-scanning BigQuery.

## Layout

```
src/schema_mapper/
  config.py              env vars, fixed date window
  models.py              Pydantic contract between the LLM and the SQL generator
  bigquery/client.py     the only BigQuery gateway (guardrails live here)
  bigquery/profiler.py   event / param profile
  agent/tools.py         the agent's three tools
  agent/mapper.py        tool-use loop, validation, retry, cost
  sql/generator.py       mapping -> CREATE VIEW (no LLM)
  evaluation/scorer.py   accuracy + did the review flag catch errors
  reporting/report.py    report.md
schemas/target_schema.yaml   target events, descriptions, params
eval/ground_truth.yaml       labeled expected targets
```

## Design decisions

**The LLM proposes, code decides.** The agent returns structured data
(target, split rules, param sources), never SQL. `sql/generator.py` turns
that into SQL the same way every time, so the output is auditable and a
re-run of the model cannot silently change the view.

**Split conditions are fields, not prose.** "Split by X: A → t1, B → t2" is
`split_by_param` + `split_cases`. Free text (`reasoning`) is for people
only and never reaches SQL.

**Human review is enforced in code.** `needs_human_review` is forced on
when confidence < 0.7 or one source maps to several targets. The model can
add flags; the validator never removes them.

**Guardrails.**
- One BigQuery gateway: SELECT/WITH only, single statement, write keywords
  blocked, dry-run before every run, `maximum_bytes_billed` on every job.
- Every query is limited to a few daily shards via `_TABLE_SUFFIX`.
- Agent tools take names, not SQL; names are checked against the profile.
- At most 15 tool calls. Invalid output is sent back with the errors once;
  a second failure stops the run.
- The SQL generator treats the mapping as untrusted: names checked,
  literals escaped (there is a test with an injection attempt).
- Per-turn token log and a cost estimate; the schema + profile prefix is
  prompt-cached.
- The view is written to `output/view.sql`, not deployed. Deploying is a
  human step.

**Type drift is handled.** The same param key arrives as `int` in some
rows and `double` in others (e.g. `level`). The generator reads every typed
value column, so those rows don't turn into silent NULLs.

## Known limitations

- The target schema is my own reading of a standard mobile-analytics
  schema; a real customer schema would replace `schemas/target_schema.yaml`
  only.
- Ground truth is 15 events, drafted by a separate Claude context that saw
  only the schema and profile facts, then reviewed. A larger, human-labeled
  set would be a stronger test; the 100% is optimistic.
- Some target params are not filled (e.g. `game_mode` for non-quickplay
  events, `score`); this is visible in the report and is what review is for.
- The model is not deterministic: two runs can explore differently. The
  reviewed mapping file, not the model, is the source of truth.
- One game, three days of data.

## Next steps

- **Schema drift detection** after app updates: re-profile, diff param
  keys and types against the last reviewed mapping, re-run the agent only
  for what changed.
- **Real subscription events** from Adapty / RevenueCat exports, where one
  event name can mean "started" or "renewed".
- **An MCP server** exposing reviewed mappings and model predictions to
  other tools.

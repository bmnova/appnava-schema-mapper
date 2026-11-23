"""The single gateway to BigQuery.

Why one module: every guardrail (read-only, dry-run first, bytes cap) lives
here, so neither the agent's tools nor the profiler can bypass them.
"""

import re
from typing import Any

from google.cloud import bigquery

from schema_mapper.config import Settings

# Statements that could change data, schema, permissions or session state.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|GRANT|REVOKE"
    r"|CALL|EXECUTE|EXPORT|LOAD|DECLARE|SET|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)


class QueryRejected(Exception):
    """Raised when a query violates a guardrail; the message is safe to show the agent."""


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)


def assert_read_only(sql: str) -> None:
    """Allow-list SELECT/WITH and block-list writes.

    Why both: an allow-list alone misses `SELECT 1; DROP ...`, a block-list
    alone misses statement types we did not think of. Keyword matching can
    false-positive on string literals like 'set'; rejecting is the safe side.
    """
    body = _strip_comments(sql).strip().rstrip(";").strip()
    if ";" in body:
        raise QueryRejected("Only a single statement is allowed.")
    if not re.match(r"^(SELECT|WITH)\b", body, re.IGNORECASE):
        raise QueryRejected("Only SELECT queries are allowed.")
    match = _FORBIDDEN.search(body)
    if match:
        raise QueryRejected(f"Forbidden keyword: {match.group(1).upper()}")


class BigQueryClient:
    def __init__(self, settings: Settings) -> None:
        self._client = bigquery.Client(project=settings.gcp_project)
        self.max_bytes_billed = settings.max_bytes_billed

    def estimate_bytes(self, sql: str) -> int:
        """Dry-run: validates SQL and returns bytes scanned, never executes.

        Also used for CREATE VIEW in sql_gen, which is why it does not apply
        the read-only check.
        """
        config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = self._client.query(sql, job_config=config)
        return job.total_bytes_processed or 0

    def run_select(self, sql: str) -> list[dict[str, Any]]:
        """Read-only check, then dry-run, then run with a server-side bytes cap.

        Why both a dry-run and maximum_bytes_billed: the dry-run gives a clear
        refusal before spending anything; the cap is the backstop BigQuery
        enforces even if our estimate were wrong.
        """
        assert_read_only(sql)
        estimated = self.estimate_bytes(sql)
        if estimated > self.max_bytes_billed:
            raise QueryRejected(
                f"Query would scan {estimated:,} bytes; limit is {self.max_bytes_billed:,}."
            )
        config = bigquery.QueryJobConfig(maximum_bytes_billed=self.max_bytes_billed)
        rows = self._client.query(sql, job_config=config).result()
        return [dict(row) for row in rows]

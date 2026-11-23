import pytest

from schema_mapper.bigquery.client import QueryRejected, assert_read_only


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "with t as (select 1) select * from t",
    "-- comment\nSELECT event_name FROM x;",
])
def test_allows_selects(sql: str) -> None:
    assert_read_only(sql)


@pytest.mark.parametrize("sql", [
    "DROP TABLE x",
    "SELECT 1; DROP TABLE x",
    "CREATE VIEW v AS SELECT 1",
    "/* hi */ DELETE FROM x WHERE true",
    "WITH t AS (SELECT 1) INSERT INTO y SELECT * FROM t",
])
def test_rejects_writes(sql: str) -> None:
    with pytest.raises(QueryRejected):
        assert_read_only(sql)

"""DQChecker — runs DQRules against a Polars frame and persists rejections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
from loguru import logger

from .rules import DQRule


class DQChecker:
    def __init__(self, source: str, batch_id: str, rules: list[DQRule]) -> None:
        self._source = source
        self._batch_id = batch_id
        self._rules = rules

    def check(self, lf: pl.LazyFrame) -> tuple[pl.LazyFrame, pl.DataFrame]:
        """Split *lf* into (passed, rejected).

        ERROR rules drop failing rows from the pipeline.
        WARNING rules annotate rows but keep them in the pipeline.
        Both produce rows in the returned rejected DataFrame.
        """
        df = lf.collect()
        all_rejected: list[pl.DataFrame] = []
        error_exprs: list[pl.Expr] = []

        for rule in self._rules:
            rule_pass: pl.Series = df.select(rule.predicate.alias("_pass"))["_pass"]
            failing = df.filter(~rule_pass)

            if len(failing) > 0:
                logger.debug(
                    "DQ [{}] '{}' ({}) — {} row(s) rejected",
                    self._source,
                    rule.name,
                    rule.severity,
                    len(failing),
                )
                annotated = failing.with_columns(
                    pl.lit(self._source).alias("dq_source"),
                    pl.lit(self._batch_id).alias("dq_batch_id"),
                    pl.lit(rule.name).alias("dq_rule_name"),
                    pl.lit(rule.description).alias("dq_rule_description"),
                    pl.lit(rule.severity).alias("dq_severity"),
                )
                all_rejected.append(annotated)

            if rule.severity == "ERROR":
                error_exprs.append(rule.predicate)

        if error_exprs:
            combined = error_exprs[0]
            for expr in error_exprs[1:]:
                combined = combined & expr
            passed_df = df.filter(combined)
        else:
            passed_df = df

        logger.info(
            "DQ [{}] batch={}: {}/{} rows passed ({} dropped by ERROR rules)",
            self._source,
            self._batch_id,
            len(passed_df),
            len(df),
            len(df) - len(passed_df),
        )

        if all_rejected:
            rejected_df = pl.concat(all_rejected, how="diagonal_relaxed")
        else:
            rejected_df = pl.DataFrame(
                schema={
                    "dq_source": pl.String,
                    "dq_batch_id": pl.String,
                    "dq_rule_name": pl.String,
                    "dq_rule_description": pl.String,
                    "dq_severity": pl.String,
                }
            )

        return passed_df.lazy(), rejected_df

    def save_rejected(
        self, rejected: pl.DataFrame, db_url: str, max_per_rule: int = 500
    ) -> int:
        """Persist a sample of rejected rows to stg_rejected_records.

        At most *max_per_rule* rows are stored per rule to keep the table lean
        when a single rule rejects millions of rows (e.g. missing prices in
        gov_data files). The total rejection count is always logged.

        Uses SQLAlchemy Core bulk insert (fast path) instead of ORM add_all.
        """
        if rejected.is_empty():
            return 0

        from sqlalchemy import insert

        from src.api.db.connection import build_engine, get_session
        from src.api.db.models import StagingRejectedRecord

        dq_cols = {
            "dq_source",
            "dq_batch_id",
            "dq_rule_name",
            "dq_rule_description",
            "dq_severity",
        }
        data_cols = [c for c in rejected.columns if c not in dq_cols]

        # Sample: take at most max_per_rule rows per rule_name
        sampled = rejected.group_by("dq_rule_name").map_groups(
            lambda g: g.head(max_per_rule)
        )
        total_rejected = len(rejected)
        total_saved = len(sampled)

        rows_to_insert: list[dict] = []
        for row in sampled.to_dicts():
            row_data: dict[str, object] = {}
            for k in data_cols:
                v = row.get(k)
                if v is not None and not isinstance(v, (str, int, float, bool)):
                    v = str(v)
                row_data[k] = v
            rows_to_insert.append(
                {
                    "source": row["dq_source"],
                    "batch_id": row.get("dq_batch_id"),
                    "rule_name": row["dq_rule_name"],
                    "rule_description": row.get("dq_rule_description"),
                    "severity": row["dq_severity"],
                    "row_data": row_data,
                }
            )

        engine = build_engine(db_url)
        with get_session(engine) as session:
            session.execute(insert(StagingRejectedRecord), rows_to_insert)

        if total_saved < total_rejected:
            logger.warning(
                "DQ [{}]: {} rejected rows — saved {} sample(s) per rule "
                "(max_per_rule={})",
                self._source,
                total_rejected,
                total_saved,
                max_per_rule,
            )
        else:
            logger.info(
                "Saved {} rejected record(s) to stg_rejected_records", total_saved
            )
        return total_rejected

    @classmethod
    def source_summary(
        cls, source: str, db_url: str, since_hours: int = 48
    ) -> dict[str, object]:
        """Query stg_rejected_records and return rejection stats for *source*."""
        from sqlalchemy import text
        from src.api.db.connection import build_engine, get_session

        cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
        engine = build_engine(db_url)

        with get_session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT rule_name, severity, COUNT(*) AS cnt"
                    " FROM stg_rejected_records"
                    " WHERE source = :source AND rejected_at > :cutoff"
                    " GROUP BY rule_name, severity"
                ),
                {"source": source, "cutoff": cutoff},
            ).fetchall()

        by_rule: dict[str, int] = {r.rule_name: int(r.cnt) for r in rows}
        by_severity: dict[str, int] = {}
        for r in rows:
            by_severity[r.severity] = by_severity.get(r.severity, 0) + int(r.cnt)

        total = sum(by_severity.values())

        if by_severity.get("ERROR", 0) > 0:
            logger.warning(
                "DQ summary [{}]: {} ERROR rejection(s) in the last {} h",
                source,
                by_severity["ERROR"],
                since_hours,
            )
        else:
            logger.info(
                "DQ summary [{}]: {} total rejection(s) in the last {} h",
                source,
                total,
                since_hours,
            )

        return {
            "source": source,
            "total_rejected": total,
            "by_rule": by_rule,
            "by_severity": by_severity,
        }

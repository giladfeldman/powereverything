"""Pilot quality metrics; applies only to manually adjudicated records."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def summary(records: Iterable[dict]) -> dict:
    records = list(records)
    labels = Counter(record.get("adjudicated_label", "unadjudicated") for record in records)
    extracted = [record for record in records if record.get("ai_candidate_found") is not None]
    retrieval_recall = (sum(bool(record.get("ai_candidate_found")) for record in extracted) / len(extracted)) if extracted else None
    flagged = [record for record in records if record.get("deterministic_label") == "potentially_inconsistent_requires_review"]
    overturned = sum(record.get("adjudicated_label") != "potentially_inconsistent_requires_review" for record in flagged)
    return {"records": len(records), "labels": dict(labels), "candidate_retrieval_recall": retrieval_recall, "potential_flags": len(flagged), "potential_flags_overturned": overturned, "potential_flag_overturn_rate": (overturned / len(flagged)) if flagged else None}

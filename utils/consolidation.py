"""
Automated Consolidation Engine.

Aggregates numeric Section-C BRSR metrics bottom-up through the org
hierarchy: Business Unit (project) -> Subsidiary -> MEIL Group.

Only metrics flagged rollup=True in the metric catalog are summed.
Consolidated values are written back into ESGData with is_consolidated=True
so the UI can visually distinguish manually-entered vs. computed figures.
"""
from extensions import db
from models import Organization, ESGData
from utils.metrics_catalog import rollup_metric_codes, get_metric
from utils.audit import log_action


def consolidate_org(org_id, period_id, user_id=None):
    """
    Recompute rolled-up Section C metrics for a SUBSIDIARY or GROUP org by
    summing the values of its direct child organizations for the given
    reporting period. Recurses so a Group total reflects all Business Units
    beneath every Subsidiary, even if a Subsidiary hasn't been individually
    re-run first.

    Returns a dict {metric_code: consolidated_value}
    """
    org = Organization.query.get(org_id)
    if org is None or org.org_type == "BUSINESS_UNIT":
        raise ValueError("Consolidation can only be run for a Subsidiary or Group organization.")

    child_orgs = [c for c in org.children if c.is_active]
    results = {}

    for code in rollup_metric_codes():
        total = 0.0
        any_value = False
        for child in child_orgs:
            if child.org_type == "BUSINESS_UNIT":
                row = ESGData.query.filter_by(org_id=child.id, period_id=period_id, metric_code=code).first()
                if row and row.numeric_value() is not None:
                    total += row.numeric_value()
                    any_value = True
            else:
                # Recurse into sub-subsidiary structures first
                child_results = consolidate_org(child.id, period_id, user_id=user_id)
                if code in child_results:
                    total += child_results[code]
                    any_value = True

        if not any_value:
            continue

        metric_def = get_metric(code)
        existing = ESGData.query.filter_by(org_id=org_id, period_id=period_id, metric_code=code).first()
        old_value = existing.value if existing else None

        if existing:
            existing.value = str(total)
            existing.is_consolidated = True
            existing.updated_by = user_id
        else:
            existing = ESGData(
                org_id=org_id,
                period_id=period_id,
                section="C",
                principle=metric_def["principle"],
                metric_code=code,
                metric_name=metric_def["name"],
                value=str(total),
                unit=metric_def.get("unit"),
                is_consolidated=True,
                created_by=user_id,
                updated_by=user_id,
            )
            db.session.add(existing)

        log_action(
            user_id=user_id,
            action="CONSOLIDATE",
            entity="ESGData",
            entity_id=f"{org_id}:{period_id}:{code}",
            old_value=old_value,
            new_value=str(total),
        )
        results[code] = total

    db.session.commit()
    return results

"""
ESG Analytics & Data Quality utilities.

Provides:
- ESG data completeness checks
- Year-over-year change detection
- Dashboard KPI summaries
"""

from utils.metrics_catalog import SECTION_C, METRIC_BY_CODE
from models import ESGData, ReportingPeriod, Organization


def get_completeness(org_id, period_id):
    """
    Calculate Section C data completeness for one organization
    and reporting period.

    Business Units:
        Check all required Section C metrics.

    Subsidiaries / Groups:
        Check only metrics currently supported by the
        consolidation engine (rollup=True).
    """

    org = Organization.query.get(org_id)

    if org is None:
        return {
            "total": 0,
            "reported": 0,
            "missing": [],
            "percentage": 100.0,
            "scope": "Unknown",
        }

    # Get required Section C metrics.
    required_metrics = [
        metric
        for metric in SECTION_C
        if metric.get("required", False)
    ]

    # At Group/Subsidiary level, only metrics supported by
    # the current consolidation engine are considered.
    if org.org_type in ("GROUP", "SUBSIDIARY"):
        required_metrics = [
            metric
            for metric in required_metrics
            if metric.get("rollup", False)
        ]
        scope = "Consolidated metrics"
    else:
        scope = "All required metrics"

    reported_codes = {
        row.metric_code
        for row in ESGData.query.filter_by(
            org_id=org_id,
            period_id=period_id
        ).all()
        if row.value is not None and str(row.value).strip() != ""
    }

    missing = [
        metric["name"]
        for metric in required_metrics
        if metric["code"] not in reported_codes
    ]

    total = len(required_metrics)
    reported = total - len(missing)

    percentage = (
        round((reported / total) * 100, 1)
        if total > 0
        else 100.0
    )

    return {
        "total": total,
        "reported": reported,
        "missing": missing,
        "percentage": percentage,
        "scope": scope,
    }
def get_anomaly_recommendation(metric, direction, severity):
    """
    Generate a practical review recommendation for an ESG anomaly.
    """

    code = metric.get("code", "")

    recommendations = {
        "C_P1_TRAINING_HRS":
            "Review ethics and anti-corruption training records, employee coverage, and reporting-period changes.",

        "C_P1_GRIEVANCES":
            "Review grievance records, case classifications, and whether reporting or resolution practices changed.",

        "C_P2_SUSTAINABLE_INVEST":
            "Review the underlying R&D/Capex classification and supporting financial records for sustainable investments.",

        "C_P3_HEALTH_COVERAGE":
            "Review employee insurance records and workforce changes to confirm the reported coverage percentage.",

        "C_P3_INJURIES":
            "Review workplace incident records, LTIFR calculations, and reporting boundaries for the affected period.",

        "C_P4_STAKEHOLDER_CONSULT":
            "Review stakeholder engagement records and confirm that all qualifying consultations were captured.",

        "C_P5_HR_TRAINING":
            "Review human-rights training records and employee population used to calculate the percentage.",

        "C_P6_ENERGY":
            "Review energy bills, meter readings, activity data, and reporting boundaries for the affected entities.",

        "C_P6_WATER":
            "Review water withdrawal records, meter readings, estimation methods, and reporting boundaries.",

        "C_P6_GHG":
            "Review emission sources, activity data, emission factors, and reporting boundaries before submission.",

        "C_P6_WASTE":
            "Review waste records, waste categories, disposal/recovery data, and reporting boundaries.",

        "C_P7_ADVOCACY":
            "Review public-policy engagement records and confirm that all reportable engagements were captured.",

        "C_P8_CSR_SPEND":
            "Review CSR expenditure records, project classifications, and the reporting period used for the calculation.",

        "C_P8_CSR_LOCAL_PCT":
            "Review CSR project locations and expenditure classification used to calculate the local-area percentage.",

        "C_P9_COMPLAINTS":
            "Review customer complaint logs, product/service categories, and reporting-period changes.",

        "C_P9_RESOLVED_PCT":
            "Review complaint closure records and confirm the calculation method used.",
    }

    recommendation = recommendations.get(
        code,
        "Review the underlying ESG records and supporting evidence for this reporting period."
    )

    if severity == "CRITICAL":
        return "Priority review: " + recommendation

    return recommendation

def get_yoy_anomalies(org_id, current_period_id, threshold=50):
    """
    Detect unusually large year-over-year changes
    in numeric Section C metrics.

    For normal numeric metrics:
        change_percentage = relative % change

    For percentage metrics:
        change_points = absolute percentage-point change
    """

    current_period = ReportingPeriod.query.get(current_period_id)

    if current_period is None:
        return []

    previous_period = (
        ReportingPeriod.query
        .filter(
            ReportingPeriod.end_date < current_period.start_date
        )
        .order_by(ReportingPeriod.end_date.desc())
        .first()
    )

    if previous_period is None:
        return []

    anomalies = []

    numeric_metrics = [
        metric
        for metric in SECTION_C
        if metric.get("data_type") in (
            "number",
            "integer",
            "percentage"
        )
    ]

    for metric in numeric_metrics:

        code = metric["code"]

        current_row = ESGData.query.filter_by(
            org_id=org_id,
            period_id=current_period_id,
            metric_code=code
        ).first()

        previous_row = ESGData.query.filter_by(
            org_id=org_id,
            period_id=previous_period.id,
            metric_code=code
        ).first()

        if not current_row or not previous_row:
            continue

        current_value = current_row.numeric_value()
        previous_value = previous_row.numeric_value()

        if current_value is None or previous_value is None:
            continue

        # Percentage metrics
        if metric.get("data_type") == "percentage":

            change_points = current_value - previous_value

            if abs(change_points) >= threshold:
                absolute_change = abs(change_points)

                if absolute_change >= 20:
                    severity = "HIGH"
                else:
                    severity = "MODERATE"

                anomalies.append({
                    "code": code,
                    "name": metric["name"],
                    "unit": metric.get("unit"),
                    "previous_period": previous_period.name,
                    "current_period": current_period.name,
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "change_percentage": None,
                    "change_points": round(change_points, 1),
                   "direction": (
                   "increase"
                   if change_points > 0
                   else "decrease"
                   ),
                   "severity": severity,
                   "recommendation": get_anomaly_recommendation(
                   metric,
                   "increase" if change_points > 0 else "decrease",
                   severity
                   ),
                   "reason": (
                   f"Percentage-point change exceeded "
                   f"{threshold} points."
                   )
                })

            continue

        # Previous year was zero
        if previous_value == 0:

            if current_value == 0:
                continue

            anomalies.append({
            "code": code,
            "name": metric["name"],
            "unit": metric.get("unit"),
            "previous_period": previous_period.name,
            "current_period": current_period.name,
            "previous_value": previous_value,
            "current_value": current_value,
            "change_percentage": None,
            "change_points": None,
            "direction": "increase",
            "severity": "HIGH",
            "recommendation": get_anomaly_recommendation(
            metric,
            "increase",
            "HIGH"
            ),
            "reason": "Previous year value was zero."
            })
            continue

        # Normal numeric metrics
        change_percentage = (
            (current_value - previous_value)
            / abs(previous_value)
        ) * 100

        if abs(change_percentage) >= threshold:

            absolute_change = abs(change_percentage)

            if absolute_change >= 200:
                severity = "CRITICAL"
            elif absolute_change >= 100:
                severity = "HIGH"
            else:
                severity = "MODERATE"

            anomalies.append({
                "code": code,
                "name": metric["name"],
                "unit": metric.get("unit"),
                "previous_period": previous_period.name,
                "current_period": current_period.name,
                "previous_value": previous_value,
                "current_value": current_value,
                "change_percentage": round(
                    change_percentage,
                    1
                ),
                "change_points": None,
                "direction": (
                "increase"
                if change_percentage > 0
                else "decrease"
                ),
                "severity": severity,
                "recommendation": get_anomaly_recommendation(
                metric,
                "increase" if change_percentage > 0 else "decrease",
                severity
                ),
                "reason": (
                f"Year-over-year change exceeded "
                f"{threshold}%."
                )
                })

    return anomalies
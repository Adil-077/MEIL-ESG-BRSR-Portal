"""
Static BRSR (Business Responsibility and Sustainability Reporting) metric catalog.
This drives dynamic form rendering, validation rules and the consolidation engine.

data_type values:
    text        - free text, no numeric validation
    yes_no      - restricted to 'Yes' / 'No'
    number      - non-negative float
    integer     - non-negative integer
    percentage  - float between 0 and 100

rollup: True  -> value is numeric and eligible for Project -> Subsidiary -> Group consolidation
        False -> qualitative / organizational, entered independently at every org level
"""

PRINCIPLES = {
    "P1": "Ethics, Transparency and Accountability",
    "P2": "Sustainable & Safe Goods and Services",
    "P3": "Employee Well-being",
    "P4": "Stakeholder Engagement",
    "P5": "Human Rights",
    "P6": "Environment Protection & Restoration",
    "P7": "Public Policy Advocacy",
    "P8": "Inclusive Growth & Equitable Development",
    "P9": "Consumer Value & Engagement",
}

# ---------------------------------------------------------------------------
# SECTION A - General Disclosures (organizational profile, one set per org+FY)
# ---------------------------------------------------------------------------
SECTION_A = [
    {"code": "A_CIN", "name": "Corporate Identity Number (CIN)", "data_type": "text", "required": True},
    {"code": "A_PAID_UP_CAPITAL", "name": "Paid-up Capital (INR Lakhs)", "data_type": "number", "required": True, "unit": "INR Lakhs"},
    {"code": "A_TURNOVER", "name": "Turnover (INR Lakhs)", "data_type": "number", "required": True, "unit": "INR Lakhs"},
    {"code": "A_WEBSITE", "name": "Website", "data_type": "text", "required": False},
    {"code": "A_REG_OFFICE", "name": "Registered Office Address", "data_type": "text", "required": True},
    {"code": "A_CONTACT_EMAIL", "name": "Business Responsibility Contact Email", "data_type": "text", "required": True},
    {"code": "A_CONTACT_PHONE", "name": "Business Responsibility Contact Phone", "data_type": "text", "required": True},
    {"code": "A_TOTAL_EMPLOYEES", "name": "Total Number of Employees", "data_type": "integer", "required": True, "unit": "count"},
]

# ---------------------------------------------------------------------------
# SECTION B - Management & Process Disclosures (policy coverage per principle)
# ---------------------------------------------------------------------------
SECTION_B = [
    {
        "code": f"B_POLICY_{p}",
        "principle": p,
        "name": f"Does the entity have a policy covering {PRINCIPLES[p]}?",
        "data_type": "yes_no",
        "required": True,
    }
    for p in PRINCIPLES
]

# ---------------------------------------------------------------------------
# SECTION C - Principle-wise Quantitative Performance Metrics
# ---------------------------------------------------------------------------
SECTION_C = [
    {"code": "C_P1_TRAINING_HRS", "principle": "P1", "name": "Anti-corruption / ethics training hours imparted", "data_type": "number", "unit": "hours", "min": 0, "rollup": True, "required": True},
    {"code": "C_P1_GRIEVANCES", "principle": "P1", "name": "Number of corruption / conflict-of-interest grievances", "data_type": "integer", "unit": "count", "min": 0, "rollup": True, "required": True},

    {"code": "C_P2_SUSTAINABLE_INVEST", "principle": "P2", "name": "R&D / Capex invested in sustainable products & processes", "data_type": "percentage", "unit": "%", "min": 0, "max": 100, "rollup": False, "required": True},

    {"code": "C_P3_HEALTH_COVERAGE", "principle": "P3", "name": "Employees covered under health insurance", "data_type": "percentage", "unit": "%", "min": 0, "max": 100, "rollup": False, "required": True},
    {"code": "C_P3_INJURIES", "principle": "P3", "name": "Number of workplace injuries (LTIFR incidents)", "data_type": "integer", "unit": "count", "min": 0, "rollup": True, "required": True},

    {"code": "C_P4_STAKEHOLDER_CONSULT", "principle": "P4", "name": "Number of stakeholder consultations conducted", "data_type": "integer", "unit": "count", "min": 0, "rollup": True, "required": True},

    {"code": "C_P5_HR_TRAINING", "principle": "P5", "name": "Employees trained on human rights issues", "data_type": "percentage", "unit": "%", "min": 0, "max": 100, "rollup": False, "required": True},

    {"code": "C_P6_ENERGY", "principle": "P6", "name": "Total energy consumption", "data_type": "number", "unit": "GJ", "min": 0, "rollup": True, "required": True},
    {"code": "C_P6_WATER", "principle": "P6", "name": "Total water withdrawal", "data_type": "number", "unit": "KL", "min": 0, "rollup": True, "required": True},
    {"code": "C_P6_GHG", "principle": "P6", "name": "Total GHG emissions (Scope 1 + Scope 2)", "data_type": "number", "unit": "tCO2e", "min": 0, "rollup": True, "required": True},
    {"code": "C_P6_WASTE", "principle": "P6", "name": "Total waste generated", "data_type": "number", "unit": "tonnes", "min": 0, "rollup": True, "required": True},

    {"code": "C_P7_ADVOCACY", "principle": "P7", "name": "Public policy advocacy engagements undertaken", "data_type": "integer", "unit": "count", "min": 0, "rollup": True, "required": True},

    {"code": "C_P8_CSR_SPEND", "principle": "P8", "name": "CSR spend", "data_type": "number", "unit": "INR Lakhs", "min": 0, "rollup": True, "required": True},
    {"code": "C_P8_CSR_LOCAL_PCT", "principle": "P8", "name": "CSR spend on local area / neighbourhood projects", "data_type": "percentage", "unit": "%", "min": 0, "max": 100, "rollup": False, "required": True},

    {"code": "C_P9_COMPLAINTS", "principle": "P9", "name": "Customer complaints received", "data_type": "integer", "unit": "count", "min": 0, "rollup": True, "required": True},
    {"code": "C_P9_RESOLVED_PCT", "principle": "P9", "name": "Customer complaints resolved", "data_type": "percentage", "unit": "%", "min": 0, "max": 100, "rollup": False, "required": True},
]

ALL_METRICS = SECTION_A + SECTION_B + SECTION_C
METRIC_BY_CODE = {m["code"]: m for m in ALL_METRICS}

# Mapping of Section C metrics to E / S / G pillar, used for dashboard KPI grouping
PILLAR_MAP = {
    "P1": "G", "P4": "G", "P7": "G",
    "P3": "S", "P5": "S", "P8": "S", "P9": "S",
    "P2": "E", "P6": "E",
}


def get_metric(code):
    return METRIC_BY_CODE.get(code)


def rollup_metric_codes():
    """Section C metric codes eligible for Project -> Subsidiary -> Group consolidation."""
    return [m["code"] for m in SECTION_C if m.get("rollup")]

"""
Seed script for the MEIL Group ESG / BRSR Reporting Portal.

Creates:
  - Org hierarchy: MEIL Group -> 2 Subsidiaries -> 3 Business Units/Projects
  - One user per RBAC role (plus one extra BU user)
  - Reporting periods FY 2024-25 (CLOSED) and FY 2025-26 (OPEN)
  - Validated mock BRSR metric values for every org, for both FYs
  - A consolidation pass so Subsidiary/Group Section-C figures are populated
  - A representative ReportSubmission workflow state per org for FY 2025-26
  - A handful of illustrative AuditLog / Review rows

Run with:  python seed_data.py
"""
import random
from datetime import date, datetime

from app import app
from extensions import db
from models import (
    Organization, User, ReportingPeriod, ESGData, ReportSubmission, Review,
)
from utils.metrics_catalog import SECTION_A, SECTION_B, SECTION_C
from utils.consolidation import consolidate_org
from utils.audit import log_action

random.seed(42)


def reset_database():
    db.drop_all()
    db.create_all()


def create_hierarchy():
    group = Organization(name="MEIL Group", code="MEIL-GRP", org_type="GROUP", location="Hyderabad, India")
    db.session.add(group)
    db.session.flush()

    sub_infra = Organization(name="MEIL Infrastructure Ltd.", code="MEIL-INFRA", org_type="SUBSIDIARY",
                              parent_id=group.id, location="Hyderabad, India")
    sub_energy = Organization(name="MEIL Energy & Power Ltd.", code="MEIL-ENERGY", org_type="SUBSIDIARY",
                               parent_id=group.id, location="Hyderabad, India")
    db.session.add_all([sub_infra, sub_energy])
    db.session.flush()

    bu_irrigation = Organization(name="Kaleshwaram Lift Irrigation Project", code="BU-KLIP", org_type="BUSINESS_UNIT",
                                  parent_id=sub_infra.id, location="Telangana, India")
    bu_highway = Organization(name="National Highways Project - NH44", code="BU-NH44", org_type="BUSINESS_UNIT",
                               parent_id=sub_infra.id, location="Andhra Pradesh, India")
    bu_solar = Organization(name="Solar Power Generation Unit", code="BU-SOLAR", org_type="BUSINESS_UNIT",
                             parent_id=sub_energy.id, location="Rajasthan, India")
    db.session.add_all([bu_irrigation, bu_highway, bu_solar])
    db.session.commit()

    return {
        "group": group, "sub_infra": sub_infra, "sub_energy": sub_energy,
        "bu_irrigation": bu_irrigation, "bu_highway": bu_highway, "bu_solar": bu_solar,
    }


def create_users(orgs):
    users_spec = [
        ("superadmin", "superadmin@meil.in", "Rajesh Varma", "SUPER_ADMIN", None, "Admin@123"),
        ("group.esg.admin", "group.esg.admin@meil.in", "Anita Desai", "GROUP_ESG_ADMIN", orgs["group"].id, "Group@123"),
        ("infra.admin", "infra.admin@meil.in", "Suresh Kumar", "SUBSIDIARY_ADMIN", orgs["sub_infra"].id, "Infra@123"),
        ("energy.admin", "energy.admin@meil.in", "Priya Nair", "SUBSIDIARY_ADMIN", orgs["sub_energy"].id, "Energy@123"),
        ("klip.user", "klip.user@meil.in", "Vikram Singh", "BU_USER", orgs["bu_irrigation"].id, "Klip@123"),
        ("nh44.user", "nh44.user@meil.in", "Deepa Rao", "BU_USER", orgs["bu_highway"].id, "Nh44@123"),
        ("solar.user", "solar.user@meil.in", "Arjun Mehta", "BU_USER", orgs["bu_solar"].id, "Solar@123"),
        ("auditor", "auditor@meil.in", "Kavita Iyer", "REVIEWER", None, "Audit@123"),
    ]
    created = {}
    for username, email, full_name, role, org_id, password in users_spec:
        u = User(username=username, email=email, full_name=full_name, role=role, org_id=org_id)
        u.set_password(password)
        db.session.add(u)
        created[username] = u
    db.session.commit()
    return created, [(u[0], u[5], u[3]) for u in users_spec]


def create_periods():
    fy2425 = ReportingPeriod(name="FY 2024-25", start_date=date(2024, 4, 1), end_date=date(2025, 3, 31), status="CLOSED")
    fy2526 = ReportingPeriod(name="FY 2025-26", start_date=date(2025, 4, 1), end_date=date(2026, 3, 31), status="OPEN")
    db.session.add_all([fy2425, fy2526])
    db.session.commit()
    return fy2425, fy2526


def _rand_range(low, high, decimals=1):
    val = random.uniform(low, high)
    return round(val, decimals)


def seed_section_a(org, period, creator_id, turnover_base):
    values = {
        "A_CIN": f"U45201TG{period.start_date.year}PLC{org.id:04d}",
        "A_PAID_UP_CAPITAL": _rand_range(500, 5000, 1),
        "A_TURNOVER": turnover_base,
        "A_WEBSITE": "https://www.meil.in",
        "A_REG_OFFICE": f"{org.location}, India",
        "A_CONTACT_EMAIL": "esg.disclosures@meil.in",
        "A_CONTACT_PHONE": "+91-40-2311-2320",
        "A_TOTAL_EMPLOYEES": random.randint(150, 3000),
    }
    for m in SECTION_A:
        _upsert(org.id, period.id, "A", None, m, str(values[m["code"]]), creator_id)


def seed_section_b(org, period, creator_id):
    for m in SECTION_B:
        answer = random.choice(["Yes", "Yes", "Yes", "No"])  # mostly Yes, some gaps for realism
        _upsert(org.id, period.id, "B", m["principle"], m, answer, creator_id)


def seed_section_c(org, period, creator_id, scale=1.0):
    generators = {
        "C_P1_TRAINING_HRS": lambda: _rand_range(40, 400) * scale,
        "C_P1_GRIEVANCES": lambda: random.randint(0, 5),
        "C_P2_SUSTAINABLE_INVEST": lambda: _rand_range(5, 35),
        "C_P3_HEALTH_COVERAGE": lambda: _rand_range(85, 100),
        "C_P3_INJURIES": lambda: random.randint(0, 8),
        "C_P4_STAKEHOLDER_CONSULT": lambda: random.randint(2, 20),
        "C_P5_HR_TRAINING": lambda: _rand_range(60, 100),
        "C_P6_ENERGY": lambda: _rand_range(500, 8000) * scale,
        "C_P6_WATER": lambda: _rand_range(200, 5000) * scale,
        "C_P6_GHG": lambda: _rand_range(100, 3000) * scale,
        "C_P6_WASTE": lambda: _rand_range(20, 600) * scale,
        "C_P7_ADVOCACY": lambda: random.randint(0, 6),
        "C_P8_CSR_SPEND": lambda: _rand_range(10, 250) * scale,
        "C_P8_CSR_LOCAL_PCT": lambda: _rand_range(30, 90),
        "C_P9_COMPLAINTS": lambda: random.randint(0, 40),
        "C_P9_RESOLVED_PCT": lambda: _rand_range(70, 100),
    }
    for m in SECTION_C:
        raw = generators[m["code"]]()
        if m["data_type"] == "integer":
            val = int(raw)
        else:
            val = round(raw, 2)
        _upsert(org.id, period.id, "C", m["principle"], m, str(val), creator_id)


def _upsert(org_id, period_id, section, principle, metric_def, value, creator_id):
    row = ESGData(
        org_id=org_id, period_id=period_id, section=section, principle=principle,
        metric_code=metric_def["code"], metric_name=metric_def["name"], value=value,
        unit=metric_def.get("unit"), created_by=creator_id, updated_by=creator_id,
    )
    db.session.add(row)


def seed_esg_data(orgs, periods_, users):
    business_units = [orgs["bu_irrigation"], orgs["bu_highway"], orgs["bu_solar"]]
    bu_user_map = {
        orgs["bu_irrigation"].id: users["klip.user"].id,
        orgs["bu_highway"].id: users["nh44.user"].id,
        orgs["bu_solar"].id: users["solar.user"].id,
    }
    for period, year_scale in zip(periods_, [0.85, 1.0]):  # FY24-25 slightly lower than FY25-26 for YoY trend
        for bu in business_units:
            creator_id = bu_user_map[bu.id]
            turnover = _rand_range(2000, 9000)
            seed_section_a(bu, period, creator_id, turnover)
            seed_section_b(bu, period, creator_id)
            seed_section_c(bu, period, creator_id, scale=year_scale)

        # Subsidiary & Group level: only Section A/B entered manually; Section C is consolidated after commit
        for org, creator_username in [
            (orgs["sub_infra"], "infra.admin"), (orgs["sub_energy"], "energy.admin"),
            (orgs["group"], "group.esg.admin"),
        ]:
            creator_id = users[creator_username].id
            turnover = _rand_range(15000, 60000)
            seed_section_a(org, period, creator_id, turnover)
            seed_section_b(org, period, creator_id)

    db.session.commit()


def run_consolidation(orgs, periods_):
    admin_id = None
    for period in periods_:
        consolidate_org(orgs["sub_infra"].id, period.id, user_id=admin_id)
        consolidate_org(orgs["sub_energy"].id, period.id, user_id=admin_id)
        consolidate_org(orgs["group"].id, period.id, user_id=admin_id)


def seed_workflow_state(orgs, fy2425, fy2526, users):
    # FY 2024-25 : fully closed-loop approved for every org (illustrates completed cycle)
    for org in [orgs["bu_irrigation"], orgs["bu_highway"], orgs["bu_solar"], orgs["sub_infra"], orgs["sub_energy"], orgs["group"]]:
        sub = ReportSubmission(
            org_id=org.id, period_id=fy2425.id, status="APPROVED",
            submitted_by=users["group.esg.admin"].id, submitted_at=datetime(2025, 4, 15),
            reviewed_by=users["auditor"].id, reviewed_at=datetime(2025, 4, 20),
            approved_by=users["group.esg.admin"].id, approved_at=datetime(2025, 4, 25),
        )
        db.session.add(sub)
        db.session.flush()
        db.session.add(Review(submission_id=sub.id, reviewer_id=users["auditor"].id, action="START_REVIEW", created_at=datetime(2025, 4, 18)))
        db.session.add(Review(submission_id=sub.id, reviewer_id=users["auditor"].id, action="APPROVE",
                               comment="All figures verified against source records.", created_at=datetime(2025, 4, 20)))
        db.session.add(Review(submission_id=sub.id, reviewer_id=users["group.esg.admin"].id, action="FINAL_APPROVE",
                               comment="Approved for Group BRSR filing.", created_at=datetime(2025, 4, 25)))

    # FY 2025-26 : realistic in-progress pipeline across different stages
    db.session.add(ReportSubmission(org_id=orgs["bu_irrigation"].id, period_id=fy2526.id, status="DRAFT"))
    db.session.add(ReportSubmission(
        org_id=orgs["bu_highway"].id, period_id=fy2526.id, status="SUBMITTED",
        submitted_by=users["nh44.user"].id, submitted_at=datetime(2025, 10, 5),
    ))
    solar_sub = ReportSubmission(
        org_id=orgs["bu_solar"].id, period_id=fy2526.id, status="UNDER_REVIEW",
        submitted_by=users["solar.user"].id, submitted_at=datetime(2025, 10, 1),
        reviewed_by=users["auditor"].id,
    )
    db.session.add(solar_sub)
    db.session.flush()
    db.session.add(Review(submission_id=solar_sub.id, reviewer_id=users["auditor"].id, action="START_REVIEW",
                           created_at=datetime(2025, 10, 3)))

    db.session.add(ReportSubmission(org_id=orgs["sub_infra"].id, period_id=fy2526.id, status="DRAFT"))
    db.session.add(ReportSubmission(org_id=orgs["sub_energy"].id, period_id=fy2526.id, status="DRAFT"))
    db.session.add(ReportSubmission(org_id=orgs["group"].id, period_id=fy2526.id, status="DRAFT"))
    db.session.commit()


def print_summary(users_creds):
    print("\n" + "=" * 72)
    print(" MEIL GROUP ESG / BRSR PORTAL — SEED DATA LOADED SUCCESSFULLY")
    print("=" * 72)
    print(f"{'Username':<18}{'Password':<14}{'Role'}")
    print("-" * 72)
    for username, password, role in users_creds:
        print(f"{username:<18}{password:<14}{role}")
    print("=" * 72)
    print(" Run:  python app.py   then visit http://127.0.0.1:5000")
    print("=" * 72 + "\n")


def main():
    with app.app_context():
        print("Resetting database...")
        reset_database()

        print("Creating organization hierarchy...")
        orgs = create_hierarchy()

        print("Creating users for all 5 RBAC roles...")
        users, users_creds = create_users(orgs)

        print("Creating reporting periods FY 2024-25 and FY 2025-26...")
        fy2425, fy2526 = create_periods()

        print("Seeding validated mock ESG metrics...")
        seed_esg_data(orgs, [fy2425, fy2526], users)

        print("Running roll-up consolidation (Project -> Subsidiary -> Group)...")
        run_consolidation(orgs, [fy2425, fy2526])

        print("Seeding representative workflow states and audit trail...")
        seed_workflow_state(orgs, fy2425, fy2526, users)
        log_action(users["superadmin"].id, "SEED", "System", None, None, "Database seeded with demo dataset")
        db.session.commit()

        print_summary(users_creds)


if __name__ == "__main__":
    main()

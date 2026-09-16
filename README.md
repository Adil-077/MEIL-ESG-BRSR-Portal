# MEIL Group — ESG / BRSR Reporting Portal (MVP)

A production-ready MVP web portal for BRSR (Business Responsibility and
Sustainability Reporting) disclosure collection, review, consolidation and
export across the MEIL Group hierarchy.

**Stack:** Python 3.11+, Flask, Flask-SQLAlchemy, Flask-Login, SQLite,
Bootstrap 5, Chart.js, ReportLab (PDF), openpyxl (Excel).

---

## 1. Architecture Overview

```
MEIL Group (GROUP)
 ├── MEIL Infrastructure Ltd. (SUBSIDIARY)
 │    ├── Kaleshwaram Lift Irrigation Project (BUSINESS_UNIT)
 │    └── National Highways Project - NH44 (BUSINESS_UNIT)
 └── MEIL Energy & Power Ltd. (SUBSIDIARY)
      └── Solar Power Generation Unit (BUSINESS_UNIT)
```

**RBAC Roles**
| Role | Scope |
|---|---|
| Super Admin | Full system access: users, hierarchy, periods, all data |
| Group ESG Admin | Group-wide data, hierarchy, periods, final approval |
| Subsidiary Admin | Own subsidiary + its business units |
| Business Unit User | Own business unit only — data entry & evidence upload |
| Reviewer / Auditor | Cross-org review queue: verify / reject submissions |

**Workflow Pipeline**
```
DRAFT → SUBMITTED → UNDER_REVIEW → VERIFIED → APPROVED
                          │
                          └──→ REJECTED (with mandatory comment) → back to DRAFT-style editing
```

**Consolidation:** Numeric Section-C metrics (e.g. GHG emissions, energy,
water, CSR spend) are entered at Business Unit level and rolled up
automatically to Subsidiary and then Group level via the "Run Consolidation"
action — implemented in `utils/consolidation.py`.

---

## 2. Project Structure

```
esg_portal/
├── app.py                  # Flask routes, RBAC, workflow, exports
├── models.py                # SQLAlchemy models
├── config.py                 # App configuration
├── extensions.py             # db / login_manager singletons
├── seed_data.py               # Demo data seeding script
├── requirements.txt
├── utils/
│   ├── metrics_catalog.py    # BRSR Section A/B/C metric definitions
│   ├── decorators.py         # RBAC decorators
│   ├── validation.py         # Boundary-check validation engine
│   ├── audit.py              # Audit trail logger
│   ├── consolidation.py      # Roll-up engine
│   ├── export_pdf.py         # ReportLab PDF generator
│   └── export_excel.py       # openpyxl Excel generator
├── templates/                # Jinja2 templates (Bootstrap 5)
├── static/
│   ├── css/style.css
│   └── js/dashboard.js       # Chart.js dashboard rendering
├── uploads/                  # Evidence file storage (created at runtime)
└── instance/                 # SQLite database file (created at runtime)
```

---

## 3. Setup Instructions

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed the database (creates instance/esg_portal.db from scratch)
python seed_data.py

# 4. Run the app
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## 4. Demo Login Credentials

| Username | Password | Role |
|---|---|---|
| `superadmin` | `Admin@123` | Super Admin |
| `group.esg.admin` | `Group@123` | Group ESG Admin |
| `infra.admin` | `Infra@123` | Subsidiary Admin (MEIL Infrastructure) |
| `energy.admin` | `Energy@123` | Subsidiary Admin (MEIL Energy & Power) |
| `klip.user` | `Klip@123` | Business Unit User (Kaleshwaram Lift Irrigation) |
| `nh44.user` | `Nh44@123` | Business Unit User (NH44 Highway Project) |
| `solar.user` | `Solar@123` | Business Unit User (Solar Power Unit) |
| `auditor` | `Audit@123` | Reviewer / Auditor |

Seeded data covers **FY 2024-25** (fully approved, closed cycle) and
**FY 2025-26** (open, with a realistic in-progress workflow — one Draft, one
Submitted, one Under Review, at Business Unit level).

## 5. Suggested Walkthrough

1. Log in as `klip.user` → open **Dashboard** → **Open BRSR Disclosure Form**
   → edit a Section C metric → Save → **Submit for Review**.
2. Log in as `auditor` → **Review Queue** → open the submission → **Start
   Review** → **Verify** (or **Reject** with a comment).
3. Log in as `group.esg.admin` → **Review Queue** → grant **Final Approval**
   on a Verified report.
4. As `infra.admin` or `group.esg.admin`, open the **Dashboard**, select the
   Subsidiary/Group entity, and click **Run Consolidation** to roll up
   Business Unit figures.
5. From any disclosure page, use **Export PDF** / **Export Excel** to
   generate a BRSR report pack.
6. As `superadmin` or `group.esg.admin`, open **Audit Trail** to see every
   create/update/workflow transition logged with old/new values.

## 6. Notes on Scope (MVP)

- The BRSR metric catalog (`utils/metrics_catalog.py`) implements a
  representative subset of Section A (8 general fields), Section B (9
  Yes/No policy questions, one per Principle P1–P9), and Section C (17
  quantitative metrics spanning all 9 principles). Extending the catalog to
  the full official BRSR metric set is a matter of adding entries to that
  file — the form rendering, validation, storage, consolidation and export
  layers are fully metric-driven and require no other code changes.
- Evidence files are stored on local disk under `uploads/<org_id>/<period_id>/`.
  For a multi-server production deployment, point this at S3 / Azure Blob
  and swap `utils` file I/O calls for the relevant SDK.
- SQLite is used for zero-config local development. The app can be pointed
  at PostgreSQL/MySQL in production by changing `DATABASE_URL` in `config.py`
  (Flask-SQLAlchemy handles both without code changes).
- Set a strong `SECRET_KEY` environment variable before any real deployment.

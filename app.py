import os
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime, date

from flask import (
    Flask, render_template, redirect, url_for, request, flash, session,
    send_file, abort, jsonify
)
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from werkzeug.utils import secure_filename

from config import Config
from extensions import db, login_manager
from models import (
    User, Organization, ReportingPeriod, ESGData, Evidence, Review,
    ReportSubmission, AuditLog, ROLES, ROLE_LABELS, PERIOD_STATUSES,
    SUBMISSION_STATUSES,
)
from utils.decorators import (
    roles_required, org_access_required, ADMIN_ROLES, HIERARCHY_MANAGERS,
    REVIEW_ROLES, DATA_ENTRY_ROLES,
)
from utils.metrics_catalog import (
    SECTION_A, SECTION_B, SECTION_C, PRINCIPLES, METRIC_BY_CODE, PILLAR_MAP,
    get_metric,
)
from utils.validation import validate_batch
from utils.audit import log_action
from utils.consolidation import consolidate_org
from utils.analytics import get_completeness, get_yoy_anomalies
from utils.export_pdf import build_pdf_report
from utils.export_excel import build_excel_report

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager.init_app(app)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "instance"), exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Template globals / helpers
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    return {
        "ROLE_LABELS": ROLE_LABELS,
        "PRINCIPLES": PRINCIPLES,
        "current_year": datetime.utcnow().year,
    }


def get_or_create_submission(org_id, period_id):
    sub = ReportSubmission.query.filter_by(org_id=org_id, period_id=period_id).first()
    if sub is None:
        sub = ReportSubmission(org_id=org_id, period_id=period_id, status="DRAFT")
        db.session.add(sub)
        db.session.commit()
    return sub


def latest_period():
    return ReportingPeriod.query.order_by(ReportingPeriod.start_date.desc()).first()


def user_default_org():
    if current_user.organization:
        return current_user.organization
    return Organization.query.filter_by(org_type="GROUP").first()


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in app.config["ALLOWED_EXTENSIONS"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active_user and user.check_password(password):
            login_user(user)
            log_action(user.id, "LOGIN", "User", user.id)
            db.session.commit()
            flash(f"Welcome back, {user.full_name}.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Invalid credentials or inactive account.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    log_action(current_user.id, "LOGOUT", "User", current_user.id)
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    accessible_ids = current_user.accessible_org_ids()
    orgs = Organization.query.filter(Organization.id.in_(accessible_ids), Organization.is_active == True).order_by(Organization.org_type, Organization.name).all()
    periods = ReportingPeriod.query.order_by(ReportingPeriod.start_date.desc()).all()

    org_id = request.args.get("org_id", type=int) or (user_default_org().id if user_default_org() else None)
    period_id = request.args.get("period_id", type=int) or (latest_period().id if latest_period() else None)

    if org_id not in accessible_ids and orgs:
        org_id = orgs[0].id

    org = Organization.query.get(org_id) if org_id else None
    period = ReportingPeriod.query.get(period_id) if period_id else None

    submission = None
    pending_reviews = 0
    if org and period:
        submission = ReportSubmission.query.filter_by(org_id=org.id, period_id=period.id).first()
    if current_user.role in REVIEW_ROLES:
        pending_reviews = ReportSubmission.query.filter(ReportSubmission.status.in_(["SUBMITTED", "UNDER_REVIEW"])).count()

    return render_template(
        "dashboard.html",
        orgs=orgs, periods=periods, selected_org=org, selected_period=period,
        submission=submission, pending_reviews=pending_reviews,
    )


@app.route("/api/dashboard-data")
@login_required
def api_dashboard_data():

    org_id = request.args.get("org_id", type=int)
    period_id = request.args.get("period_id", type=int)

    if org_id not in current_user.accessible_org_ids():
        abort(403)

    period = ReportingPeriod.query.get_or_404(period_id)

    prior_period = (
        ReportingPeriod.query
        .filter(ReportingPeriod.start_date < period.start_date)
        .order_by(ReportingPeriod.start_date.desc())
        .first()
    )

    def pillar_totals(pid):
        totals = {"E": 0.0, "S": 0.0, "G": 0.0}

        rows = ESGData.query.filter_by(
            org_id=org_id,
            period_id=pid,
            section="C"
        ).all()

        for r in rows:
            principle = r.principle
            pillar = PILLAR_MAP.get(principle)

            val = r.numeric_value()
            metric = get_metric(r.metric_code)

            if (
                pillar
                and val is not None
                and metric
                and metric.get("data_type") != "percentage"
            ):
                totals[pillar] += val

        return totals

    # ---------------------------------------------------------
    # E / S / G PILLAR TOTALS
    # ---------------------------------------------------------

    current_totals = pillar_totals(period_id)

    prior_totals = (
        pillar_totals(prior_period.id)
        if prior_period
        else {"E": 0, "S": 0, "G": 0}
    )

    # ---------------------------------------------------------
    # KEY HEADLINE METRICS
    # ---------------------------------------------------------

    headline_codes = [
        "C_P6_GHG",
        "C_P6_ENERGY",
        "C_P6_WATER",
        "C_P8_CSR_SPEND"
    ]

    headline = {}

    for code in headline_codes:
        row = ESGData.query.filter_by(
            org_id=org_id,
            period_id=period_id,
            metric_code=code
        ).first()

        headline[code] = (
            row.numeric_value()
            if row and row.numeric_value() is not None
            else 0
        )

    # ---------------------------------------------------------
    # GHG YEAR-ON-YEAR TREND
    # ---------------------------------------------------------

    all_periods = (
        ReportingPeriod.query
        .order_by(ReportingPeriod.start_date)
        .all()
    )

    trend_labels = [p.name for p in all_periods]

    trend_ghg = []

    for p in all_periods:

        row = ESGData.query.filter_by(
            org_id=org_id,
            period_id=p.id,
            metric_code="C_P6_GHG"
        ).first()

        trend_ghg.append(
            row.numeric_value()
            if row and row.numeric_value() is not None
            else 0
        )

    # ---------------------------------------------------------
    # ESG INTELLIGENCE
    # ---------------------------------------------------------

    completeness = get_completeness(
        org_id,
        period_id
    )

    anomalies = get_yoy_anomalies(
        org_id,
        period_id
    )

    # ---------------------------------------------------------
    # FINAL DASHBOARD RESPONSE
    # ---------------------------------------------------------

    return jsonify({

        # Existing dashboard data
        "pillar_current": current_totals,
        "pillar_prior": prior_totals,
        "prior_period_name": (
            prior_period.name
            if prior_period
            else None
        ),

        "headline": headline,

        "trend_labels": trend_labels,
        "trend_ghg": trend_ghg,

        # New ESG Intelligence
        "completeness": completeness,
        "anomalies": anomalies,

    })
# ---------------------------------------------------------------------------
# Hierarchy management
# ---------------------------------------------------------------------------
@app.route("/hierarchy")
@login_required
@roles_required(*HIERARCHY_MANAGERS, "REVIEWER")
def hierarchy():
    accessible_ids = current_user.accessible_org_ids()
    orgs = Organization.query.filter(Organization.id.in_(accessible_ids)).order_by(Organization.org_type, Organization.name).all()
    return render_template("hierarchy.html", orgs=orgs)


@app.route("/hierarchy/add", methods=["GET", "POST"])
@login_required
@roles_required(*HIERARCHY_MANAGERS)
def hierarchy_add():
    accessible_ids = current_user.accessible_org_ids()
    possible_parents = Organization.query.filter(Organization.id.in_(accessible_ids), Organization.org_type != "BUSINESS_UNIT").all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        org_type = request.form.get("org_type")
        parent_id = request.form.get("parent_id", type=int)
        location = request.form.get("location", "").strip()

        errors = []
        if not name:
            errors.append("Name is required.")
        if not code:
            errors.append("Code is required.")
        elif Organization.query.filter_by(code=code).first():
            errors.append("Org code already exists.")
        if org_type not in ("SUBSIDIARY", "BUSINESS_UNIT"):
            errors.append("Invalid organization type.")
        if parent_id and parent_id not in accessible_ids:
            errors.append("You do not have access to that parent organization.")
        if current_user.role == "SUBSIDIARY_ADMIN" and org_type != "BUSINESS_UNIT":
            errors.append("Subsidiary Admins may only create Business Units.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            org = Organization(name=name, code=code, org_type=org_type, parent_id=parent_id, location=location)
            db.session.add(org)
            db.session.commit()
            log_action(current_user.id, "CREATE", "Organization", org.id, None, f"{name} ({org_type})")
            db.session.commit()
            flash(f"Organization '{name}' created.", "success")
            return redirect(url_for("hierarchy"))

    return render_template("org_form.html", possible_parents=possible_parents, org=None)


@app.route("/hierarchy/<int:org_id>/toggle", methods=["POST"])
@login_required
@roles_required(*HIERARCHY_MANAGERS)
@org_access_required
def hierarchy_toggle(org_id):
    org = Organization.query.get_or_404(org_id)
    old = org.is_active
    org.is_active = not org.is_active
    db.session.commit()
    log_action(current_user.id, "UPDATE", "Organization", org.id, f"is_active={old}", f"is_active={org.is_active}")
    db.session.commit()
    flash(f"Organization '{org.name}' {'activated' if org.is_active else 'deactivated'}.", "success")
    return redirect(url_for("hierarchy"))


# ---------------------------------------------------------------------------
# Reporting period management
# ---------------------------------------------------------------------------
@app.route("/periods")
@login_required
def periods():
    all_periods = ReportingPeriod.query.order_by(ReportingPeriod.start_date.desc()).all()
    return render_template("periods.html", periods=all_periods)


@app.route("/periods/add", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def periods_add():
    name = request.form.get("name", "").strip()
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    errors = []
    if not name or ReportingPeriod.query.filter_by(name=name).first():
        errors.append("A unique period name is required (e.g. FY 2026-27).")
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
        if ed <= sd:
            errors.append("End date must be after start date.")
    except (ValueError, TypeError):
        errors.append("Valid start and end dates are required.")
        sd = ed = None

    if errors:
        for e in errors:
            flash(e, "danger")
    else:
        p = ReportingPeriod(name=name, start_date=sd, end_date=ed, status="OPEN")
        db.session.add(p)
        db.session.commit()
        log_action(current_user.id, "CREATE", "ReportingPeriod", p.id, None, name)
        db.session.commit()
        flash(f"Reporting period '{name}' created.", "success")
    return redirect(url_for("periods"))


@app.route("/periods/<int:period_id>/status", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def periods_status(period_id):
    p = ReportingPeriod.query.get_or_404(period_id)
    new_status = request.form.get("status")
    if new_status not in PERIOD_STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("periods"))
    old = p.status
    p.status = new_status
    db.session.commit()
    log_action(current_user.id, "UPDATE", "ReportingPeriod", p.id, f"status={old}", f"status={new_status}")
    db.session.commit()
    flash(f"Period '{p.name}' status set to {new_status}.", "success")
    return redirect(url_for("periods"))


# ---------------------------------------------------------------------------
# User management (Super Admin)
# ---------------------------------------------------------------------------
@app.route("/users")
@login_required
@roles_required("SUPER_ADMIN")
def users():
    all_users = User.query.order_by(User.role, User.username).all()
    orgs = Organization.query.filter_by(is_active=True).order_by(Organization.org_type, Organization.name).all()
    return render_template("users.html", users=all_users, orgs=orgs, roles=ROLES)


@app.route("/users/add", methods=["POST"])
@login_required
@roles_required("SUPER_ADMIN")
def users_add():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role")
    org_id = request.form.get("org_id", type=int)
    password = request.form.get("password", "")

    errors = []
    if not username or User.query.filter_by(username=username).first():
        errors.append("A unique username is required.")
    if not email or User.query.filter_by(email=email).first():
        errors.append("A unique email is required.")
    if role not in ROLES:
        errors.append("Invalid role.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if role != "GROUP_ESG_ADMIN" and role != "SUPER_ADMIN" and role != "REVIEWER" and not org_id:
        errors.append("An organization must be assigned for this role.")

    if errors:
        for e in errors:
            flash(e, "danger")
    else:
        u = User(username=username, email=email, full_name=full_name, role=role, org_id=org_id)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        log_action(current_user.id, "CREATE", "User", u.id, None, f"{username} ({role})")
        db.session.commit()
        flash(f"User '{username}' created.", "success")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@roles_required("SUPER_ADMIN")
def users_toggle(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("users"))
    old = u.is_active_user
    u.is_active_user = not u.is_active_user
    db.session.commit()
    log_action(current_user.id, "UPDATE", "User", u.id, f"is_active={old}", f"is_active={u.is_active_user}")
    db.session.commit()
    flash(f"User '{u.username}' {'activated' if u.is_active_user else 'deactivated'}.", "success")
    return redirect(url_for("users"))


# ---------------------------------------------------------------------------
# ESG Disclosure entry
# ---------------------------------------------------------------------------
@app.route("/esg/<int:org_id>/<int:period_id>")
@login_required
@org_access_required
def esg_entry(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    period = ReportingPeriod.query.get_or_404(period_id)
    submission = get_or_create_submission(org_id, period_id)

    rows = ESGData.query.filter_by(org_id=org_id, period_id=period_id).all()
    values_by_code = {r.metric_code: r for r in rows}

    is_bu = org.org_type == "BUSINESS_UNIT"
    can_edit = (
        current_user.role in DATA_ENTRY_ROLES
        and org_id in current_user.accessible_org_ids()
        and period.status in ("OPEN", "REVIEW")
        and submission.status in ("DRAFT", "REJECTED")
    )
    # A Subsidiary/Group admin editing a BU's data directly isn't allowed unless it's their own org
    if current_user.role == "BU_USER" and current_user.org_id != org_id:
        can_edit = False

    evidences_by_esg_id = {r.id: r.evidences for r in rows}

    return render_template(
        "esg_entry.html",
        org=org, period=period, submission=submission,
        section_a=SECTION_A, section_b=SECTION_B, section_c=SECTION_C,
        principles=PRINCIPLES, values=values_by_code, is_bu=is_bu,
        can_edit=can_edit, evidences_by_esg_id=evidences_by_esg_id,
    )


@app.route("/esg/<int:org_id>/<int:period_id>/save", methods=["POST"])
@login_required
@org_access_required
def esg_save(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    period = ReportingPeriod.query.get_or_404(period_id)
    submission = get_or_create_submission(org_id, period_id)
    section = request.form.get("section", "A")

    if period.status == "CLOSED":
        flash("This reporting period is closed and cannot be edited.", "danger")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))
    if submission.status not in ("DRAFT", "REJECTED"):
        flash("This report has already been submitted and is locked for editing.", "warning")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))

    catalog = {"A": SECTION_A, "B": SECTION_B, "C": SECTION_C}.get(section, [])
    # Section C rollup metrics are read-only / system-generated for non-BU orgs
    editable_catalog = catalog
    if section == "C" and org.org_type != "BUSINESS_UNIT":
        editable_catalog = [m for m in catalog if not m.get("rollup")]

    metric_defs = {m["code"]: m for m in editable_catalog}
    form_values = {code: request.form.get(code, "") for code in metric_defs}

    errors, clean_values = validate_batch(metric_defs, form_values)

    if errors:
        for code, msg in errors.items():
            flash(msg, "danger")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id) + f"#section-{section}")

    for code, clean_val in clean_values.items():
        metric_def = metric_defs[code]
        existing = ESGData.query.filter_by(org_id=org_id, period_id=period_id, metric_code=code).first()
        old_val = existing.value if existing else None
        if existing:
            if existing.value != clean_val:
                existing.value = clean_val
                existing.updated_by = current_user.id
                log_action(current_user.id, "UPDATE", "ESGData", existing.id, old_val, clean_val)
        else:
            new_row = ESGData(
                org_id=org_id, period_id=period_id,
                section=section, principle=metric_def.get("principle"),
                metric_code=code, metric_name=metric_def["name"],
                value=clean_val, unit=metric_def.get("unit"),
                created_by=current_user.id, updated_by=current_user.id,
            )
            db.session.add(new_row)
            db.session.flush()
            log_action(current_user.id, "CREATE", "ESGData", new_row.id, None, clean_val)

    db.session.commit()
    flash(f"Section {section} saved successfully.", "success")
    return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id) + f"#section-{section}")


@app.route("/esg/<int:org_id>/<int:period_id>/submit", methods=["POST"])
@login_required
@org_access_required
def esg_submit(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    period = ReportingPeriod.query.get_or_404(period_id)
    submission = get_or_create_submission(org_id, period_id)

    if period.status == "CLOSED":
        flash("This reporting period is closed.", "danger")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))
    if submission.status not in ("DRAFT", "REJECTED"):
        flash("Report has already been submitted.", "warning")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))

    # Required-field completeness check across all sections
    catalog = SECTION_A + SECTION_B + (SECTION_C if org.org_type == "BUSINESS_UNIT" else [m for m in SECTION_C if not m.get("rollup")])
    rows = {r.metric_code: r for r in ESGData.query.filter_by(org_id=org_id, period_id=period_id).all()}
    missing = [m["name"] for m in catalog if m.get("required") and not (rows.get(m["code"]) and rows[m["code"]].value)]
    if missing:
        flash(f"Cannot submit — {len(missing)} required field(s) missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}", "danger")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))

    old_status = submission.status
    submission.status = "SUBMITTED"
    submission.submitted_by = current_user.id
    submission.submitted_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user.id, "SUBMIT", "ReportSubmission", submission.id, old_status, "SUBMITTED")
    db.session.commit()
    flash("Report submitted for review.", "success")
    return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))


# ---------------------------------------------------------------------------
# Evidence management
# ---------------------------------------------------------------------------
@app.route("/evidence/upload", methods=["POST"])
@login_required
def evidence_upload():
    esg_data_id = request.form.get("esg_data_id", type=int)

    file = request.files.get("file")

    if not esg_data_id or not file or not file.filename:
        flash("Please select a file to upload.", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    ev_data = ESGData.query.get_or_404(esg_data_id)

    if ev_data.org_id not in current_user.accessible_org_ids():
        abort(403)

    period = ReportingPeriod.query.get_or_404(ev_data.period_id)

    submission = get_or_create_submission(
        ev_data.org_id,
        ev_data.period_id
    )

    if (
        current_user.role not in DATA_ENTRY_ROLES
        or ev_data.org_id not in current_user.accessible_org_ids()
        or period.status not in ("OPEN", "REVIEW")
        or submission.status not in ("DRAFT", "REJECTED")
    ):
        abort(403)

    filename = secure_filename(file.filename)

    if not filename:
        flash("Invalid file name.", "danger")
        return redirect(
            url_for(
                "esg_entry",
                org_id=ev_data.org_id,
                period_id=ev_data.period_id
            )
        )
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], "evidence")
    os.makedirs(upload_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}_{filename}"
    stored_path = os.path.join(upload_dir, stored_name)

    file.save(stored_path)

    evidence = Evidence(
        esg_data_id=ev_data.id,
        file_name=filename,
        stored_path=stored_path,
        uploaded_by=current_user.id,
        status="PENDING"
    )

    db.session.add(evidence)
    db.session.commit()

    log_action(
        current_user.id,
        "UPLOAD",
        "Evidence",
        evidence.id,
        None,
        filename
    )
    db.session.commit()

    flash("Evidence uploaded successfully.", "success")

    return redirect(
        url_for(
            "esg_entry",
            org_id=ev_data.org_id,
            period_id=ev_data.period_id
        )
    )
@app.route("/evidence/<int:evidence_id>/delete", methods=["POST"])
@login_required
def evidence_delete(evidence_id):
    ev = Evidence.query.get_or_404(evidence_id)

    if ev.esg_data.org_id not in current_user.accessible_org_ids():
        abort(403)

    if current_user.role not in DATA_ENTRY_ROLES:
        abort(403)

    old_filename = ev.file_name

    # Delete physical file
    if os.path.exists(ev.stored_path):
        os.remove(ev.stored_path)

    db.session.delete(ev)
    db.session.commit()

    log_action(
        current_user.id,
        "DELETE",
        "Evidence",
        evidence_id,
        old_filename,
        None
    )
    db.session.commit()

    flash("Evidence deleted successfully.", "success")

    return redirect(
        url_for(
            "esg_entry",
            org_id=ev.esg_data.org_id,
            period_id=ev.esg_data.period_id
        )
    )
@app.route("/evidence/<int:evidence_id>/download")
@login_required
def evidence_download(evidence_id):
    ev = Evidence.query.get_or_404(evidence_id)

    if ev.esg_data.org_id not in current_user.accessible_org_ids():
        abort(403)

    if not os.path.exists(ev.stored_path):
        flash("Evidence file not found.", "danger")
        return redirect(
            url_for(
                "esg_entry",
                org_id=ev.esg_data.org_id,
                period_id=ev.esg_data.period_id
            )
        )

    return send_file(
        ev.stored_path,
        as_attachment=True,
        download_name=ev.file_name
    )
@app.route("/evidence/<int:evidence_id>/verify", methods=["POST"])
@login_required
def evidence_verify(evidence_id):

    ev = Evidence.query.get_or_404(evidence_id)

    if ev.esg_data.org_id not in current_user.accessible_org_ids():
        abort(403)

    # Only reviewers/admins can verify evidence
    allowed_roles = [
        "SUPER_ADMIN",
        "GROUP_ESG_ADMIN",
        "SUBSIDIARY_ADMIN",
        "REVIEWER"
    ]

    if current_user.role not in allowed_roles:
        abort(403)

    old_status = ev.status

    ev.status = "VERIFIED"
    ev.verified_by = current_user.id
    ev.verified_at = datetime.utcnow()
    ev.verification_comment = request.form.get("comment", "").strip() or None

    db.session.commit()

    log_action(
        current_user.id,
        "VERIFY",
        "Evidence",
        ev.id,
        old_status,
        "VERIFIED"
    )

    db.session.commit()

    flash("Evidence marked as verified.", "success")

    return redirect(
        url_for(
            "esg_entry",
            org_id=ev.esg_data.org_id,
            period_id=ev.esg_data.period_id
        )
    )


@app.route("/evidence/<int:evidence_id>/reject", methods=["POST"])
@login_required
def evidence_reject(evidence_id):

    ev = Evidence.query.get_or_404(evidence_id)

    if ev.esg_data.org_id not in current_user.accessible_org_ids():
        abort(403)

    # Only reviewers/admins can reject evidence
    allowed_roles = [
        "SUPER_ADMIN",
        "GROUP_ESG_ADMIN",
        "SUBSIDIARY_ADMIN",
        "REVIEWER"
    ]

    if current_user.role not in allowed_roles:
        abort(403)

    comment = request.form.get("comment", "").strip()

    if not comment:
        flash("A rejection comment is required.", "danger")

        return redirect(
            url_for(
                "esg_entry",
                org_id=ev.esg_data.org_id,
                period_id=ev.esg_data.period_id
            )
        )

    old_status = ev.status

    ev.status = "REJECTED"
    ev.verified_by = current_user.id
    ev.verified_at = datetime.utcnow()
    ev.verification_comment = comment

    db.session.commit()

    log_action(
        current_user.id,
        "REJECT",
        "Evidence",
        ev.id,
        old_status,
        comment
    )

    db.session.commit()

    flash("Evidence rejected.", "warning")

    return redirect(
        url_for(
            "esg_entry",
            org_id=ev.esg_data.org_id,
            period_id=ev.esg_data.period_id
        )
    )# ---------------------------------------------------------------------------
# Review workflow
# ---------------------------------------------------------------------------
@app.route("/review")
@login_required
@roles_required(*REVIEW_ROLES)
def review_dashboard():
    submissions = (ReportSubmission.query
                   .filter(ReportSubmission.status.in_(["SUBMITTED", "UNDER_REVIEW", "VERIFIED", "REJECTED", "APPROVED"]))
                   .order_by(ReportSubmission.updated_at.desc()).all())
    return render_template("review_dashboard.html", submissions=submissions)


@app.route("/review/<int:submission_id>")
@login_required
@roles_required(*REVIEW_ROLES)
def review_detail(submission_id):
    submission = ReportSubmission.query.get_or_404(submission_id)
    org = submission.organization
    period = submission.period
    rows = ESGData.query.filter_by(org_id=org.id, period_id=period.id).all()
    values_by_code = {r.metric_code: r for r in rows}
    return render_template(
        "review_detail.html", submission=submission, org=org, period=period,
        section_a=SECTION_A, section_b=SECTION_B, section_c=SECTION_C,
        principles=PRINCIPLES, values=values_by_code,
    )


@app.route("/review/<int:submission_id>/start", methods=["POST"])
@login_required
@roles_required(*REVIEW_ROLES)
def review_start(submission_id):
    submission = ReportSubmission.query.get_or_404(submission_id)
    if submission.status != "SUBMITTED":
        flash("Only submitted reports can enter review.", "warning")
        return redirect(url_for("review_dashboard"))
    old = submission.status
    submission.status = "UNDER_REVIEW"
    submission.reviewed_by = current_user.id
    db.session.add(Review(submission_id=submission.id, reviewer_id=current_user.id, action="START_REVIEW"))
    db.session.commit()
    log_action(current_user.id, "REVIEW_START", "ReportSubmission", submission.id, old, "UNDER_REVIEW")
    db.session.commit()
    flash("Report moved to Under Review.", "success")
    return redirect(url_for("review_detail", submission_id=submission.id))


@app.route("/review/<int:submission_id>/decision", methods=["POST"])
@login_required
@roles_required(*REVIEW_ROLES)
def review_decision(submission_id):
    submission = ReportSubmission.query.get_or_404(submission_id)
    action = request.form.get("action")
    comment = request.form.get("comment", "").strip()

    if submission.status != "UNDER_REVIEW":
        flash("Report must be Under Review before a decision can be recorded.", "warning")
        return redirect(url_for("review_dashboard"))
    if action == "reject" and not comment:
        flash("A comment is required when rejecting a report.", "danger")
        return redirect(url_for("review_detail", submission_id=submission.id))

    old = submission.status
    if action == "approve":
        submission.status = "VERIFIED"
        submission.reviewed_at = datetime.utcnow()
        review_action = "APPROVE"
    elif action == "reject":
        submission.status = "REJECTED"
        submission.reviewed_at = datetime.utcnow()
        review_action = "REJECT"
    else:
        flash("Invalid review action.", "danger")
        return redirect(url_for("review_detail", submission_id=submission.id))

    db.session.add(Review(submission_id=submission.id, reviewer_id=current_user.id, action=review_action, comment=comment))
    db.session.commit()
    log_action(current_user.id, f"REVIEW_{review_action}", "ReportSubmission", submission.id, old, submission.status)
    db.session.commit()
    flash(f"Report {'verified' if action == 'approve' else 'rejected'}.", "success")
    return redirect(url_for("review_dashboard"))


@app.route("/review/<int:submission_id>/final-approve", methods=["POST"])
@login_required
@roles_required(*ADMIN_ROLES)
def review_final_approve(submission_id):
    submission = ReportSubmission.query.get_or_404(submission_id)
    comment = request.form.get("comment", "").strip()
    if submission.status != "VERIFIED":
        flash("Only verified reports can receive final approval.", "warning")
        return redirect(url_for("review_dashboard"))

    old = submission.status
    submission.status = "APPROVED"
    submission.approved_by = current_user.id
    submission.approved_at = datetime.utcnow()
    db.session.add(Review(submission_id=submission.id, reviewer_id=current_user.id, action="FINAL_APPROVE", comment=comment))
    db.session.commit()
    log_action(current_user.id, "FINAL_APPROVE", "ReportSubmission", submission.id, old, "APPROVED")
    db.session.commit()
    flash("Report given final approval.", "success")
    return redirect(url_for("review_dashboard"))


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------
@app.route("/consolidate/<int:org_id>/<int:period_id>", methods=["POST"])
@login_required
@roles_required(*HIERARCHY_MANAGERS)
@org_access_required
def consolidate(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    if org.org_type == "BUSINESS_UNIT":
        flash("Consolidation only applies to Subsidiary or Group level organizations.", "danger")
        return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))
    results = consolidate_org(org_id, period_id, user_id=current_user.id)
    flash(f"Consolidation complete — {len(results)} metric(s) rolled up from subordinate entities.", "success")
    return redirect(url_for("esg_entry", org_id=org_id, period_id=period_id))


# ---------------------------------------------------------------------------
# Export engine
# ---------------------------------------------------------------------------
@app.route("/export/pdf/<int:org_id>/<int:period_id>")
@login_required
@org_access_required
def export_pdf(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    period = ReportingPeriod.query.get_or_404(period_id)
    submission = ReportSubmission.query.filter_by(org_id=org_id, period_id=period_id).first()
    rows = ESGData.query.filter_by(org_id=org_id, period_id=period_id).all()
    buf = build_pdf_report(org, period, rows, submission)
    log_action(current_user.id, "EXPORT_PDF", "ReportSubmission", submission.id if submission else None)
    db.session.commit()
    filename = f"BRSR_{org.code}_{period.name.replace(' ', '_')}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/export/excel/<int:org_id>/<int:period_id>")
@login_required
@org_access_required
def export_excel(org_id, period_id):
    org = Organization.query.get_or_404(org_id)
    period = ReportingPeriod.query.get_or_404(period_id)
    rows = ESGData.query.filter_by(org_id=org_id, period_id=period_id).all()
    buf = build_excel_report(org, period, rows)
    log_action(current_user.id, "EXPORT_EXCEL", "Organization", org_id)
    db.session.commit()
    filename = f"BRSR_{org.code}_{period.name.replace(' ', '_')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------
@app.route("/audit-log")
@login_required
@roles_required(*ADMIN_ROLES)
def audit_log():
    entity_filter = request.args.get("entity", "")
    query = AuditLog.query
    if entity_filter:
        query = query.filter(AuditLog.entity == entity_filter)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    entities = [e[0] for e in db.session.query(AuditLog.entity).distinct().all()]
    return render_template("audit_log.html", logs=logs, entities=entities, selected_entity=entity_filter)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="The page you requested could not be found."), 404


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)

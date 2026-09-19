from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums (stored as plain strings for SQLite simplicity, validated in code)
# ---------------------------------------------------------------------------
ROLES = ["SUPER_ADMIN", "GROUP_ESG_ADMIN", "SUBSIDIARY_ADMIN", "BU_USER", "REVIEWER"]

ROLE_LABELS = {
    "SUPER_ADMIN": "Super Admin",
    "GROUP_ESG_ADMIN": "Group ESG Admin",
    "SUBSIDIARY_ADMIN": "Subsidiary Admin",
    "BU_USER": "Business Unit User",
    "REVIEWER": "Reviewer / Auditor",
}

ORG_TYPES = ["GROUP", "SUBSIDIARY", "BUSINESS_UNIT"]

PERIOD_STATUSES = ["OPEN", "REVIEW", "CLOSED"]

SUBMISSION_STATUSES = ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "VERIFIED", "APPROVED", "REJECTED"]
EVIDENCE_STATUSES = ["PENDING", "VERIFIED", "REJECTED"]


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    org_type = db.Column(db.String(20), nullable=False)  # GROUP / SUBSIDIARY / BUSINESS_UNIT
    parent_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True)
    location = db.Column(db.String(150))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    parent = db.relationship("Organization", remote_side=[id], backref="children")

    def descendant_ids(self, include_self=True):
        """Recursively collect ids of this org and all descendants."""
        ids = [self.id] if include_self else []
        for child in self.children:
            ids.extend(child.descendant_ids(include_self=True))
        return ids

    def __repr__(self):
        return f"<Organization {self.code} {self.name}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    organization = db.relationship("Organization", backref="users")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # Flask-Login expects is_active as a property/attribute
    @property
    def is_active(self):
        return self.is_active_user

    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    def accessible_org_ids(self):
        """Org ids this user is permitted to view/act on, based on hierarchy."""
        if self.role in ("SUPER_ADMIN", "GROUP_ESG_ADMIN", "REVIEWER"):
            return [o.id for o in Organization.query.all()]
        if self.organization is None:
            return []
        return self.organization.descendant_ids(include_self=True)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class ReportingPeriod(db.Model):
    __tablename__ = "reporting_periods"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)  # e.g. "FY 2025-26"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="OPEN")  # OPEN / REVIEW / CLOSED
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f"<ReportingPeriod {self.name} [{self.status}]>"


class ReportSubmission(db.Model):
    """Represents the overall workflow state of one org's BRSR report for one FY."""
    __tablename__ = "report_submissions"
    __table_args__ = (db.UniqueConstraint("org_id", "period_id", name="uq_submission_org_period"),)

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey("reporting_periods.id"), nullable=False)
    status = db.Column(db.String(20), default="DRAFT", nullable=False)

    submitted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    organization = db.relationship("Organization", backref="submissions")
    period = db.relationship("ReportingPeriod", backref="submissions")
    reviews = db.relationship("Review", backref="submission", order_by="Review.created_at")

    def __repr__(self):
        return f"<ReportSubmission org={self.org_id} period={self.period_id} {self.status}>"


class ESGData(db.Model):
    """A single BRSR metric value for one org, in one reporting period."""
    __tablename__ = "esg_data"
    __table_args__ = (db.UniqueConstraint("org_id", "period_id", "metric_code", name="uq_metric_per_org_period"),)

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey("reporting_periods.id"), nullable=False)

    section = db.Column(db.String(1), nullable=False)  # A / B / C
    principle = db.Column(db.String(5), nullable=True)  # P1..P9, null for Section A
    metric_code = db.Column(db.String(50), nullable=False)
    metric_name = db.Column(db.String(255), nullable=False)
    value = db.Column(db.String(255))  # stored as text; interpreted per data_type
    unit = db.Column(db.String(30))

    is_consolidated = db.Column(db.Boolean, default=False)  # True if value was rolled up automatically

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    organization = db.relationship("Organization", backref="esg_entries")
    period = db.relationship("ReportingPeriod", backref="esg_entries")
    evidences = db.relationship("Evidence", backref="esg_data", cascade="all, delete-orphan")

    def numeric_value(self):
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return None

    def __repr__(self):
        return f"<ESGData {self.metric_code}={self.value} org={self.org_id}>"


class Evidence(db.Model):

    __tablename__ = "evidence"

    id = db.Column(db.Integer, primary_key=True)

    esg_data_id = db.Column(
        db.Integer,
        db.ForeignKey("esg_data.id"),
        nullable=False
    )

    file_name = db.Column(db.String(255), nullable=False)

    stored_path = db.Column(db.String(500), nullable=False)

    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    uploaded_at = db.Column(
        db.DateTime,
        default=utcnow
    )

    # Evidence verification
    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING"
    )

    verified_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    verified_at = db.Column(
        db.DateTime,
        nullable=True
    )

    verification_comment = db.Column(
        db.Text,
        nullable=True
    )

    uploader = db.relationship(
        "User",
        foreign_keys=[uploaded_by]
    )

    verifier = db.relationship(
        "User",
        foreign_keys=[verified_by]
    )

    def __repr__(self):
        return f"<Evidence {self.file_name}>"

class Review(db.Model):
    """A single review action (start review / approve / reject) on a ReportSubmission."""
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("report_submissions.id"), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(30), nullable=False)  # START_REVIEW / APPROVE / REJECT / FINAL_APPROVE
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

    reviewer = db.relationship("User")

    def __repr__(self):
        return f"<Review {self.action} by user={self.reviewer_id}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity = db.Column(db.String(100), nullable=False)
    entity_id = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity}#{self.entity_id}>"

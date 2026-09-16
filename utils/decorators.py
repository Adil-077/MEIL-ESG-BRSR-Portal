from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def roles_required(*roles):
    """Restrict a view to one or more of the 5 RBAC roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.role not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def org_access_required(view_func):
    """
    Ensures the requesting user may act on the org_id supplied in the route
    (as a URL kwarg named 'org_id'), based on group hierarchy scoping.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        org_id = kwargs.get("org_id")
        if org_id is not None:
            org_id = int(org_id)
            if org_id not in current_user.accessible_org_ids():
                abort(403)
        return view_func(*args, **kwargs)
    return wrapped


# Convenience role groupings used across routes
ADMIN_ROLES = ("SUPER_ADMIN", "GROUP_ESG_ADMIN")
HIERARCHY_MANAGERS = ("SUPER_ADMIN", "GROUP_ESG_ADMIN", "SUBSIDIARY_ADMIN")
REVIEW_ROLES = ("REVIEWER", "GROUP_ESG_ADMIN", "SUPER_ADMIN")
DATA_ENTRY_ROLES = ("BU_USER", "SUBSIDIARY_ADMIN", "GROUP_ESG_ADMIN", "SUPER_ADMIN")

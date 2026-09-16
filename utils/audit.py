from extensions import db
from models import AuditLog


def log_action(user_id, action, entity, entity_id=None, old_value=None, new_value=None):
    """
    Central audit-trail writer. Called from every state-changing route so
    that every create/update/delete/workflow-transition is traceable.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    )
    db.session.add(entry)
    # Caller is responsible for the surrounding db.session.commit() so the
    # audit row is committed atomically with the business-data change.
    return entry

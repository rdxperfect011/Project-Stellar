from flask import request
from flask_login import current_user
from app import db
from app.models.admin import AuditLog

def log_admin_action(action, details=None):
    """
    Helper function to log an admin action.
    Should be called within a Flask application context.
    """
    if not current_user.is_authenticated:
        return
        
    admin_email = current_user.email
    ip_address = request.remote_addr
    
    log = AuditLog(
        admin_email=admin_email,
        action=action,
        details=details,
        ip_address=ip_address
    )
    db.session.add(log)
    db.session.commit()

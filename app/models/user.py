from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone

# ── Role-based permission definitions ──────────────────────────────────
# Each key is a "page slug" used in templates and route guards.
# Values list the roles allowed to view that page.
ROLE_PERMISSIONS = {
    'dashboard':          ['ADMIN', 'MANAGER'],
    'bookings':           ['ADMIN', 'MANAGER', 'RECEPTIONIST'],
    'inquiries':          ['ADMIN', 'MANAGER', 'RECEPTIONIST'],
    'availability':       ['ADMIN', 'MANAGER'],
    'content':            ['ADMIN'],
    'emails':             ['ADMIN'],
    'staff':              ['ADMIN'],
    'audit_logs':         ['ADMIN', 'MANAGER'],
    'export_csv':         ['ADMIN', 'MANAGER'],
    'revenue':            ['ADMIN'],
}

# Human-readable permission labels per role (for the permissions preview)
ROLE_PERMISSION_LABELS = {
    'RECEPTIONIST': {
        'can': [
            'View Bookings & Enquiries',
            'Accept / Reject Enquiries',
            'Mark Check-in / Check-out',
            'View Contact Messages',
        ],
        'cannot': [
            'View Dashboard Analytics',
            'View Revenue Data',
            'Manage Content',
            'Manage Staff',
            'View Audit Logs',
            'Export CSV',
        ],
    },
    'MANAGER': {
        'can': [
            'View Bookings & Enquiries',
            'Accept / Reject Enquiries',
            'Mark Check-in / Check-out',
            'View Contact Messages',
            'View Dashboard (no Revenue)',
            'View Booking Trends Chart',
            'Export CSV',
            'View Audit Logs',
        ],
        'cannot': [
            'Manage Staff',
            'Manage Content',
            'View Revenue Data',
        ],
    },
}


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='ADMIN')
    is_active_staff = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
        
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ── Role helpers ───────────────────────────────────────────────────
    @property
    def is_admin(self):
        return self.role == 'ADMIN'

    @property
    def is_manager(self):
        return self.role == 'MANAGER'

    @property
    def is_receptionist(self):
        return self.role == 'RECEPTIONIST'

    def can_access(self, page_slug):
        """Return True if this user's role allows access to *page_slug*."""
        allowed = ROLE_PERMISSIONS.get(page_slug)
        if allowed is None:
            return True          # pages not listed are open
        return self.role in allowed

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

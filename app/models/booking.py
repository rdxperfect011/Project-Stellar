from app import db
from datetime import datetime, timezone

class BookingEnquiry(db.Model):
    __tablename__ = 'booking_enquiries'
    id = db.Column(db.Integer, primary_key=True)
    reference_number = db.Column(db.String(20), unique=True, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    number_of_guests = db.Column(db.Integer, nullable=False)
    number_of_rooms = db.Column(db.Integer, nullable=False, server_default='1')
    check_in_date = db.Column(db.DateTime, nullable=False)
    check_out_date = db.Column(db.DateTime, nullable=False)
    special_requests = db.Column(db.Text)
    accommodation_id = db.Column(db.Integer, db.ForeignKey('accommodations.id'), nullable=True)
    package_id = db.Column(db.Integer, db.ForeignKey('accommodation_packages.id'), nullable=True)
    total_price = db.Column(db.Float, nullable=True)
    price_breakdown = db.Column(db.Text, nullable=True)  # JSON: itemised cost from PricingEngine
    status = db.Column(db.String(20), default='PENDING') # PENDING, ACCEPTED, REJECTED
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    booking = db.relationship('Booking', backref='enquiry', uselist=False)
    accommodation = db.relationship('AccommodationCategory', backref='enquiries', lazy=True)
    package = db.relationship('AccommodationPackage', backref='enquiries', lazy=True)

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey('booking_enquiries.id'), unique=True)
    reference_number = db.Column(db.String(20), unique=True, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    number_of_guests = db.Column(db.Integer, nullable=False)
    number_of_rooms = db.Column(db.Integer, nullable=False, server_default='1')
    check_in_date = db.Column(db.DateTime, nullable=False)
    check_out_date = db.Column(db.DateTime, nullable=False)
    special_requests = db.Column(db.Text)
    accommodation_id = db.Column(db.Integer, db.ForeignKey('accommodations.id'), nullable=True)
    package_id = db.Column(db.Integer, db.ForeignKey('accommodation_packages.id'), nullable=True)
    notes = db.Column(db.Text)  # Admin notes for manual bookings
    total_price = db.Column(db.Float)
    price_breakdown = db.Column(db.Text, nullable=True)  # JSON: itemised cost from PricingEngine
    status = db.Column(db.String(20), default='CONFIRMED') # CONFIRMED, COMPLETED, CANCELLED
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    accommodation = db.relationship('AccommodationCategory', backref='bookings', lazy=True)
    package = db.relationship('AccommodationPackage', backref='bookings', lazy=True)

class BlockedDate(db.Model):
    __tablename__ = 'blocked_dates'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class BookingStatusHistory(db.Model):
    __tablename__ = 'booking_status_history'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey('booking_enquiries.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

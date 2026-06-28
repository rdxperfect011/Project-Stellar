from app import db
from datetime import datetime, timezone

# Association table for many-to-many relationship
accommodation_amenities = db.Table('accommodation_amenities',
    db.Column('accommodation_id', db.Integer, db.ForeignKey('accommodations.id'), primary_key=True),
    db.Column('amenity_id', db.Integer, db.ForeignKey('amenities.id'), primary_key=True)
)

class AccommodationCategory(db.Model):
    __tablename__ = 'accommodations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    internal_count = db.Column(db.Integer, default=1) # Hidden from public
    cover_image = db.Column(db.String(255), nullable=False)
    gallery = db.Column(db.Text) # Comma-separated list of image URLs
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    amenities = db.relationship('Amenity', secondary=accommodation_amenities, lazy='subquery',
        backref=db.backref('accommodations', lazy=True))
    pricing_rules = db.relationship('AccommodationPricing', backref='accommodation', lazy=True, cascade='all, delete-orphan')
    packages = db.relationship('AccommodationPackage', backref='accommodation', lazy=True, cascade='all, delete-orphan')

class AccommodationPricing(db.Model):
    __tablename__ = 'accommodation_pricing'
    id = db.Column(db.Integer, primary_key=True)
    accommodation_id = db.Column(db.Integer, db.ForeignKey('accommodations.id'), nullable=False)
    guests = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class AccommodationPackage(db.Model):
    __tablename__ = 'accommodation_packages'
    id = db.Column(db.Integer, primary_key=True)
    accommodation_id = db.Column(db.Integer, db.ForeignKey('accommodations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    is_per_guest = db.Column(db.Boolean, default=True)

class Amenity(db.Model):
    __tablename__ = 'amenities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    icon = db.Column(db.String(64)) # Icon class or identifier

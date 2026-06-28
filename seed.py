import os
from app import create_app, db
from app.models.accommodation import AccommodationCategory, Amenity, AccommodationPricing, AccommodationPackage
from app.models.content import Testimonial, WebsiteSetting
from app.models.booking import BookingEnquiry, Booking, BlockedDate
from app.models.email import EmailTemplate
from app.models.admin import AuditLog, AdminNotification
from datetime import datetime, timedelta, timezone

app = create_app('default')

with app.app_context():
    db.create_all()
    # Only seed if empty
    if AccommodationCategory.query.count() == 0:
        print("Seeding accommodations...")
        
        # Amenities
        wifi = Amenity(name="Free Wi-Fi", icon="wifi")
        parking = Amenity(name="Free Parking", icon="car")
        friendly = Amenity(name="Friendly Environment", icon="heart")
        db.session.add_all([wifi, parking, friendly])
        
        # Standard Room
        standard = AccommodationCategory(
            name="Standard Room",
            description="A cozy sanctuary offering all the essential comforts.",
            capacity=4,
            internal_count=5,
            cover_image="images/standard_room.jpeg",
            is_active=True
        )
        standard.amenities.extend([wifi, parking, friendly])
        db.session.add(standard)

        # Deluxe Room
        deluxe = AccommodationCategory(
            name="Deluxe Room",
            description="A premium experience featuring a larger room, premium washroom, better interiors, and a friendly environment.",
            capacity=4,
            internal_count=5,
            cover_image="images/standard_room.jpeg",
            is_active=True
        )
        deluxe.amenities.extend([wifi, parking, friendly])
        db.session.add(deluxe)
        db.session.commit()

        # Pricing - Standard Room (2 Guests ₹1,800 | 3 Guests ₹2,500 | 4 Guests ₹3,500)
        db.session.add_all([
            AccommodationPricing(accommodation_id=standard.id, guests=2, price=1800),
            AccommodationPricing(accommodation_id=standard.id, guests=3, price=2500),
            AccommodationPricing(accommodation_id=standard.id, guests=4, price=3500)
        ])

        # Pricing - Deluxe Room (2 Guests ₹2,000 | 3 Guests ₹2,700 | 4 Guests ₹3,800)
        db.session.add_all([
            AccommodationPricing(accommodation_id=deluxe.id, guests=2, price=2000),
            AccommodationPricing(accommodation_id=deluxe.id, guests=3, price=2700),
            AccommodationPricing(accommodation_id=deluxe.id, guests=4, price=3800)
        ])

        # Meals & Tea Package for both rooms
        meals_package = AccommodationPackage(
            accommodation_id=standard.id,
            name="Meals & Tea Package",
            description="Enjoy delicious home-cooked meals and refreshing tea during your stay.",
            price=500.0,
            is_per_guest=True
        )
        deluxe_meals_package = AccommodationPackage(
            accommodation_id=deluxe.id,
            name="Meals & Tea Package",
            description="Enjoy delicious home-cooked meals and refreshing tea during your stay.",
            price=500.0,
            is_per_guest=True
        )
        db.session.add_all([meals_package, deluxe_meals_package])
        db.session.commit()
        
        # Testimonials
        t1 = Testimonial(
            guest_name="Sarah Jenkins",
            location="New York, USA",
            review="Absolutely breathtaking. The attention to detail in the rooms and the stunning views made our anniversary unforgettable."
        )
        t2 = Testimonial(
            guest_name="David Chen",
            location="London, UK",
            review="A true sanctuary. We felt completely at peace the moment we arrived. The staff was incredibly accommodating."
        )
        db.session.add_all([t1, t2])
        
        # Blocked Dates
        today = datetime.now(timezone.utc)
        b1 = BlockedDate(date=today + timedelta(days=5), reason="Maintenance")
        b2 = BlockedDate(date=today + timedelta(days=6), reason="Maintenance")
        db.session.add_all([b1, b2])

        # Booking Enquiries
        enq1 = BookingEnquiry(
            reference_number="REF-ABC123XYZ",
            full_name="John Doe",
            email="john@example.com",
            phone_number="+1234567890",
            number_of_guests=2,
            number_of_rooms=1,
            check_in_date=today + timedelta(days=10),
            check_out_date=today + timedelta(days=15),
            accommodation_id=standard.id,
            package_id=meals_package.id,
            total_price=2500.0 * 5, # (1800 + 500) * 5 nights
            special_requests="We would love a room with a nice view.",
            status="PENDING"
        )
        enq2 = BookingEnquiry(
            reference_number="REF-XYZ987ABC",
            full_name="Jane Smith",
            email="jane@example.com",
            phone_number="+0987654321",
            number_of_guests=3,
            number_of_rooms=1,
            check_in_date=today + timedelta(days=20),
            check_out_date=today + timedelta(days=22),
            accommodation_id=standard.id,
            total_price=2500.0 * 2, # 2500 * 2 nights
            special_requests="Late check-in requested.",
            status="ACCEPTED"
        )
        db.session.add_all([enq1, enq2])
        db.session.commit() # Commit enquiries first to get their IDs

        # Bookings (from accepted enquiry)
        booking1 = Booking(
            enquiry_id=enq2.id,
            reference_number=enq2.reference_number,
            full_name=enq2.full_name,
            email=enq2.email,
            phone_number=enq2.phone_number,
            number_of_guests=enq2.number_of_guests,
            number_of_rooms=enq2.number_of_rooms,
            check_in_date=enq2.check_in_date,
            check_out_date=enq2.check_out_date,
            accommodation_id=enq2.accommodation_id,
            special_requests=enq2.special_requests,
            total_price=enq2.total_price,
            status="CONFIRMED"
        )
        db.session.add(booking1)

        # Settings
        cap = WebsiteSetting(key="total_rooms", value="5", description="Total number of rooms available for internal capacity check")
        db.session.add(cap)

        # Email Templates
        t_enquiry = EmailTemplate(
            name="new_enquiry",
            subject="New Booking Enquiry Received - Shrine Home Stay",
            body="Hello Admin,\n\nA new booking enquiry has been received.\n\nDetails:\nName: {{ enquiry.full_name }}\nCheck-in: {{ enquiry.check_in_date.strftime('%Y-%m-%d') }}\nCheck-out: {{ enquiry.check_out_date.strftime('%Y-%m-%d') }}\nGuests: {{ enquiry.number_of_guests }}\n\nPlease review it in the admin dashboard."
        )
        t_enq_guest = EmailTemplate(
            name="enquiry_received_guest",
            subject="Booking Enquiry Received - Shrine Home Stay",
            body="Dear {{ enquiry.full_name }},\n\nThank you for your booking request. Our team will contact you shortly to confirm your stay.\n\nReference: {{ enquiry.reference_number }}"
        )
        t_confirmed = EmailTemplate(
            name="booking_confirmed",
            subject="Booking Confirmed - Shrine Home Stay",
            body="Dear {{ booking.full_name }},\n\nYour booking has been confirmed! We look forward to hosting you.\n\nReference: {{ booking.reference_number }}\nCheck-in: {{ booking.check_in_date.strftime('%Y-%m-%d') }}"
        )
        db.session.add_all([t_enquiry, t_enq_guest, t_confirmed])

        db.session.commit()
        print("Seeding complete.")
    else:
        print("Database already has data. To re-seed, drop the tables first.")

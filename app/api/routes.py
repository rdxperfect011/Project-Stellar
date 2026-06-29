"""
Public-facing API routes.

All pricing is calculated exclusively by PricingEngine.
No price arithmetic lives in this file.
"""
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.content import ContactInquiry
from app.models.accommodation import AccommodationCategory, AccommodationPackage
from app.services.booking_service import BookingService
from app.services.availability_service import AvailabilityService
from app.services.pricing_engine import PricingEngine
from datetime import datetime

api = Blueprint('api', __name__)


def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Check availability
# ---------------------------------------------------------------------------

@api.route('/check-availability', methods=['POST'])

def check_availability():
    """
    Returns: 'available', 'limited', or 'unavailable'.
    Does not expose actual room counts.
    """
    data = request.get_json()
    if not data or 'checkIn' not in data or 'checkOut' not in data:
        return jsonify({'error': 'Invalid request'}), 400

    check_in  = parse_date(data['checkIn'])
    check_out = parse_date(data['checkOut'])
    guests    = int(data.get('guests', 1))
    rooms     = int(data.get('rooms', 1))
    today     = datetime.now().date()

    if not check_in or not check_out or check_in >= check_out:
        return jsonify({'error': 'Invalid dates: Check-out must be after check-in.'}), 400
    if check_in < today:
        return jsonify({'error': 'Invalid dates: Past dates cannot be selected.'}), 400
    if guests <= 0:
        return jsonify({'error': 'Guest count must be at least 1.'}), 400

    # Validate occupancy before checking availability (fast-fail with helpful message)
    if rooms > 0 and guests > 0:
        accommodation_id = data.get('accommodationId')
        if accommodation_id:
            accommodation = AccommodationCategory.query.get(accommodation_id)
            if accommodation:
                err = PricingEngine.validate_occupancy(accommodation, rooms, guests)
                if err:
                    return jsonify({'error': err}), 400

    status = AvailabilityService.check_availability_status(check_in, check_out, guests, rooms)

    messages = {
        'unavailable': 'Unfortunately, we do not have availability for your selected dates. Please try different dates.',
        'limited':     'Accommodation is filling up quickly for these dates. Contact us to confirm your stay.',
        'available':   'We have accommodation available for your selected dates. Please proceed with your booking request.',
    }
    return jsonify({'status': status, 'message': messages.get(status, '')})


# ---------------------------------------------------------------------------
# Real-time price calculation
# ---------------------------------------------------------------------------

@api.route('/calculate-price', methods=['POST'])

def calculate_price():
    """
    Calculate the full price breakdown for a set of booking parameters.
    Called by the booking modal on every input change (real-time updates).

    Request body (JSON):
      checkIn, checkOut, rooms, guests, accommodationId, packageId (optional)

    Response:
      Full PriceBreakdown.to_dict() + is_valid flag.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    check_in  = parse_date(data.get('checkIn', ''))
    check_out = parse_date(data.get('checkOut', ''))

    if not check_in or not check_out:
        return jsonify({'is_valid': False, 'validation_error': 'Please select check-in and check-out dates.'}), 200

    nights = (check_out - check_in).days

    try:
        rooms     = int(data.get('rooms', 1))
        guests    = int(data.get('guests', 1))
        accom_id  = int(data['accommodationId'])
        pkg_id    = int(data['packageId']) if data.get('packageId') else None
    except (ValueError, TypeError, KeyError):
        return jsonify({'is_valid': False, 'validation_error': 'Invalid parameters.'}), 200

    breakdown = PricingEngine.calculate(
        accommodation_id=accom_id,
        num_rooms=rooms,
        total_guests=guests,
        nights=nights,
        package_id=pkg_id,
    )

    return jsonify(breakdown.to_dict())


# ---------------------------------------------------------------------------
# Accommodations pricing (for modal initialisation)
# ---------------------------------------------------------------------------

@api.route('/accommodations/pricing', methods=['GET'])
def get_accommodation_pricing():
    """
    Returns all active room types with their pricing tiers and add-on packages.
    Used to populate the booking modal dropdowns.
    """
    categories = AccommodationCategory.query.filter_by(is_active=True).all()
    result = []
    for cat in categories:
        pricing = sorted(
            [{'guests': p.guests, 'price': p.price} for p in cat.pricing_rules],
            key=lambda x: x['guests'],
        )
        packages = [
            {
                'id':          pkg.id,
                'name':        pkg.name,
                'price':       pkg.price,
                'description': pkg.description,
                'is_per_guest': pkg.is_per_guest,
            }
            for pkg in cat.packages
        ]
        result.append({
            'id':           cat.id,
            'name':         cat.name,
            'capacity':     cat.capacity,
            'internal_count': cat.internal_count,
            'pricing':      pricing,
            'packages':     packages,
        })
    return jsonify(result)


# ---------------------------------------------------------------------------
# Booking request
# ---------------------------------------------------------------------------

@api.route('/booking-request', methods=['POST'])

def booking_request():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    required = ['fullName', 'email', 'phone', 'guests', 'checkIn', 'checkOut', 'accommodationId']
    if not all(f in data for f in required):
        return jsonify({'error': 'Missing required fields'}), 400

    check_in  = parse_date(data['checkIn'])
    check_out = parse_date(data['checkOut'])
    today     = datetime.now().date()

    if not check_in or not check_out or check_in >= check_out or check_in < today:
        return jsonify({'error': 'Invalid date range.'}), 400

    admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@shrinehomestay.com')
    result = BookingService.create_enquiry(data, admin_email)

    if not result['success']:
        return jsonify({'error': result['error']}), 400

    return jsonify({'message': 'Booking request received successfully.'})


# ---------------------------------------------------------------------------
# Contact form
# ---------------------------------------------------------------------------

@api.route('/contact', methods=['POST'])

def contact():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    required = ['firstName', 'lastName', 'email', 'message']
    if not all(f in data for f in required):
        return jsonify({'error': 'Missing required fields'}), 400

    inquiry = ContactInquiry(
        first_name=data['firstName'],
        last_name=data['lastName'],
        email=data['email'],
        message=data['message'],
    )
    db.session.add(inquiry)
    db.session.commit()

    admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@shrinehomestay.com')
    from app.utils.mail import send_email
    sender = current_app.config.get('MAIL_USERNAME') or 'noreply@shrinehomestay.com'
    send_email(
        subject=f"New Contact Form Submission from {inquiry.first_name}",
        sender=sender,
        recipients=[admin_email],
        text_body=f"Message from {inquiry.first_name} {inquiry.last_name} ({inquiry.email}):\n\n{inquiry.message}",
        html_body=f"<p>Message from {inquiry.first_name} {inquiry.last_name} ({inquiry.email}):</p><p>{inquiry.message}</p>",
    )

    return jsonify({'message': 'Your message has been sent successfully. We will get back to you soon.'})

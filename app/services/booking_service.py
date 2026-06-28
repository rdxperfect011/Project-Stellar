"""
BookingService — all booking lifecycle operations.

All price calculations are delegated exclusively to PricingEngine.
This file must NEVER contain hardcoded prices or duplicate arithmetic.
"""
import json
import uuid
from datetime import datetime

from app import db
from app.models.booking import BookingEnquiry, Booking, BookingStatusHistory
from app.models.accommodation import AccommodationCategory
from app.services.email_service import EmailService
from app.services.pricing_engine import PricingEngine
from app.utils.audit import log_admin_action


class BookingService:

    # -------------------------------------------------------------------------
    # Create enquiry (public booking flow)
    # -------------------------------------------------------------------------

    @staticmethod
    def create_enquiry(data: dict, admin_email: str) -> dict:
        """
        Validate and create a booking enquiry.

        Returns a dict:
          { 'success': True, 'reference': 'REF-XXXX' }   on success
          { 'success': False, 'error': '<message>' }      on validation failure
        """
        reference_number = f"REF-{uuid.uuid4().hex[:8].upper()}"

        check_in  = datetime.strptime(data['checkIn'],  '%Y-%m-%d').date()
        check_out = datetime.strptime(data['checkOut'], '%Y-%m-%d').date()
        guests    = int(data.get('guests', 1))
        rooms     = int(data.get('rooms',  1))
        accommodation_id = data.get('accommodationId')
        package_id       = data.get('packageId')

        nights = (check_out - check_in).days

        # Validate dates
        if nights <= 0:
            return {'success': False, 'error': 'Check-out date must be after check-in date.'}

        # Validate room type exists
        if not accommodation_id:
            return {'success': False, 'error': 'Please select a room type.'}

        accommodation = db.session.get(AccommodationCategory, accommodation_id)
        if not accommodation:
            return {'success': False, 'error': 'Selected room type not found.'}

        # Run pricing engine (includes occupancy validation)
        breakdown = PricingEngine.calculate(
            accommodation_id=int(accommodation_id),
            num_rooms=rooms,
            total_guests=guests,
            nights=nights,
            package_id=int(package_id) if package_id else None,
        )

        if not breakdown.is_valid:
            return {'success': False, 'error': breakdown.validation_error}

        enquiry = BookingEnquiry(
            reference_number=reference_number,
            full_name=data['fullName'],
            email=data['email'],
            phone_number=data['phone'],
            number_of_guests=guests,
            number_of_rooms=rooms,
            check_in_date=datetime.combine(check_in, datetime.min.time()),
            check_out_date=datetime.combine(check_out, datetime.min.time()),
            special_requests=data.get('specialRequests', ''),
            accommodation_id=int(accommodation_id),
            package_id=int(package_id) if package_id else None,
            total_price=breakdown.total,
            price_breakdown=json.dumps(breakdown.to_dict()),
        )

        db.session.add(enquiry)
        db.session.commit()

        EmailService.send_enquiry_received_emails(enquiry, admin_email)
        return {'success': True, 'reference': reference_number}

    # -------------------------------------------------------------------------
    # Enquiry lifecycle
    # -------------------------------------------------------------------------

    @staticmethod
    def accept_enquiry(enquiry_id):
        enquiry = BookingEnquiry.query.get_or_404(enquiry_id)
        enquiry.status = 'ACCEPTED'

        booking = Booking(
            enquiry_id=enquiry.id,
            reference_number=enquiry.reference_number,
            full_name=enquiry.full_name,
            email=enquiry.email,
            phone_number=enquiry.phone_number,
            number_of_guests=enquiry.number_of_guests,
            number_of_rooms=enquiry.number_of_rooms,
            check_in_date=enquiry.check_in_date,
            check_out_date=enquiry.check_out_date,
            special_requests=enquiry.special_requests,
            accommodation_id=enquiry.accommodation_id,
            package_id=enquiry.package_id,
            total_price=enquiry.total_price,
            price_breakdown=enquiry.price_breakdown,
            status='CONFIRMED',
        )
        db.session.add(booking)
        db.session.flush()

        history = BookingStatusHistory(
            booking_id=booking.id,
            enquiry_id=enquiry.id,
            status='CONFIRMED',
            notes='Booking accepted from enquiry',
        )
        db.session.add(history)
        db.session.commit()

        log_admin_action("Enquiry ACCEPTED", f"Enquiry {enquiry.reference_number} was accepted.")
        return True

    @staticmethod
    def reject_enquiry(enquiry_id):
        enquiry = BookingEnquiry.query.get_or_404(enquiry_id)
        enquiry.status = 'REJECTED'
        db.session.commit()

        EmailService.send_booking_rejected_email(enquiry)
        log_admin_action("Enquiry REJECTED", f"Enquiry {enquiry.reference_number} was rejected.")
        return True

    @staticmethod
    def cancel_enquiry(enquiry_id):
        enquiry = BookingEnquiry.query.get_or_404(enquiry_id)
        enquiry.status = 'CANCELLED'

        booking = Booking.query.filter_by(enquiry_id=enquiry_id).first()
        if booking and booking.status != 'CANCELLED':
            booking.status = 'CANCELLED'
            history = BookingStatusHistory(
                booking_id=booking.id,
                status='CANCELLED',
                notes='Cancelled from enquiries tab',
            )
            db.session.add(history)
            EmailService.send_booking_cancelled_email(booking)

        db.session.commit()
        log_admin_action(
            "Enquiry CANCELLED",
            f"Enquiry and booking {enquiry.reference_number} was cancelled.",
        )
        return True

    @staticmethod
    def change_booking_status(booking_id, new_status):
        booking = Booking.query.get_or_404(booking_id)
        booking.status = new_status

        history = BookingStatusHistory(
            booking_id=booking.id,
            status=new_status,
            notes=f'Marked as {new_status} by admin',
        )
        db.session.add(history)
        db.session.commit()

        if new_status == 'CANCELLED':
            EmailService.send_booking_cancelled_email(booking)

        log_admin_action(
            f"Booking {new_status}",
            f"Booking {booking.reference_number} marked as {new_status}.",
        )
        return True

    # -------------------------------------------------------------------------
    # Manual booking (admin)
    # -------------------------------------------------------------------------

    @staticmethod
    def create_manual_booking(data) -> dict:
        """
        Create a manual booking from admin dashboard form data.

        Price is recalculated via PricingEngine if room/guest/dates are provided.
        Admin may also supply a manual total_price override.

        Returns { 'success': True } or { 'success': False, 'error': '...' }
        """
        check_in  = datetime.strptime(data['check_in'],  '%Y-%m-%d').date()
        check_out = datetime.strptime(data['check_out'], '%Y-%m-%d').date()
        guests    = int(data.get('guests', 1))
        rooms     = int(data.get('rooms',  1))
        nights    = (check_out - check_in).days
        accommodation_id = data.get('accommodation_id')
        package_id       = data.get('package_id')

        total_price    = None
        price_breakdown_json = None

        if accommodation_id and nights > 0:
            breakdown = PricingEngine.calculate(
                accommodation_id=int(accommodation_id),
                num_rooms=rooms,
                total_guests=guests,
                nights=nights,
                package_id=int(package_id) if package_id else None,
            )
            if not breakdown.is_valid:
                return {'success': False, 'error': breakdown.validation_error}
            total_price = breakdown.total
            price_breakdown_json = json.dumps(breakdown.to_dict())
        else:
            # Admin override — trust whatever they typed
            try:
                total_price = float(data.get('total_price', 0)) or None
            except (ValueError, TypeError):
                total_price = None

        booking = Booking(
            reference_number=f"MAN-{uuid.uuid4().hex[:8].upper()}",
            full_name=data['full_name'],
            email=data['email'],
            phone_number=data['phone_number'],
            number_of_guests=guests,
            number_of_rooms=rooms,
            check_in_date=datetime.combine(check_in, datetime.min.time()),
            check_out_date=datetime.combine(check_out, datetime.min.time()),
            accommodation_id=int(accommodation_id) if accommodation_id else None,
            package_id=int(package_id) if package_id else None,
            special_requests=data.get('special_requests', ''),
            total_price=total_price,
            price_breakdown=price_breakdown_json,
            status='CONFIRMED',
        )
        db.session.add(booking)
        db.session.commit()

        log_admin_action(
            "Manual Booking Added",
            f"Added manual booking {booking.reference_number} for {booking.full_name}.",
        )
        return {'success': True}

from app import db
from app.models.booking import BlockedDate, Booking
from app.models.content import WebsiteSetting
from app.utils.audit import log_admin_action
from datetime import datetime, timedelta
from sqlalchemy import and_

class AvailabilityService:
    @staticmethod
    def get_total_capacity():
        setting = WebsiteSetting.query.filter_by(key='total_rooms').first()
        return int(setting.value) if setting and setting.value.isdigit() else 5

    @staticmethod
    def update_capacity(capacity):
        setting = WebsiteSetting.query.filter_by(key='total_rooms').first()
        if not setting:
            setting = WebsiteSetting(key='total_rooms', description='Total rooms for availability')
            db.session.add(setting)
        setting.value = str(capacity)
        db.session.commit()
        log_admin_action("Updated Capacity", f"Set internal capacity to {capacity}.")
        return True

    @staticmethod
    def block_dates(start_date_str, end_date_str, reason):
        if not start_date_str:
            return False
            
        end_date_str = end_date_str or start_date_str
        start_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        current = start_obj
        while current <= end_obj:
            existing = BlockedDate.query.filter(db.func.date(BlockedDate.date) == current).first()
            if not existing:
                new_block = BlockedDate(
                    date=datetime.combine(current, datetime.min.time()),
                    reason=reason
                )
                db.session.add(new_block)
            current += timedelta(days=1)
        
        db.session.commit()
        log_admin_action("Blocked Date Range", f"Blocked dates {start_date_str} to {end_date_str} for: {reason}")
        return True

    @staticmethod
    def unblock_date(block_id):
        block = BlockedDate.query.get(block_id)
        if block:
            db.session.delete(block)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_calendar_data(start_date_str, end_date_str):
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else datetime.now().date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else start_date + timedelta(days=60)
        
        blocked = BlockedDate.query.filter(BlockedDate.date >= start_date, BlockedDate.date <= end_date).all()
        blocked_dict = {b.date.strftime('%Y-%m-%d'): b.reason for b in blocked}
        
        bookings = Booking.query.filter(Booking.status != 'CANCELLED').all()
        booking_counts = {}
        for b in bookings:
            current = b.check_in_date.date()
            while current < b.check_out_date.date():
                d_str = current.strftime('%Y-%m-%d')
                booking_counts[d_str] = booking_counts.get(d_str, 0) + b.number_of_rooms
                current += timedelta(days=1)
                
        total_capacity = AvailabilityService.get_total_capacity()
        
        return {
            'blocked': blocked_dict,
            'bookings': booking_counts,
            'capacity': total_capacity
        }

    @staticmethod
    def check_availability_status(check_in_date, check_out_date, guests, rooms=1):
        total_days = (check_out_date - check_in_date).days
        current_date = check_in_date
        blocked_count = 0
        
        while current_date < check_out_date:
            is_blocked = BlockedDate.query.filter(db.func.date(BlockedDate.date) == current_date).first()
            if is_blocked:
                blocked_count += 1
            current_date += timedelta(days=1)
            
        if blocked_count == total_days:
            return 'unavailable'
            
        total_capacity = AvailabilityService.get_total_capacity()
        
        overlapping_rooms = db.session.query(db.func.sum(Booking.number_of_rooms)).filter(
            and_(
                db.func.date(Booking.check_in_date) < check_out_date,
                db.func.date(Booking.check_out_date) > check_in_date,
                Booking.status != 'CANCELLED'
            )
        ).scalar() or 0
        
        remaining = total_capacity - overlapping_rooms
        
        if remaining < rooms:
            return 'unavailable'
        elif remaining <= rooms + 1:
            return 'limited'
        else:
            return 'available'

    @staticmethod
    def get_available_rooms(check_in_date, check_out_date):
        total_days = (check_out_date.date() - check_in_date.date()).days
        current_date = check_in_date.date()
        
        while current_date < check_out_date.date():
            is_blocked = BlockedDate.query.filter(db.func.date(BlockedDate.date) == current_date).first()
            if is_blocked:
                return 0
            current_date += timedelta(days=1)
            
        total_capacity = AvailabilityService.get_total_capacity()
        
        overlapping_rooms = db.session.query(db.func.sum(Booking.number_of_rooms)).filter(
            and_(
                db.func.date(Booking.check_in_date) < check_out_date.date(),
                db.func.date(Booking.check_out_date) > check_in_date.date(),
                Booking.status != 'CANCELLED'
            )
        ).scalar() or 0
        
        remaining = total_capacity - overlapping_rooms
        return max(0, remaining)

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.booking import BookingEnquiry, Booking, BlockedDate
from app.models.content import GalleryCategory, GalleryImage, WebsiteSetting, Testimonial, Attraction, ContactInquiry
from app.models.email import EmailTemplate
from app.models.admin import AuditLog, AdminNotification
from app.services.booking_service import BookingService
from app.services.availability_service import AvailabilityService
import csv
from io import StringIO
from flask import make_response, current_app
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename

admin = Blueprint('admin', __name__)

@admin.context_processor
def inject_notifications():
    unread_notifications = AdminNotification.query.filter_by(is_read=False).order_by(AdminNotification.created_at.desc()).limit(10).all()
    unread_count = len(unread_notifications)
    return dict(unread_notifications=unread_notifications, unread_count=unread_count)

@admin.route('/')
@login_required
def dashboard():
    today = datetime.now().date()
    start_of_month = today.replace(day=1)
    
    new_enquiries = BookingEnquiry.query.filter_by(status='PENDING').count()
    total_bookings = Booking.query.filter(Booking.status != 'CANCELLED').count()
    
    today_checkins = Booking.query.filter(db.func.date(Booking.check_in_date) == today, Booking.status == 'CONFIRMED').count()
    today_checkouts = Booking.query.filter(db.func.date(Booking.check_out_date) == today, Booking.status == 'CONFIRMED').count()
    
    # Revenue (this month)
    monthly_bookings = Booking.query.filter(Booking.created_at >= start_of_month, Booking.status.in_(['CONFIRMED', 'COMPLETED'])).all()
    revenue = sum([b.total_price for b in monthly_bookings if b.total_price])
    
    # Calculate occupancy for the next 30 days
    # (Simplified calculation)
    # Get capacity
    capacity_setting = WebsiteSetting.query.filter_by(key='total_rooms').first()
    total_capacity = int(capacity_setting.value) if capacity_setting else 5
    
    stats = {
        'new_enquiries': new_enquiries,
        'today_checkins': today_checkins,
        'today_checkouts': today_checkouts,
        'total_bookings': total_bookings,
        'revenue': f"₹{revenue:,.2f}",
        'occupancy_rate': f"{min(100, (total_bookings / (total_capacity * 30)) * 100):.1f}%" # Very basic approx
    }
    
    recent_enquiries = BookingEnquiry.query.order_by(BookingEnquiry.created_at.desc()).limit(5).all()
    
    # Chart Data (Mockup for Monthly Trends)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    chart_data = {
        'labels': months[-6:], # Last 6 months
        'bookings': [12, 19, 15, 25, 22, 30],
        'occupancy': [40, 55, 45, 75, 65, 85]
    }
    
    return render_template('admin/dashboard.html', stats=stats, recent_enquiries=recent_enquiries, chart_data=chart_data)

@admin.route('/bookings', methods=['GET', 'POST'])
@login_required
def bookings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'ACCEPTED':
                enquiry_id = request.form.get('enquiry_id')
                BookingService.accept_enquiry(enquiry_id)
                flash('Enquiry accepted successfully.', 'success')
                
            elif action == 'REJECTED':
                enquiry_id = request.form.get('enquiry_id')
                BookingService.reject_enquiry(enquiry_id)
                flash('Enquiry rejected successfully.', 'success')
                
            elif action == 'CANCEL_ENQUIRY':
                enquiry_id = request.form.get('enquiry_id')
                BookingService.cancel_enquiry(enquiry_id)
                flash('Booking cancelled successfully.', 'success')
                
            elif action in ['COMPLETE', 'CANCEL']:
                booking_id = request.form.get('booking_id')
                new_status = 'COMPLETED' if action == 'COMPLETE' else 'CANCELLED'
                BookingService.change_booking_status(booking_id, new_status)
                flash(f'Booking marked as {new_status}.', 'success')
                
            elif action == 'ADD_MANUAL':
                BookingService.create_manual_booking(request.form)
                flash('Manual booking added.', 'success')
                
        except Exception as e:
            flash(f'Error processing action: {e}', 'error')

        return redirect(url_for('admin.bookings'))
            
    # Filters
    status_filter = request.args.get('status')
    search_query = request.args.get('search')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    enquiries_q = BookingEnquiry.query
    bookings_q = Booking.query
    
    if search_query:
        search = f"%{search_query}%"
        enquiries_q = enquiries_q.filter((BookingEnquiry.full_name.ilike(search)) | (BookingEnquiry.reference_number.ilike(search)) | (BookingEnquiry.email.ilike(search)) | (BookingEnquiry.phone_number.ilike(search)))
        bookings_q = bookings_q.filter((Booking.full_name.ilike(search)) | (Booking.reference_number.ilike(search)) | (Booking.email.ilike(search)) | (Booking.phone_number.ilike(search)))
        
    if status_filter:
        if status_filter in ['PENDING', 'ACCEPTED', 'REJECTED']:
            enquiries_q = enquiries_q.filter_by(status=status_filter)
            bookings_q = bookings_q.filter(Booking.id == 0) # Return empty for bookings tab
        elif status_filter in ['CONFIRMED', 'COMPLETED', 'CANCELLED']:
            bookings_q = bookings_q.filter_by(status=status_filter)
            enquiries_q = enquiries_q.filter(BookingEnquiry.id == 0) # Return empty for enquiries tab
            
    if start_date:
        s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        enquiries_q = enquiries_q.filter(db.func.date(BookingEnquiry.check_in_date) >= s_date)
        bookings_q = bookings_q.filter(db.func.date(Booking.check_in_date) >= s_date)
        
    if end_date:
        e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        enquiries_q = enquiries_q.filter(db.func.date(BookingEnquiry.check_in_date) <= e_date)
        bookings_q = bookings_q.filter(db.func.date(Booking.check_in_date) <= e_date)
        
    enquiries = enquiries_q.order_by(BookingEnquiry.created_at.desc()).all()
    confirmed_bookings = bookings_q.order_by(Booking.created_at.desc()).all()
    
    for enq in enquiries:
        if enq.status == 'PENDING':
            enq.available_rooms = AvailabilityService.get_available_rooms(enq.check_in_date, enq.check_out_date)
    
    return render_template('admin/bookings.html', enquiries=enquiries, confirmed_bookings=confirmed_bookings, search_query=search_query, status_filter=status_filter, start_date=start_date, end_date=end_date)

@admin.route('/bookings/export')
@login_required
def export_bookings():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Reference', 'Guest Name', 'Email', 'Phone', 'Rooms', 'Guests', 'Check In', 'Check Out', 'Total Price', 'Status', 'Created At'])
    
    for b in bookings:
        cw.writerow([
            b.reference_number,
            b.full_name,
            b.email,
            b.phone_number,
            b.number_of_rooms,
            b.number_of_guests,
            b.check_in_date.strftime('%Y-%m-%d'),
            b.check_out_date.strftime('%Y-%m-%d'),
            b.total_price if b.total_price else '',
            b.status,
            b.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=bookings_export.csv"
    output.headers["Content-type"] = "text/csv"
    
    from app.utils.audit import log_admin_action
    log_admin_action("Exported Bookings", "Exported bookings to CSV.")
    return output

@admin.route('/gallery', methods=['GET', 'POST'])
@login_required
def gallery():
    from sqlalchemy.orm import joinedload
    
    # Ensure at least one category exists
    if GalleryCategory.query.count() == 0:
        default_cat = GalleryCategory(name='General')
        db.session.add(default_cat)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_image':
            image_file = request.files.get('image')
            alt_text = request.form.get('alt_text')
            category_id = request.form.get('category_id')
            is_featured = request.form.get('is_featured') == 'on'
            
            if image_file and image_file.filename != '' and category_id:
                # Generate unique filename
                ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
                filename = secure_filename(f"{uuid.uuid4().hex[:8]}.{ext}")
                
                # Save locally (Warning: Will not persist on Vercel)
                try:
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    image_file.save(file_path)
                    
                    # The URL path for serving the file
                    url = f"/static/uploads/{filename}"
                    
                    new_image = GalleryImage(
                        url=url,
                        alt_text=alt_text,
                        category_id=int(category_id),
                        is_featured=is_featured
                    )
                    db.session.add(new_image)
                    db.session.commit()
                    flash('Image uploaded successfully.', 'success')
                except Exception as e:
                    flash(f'Failed to save image: {e}', 'error')
                
        elif action == 'delete_image':
            image_id = request.form.get('image_id')
            if image_id:
                image = GalleryImage.query.get(image_id)
                if image:
                    db.session.delete(image)
                    db.session.commit()

    categories = GalleryCategory.query.all()
    
    # 1. Get database images
    db_images = []
    try:
        db_images = GalleryImage.query.options(joinedload(GalleryImage.category)).order_by(GalleryImage.created_at.desc()).all()
    except Exception:
        pass
        
    # 2. Get static folder images
    static_images = []
    gallery_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
    if os.path.exists(gallery_dir):
        all_files = sorted(os.listdir(gallery_dir))
        
        # Prioritize files starting with "WhatsApp"
        whatsapp_files = [f for f in all_files if f.startswith('WhatsApp') and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        other_files = [f for f in all_files if not f.startswith('WhatsApp') and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and not f.startswith('.')]
        
        db_urls = {img.url for img in db_images}
        
        for filename in whatsapp_files + other_files:
            url = url_for('static', filename='images/gallery/' + filename)
            if url not in db_urls:
                static_images.append({
                    'id': None,
                    'url': url,
                    'alt_text': 'Shrine Homestay Gallery Photo',
                    'category': {'name': 'Homestay'},
                    'is_featured': False
                })
                
    images = static_images + db_images
    return render_template('admin/gallery.html', categories=categories, images=images)

@admin.route('/content')
@login_required
def content():
    return render_template('admin/content.html')



@admin.route('/availability', methods=['GET', 'POST'])
@login_required
def availability():
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'update_capacity':
                capacity = request.form.get('capacity')
                AvailabilityService.update_capacity(capacity)
                flash('Capacity updated successfully', 'success')
                
            elif action == 'block':
                start_date_str = request.form.get('start_date')
                end_date_str = request.form.get('end_date') or start_date_str
                reason = request.form.get('reason')
                AvailabilityService.block_dates(start_date_str, end_date_str, reason)
                flash('Date(s) blocked successfully', 'success')
                    
            elif action == 'unblock':
                block_id = request.form.get('block_id')
                if AvailabilityService.unblock_date(block_id):
                    flash('Date unblocked', 'success')
        except Exception as e:
            flash(f"Error processing availability action: {e}", "error")
            
        return redirect(url_for('admin.availability'))
                    
    blocked_dates = BlockedDate.query.order_by(BlockedDate.date.asc()).all()
    capacity = AvailabilityService.get_total_capacity()
    
    return render_template('admin/availability.html', blocked_dates=blocked_dates, capacity=capacity)

@admin.route('/testimonials', methods=['GET', 'POST'])
@login_required
def testimonials():
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'add':
                guest_name = request.form.get('guest_name')
                location = request.form.get('location')
                rating = request.form.get('rating', type=int)
                review = request.form.get('review')
                is_active = request.form.get('is_active') == 'on'
                
                new_testimonial = Testimonial(
                    guest_name=guest_name,
                    location=location,
                    rating=rating,
                    review=review,
                    is_active=is_active
                )
                db.session.add(new_testimonial)
                db.session.commit()
                flash('Testimonial added successfully', 'success')
                
            elif action == 'toggle':
                testimonial_id = request.form.get('testimonial_id')
                testimonial = Testimonial.query.get(testimonial_id)
                if testimonial:
                    testimonial.is_active = not testimonial.is_active
                    db.session.commit()
                    flash('Testimonial status updated', 'success')
                    
            elif action == 'delete':
                testimonial_id = request.form.get('testimonial_id')
                testimonial = Testimonial.query.get(testimonial_id)
                if testimonial:
                    db.session.delete(testimonial)
                    db.session.commit()
                    flash('Testimonial deleted', 'success')
        except Exception as e:
            flash(f'Error processing action: {e}', 'error')
            
        return redirect(url_for('admin.testimonials'))
        
    testimonials = Testimonial.query.order_by(Testimonial.created_at.desc()).all()
    return render_template('admin/testimonials.html', testimonials=testimonials)

@admin.route('/attractions', methods=['GET', 'POST'])
@login_required
def attractions():
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'add':
                title = request.form.get('title')
                description = request.form.get('description')
                distance = request.form.get('distance')
                is_active = request.form.get('is_active') == 'on'
                image_file = request.files.get('image')
                
                image_url = None
                if image_file and image_file.filename != '':
                    ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
                    filename = secure_filename(f"attr_{uuid.uuid4().hex[:8]}.{ext}")
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    image_file.save(file_path)
                    image_url = f"/static/uploads/{filename}"
                
                new_attraction = Attraction(
                    title=title,
                    description=description,
                    distance=distance,
                    image_url=image_url,
                    is_active=is_active
                )
                db.session.add(new_attraction)
                db.session.commit()
                flash('Attraction added successfully', 'success')
                
            elif action == 'toggle':
                attraction_id = request.form.get('attraction_id')
                attraction = Attraction.query.get(attraction_id)
                if attraction:
                    attraction.is_active = not attraction.is_active
                    db.session.commit()
                    flash('Attraction status updated', 'success')
                    
            elif action == 'delete':
                attraction_id = request.form.get('attraction_id')
                attraction = Attraction.query.get(attraction_id)
                if attraction:
                    db.session.delete(attraction)
                    db.session.commit()
                    flash('Attraction deleted', 'success')
        except Exception as e:
            flash(f'Error processing action: {e}', 'error')
            
        return redirect(url_for('admin.attractions'))
        
    attractions_list = Attraction.query.order_by(Attraction.created_at.desc()).all()
    return render_template('admin/attractions.html', attractions=attractions_list)

@admin.route('/emails', methods=['GET', 'POST'])
@login_required
def emails():
    if request.method == 'POST':
        template_id = request.form.get('template_id')
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        template = EmailTemplate.query.get_or_404(template_id)
        template.subject = subject
        template.body = body
        db.session.commit()
        flash('Template updated successfully', 'success')
        return redirect(url_for('admin.emails'))
        
    templates = EmailTemplate.query.all()
    return render_template('admin/emails.html', templates=templates)

@admin.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        try:
            for key, value in request.form.items():
                if key.startswith('setting_'):
                    setting_key = key.replace('setting_', '')
                    setting = WebsiteSetting.query.filter_by(key=setting_key).first()
                    if setting:
                        setting.value = value
                    else:
                        new_setting = WebsiteSetting(key=setting_key, value=value)
                        db.session.add(new_setting)
            db.session.commit()
            flash('Settings updated successfully', 'success')
        except Exception as e:
            flash(f'Error updating settings: {e}', 'error')
            
        return redirect(url_for('admin.settings'))
        
    settings_records = WebsiteSetting.query.all()
    settings_dict = {s.key: s.value for s in settings_records}
    
    default_keys = [
        'site_title', 'site_description', 'contact_email', 'contact_phone', 
        'contact_address', 'facebook_url', 'instagram_url', 'total_rooms'
    ]
    
    return render_template('admin/settings.html', settings=settings_dict, default_keys=default_keys)

@admin.route('/audit-logs')
@login_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template('admin/audit_logs.html', logs=logs)

@admin.route('/inquiries', methods=['GET', 'POST'])
@login_required
def inquiries():
    if request.method == 'POST':
        action = request.form.get('action')
        inquiry_id = request.form.get('inquiry_id')
        
        try:
            inquiry = ContactInquiry.query.get(inquiry_id)
            if inquiry:
                if action == 'mark_read':
                    inquiry.status = 'READ'
                    db.session.commit()
                    flash('Inquiry marked as read.', 'success')
                elif action == 'delete':
                    db.session.delete(inquiry)
                    db.session.commit()
                    flash('Inquiry deleted.', 'success')
        except Exception as e:
            flash(f'Error processing inquiry: {e}', 'error')
            
        return redirect(url_for('admin.inquiries'))
        
    inquiries_list = ContactInquiry.query.order_by(ContactInquiry.created_at.desc()).all()
    return render_template('admin/inquiries.html', inquiries=inquiries_list)

@admin.route('/availability/calendar')
@login_required
def availability_calendar():
    start = request.args.get('start')
    end = request.args.get('end')
    return jsonify(AvailabilityService.get_calendar_data(start, end))

from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.models.accommodation import AccommodationCategory
from app.models.content import Testimonial
from app import db

main = Blueprint('main', __name__)

@main.route('/')
def index():
    accommodations = AccommodationCategory.query.filter_by(is_active=True).limit(3).all()
    testimonials = Testimonial.query.filter_by(is_active=True).limit(3).all()
    return render_template('main/index.html', accommodations=accommodations, testimonials=testimonials)

@main.route('/about')
def about():
    return render_template('main/about.html')

@main.route('/accommodations')
def accommodations():
    categories = AccommodationCategory.query.filter_by(is_active=True).all()
    return render_template('main/accommodations.html', categories=categories)

@main.route('/gallery')
def gallery():
    from app.models.content import GalleryCategory, GalleryImage
    import os
    from flask import current_app, url_for
    
    # 1. Get database images
    db_images = []
    try:
        db_images = GalleryImage.query.order_by(GalleryImage.created_at.desc()).all()
    except Exception:
        pass
        
    # 2. Get static folder images
    static_images = []
    gallery_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
    if os.path.exists(gallery_dir):
        all_files = sorted(os.listdir(gallery_dir))
        
        whatsapp_files = [f for f in all_files if f.startswith('WhatsApp') and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        other_files = [f for f in all_files if not f.startswith('WhatsApp') and f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and not f.startswith('.')]
        
        db_urls = {img.url for img in db_images}
        
        for filename in whatsapp_files + other_files:
            url = url_for('static', filename='images/gallery/' + filename)
            if url not in db_urls:
                static_images.append({
                    'url': url,
                    'alt_text': 'Shrine Homestay Gallery Photo',
                    'category': {'name': 'Homestay'}
                })

    # Combine them, displaying static images (including the new photos) first
    images = static_images + db_images
    
    categories = []
    try:
        categories = GalleryCategory.query.all()
    except Exception:
        pass
        
    return render_template('main/gallery.html', categories=categories, images=images)

@main.route('/contact')
def contact():
    return render_template('main/contact.html')

@main.route('/submit-review', methods=['POST'])
def submit_review():
    guest_name = request.form.get('guest_name')
    location = request.form.get('location')
    rating = request.form.get('rating', type=int)
    review = request.form.get('review')
    
    if guest_name and rating and review:
        new_testimonial = Testimonial(
            guest_name=guest_name,
            location=location,
            rating=rating,
            review=review,
            is_active=False # Requires admin approval
        )
        db.session.add(new_testimonial)
        db.session.commit()
        flash('Thank you for your review! It will be published after approval.', 'success')
    else:
        flash('Please fill in all required fields.', 'error')
        
    return redirect(url_for('main.index'))

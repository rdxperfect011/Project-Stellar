from flask import Blueprint, render_template, redirect, request, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.auth.forms import LoginForm
from urllib.parse import urlparse
from app.utils.audit import log_admin_action
from app import limiter

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
        
    form = LoginForm()
    if request.method == 'POST':
        try:
            if form.validate_on_submit():
                user = User.query.filter_by(email=form.email.data).first()
                if user is not None and user.verify_password(form.password.data):
                    login_user(user, form.remember_me.data)
                    log_admin_action("LOGIN", "Admin logged in successfully")
                    next_page = request.args.get('next')
                    if next_page is None or not next_page.startswith('/'):
                        next_page = url_for('admin.dashboard')
                    return redirect(next_page)
                flash('Invalid email or password.', 'error')
        except Exception as e:
            import traceback
            print("POST /auth/login CRASH:", traceback.format_exc(), flush=True)
            return {"error": str(e)}, 500
    return render_template('auth/login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    log_admin_action("LOGOUT", "Admin logged out")
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

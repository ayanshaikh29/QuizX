"""
Authentication Routes
Handles login, logout, registration, profile
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import User
from app.utils import get_current_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """Homepage"""
    return render_template('index.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if not username or not password or role not in ['admin', 'student']:
            flash('Invalid input', 'error')

        elif User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')

        else:
            user = User(
                username=username,
                password=generate_password_hash(password),
                role=role,
            )
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))

        return render_template('register.html')

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login
    FIXED: Supports Google-Form style redirect using session['next_url']
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        user = User.query.filter_by(username=username, role=role).first()

        if not user:
            flash('User not found or role mismatch', 'error')

        elif not check_password_hash(user.password, password):
            flash('Incorrect password', 'error')

        else:
            # ✅ Create session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role

            flash('Login successful!', 'success')

            # 🔥 GOOGLE FORM STYLE FIX
            # If user came from join link, redirect back there
            next_url = session.pop('next_url', None)
            if next_url:
                return redirect(next_url)

            # Normal dashboard redirect
            return redirect(
                url_for('admin.dashboard')
                if user.role == 'admin'
                else url_for('student.dashboard')
            )

        return render_template('login.html')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('auth.index'))


@auth_bp.route('/profile')
def profile():
    """User profile page"""
    user = get_current_user()
    if not user:
        return redirect(url_for('auth.login'))

    return render_template('profile.html', user=user)


@auth_bp.route('/quizzes')
def redirect_quizzes():
    """Redirect /quizzes to /student/quizzes"""
    return redirect(url_for('student.quizzes'))


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    """Edit user profile"""
    user = get_current_user()
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_username = request.form.get('username')

        if new_username and new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already taken!', 'error')
            else:
                user.username = new_username
                session['username'] = new_username
                flash('Profile updated!', 'success')

        db.session.commit()
        return redirect(url_for('auth.profile'))

    return render_template('edit_profile.html', user=user)

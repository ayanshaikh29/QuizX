"""
Helper Functions
Utility functions used across the application
CRITICAL FIX: Decorators should not redirect guests to admin dashboard
"""
from datetime import datetime, timezone
from flask import session, redirect, url_for, flash
from functools import wraps
import random
import string
import uuid
import pytz


def now_utc():
    """Get current UTC timestamp"""
    return datetime.now(timezone.utc)


def utc_to_ist(utc_dt):
    """Convert UTC datetime to IST for display"""
    if not utc_dt:
        return None
    ist = pytz.timezone('Asia/Kolkata')
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(ist)


def generate_join_code(length=6):
    """Generate random join code"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def get_current_user():
    """Get current logged-in user"""
    from app.models import User
    
    if "user_id" not in session or session.get("user_id") == -1:
        return None
    return User.query.get(session["user_id"])


def ensure_guest_student():
    """
    Ensure guest users have student session
    CRITICAL: This should ONLY set up guest session, NOT redirect
    """
    if "user_id" not in session:
        session["role"] = "student"
        session["user_id"] = -1
        
    if "username" not in session:
        session["username"] = "Guest"
        
    # Unique guest ID
    if "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())[:8]


# Decorators
def require_admin(f):
    """
    Decorator to require admin role
    CRITICAL: Redirects to LOGIN, not admin dashboard
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def require_student(f):
    """
    Decorator to require student role (logged-in student)
    CRITICAL: Redirects to LOGIN, not admin dashboard
    Does NOT allow guests (use ensure_guest_student() for that)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in as student
        if session.get("role") != "student":
            flash("Student login required", "warning")
            return redirect(url_for("auth.login"))
        
        # Check if it's a guest (user_id == -1)
        if session.get("user_id") == -1:
            flash("Please login with a student account", "warning")
            return redirect(url_for("auth.login"))
        
        return f(*args, **kwargs)
    return decorated_function
"""
Quiz Model
ENHANCED: Added overall timer and global leaderboard settings with NULL defaults
"""
from app.extensions import db
from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


class Quiz(db.Model):
    """Quiz model"""
    __tablename__ = 'quiz'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    has_timer = db.Column(db.Boolean, default=False)
    
    # NEW: Overall quiz timer (in minutes) - NULL means disabled
    overall_timer = db.Column(db.Integer, nullable=True)
    
    # NEW: Global leaderboard toggle - NULL means disabled
    show_leaderboard_global = db.Column(db.Boolean, nullable=True)
    
    published_at = db.Column(db.DateTime)
    publish_count = db.Column(db.Integer, default=0)
    start_time = db.Column(db.DateTime)
    is_locked = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    join_code = db.Column(db.String(10), unique=True)
    is_paused = db.Column(db.Boolean, default=False)
    paused_at = db.Column(db.DateTime)
    paused_seconds = db.Column(db.Integer, default=0)
    
    # Relationships
    questions = db.relationship('Question', backref='quiz', lazy=True, order_by='Question.order')
    
    def __repr__(self):
        return f'<Quiz {self.title}>'
    
    def get_total_time_seconds(self):
        """Get total quiz time in seconds - returns 0 if disabled"""
        return self.overall_timer * 60 if self.overall_timer else 0
    
    def should_show_leaderboard(self, question=None):
        """
        Determine if leaderboard should be shown
        Returns False if global is None/False
        """
        if not self.show_leaderboard_global:
            return False
        if question and hasattr(question, 'show_leaderboard'):
            return question.show_leaderboard
        return bool(self.show_leaderboard_global)
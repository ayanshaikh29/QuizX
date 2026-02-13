"""
PartialAnswer Model
Stores individual question answers
"""
from app.extensions import db
from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


class PartialAnswer(db.Model):
    """Partial answer model"""
    __tablename__ = 'partial_answer'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, nullable=False, index=True)
    question_id = db.Column(db.Integer, nullable=False, index=True)
    student = db.Column(db.String(100), nullable=False, index=True)
    is_correct = db.Column(db.Boolean, nullable=False)
    time_taken = db.Column(db.Integer, nullable=False, default=0)
    points = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=now_utc)
    
    __table_args__ = (
        db.UniqueConstraint(
            'quiz_id', 'question_id', 'student',
            name='unique_answer_per_question'
        ),
    )
    
    def __repr__(self):
        return f'<PartialAnswer Q{self.question_id} by {self.student}>'
"""
Result Model
Final quiz results
"""
from app.extensions import db


class Result(db.Model):
    """Result model"""
    __tablename__ = 'result'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer)
    student = db.Column(db.String(100))
    score = db.Column(db.Integer)
    total = db.Column(db.Integer)
    time_taken = db.Column(db.Integer)
    total_points = db.Column(db.Integer)
    submitted_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Result {self.student}: {self.score}/{self.total}>'
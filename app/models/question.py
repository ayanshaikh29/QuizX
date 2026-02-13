"""
Question Model
ENHANCED: Added new fields for advanced question types
"""
from app.extensions import db
import json

class Question(db.Model):
    """Question model"""
    __tablename__ = 'question'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    order = db.Column(db.Integer, default=0)
    
    # Question content
    question = db.Column(db.Text, nullable=False)  # HTML content from editor
    question_text_plain = db.Column(db.Text)  # Plain text version for search
    
    # Question type: multiple-choice, checkbox, short-answer, paragraph
    question_type = db.Column(db.String(50), default='multiple-choice')
    
    # Options (for multiple-choice and checkbox)
    options = db.Column(db.Text)  # Store as JSON string
    
    # Correct answers (supports multiple correct for checkboxes)
    correct_answers = db.Column(db.Text)  # JSON string
    
    # Scoring
    points = db.Column(db.Float, default=1.0)
    time_limit = db.Column(db.Integer, default=0)  # seconds, 0 = no timer
    
    # Leaderboard settings
    show_leaderboard = db.Column(db.Boolean, default=True)
    
    # Image in question
    question_image = db.Column(db.Text)  # Base64 or URL
    
    # For backward compatibility
    option1 = db.Column(db.String(200))
    option2 = db.Column(db.String(200))
    option3 = db.Column(db.String(200))
    option4 = db.Column(db.String(200))
    answer = db.Column(db.String(200))
    
    def __repr__(self):
        return f'<Question {self.id}: {self.question[:50]}...>'
    
    def get_options_with_images(self):
        """Get options with images"""
        if self.options:
            try:
                return json.loads(self.options)
            except:
                pass
        
        # Fallback for old data
        options = []
        for i, opt in enumerate([self.option1, self.option2, self.option3, self.option4], 1):
            if opt:
                options.append({
                    'text': opt,
                    'image': None,
                    'order': i
                })
        return options
    
    def get_correct_answers(self):
        """Get correct answers as list"""
        if self.correct_answers:
            try:
                return json.loads(self.correct_answers)
            except:
                pass
        
        # Fallback for old data
        if self.answer:
            return [self.answer]
        return []
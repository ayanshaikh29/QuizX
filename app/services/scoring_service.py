"""
Scoring Service
ENHANCED: Support for different question types
"""
from app.extensions import db
from app.models import PartialAnswer, Question
import math


class ScoringService:
    """Service for scoring answers"""
    
    @staticmethod
    def calculate_points(is_correct, time_taken, time_limit=None, has_timer=False, 
                        question_type='multiple-choice', correct_count=1, total_correct=1):
        """
        Calculate points for an answer
        Supports all question types
        """
        if not is_correct:
            return 0
        
        base_points = 1
        
        # For checkbox questions with multiple correct answers
        if question_type == 'checkbox' and total_correct > 1:
            # Partial credit: (correct_selected / total_correct) * base_points
            if correct_count > 0:
                return round((correct_count / total_correct) * base_points, 1)
            return 0
        
        # Time bonus for timer-based quizzes
        if has_timer and time_limit and time_limit > 0:
            # Faster answers get more points
            time_ratio = time_taken / time_limit
            
            if time_ratio <= 0.3:  # Top 30% speed
                return base_points * 1.5
            elif time_ratio <= 0.6:  # Middle 30% speed
                return base_points * 1.2
            elif time_ratio <= 0.9:  # Normal speed
                return base_points * 1.0
            else:  # Slow but correct
                return base_points * 0.8
        
        return base_points
    
    @staticmethod
    def update_question_rank_bonuses(quiz_id, question_id):
        """
        Award bonus points for fastest correct answers
        """
        # Get all correct answers for this question, ordered by time
        correct_answers = PartialAnswer.query.filter_by(
            quiz_id=quiz_id,
            question_id=question_id,
            is_correct=True
        ).order_by(PartialAnswer.time_taken).all()
        
        # Award bonus points to top 3 fastest
        bonus_points = [3, 2, 1]  # 1st: +3, 2nd: +2, 3rd: +1
        
        for idx, answer in enumerate(correct_answers[:3]):
            bonus = bonus_points[idx]
            
            # Update points with bonus
            answer.points += bonus
            
            print(f"🏆 Bonus: {answer.student} +{bonus} points (Rank #{idx+1})")
        
        db.session.commit()
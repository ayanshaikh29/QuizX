"""
Leaderboard Service
ENHANCED: Respect quiz and question leaderboard settings
"""
from app.extensions import db
from app.models import PartialAnswer, Quiz, Question
from sqlalchemy import func


class LeaderboardService:
    """Service for leaderboard operations"""
    
    @staticmethod
    def build_leaderboard_payload(quiz_id):
        """
        Build leaderboard payload for a quiz
        CRITICAL: Only includes data from current quiz
        """
        # Get quiz to check settings
        quiz = Quiz.query.get(quiz_id)
        if not quiz or not quiz.show_leaderboard_global:
            # Leaderboard disabled globally
            return []
        
        # Aggregate all answers for this quiz
        leaderboard = db.session.query(
            PartialAnswer.student.label('name'),
            func.sum(PartialAnswer.points).label('points'),
            func.sum(PartialAnswer.is_correct.cast(db.Integer)).label('correct'),
            func.avg(PartialAnswer.time_taken).label('avg_time'),
            func.sum(PartialAnswer.time_taken).label('time'),
            func.count(PartialAnswer.id).label('answered')
        ).filter(
            PartialAnswer.quiz_id == quiz_id
        ).group_by(
            PartialAnswer.student
        ).all()
        
        # Get total questions for this quiz
        total_questions = Question.query.filter_by(quiz_id=quiz_id).count()
        
        payload = []
        for entry in leaderboard:
            # Skip entries that have answered all questions? No - show all
            
            # Check if this student should have leaderboard shown per-question
            # This is handled at question level, not here
            
            payload.append({
                'name': entry.name,
                'points': float(entry.points or 0),
                'correct': int(entry.correct or 0),
                'avg_time': int(entry.avg_time or 0),
                'time': int(entry.time or 0),
                'answered': int(entry.answered or 0),
                'total_questions': total_questions
            })
        
        # Sort: most points first, then most correct, then least time
        payload.sort(key=lambda x: (-x['points'], -x['correct'], x['time']))
        
        # Add ranks
        for idx, entry in enumerate(payload, 1):
            entry['rank'] = idx
        
        return payload
    
    @staticmethod
    def get_question_leaderboard(quiz_id, question_id):
        """
        Get leaderboard for a specific question
        Used for per-question leaderboard display
        """
        # Get question to check settings
        question = Question.query.get(question_id)
        quiz = Quiz.query.get(quiz_id)
        
        # Check if leaderboard should be shown
        if not quiz or not quiz.show_leaderboard_global:
            return []
        
        if question and not question.show_leaderboard:
            return []
        
        # Get all answers for this question
        answers = PartialAnswer.query.filter_by(
            quiz_id=quiz_id,
            question_id=question_id
        ).order_by(
            PartialAnswer.is_correct.desc(),
            PartialAnswer.time_taken.asc()
        ).all()
        
        payload = []
        for idx, answer in enumerate(answers, 1):
            payload.append({
                'rank': idx,
                'name': answer.student,
                'is_correct': answer.is_correct,
                'time_taken': answer.time_taken,
                'points': answer.points,
                'submitted_at': answer.submitted_at.isoformat() if answer.submitted_at else None
            })
        
        return payload
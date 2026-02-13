"""
Leaderboard Service
Handles leaderboard generation and queries
"""
from app.extensions import db
from app.models import PartialAnswer, Question
from sqlalchemy import func


class LeaderboardService:
    """Leaderboard generation and management"""
    
    @staticmethod
    def build_leaderboard_payload(quiz_id):
        """
        Build full leaderboard payload for a quiz
        
        Returns:
            list: List of dicts with student, points, correct, incorrect, time, total
        """
        total_questions = Question.query.filter_by(quiz_id=quiz_id).count()
        
        rows = db.session.query(
            PartialAnswer.student,
            func.sum(PartialAnswer.points).label("total_points"),
            func.sum(
                db.case((PartialAnswer.is_correct == True, 1), else_=0)
            ).label("correct_count"),
            func.sum(
                db.case((PartialAnswer.is_correct == False, 1), else_=0)
            ).label("incorrect_count"),
            func.sum(PartialAnswer.time_taken).label("total_time"),
        ).filter_by(quiz_id=quiz_id).group_by(PartialAnswer.student).all()
        
        return [
            {
                "student": row.student,
                "points": int(row.total_points or 0),
                "correct": int(row.correct_count or 0),
                "incorrect": int(row.incorrect_count or 0),
                "time": int(row.total_time or 0),
                "total": total_questions,
            }
            for row in rows
        ]
    
    @staticmethod
    def get_leaderboard_data(quiz_id):
        """Get simple leaderboard data (name, score)"""
        points_query = db.session.query(
            PartialAnswer.student.label('name'),
            func.sum(PartialAnswer.points).label('score')
        ).filter_by(quiz_id=quiz_id)\
         .group_by(PartialAnswer.student)\
         .order_by(func.sum(PartialAnswer.points).desc()).all()
        
        return [{"name": r.name, "score": int(r.score)} for r in points_query]
    
    @staticmethod
    def get_question_leaderboard(quiz_id, question_id):
        """Get leaderboard for a specific question"""
        from app.models import Quiz
        
        quiz = Quiz.query.get(quiz_id)
        if not quiz:
            return []
        
        if quiz.has_timer:
            answers = PartialAnswer.query.filter_by(
                quiz_id=quiz_id,
                question_id=question_id,
                is_correct=True
            ).order_by(
                PartialAnswer.time_taken.asc(),
                PartialAnswer.submitted_at.asc()
            ).limit(10).all()
        else:
            answers = PartialAnswer.query.filter_by(
                quiz_id=quiz_id,
                question_id=question_id,
                is_correct=True
            ).order_by(
                PartialAnswer.submitted_at.asc()
            ).limit(10).all()
        
        return [
            {
                "rank": i + 1,
                "student": a.student,
                "time_taken": a.time_taken,
                "points": a.points
            }
            for i, a in enumerate(answers)
        ]
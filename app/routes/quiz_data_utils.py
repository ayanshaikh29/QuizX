"""
Quiz Data Management Utilities
Helper functions for managing quiz data lifecycle
"""
from app.models import PartialAnswer, Result, Quiz
from app.extensions import db
from datetime import datetime


def clear_quiz_session_data(quiz_id):
    """
    Clear all partial answers and results for a quiz
    Should be called when:
    1. Admin restarts a quiz
    2. Admin starts a new quiz session
    3. Quiz is reset
    
    Args:
        quiz_id: The quiz ID to clear
        
    Returns:
        Dict with counts of deleted records
    """
    print(f"\n{'='*60}")
    print(f"CLEARING SESSION DATA FOR QUIZ {quiz_id}")
    print(f"{'='*60}")
    
    # Delete all partial answers
    partial_count = PartialAnswer.query.filter_by(quiz_id=quiz_id).count()
    PartialAnswer.query.filter_by(quiz_id=quiz_id).delete()
    
    # Note: We might want to keep Results for history, so only delete if needed
    # For now, we'll keep results and only clear partial answers
    
    db.session.commit()
    
    print(f"✓ Deleted {partial_count} partial answers")
    print(f"{'='*60}\n")
    
    return {
        'partial_answers_cleared': partial_count,
        'quiz_id': quiz_id,
        'timestamp': datetime.utcnow().isoformat()
    }


def clear_student_quiz_data(quiz_id, student_name):
    """
    Clear data for a specific student in a quiz
    Used for retakes or resetting individual student progress
    
    Args:
        quiz_id: The quiz ID
        student_name: The student's name
        
    Returns:
        Dict with counts of deleted records
    """
    print(f"\nClearing data for student '{student_name}' in quiz {quiz_id}")
    
    # Delete partial answers
    partial_count = PartialAnswer.query.filter_by(
        quiz_id=quiz_id,
        student=student_name
    ).delete()
    
    # Delete result
    result_count = Result.query.filter_by(
        quiz_id=quiz_id,
        student=student_name
    ).delete()
    
    db.session.commit()
    
    print(f"✓ Deleted {partial_count} partial answers and {result_count} results")
    
    return {
        'partial_answers_cleared': partial_count,
        'results_cleared': result_count,
        'student': student_name,
        'quiz_id': quiz_id
    }


def validate_quiz_data_integrity(quiz_id):
    """
    Check if quiz data is consistent
    Useful for debugging leaderboard issues
    
    Args:
        quiz_id: The quiz ID to validate
        
    Returns:
        Dict with validation results
    """
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return {'error': 'Quiz not found', 'quiz_id': quiz_id}
    
    from app.models import Question
    
    # Get all questions
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    question_ids = [q.id for q in questions]
    
    # Get all partial answers
    partials = PartialAnswer.query.filter_by(quiz_id=quiz_id).all()
    
    # Check for orphaned partial answers (question doesn't exist)
    orphaned = [p for p in partials if p.question_id not in question_ids]
    
    # Get unique students
    students = set(p.student for p in partials)
    
    # Check for partial answers with wrong quiz_id
    wrong_quiz = PartialAnswer.query.filter(
        PartialAnswer.quiz_id != quiz_id,
        PartialAnswer.question_id.in_(question_ids)
    ).all()
    
    validation_result = {
        'quiz_id': quiz_id,
        'quiz_title': quiz.title,
        'total_questions': len(questions),
        'total_partial_answers': len(partials),
        'unique_students': len(students),
        'orphaned_answers': len(orphaned),
        'wrong_quiz_answers': len(wrong_quiz),
        'is_valid': len(orphaned) == 0 and len(wrong_quiz) == 0
    }
    
    if not validation_result['is_valid']:
        print(f"\n⚠️  VALIDATION FAILED FOR QUIZ {quiz_id}")
        print(f"Orphaned answers: {len(orphaned)}")
        print(f"Wrong quiz answers: {len(wrong_quiz)}")
    else:
        print(f"\n✓ Quiz {quiz_id} data is valid")
    
    return validation_result


def cleanup_old_partial_answers(days=7):
    """
    Clean up partial answers older than specified days
    Useful for database maintenance
    
    Args:
        days: Number of days to keep (default: 7)
        
    Returns:
        Number of records deleted
    """
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    old_partials = PartialAnswer.query.filter(
        PartialAnswer.submitted_at < cutoff_date
    ).all()
    
    count = len(old_partials)
    
    for partial in old_partials:
        db.session.delete(partial)
    
    db.session.commit()
    
    print(f"Cleaned up {count} partial answers older than {days} days")
    
    return count


def get_quiz_participation_stats(quiz_id):
    """
    Get participation statistics for a quiz
    
    Args:
        quiz_id: The quiz ID
        
    Returns:
        Dict with participation stats
    """
    partials = PartialAnswer.query.filter_by(quiz_id=quiz_id).all()
    
    students = set(p.student for p in partials)
    
    from app.models import Question
    total_questions = Question.query.filter_by(quiz_id=quiz_id).count()
    
    # Calculate completion rates
    student_progress = {}
    for student in students:
        student_partials = [p for p in partials if p.student == student]
        student_progress[student] = {
            'answered': len(student_partials),
            'total': total_questions,
            'percentage': (len(student_partials) / total_questions * 100) if total_questions > 0 else 0
        }
    
    # Count students who completed
    completed_students = sum(1 for progress in student_progress.values() 
                            if progress['answered'] == total_questions)
    
    return {
        'quiz_id': quiz_id,
        'total_students': len(students),
        'completed_students': completed_students,
        'in_progress_students': len(students) - completed_students,
        'total_questions': total_questions,
        'total_answers_submitted': len(partials),
        'student_progress': student_progress
    }
"""
Student Routes
All student functionality: dashboard, quiz attempt, results, history
CRITICAL FIX: Prevent auto-redirect to admin dashboard
LEADERBOARD FIX: Only show current quiz data, filter out past quiz data
ENHANCED: Support for new question types, leaderboard toggles, overall timer
FIXED: Added quiz_id to render_template to fix POST /student/quiz/null 404 error
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.extensions import db, socketio, quiz_state
from app.models import Quiz, Question, PartialAnswer, Result
from app.utils import require_student, ensure_guest_student, now_utc
from app.services import ScoringService, LeaderboardService
import time
import re

student_bp = Blueprint('student', __name__)


def strip_html_tags(html_text):
    """Strip HTML tags from text for plain text comparison"""
    if not html_text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html_text)


def get_student_name():
    """Get current student name from session"""
    if session.get('user_id') == -1 or session.get('user_id') is None:
        return f"Guest-{session.get('guest_id', '00000000')[:8]}"
    return session.get('username', 'Unknown Student')


@student_bp.route('/dashboard')
@require_student
def dashboard():
    """Student dashboard"""
    return render_template('student_dashboard.html', username=session.get('username'))


@student_bp.route('/quizzes')
def quizzes():
    """List available quizzes - NO LOGIN REQUIRED (allows guests)"""
    print(f"\n{'='*60}")
    print("STUDENT QUIZZES PAGE - DEBUG")
    print(f"{'='*60}")
    
    # CRITICAL: Block only admins, allow students AND guests
    if session.get('role') == 'admin':
        print("⚠️ Admin detected, redirecting to admin dashboard")
        flash('Admins cannot join quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Ensure guest session
    ensure_guest_student()
    
    # SHOW ALL PUBLISHED QUIZZES
    all_quizzes = Quiz.query.filter_by(is_published=True).order_by(Quiz.published_at.desc()).all()
    
    print(f"Found {len(all_quizzes)} published quizzes:")
    
    # ADD QUESTION COUNT AND SETTINGS FOR TEMPLATE
    for quiz in all_quizzes:
        quiz.question_count = Question.query.filter_by(quiz_id=quiz.id).count()
        print(f"  - {quiz.title}: active={quiz.is_active}, published={quiz.is_published}, questions={quiz.question_count}")
    
    print(f"Sending {len(all_quizzes)} quizzes to template")
    print(f"{'='*60}\n")
    
    return render_template('student_quiz.html', quizzes=all_quizzes)


@student_bp.route('/join', methods=['GET', 'POST'])
def join_by_code():
    """Join quiz by code - NO LOGIN REQUIRED (allows guests)"""
    # CRITICAL: Block only admins, allow students AND guests
    if session.get('role') == 'admin':
        flash('Admins cannot join quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    ensure_guest_student()
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        quiz = Quiz.query.filter_by(
            join_code=code, is_active=True, is_published=True
        ).first()
        
        if quiz:
            return redirect(url_for('student.waiting_room', quiz_id=quiz.id))
        
        flash('Invalid or inactive quiz code.', 'error')
    
    return render_template('student_quiz.html')


@student_bp.route('/join/<code>')
def join_by_link(code):
    """Join quiz by link - NO LOGIN REQUIRED (allows guests)"""
    # CRITICAL: Block only admins, allow students AND guests
    if session.get('role') == 'admin':
        flash('Admins are not allowed to attempt quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    ensure_guest_student()
    
    quiz = Quiz.query.filter_by(
        join_code=code.upper(), is_active=True, is_published=True
    ).first()
    
    if not quiz:
        return render_template('quiz_closed.html', message='Quiz not found or not active.')
    
    return redirect(url_for('student.waiting_room', quiz_id=quiz.id))


@student_bp.route('/waiting-room/<int:quiz_id>')
def waiting_room(quiz_id):
    """Waiting room before quiz starts - NO LOGIN REQUIRED (allows guests)"""
    # CRITICAL: Block only admins, allow students AND guests
    if session.get('role') == 'admin':
        flash('Admins cannot join quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    ensure_guest_student()
    
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # If admin already started it, redirect to the actual quiz
    if quiz.is_active:
        return redirect(url_for('student.attempt_quiz', quiz_id=quiz.id))
    
    # Get student name for display
    student_name = get_student_name()
    
    return render_template('waiting_room.html', quiz=quiz, student_name=student_name)


@student_bp.route('/test-waiting-room/<int:quiz_id>')
def test_waiting_room(quiz_id):
    """Test waiting room directly"""
    quiz = Quiz.query.get_or_404(quiz_id)
    return f"Waiting room test successful! Quiz: {quiz.title}, ID: {quiz.id}"


def check_answer_correctness(question, selected_answer):
    """
    Check if selected answer is correct based on question type
    Supports all question types: multiple-choice, checkbox, short-answer, paragraph
    """
    if not selected_answer or selected_answer == 'No Answer':
        return False
    
    question_type = question.question_type
    
    if question_type == 'multiple-choice':
        # Single correct answer
        correct_answers = question.get_correct_answers()
        return str(selected_answer).strip() in [str(ans).strip() for ans in correct_answers]
    
    elif question_type == 'checkbox':
        # Multiple correct answers - need to compare sets
        try:
            import json
            student_answers = json.loads(selected_answer) if isinstance(selected_answer, str) else selected_answer
            if not isinstance(student_answers, list):
                student_answers = [student_answers]
            
            correct_answers = [str(ans) for ans in question.get_correct_answers()]
            student_answers = [str(ans) for ans in student_answers]
            
            return set(student_answers) == set(correct_answers)
        except:
            return False
    
    elif question_type in ['short-answer', 'paragraph']:
        # Text comparison - case insensitive, strip HTML
        student_text = strip_html_tags(str(selected_answer)).strip().lower()
        correct_answers = [strip_html_tags(str(ans)).strip().lower() 
                          for ans in question.get_correct_answers()]
        
        return student_text in correct_answers if correct_answers else False
    
    else:
        # Fallback to old method
        return str(selected_answer).strip() == str(question.answer).strip()


def calculate_question_points(question, is_correct, time_taken, quiz):
    """Calculate points for a question based on type and correctness"""
    if not is_correct:
        return 0
    
    base_points = question.points or 1.0
    
    # Time bonus for timer-based quizzes
    if quiz.has_timer and question.time_limit and question.time_limit > 0:
        time_ratio = time_taken / question.time_limit
        
        if time_ratio <= 0.3:  # Top 30% speed
            return base_points * 1.5
        elif time_ratio <= 0.6:  # Middle 30% speed
            return base_points * 1.2
        elif time_ratio <= 0.9:  # Normal speed
            return base_points * 1.0
        else:  # Slow but correct
            return base_points * 0.8
    
    return base_points

@student_bp.route('/quiz/<int:quiz_id>', methods=['GET', 'POST'])
def attempt_quiz(quiz_id):

    print("\n" + "="*60)
    print(f"ATTEMPT QUIZ - Quiz ID: {quiz_id}")
    print("="*60)

    # Block admins only
    if session.get('role') == 'admin':
        flash('Admins cannot solve quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))

    ensure_guest_student()
    quiz = Quiz.query.get_or_404(quiz_id)

    if not quiz.is_active:
        flash('Quiz is not active yet.', 'info')
        return redirect(url_for('student.waiting_room', quiz_id=quiz.id))

    if not quiz.is_published:
        return render_template('quiz_closed.html', message='Quiz not available.')

    if quiz.is_paused:
        return render_template('quiz_closed.html', message='Quiz is paused.')

    questions = Question.query.filter_by(
        quiz_id=quiz_id
    ).order_by(Question.order).all()

    if not questions:
        return render_template(
            'quiz_closed.html',
            message='No questions added yet.'
        )

    student_name = get_student_name()

    # ======================= POST ===========================
    if request.method == 'POST':

        qindex = int(request.form.get('qindex', 0))
        question_id = int(request.form.get('question_id'))
        selected_answer = request.form.get('selected_answer')
        time_taken = int(request.form.get('time_taken', 0))

        current_question_obj = Question.query.get_or_404(question_id)

        # Prevent duplicate submission
        PartialAnswer.query.filter_by(
            quiz_id=quiz_id,
            question_id=question_id,
            student=student_name
        ).delete()
        db.session.commit()

        is_correct = check_answer_correctness(
            current_question_obj,
            selected_answer
        )

        question_points = calculate_question_points(
            current_question_obj,
            is_correct,
            time_taken,
            quiz
        )

        partial = PartialAnswer(
            quiz_id=quiz_id,
            question_id=question_id,
            student=student_name,
            is_correct=is_correct,
            time_taken=time_taken,
            points=question_points,
            submitted_at=now_utc(),
        )

        db.session.add(partial)
        db.session.commit()

        ScoringService.update_question_rank_bonuses(
            quiz_id,
            question_id
        )

        should_show_leaderboard = quiz.should_show_leaderboard(
            current_question_obj
        )

        total_questions = len(questions)
        is_last = (qindex >= total_questions - 1)

        # ================= QUIZ COMPLETE =================
        if is_last:

            partials = PartialAnswer.query.filter_by(
                quiz_id=quiz_id,
                student=student_name
            ).all()

            score = sum(1 for p in partials if p.is_correct)
            total_time = sum(p.time_taken for p in partials)
            total_points = sum(p.points for p in partials)

            existing = Result.query.filter_by(
                quiz_id=quiz_id,
                student=student_name
            ).first()

            if not existing:
                result = Result(
                    quiz_id=quiz_id,
                    student=student_name,
                    score=score,
                    total=total_questions,
                    time_taken=total_time,
                    total_points=total_points
                )
                db.session.add(result)
                db.session.commit()

            return jsonify({
                'success': True,
                'is_correct': is_correct,
                'correct_answer': str(current_question_obj.get_correct_answers()),
                'student_complete': True,
                'next_question': None,
                'show_leaderboard': should_show_leaderboard
            })

        # ================= NEXT QUESTION =================
        return jsonify({
            'success': True,
            'is_correct': is_correct,
            'correct_answer': str(current_question_obj.get_correct_answers()),
            'student_complete': False,
            'next_question': qindex + 1,
            'show_leaderboard': should_show_leaderboard
        })

    # ======================= GET ===========================

    qindex = request.args.get('qindex', type=int)

    if qindex is None:
        if quiz.has_timer:
            qindex = quiz_state.get(quiz_id, {}).get('current_qindex', 0)
        else:
            qindex = 0

    total_questions = len(questions)

    if qindex >= total_questions:
        return redirect(url_for('student.result', quiz_id=quiz_id))

    current_q = questions[qindex]

    current_question = {
        'id': current_q.id,
        'question_text': current_q.question,  # FIXED: Changed from 'question' to 'question_text'
        'question_type': current_q.question_type,
        'options': current_q.get_options_with_images() if current_q.question_type in ['multiple-choice', 'checkbox'] else [],
        'time_limit': current_q.time_limit if quiz.has_timer else None,
        'points': current_q.points
    }

    remaining_seconds = None
    if quiz.has_timer and quiz.overall_timer:
        if quiz_id in quiz_state and 'overall_started_at' in quiz_state[quiz_id]:
            elapsed = int(time.time() - quiz_state[quiz_id]['overall_started_at'])
            total_sec = quiz.overall_timer * 60
            remaining_seconds = max(0, total_sec - elapsed)

    template_name = 'attempt_quiz.html' if quiz.has_timer else 'normal_attempt_quiz.html'

    # ✅ FIXED: Added quiz_id to render_template call
    return render_template(
        template_name,
        quiz=quiz,
        quiz_id=quiz_id,  # ✅ CRITICAL FIX - This was missing!
        current_question=current_question,
        total_questions=total_questions,
        curIdx=qindex,
        questionType=current_q.question_type,
        timeLimit=current_q.time_limit,
        hasOverallTimer=True if quiz.overall_timer else False,
        remaining_seconds=remaining_seconds,
        student_name=student_name,
        show_leaderboard_global=quiz.show_leaderboard_global
    )




@student_bp.route('/leaderboard/live/<int:quiz_id>')
def leaderboard_live(quiz_id):
    """
    Live leaderboard for students - NO LOGIN REQUIRED (allows guests)
    Shows leaderboard after each question and waits for host to advance
    ENHANCED: Respects quiz and question leaderboard settings
    """
    print(f"\n{'='*60}")
    print("LEADERBOARD LIVE PAGE")
    print(f"{'='*60}")
    
    # CRITICAL: Block only admins
    if session.get('role') == 'admin':
        flash('Admins cannot join quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    ensure_guest_student()
    
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if leaderboard is enabled globally
    if not quiz.show_leaderboard_global:
        flash('Leaderboard is disabled for this quiz.', 'info')
        return redirect(url_for('student.attempt_quiz', quiz_id=quiz_id))
    
    # Get qindex from URL (can be 'done' or a number)
    qindex = request.args.get('qindex', '0')
    
    # Get current question for leaderboard settings
    try:
        current_qindex = int(qindex) if qindex != 'done' else 0
        questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
        current_question = questions[current_qindex] if questions and current_qindex < len(questions) else None
    except:
        current_question = None
    
    # Check if leaderboard is enabled for this specific question
    if current_question and not current_question.show_leaderboard:
        flash('Leaderboard is disabled for this question.', 'info')
        return redirect(url_for('student.attempt_quiz', quiz_id=quiz_id, qindex=current_qindex))
    
    # Determine quiz status
    if qindex == 'done':
        quiz_status = 'done'
        current_qindex = 0
        print("Quiz Status: COMPLETE (done)")
    else:
        quiz_status = 'ongoing'
        try:
            current_qindex = int(qindex)
        except ValueError:
            current_qindex = 0
        print(f"Quiz Status: ONGOING (question {current_qindex})")
    
    print(f"Quiz ID: {quiz_id}")
    print(f"Quiz Title: {quiz.title}")
    print(f"QIndex from URL: {qindex}")
    print(f"Current QIndex: {current_qindex}")
    print(f"Show Leaderboard: {quiz.show_leaderboard_global}")
    print(f"{'='*60}\n")
    
    return render_template(
        'student_live_leaderboard.html',
        quiz=quiz,
        quiz_id=quiz_id,
        quiz_title=quiz.title,
        current_qindex=current_qindex,
        quiz_status=quiz_status,
        student_name=get_student_name()
    )


@student_bp.route('/leaderboard/<int:quiz_id>')
def leaderboard(quiz_id):
    """Final leaderboard - NO LOGIN REQUIRED (allows guests)"""
    # CRITICAL: Block only admins
    if session.get('role') == 'admin':
        flash('Admins cannot join quizzes ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    ensure_guest_student()
    
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Get final results
    results = Result.query.filter_by(quiz_id=quiz_id).order_by(Result.total_points.desc()).all()
    
    return render_template(
        'student_live_leaderboard.html',
        quiz=quiz,
        quiz_id=quiz_id,
        quiz_title=quiz.title,
        results=results,
        student_name=get_student_name()
    )


@student_bp.route('/report/<int:history_id>')
def quiz_report(history_id):
    """Detailed quiz report - REQUIRES LOGIN"""
    if session.get('role') == 'admin':
        flash('Admins cannot view student reports ❌', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # For guests, check if they own this history
    history = Result.query.get_or_404(history_id)
    student_name = get_student_name()
    
    if history.student != student_name:
        flash('You do not have permission to view this report.', 'error')
        return redirect(url_for('student.history'))
    
    quiz = Quiz.query.get(history.quiz_id)
    partials = PartialAnswer.query.filter_by(
        quiz_id=history.quiz_id,
        student=student_name
    ).all()
    questions = Question.query.filter_by(quiz_id=history.quiz_id).order_by(Question.order).all()
    
    question_details = []
    for i, question in enumerate(questions):
        answer = next((p for p in partials if p.question_id == question.id), None)
        question_details.append({
            'number': i + 1,
            'text': question.question,
            'type': question.question_type,
            'is_correct': answer.is_correct if answer else False,
            'time_taken': answer.time_taken if answer else 0,
            'points': answer.points if answer else 0,
            'correct_answer': question.get_correct_answers()
        })
    
    return render_template(
        'student_report.html',
        history=history,
        quiz=quiz,
        question_details=question_details
    )


@student_bp.route('/history')
@require_student
def history():
    """Student quiz history - REQUIRES LOGIN"""
    username = session.get('username')
    quiz_history = (
        Result.query
        .filter_by(student=username)
        .order_by(Result.submitted_at.desc())
        .all()
    )
    
    # Add quiz titles
    for result in quiz_history:
        quiz = Quiz.query.get(result.quiz_id)
        result.quiz_title = quiz.title if quiz else 'Unknown Quiz'
    
    return render_template('student_history.html', history=quiz_history)


# ========================================
# API ENDPOINTS
# ========================================

@student_bp.route('/api/leaderboard/<int:quiz_id>')
def api_leaderboard(quiz_id):
    """
    API: Get leaderboard data
    CRITICAL: Only return data for the specified quiz_id
    """
    print(f"\n{'='*60}")
    print(f"API LEADERBOARD REQUEST - Quiz ID: {quiz_id}")
    print(f"{'='*60}")
    
    quiz = Quiz.query.get(quiz_id)
    if not quiz or not quiz.show_leaderboard_global:
        return jsonify({
            'quiz_id': quiz_id,
            'participants': 0,
            'leaderboard': [],
            'message': 'Leaderboard disabled'
        })
    
    # Build leaderboard ONLY for this quiz
    leaderboard_data = LeaderboardService.build_leaderboard_payload(quiz_id)
    
    # Add quiz_id to each entry for frontend filtering
    for entry in leaderboard_data:
        entry['quiz_id'] = quiz_id
    
    print(f'Returning {len(leaderboard_data)} entries for quiz {quiz_id}')
    print(f"{'='*60}\n")
    
    return jsonify({
        'quiz_id': quiz_id,
        'participants': len(leaderboard_data),
        'leaderboard': leaderboard_data,
    })


@student_bp.route('/api/question-leaderboard/<int:quiz_id>/<int:question_id>')
def api_question_leaderboard(quiz_id, question_id):
    """
    API: Get question leaderboard for a specific question
    """
    quiz = Quiz.query.get(quiz_id)
    question = Question.query.get(question_id)
    
    if not quiz or not quiz.show_leaderboard_global or (question and not question.show_leaderboard):
        return jsonify({
            'quiz_id': quiz_id,
            'question_id': question_id,
            'participants': 0,
            'leaderboard': [],
            'message': 'Leaderboard disabled'
        })
    
    leaderboard_data = LeaderboardService.get_question_leaderboard(quiz_id, question_id)
    
    # Add metadata to each entry
    for entry in leaderboard_data:
        entry['quiz_id'] = quiz_id
        entry['question_id'] = question_id
    
    print(f'API Question Leaderboard: {len(leaderboard_data)} entries')
    
    return jsonify({
        'quiz_id': quiz_id,
        'question_id': question_id,
        'participants': len(leaderboard_data),
        'leaderboard': leaderboard_data,
    })


@student_bp.route('/api/quiz-status/<int:quiz_id>')
def api_quiz_status(quiz_id):
    """API: Get current quiz status (for leaderboard auto-refresh)"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    current_index = quiz_state.get(quiz_id, {}).get('current_qindex', 0)
    total_questions = Question.query.filter_by(quiz_id=quiz_id).count()
    
    return jsonify({
        'quiz_id': quiz_id,
        'is_active': quiz.is_active,
        'is_paused': quiz.is_paused,
        'current_qindex': current_index,
        'total_questions': total_questions,
        'show_leaderboard': quiz.show_leaderboard_global,
        'has_timer': quiz.has_timer,
        'overall_timer': quiz.overall_timer
    })


@student_bp.route('/api/my-stats/<int:quiz_id>')
def api_my_stats(quiz_id):
    """API: Get current student's stats for this quiz"""
    student_name = get_student_name()
    
    partials = PartialAnswer.query.filter_by(
        quiz_id=quiz_id,
        student=student_name
    ).all()
    
    total_points = sum(p.points for p in partials)
    correct_count = sum(1 for p in partials if p.is_correct)
    total_answered = len(partials)
    
    return jsonify({
        'student': student_name,
        'total_points': total_points,
        'correct_count': correct_count,
        'total_answered': total_answered,
        'rank': 0  # Will be calculated on frontend
    })
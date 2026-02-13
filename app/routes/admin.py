"""
Admin Routes
All admin functionality: dashboard, quizzes, questions, live control, analytics
ENHANCED: Added overall timer, leaderboard toggle, advanced question types
FIXED: Quiz creation defaults, question collection using getlist('question[]')
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.extensions import db, socketio, quiz_state
from app.models import User, Quiz, Question, PartialAnswer, Result
from app.utils import require_admin, now_utc, utc_to_ist, generate_join_code
from app.services import ScoringService, LeaderboardService
from sqlalchemy import func
import time
import json
import re

admin_bp = Blueprint('admin', __name__)


def clear_quiz_session_data(quiz_id):
    """Clear all partial answers for a quiz session"""
    print(f"\n{'='*60}")
    print(f"CLEARING SESSION DATA FOR QUIZ {quiz_id}")
    print(f"{'='*60}")
    
    partial_count = PartialAnswer.query.filter_by(quiz_id=quiz_id).count()
    PartialAnswer.query.filter_by(quiz_id=quiz_id).delete()
    db.session.commit()
    
    print(f"✓ Deleted {partial_count} partial answers")
    print(f"{'='*60}\n")
    
    return {
        'partial_answers_cleared': partial_count,
        'quiz_id': quiz_id,
    }


def strip_html_tags(html_text):
    """Strip HTML tags from text for plain text storage"""
    if not html_text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html_text)


@admin_bp.route('/dashboard')
@require_admin
def dashboard():
    """Admin dashboard"""
    total_quizzes = Quiz.query.count()
    active_quizzes = Quiz.query.filter_by(is_active=True).count()
    total_students = User.query.filter_by(role='student').count()
    total_responses = Result.query.count()
    recent_results = Result.query.order_by(Result.submitted_at.desc()).limit(5).all()
    
    return render_template(
        'admin_dashboard.html',
        total_quizzes=total_quizzes,
        active_quizzes=active_quizzes,
        total_students=total_students,
        total_responses=total_responses,
        recent_results=recent_results
    )


@admin_bp.route('/quizzes', methods=['GET', 'POST'])
@require_admin
def quizzes():
    """Quiz management"""
    if request.method == 'POST':
        title = request.form.get('title')
        quiz_type = request.form.get('quiz_type')
        
        if not title:
            flash('Quiz title is required', 'error')
            return redirect(url_for('admin.quizzes'))
        
        has_timer = (quiz_type == 'timer')
        
        # ========== FIXED: No default values ==========
        # Overall timer should be NULL until explicitly enabled
        # Leaderboard should be NULL until explicitly enabled
        quiz = Quiz(
            title=title, 
            has_timer=has_timer,
            overall_timer=None,  # ✅ NULL = disabled
            show_leaderboard_global=None  # ✅ NULL = disabled
        )
        db.session.add(quiz)
        db.session.commit()
        
        flash(
            f"{'Timer-based' if has_timer else 'Normal'} quiz created successfully! Now add questions.",
            'success',
        )
        return redirect(url_for('admin.add_question', quiz_id=quiz.id))
    
    all_quizzes = Quiz.query.order_by(Quiz.id.desc()).all()
    return render_template('admin_quiz.html', quizzes=all_quizzes)

@admin_bp.route('/add-question/<int:quiz_id>', methods=['GET', 'POST'])
@require_admin
def add_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if quiz.is_active:
        flash('Cannot add questions to an active quiz.', 'error')
        return redirect(url_for('admin.quizzes'))

    if request.method == 'POST':

        # ================= QUIZ SETTINGS =================
        enable_overall_timer = request.form.get('enable_overall_timer')
        if enable_overall_timer == 'on':
            try:
                hours = int(request.form.get('overall_timer_hours', 0))
                minutes = int(request.form.get('overall_timer_minutes', 0))
                total_minutes = (hours * 60) + minutes
                quiz.overall_timer = total_minutes if total_minutes > 0 else None
            except:
                quiz.overall_timer = None
        else:
            quiz.overall_timer = None

        quiz.show_leaderboard_global = True if request.form.get('show_leaderboard_global') == 'on' else None

        # ================= DELETE OLD QUESTIONS =================
        if request.form.get('overwrite') == '1':
            Question.query.filter_by(quiz_id=quiz_id).delete()
            db.session.commit()
            print(f"✅ Deleted existing questions for quiz {quiz_id}")

        added = False
        question_count = 0

        # ================= READ DYNAMIC QUESTIONS =================
        i = 0
        while True:
            qtext = request.form.get(f'question_{i}')
            qtype = request.form.get(f'question_type_{i}')

            if qtext is None:
                break

            if not qtext.strip():
                i += 1
                continue

            question_count += 1
            qtype = qtype if qtype else 'multiple-choice'

            options = []
            correct_answers = []

            # ================= OPTIONS =================
            if qtype in ['multiple-choice', 'checkbox']:
                option_index = 1
                while True:
                    option_text = request.form.get(f'option{option_index}_{i}')
                    if not option_text:
                        break

                    option_image = request.form.get(f'option_image_{option_index}_{i}')

                    options.append({
                        "text": option_text,
                        "image": option_image,
                        "order": option_index
                    })

                    # Correct Answer
                    if qtype == 'multiple-choice':
                        correct_val = request.form.get(f'answer_{i}')
                        if correct_val and str(option_index) == str(correct_val):
                            correct_answers = [option_index]
                    else:
                        if request.form.get(f'correct_{i}_{option_index}') == 'on':
                            correct_answers.append(option_index)

                    option_index += 1

            else:
                correct_text = request.form.get(f'correct_answer_{i}', '')
                if correct_text:
                    correct_answers = [correct_text]
                    options = [{
                        "text": correct_text,
                        "image": None,
                        "order": 1
                    }]

            # ================= POINTS =================
            try:
                points = float(request.form.get(f'points_{i}', 1))
            except:
                points = 1.0

            # ================= TIME LIMIT =================
            if quiz.has_timer:
                try:
                    time_limit = int(request.form.get(f'time_limit_{i}', 30))
                    time_limit = max(5, time_limit)
                except:
                    time_limit = 30
            else:
                time_limit = 0

            # ================= PER QUESTION LEADERBOARD =================
            show_leaderboard = True if request.form.get(f'show_leaderboard_{i}') == 'on' else False

            # ================= CREATE QUESTION =================
            new_question = Question(
                quiz_id=quiz_id,
                order=i + 1,
                question=qtext,
                question_text_plain=strip_html_tags(qtext),
                question_type=qtype,
                options=json.dumps(options) if options else None,
                correct_answers=json.dumps(correct_answers) if correct_answers else None,
                points=points,
                time_limit=time_limit,
                show_leaderboard=show_leaderboard,

                # backward compatibility
                option1=options[0]['text'] if len(options) > 0 else '',
                option2=options[1]['text'] if len(options) > 1 else '',
                option3=options[2]['text'] if len(options) > 2 else '',
                option4=options[3]['text'] if len(options) > 3 else '',
                answer=str(correct_answers[0]) if correct_answers else ''
            )

            db.session.add(new_question)
            added = True

            print(f"✅ Added question {i+1} | type={qtype} | points={points} | time={time_limit}")

            i += 1

        # ================= FINAL COMMIT =================
        if added:
            db.session.commit()
            flash(f'✅ {question_count} questions added successfully!', 'success')
        else:
            flash('⚠️ No valid questions were added.', 'warning')

        return redirect(url_for('admin.add_question', quiz_id=quiz_id))

    # ================= GET REQUEST =================
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    template_name = 'add_question.html' if quiz.has_timer else 'normal_add_question.html'

    return render_template(template_name, quiz=quiz, questions=questions)


@admin_bp.route('/end-questions/<int:quiz_id>')
@require_admin
def end_questions(quiz_id):
    """Lock quiz questions"""
    quiz = Quiz.query.get_or_404(quiz_id)
    quiz.is_locked = True
    db.session.commit()
    flash('Question adding locked.', 'info')
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/publish-quiz/<int:quiz_id>')
@require_admin
def publish_quiz(quiz_id):
    """Publish quiz"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    if not quiz.is_locked:
        flash('Lock questions first before publishing!', 'error')
        return redirect(url_for('admin.quizzes'))
    
    # FIXED: Check if quiz has questions
    question_count = Question.query.filter_by(quiz_id=quiz_id).count()
    if question_count == 0:
        flash('Cannot publish a quiz with no questions!', 'error')
        return redirect(url_for('admin.add_question', quiz_id=quiz_id))
    
    quiz.is_published = True
    quiz.is_active = False
    quiz.start_time = now_utc()
    quiz.published_at = now_utc()
    quiz.publish_count = (quiz.publish_count or 0) + 1
    quiz.paused_seconds = 0
    quiz.is_paused = False
    
    if not quiz.join_code:
        quiz.join_code = generate_join_code()
    
    quiz_state[quiz.id] = {'current_qindex': 0}
    db.session.commit()
    
    ist_time = utc_to_ist(quiz.published_at)
    flash(
        f"Quiz published at {ist_time.strftime('%d %b %Y, %I:%M %p')} IST "
        f"(Published {quiz.publish_count} times)",
        'success',
    )
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/pause-quiz/<int:quiz_id>')
@require_admin
def pause_quiz(quiz_id):
    """Pause quiz"""
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.is_active and not quiz.is_paused:
        quiz.is_paused = True
        quiz.paused_at = now_utc()
        db.session.commit()
        flash('Quiz paused.', 'info')
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/resume-quiz/<int:quiz_id>')
@require_admin
def resume_quiz(quiz_id):
    """Resume paused quiz"""
    quiz = Quiz.query.get_or_404(quiz_id)
    if quiz.is_active and quiz.is_paused:
        paused_time = (now_utc() - quiz.paused_at).total_seconds()
        quiz.paused_seconds += int(paused_time)
        quiz.is_paused = False
        quiz.paused_at = None
        db.session.commit()
        flash('Quiz resumed.', 'info')
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/stop-quiz/<int:quiz_id>')
@require_admin
def stop_quiz(quiz_id):
    """Stop quiz"""
    quiz = Quiz.query.get_or_404(quiz_id)
    quiz.is_active = False
    quiz.is_published = False
    quiz.is_paused = False
    quiz.paused_at = None
    quiz.paused_seconds = 0
    db.session.commit()
    
    quiz_state.pop(quiz_id, None)
    
    socketio.emit(
        'quiz_stopped',
        {'quiz_id': quiz_id},
        room=str(quiz_id)
    )
    
    flash('Quiz stopped successfully.', 'info')
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/start-quiz/<int:quiz_id>')
@require_admin
def start_quiz(quiz_id):
    """Start quiz"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    if not quiz.is_published:
        flash('Quiz is not published yet!', 'error')
        return redirect(url_for('admin.quizzes'))
    
    # FIXED: Check if quiz has questions
    question_count = Question.query.filter_by(quiz_id=quiz_id).count()
    if question_count == 0:
        flash('Cannot start a quiz with no questions!', 'error')
        return redirect(url_for('admin.add_question', quiz_id=quiz_id))
    
    if quiz.is_active:
        flash('Quiz is already active!', 'warning')
        return redirect(url_for('admin.live_control', quiz_id=quiz_id))
    
    print(f"\n{'='*60}")
    print(f"STARTING QUIZ: {quiz.title} (ID: {quiz_id})")
    print(f"{'='*60}")
    
    # Clear previous session data
    cleared = clear_quiz_session_data(quiz_id)
    print(f"✓ Cleared {cleared['partial_answers_cleared']} old answers")
    
    # Start the quiz
    quiz.is_active = True
    quiz.is_paused = False
    
    # Initialize quiz state
    quiz_state[quiz_id] = {
        'current_qindex': 0,
        'started_at': time.time()
    }
    
    # Only add overall timer if it's enabled (not None and > 0)
    if quiz.overall_timer and quiz.overall_timer > 0:
        quiz_state[quiz_id]['overall_timer'] = quiz.overall_timer * 60
        quiz_state[quiz_id]['overall_started_at'] = time.time()
    
    db.session.commit()
    
    # Notify all students in waiting room
    socketio.emit('begin_quiz', {
        'quiz_id': quiz_id,
        'message': 'Quiz is starting now!',
        'has_timer': quiz.has_timer,
        'overall_timer': quiz.overall_timer if quiz.overall_timer else None,
        'show_leaderboard': quiz.show_leaderboard_global if quiz.show_leaderboard_global else False
    }, room=f'waiting_room_{quiz_id}')
    
    # Tell students to join the quiz room
    socketio.emit('join_quiz_room', {
        'quiz_id': quiz_id
    }, room=f'waiting_room_{quiz_id}')
    
    flash(f'Quiz "{quiz.title}" is now LIVE! 🚀 Old data cleared.', 'success')
    return redirect(url_for('admin.live_control', quiz_id=quiz_id))


@admin_bp.route('/reset-quiz/<int:quiz_id>', methods=['POST'])
@require_admin
def reset_quiz(quiz_id):
    """Reset quiz completely"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    print(f"\n{'='*60}")
    print(f"RESETTING QUIZ: {quiz.title} (ID: {quiz_id})")
    print(f"{'='*60}")
    
    cleared = clear_quiz_session_data(quiz_id)
    
    quiz.is_active = False
    quiz.is_paused = False
    quiz.paused_at = None
    quiz.paused_seconds = 0
    
    if quiz_id in quiz_state:
        del quiz_state[quiz_id]
    
    db.session.commit()
    
    print(f"✓ Quiz reset complete")
    print(f"✓ Cleared {cleared['partial_answers_cleared']} answers")
    print(f"{'='*60}\n")
    
    flash(
        f'Quiz "{quiz.title}" has been reset. '
        f'All progress cleared ({cleared["partial_answers_cleared"]} answers deleted).',
        'info'
    )
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/live-control/<int:quiz_id>')
@require_admin
def live_control(quiz_id):
    """Live quiz control"""
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    
    current_index = quiz_state.get(quiz_id, {}).get('current_qindex', 0)
    current_question = questions[current_index] if current_index < len(questions) else None
    
    # Calculate elapsed time for overall timer - only if enabled
    elapsed_seconds = 0
    remaining_seconds = 0
    if (quiz.has_timer and quiz.is_active and quiz_id in quiz_state and 
        quiz.overall_timer and quiz.overall_timer > 0):
        started_at = quiz_state[quiz_id].get('overall_started_at')
        if started_at:
            elapsed_seconds = int(time.time() - started_at - quiz.paused_seconds)
            total_seconds = quiz.overall_timer * 60
            remaining_seconds = max(0, total_seconds - elapsed_seconds)
    
    return render_template(
        'admin_live_control.html',
        quiz=quiz,
        questions=questions,
        total_questions=len(questions),
        current_index=current_index,
        current_question=current_question,
        remaining_seconds=remaining_seconds,
        elapsed_seconds=elapsed_seconds
    )


@admin_bp.route('/live-leaderboard/<int:quiz_id>')
@require_admin
def live_leaderboard(quiz_id):
    """Admin live leaderboard view"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    total_questions = len(questions)
    current_index = quiz_state.get(quiz_id, {}).get('current_qindex', 0)
    
    current_question = None
    if questions and 0 <= current_index < len(questions):
        current_question = questions[current_index]
    
    is_last = (current_index + 1 >= total_questions) if total_questions > 0 else True
    qindex = request.args.get('qindex', current_index, type=str)
    
    return render_template(
        'admin_live_leaderboard.html',  # ✅ FIXED: Changed from student_live_leaderboard.html
        quiz=quiz,
        quiz_id=quiz_id,
        quiz_title=quiz.title,
        qindex=qindex,
        current_index=current_index,
        total_questions=total_questions,
        is_last=is_last,
        current_question=current_question,
        show_leaderboard=quiz.show_leaderboard_global if quiz.show_leaderboard_global else False
    )


@admin_bp.route('/analytics/<int:quiz_id>')
@require_admin
def analytics(quiz_id):
    """Quiz analytics"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    total_participants = db.session.query(
        PartialAnswer.student
    ).filter_by(quiz_id=quiz_id).distinct().count()
    
    total_answers = PartialAnswer.query.filter_by(quiz_id=quiz_id).count()
    correct_answers = PartialAnswer.query.filter_by(
        quiz_id=quiz_id, is_correct=True
    ).count()
    
    accuracy_rate = int((correct_answers / total_answers) * 100) if total_answers else 0
    
    avg_time = int(
        db.session.query(func.avg(PartialAnswer.time_taken))
        .filter_by(quiz_id=quiz_id).scalar() or 0
    )
    
    question_data = []
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()
    for q in questions:
        total_q = PartialAnswer.query.filter_by(
            quiz_id=quiz_id, question_id=q.id
        ).count()
        correct_q = PartialAnswer.query.filter_by(
            quiz_id=quiz_id, question_id=q.id, is_correct=True
        ).count()
        avg_q_time = db.session.query(func.avg(PartialAnswer.time_taken))\
            .filter_by(quiz_id=quiz_id, question_id=q.id).scalar() or 0
        
        correct_pct = int((correct_q / total_q) * 100) if total_q else 0
        difficulty = 'easy' if correct_pct > 70 else 'medium' if correct_pct > 40 else 'hard'
        
        question_data.append({
            'id': q.id,
            'text': q.question[:100] + '...' if len(q.question) > 100 else q.question,
            'type': q.question_type,
            'points': q.points,
            'difficulty': difficulty,
            'correct_pct': correct_pct,
            'avg_time': int(avg_q_time),
            'total_attempts': total_q,
            'correct_count': correct_q
        })
    
    top_students = db.session.query(
        PartialAnswer.student.label('name'),
        func.sum(PartialAnswer.points).label('score')
    ).filter_by(quiz_id=quiz_id)\
     .group_by(PartialAnswer.student)\
     .order_by(func.sum(PartialAnswer.points).desc())\
     .limit(5).all()
    
    return render_template(
        'admin_analytics.html',
        quiz=quiz,
        total_participants=total_participants,
        accuracy_rate=accuracy_rate,
        avg_time=avg_time,
        question_data=question_data,
        top_students=top_students,
        total_questions=len(questions),
        total_points=sum(q.points for q in questions)
    )


@admin_bp.route('/delete-quiz/<int:quiz_id>')
@require_admin
def delete_quiz(quiz_id):
    """Delete quiz and all associated data"""
    quiz = Quiz.query.get_or_404(quiz_id)
    
    Question.query.filter_by(quiz_id=quiz_id).delete()
    PartialAnswer.query.filter_by(quiz_id=quiz_id).delete()
    Result.query.filter_by(quiz_id=quiz_id).delete()
    
    db.session.delete(quiz)
    db.session.commit()
    
    quiz_state.pop(quiz_id, None)
    
    flash('Quiz and all associated data deleted successfully.', 'info')
    return redirect(url_for('admin.quizzes'))


@admin_bp.route('/rename-quiz', methods=['POST'])
@require_admin
def rename_quiz():
    """Rename quiz"""
    quiz_id = request.form.get('quiz_id')
    new_title = request.form.get('new_title')
    
    if quiz_id and new_title:
        quiz = Quiz.query.get(quiz_id)
        if quiz:
            quiz.title = new_title
            db.session.commit()
            flash('Quiz renamed successfully!', 'success')
    
    return redirect(url_for('admin.quizzes'))


# ============================================
# SOCKET.IO EVENT HANDLERS
# ============================================

@socketio.on('admin_start_quiz')
def handle_admin_start_quiz(data):
    """Admin starts quiz via Socket.IO"""
    quiz_id = data.get('quiz_id')
    
    if not quiz_id:
        return {'error': 'No quiz_id provided'}
    
    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return {'error': 'Quiz not found'}
    
    cleared = clear_quiz_session_data(quiz_id)
    
    quiz.is_active = True
    quiz.is_paused = False
    
    quiz_state[quiz_id] = {
        'current_qindex': 0,
        'started_at': time.time()
    }
    
    if quiz.overall_timer and quiz.overall_timer > 0:
        quiz_state[quiz_id]['overall_started_at'] = time.time()
        quiz_state[quiz_id]['overall_timer'] = quiz.overall_timer * 60
    
    db.session.commit()
    
    socketio.emit(
        'quiz_started',
        {
            'quiz_id': quiz_id,
            'title': quiz.title,
            'has_timer': quiz.has_timer,
            'overall_timer': quiz.overall_timer if quiz.overall_timer else None,
            'show_leaderboard': quiz.show_leaderboard_global if quiz.show_leaderboard_global else False,
            'timestamp': time.time()
        },
        room=str(quiz_id)
    )
    
    return {
        'success': True,
        'cleared': cleared['partial_answers_cleared'],
        'quiz_id': quiz_id
    }


@socketio.on('admin_next_question')
def handle_admin_next_question(data):
    """Admin moves to next question"""
    quiz_id = data.get('quiz_id')
    
    if quiz_id in quiz_state:
        quiz_state[quiz_id]['current_qindex'] = quiz_state[quiz_id].get('current_qindex', 0) + 1
        
        socketio.emit(
            'next_question',
            {'quiz_id': quiz_id, 'qindex': quiz_state[quiz_id]['current_qindex']},
            room=f"quiz_{quiz_id}"
        )
    
    return {'success': True}


@socketio.on('admin_previous_question')
def handle_admin_previous_question(data):
    """Admin moves to previous question"""
    quiz_id = data.get('quiz_id')
    
    if quiz_id in quiz_state:
        current = quiz_state[quiz_id].get('current_qindex', 0)
        quiz_state[quiz_id]['current_qindex'] = max(0, current - 1)
        
        socketio.emit(
            'previous_question',
            {'quiz_id': quiz_id, 'qindex': quiz_state[quiz_id]['current_qindex']},
            room=f"quiz_{quiz_id}"
        )
    
    return {'success': True}
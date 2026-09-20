from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Exam, ExamSession, Question, StudentAnswer
import uuid


@login_required
def student_home(request):
    sessions = ExamSession.objects.filter(student=request.user).select_related('exam').order_by('-started_at')
    return render(request, 'exams/student_home.html', {'sessions': sessions})


@login_required
def create_exam(request):
    if not (request.user.is_professor() or request.user.is_recruiter()):
        return redirect('student_home')
    if request.method == 'POST':
        exam = Exam.objects.create(
            title=request.POST.get('title'),
            description=request.POST.get('description', ''),
            professor=request.user,
            duration_minutes=int(request.POST.get('duration', 60)),
            max_violations=int(request.POST.get('max_violations', 5)),
            status='active'
        )
        return redirect('manage_questions', exam_id=exam.id)
    return render(request, 'exams/create_exam.html')


@login_required
def join_exam(request):
    if request.method == 'POST':
        code = request.POST.get('access_code', '').strip().upper()
        try:
            exam = Exam.objects.get(access_code=code, status='active')
            session = ExamSession.objects.filter(exam=exam, student=request.user).first()
            if session:
                if session.status == 'completed':
                    from django.contrib import messages
                    messages.error(request, 'You have already submitted this exam.')
                    return redirect('student_home')
            else:
                session = ExamSession.objects.create(exam=exam, student=request.user, status='waiting')
                
            return redirect('exam_session', exam_id=exam.id, session_id=session.id)
        except Exam.DoesNotExist:
            from django.contrib import messages
            messages.error(request, 'Invalid exam code. Please try again.')
    return render(request, 'exams/join_exam.html')




@login_required
def exam_session(request, exam_id, session_id):
    exam = get_object_or_404(Exam, id=exam_id)
    session = get_object_or_404(ExamSession, id=session_id, student=request.user)
    
    # Prevent access if exam is already completed
    if session.status == 'completed':
        from django.contrib import messages
        messages.error(request, 'You have already completed this exam. Multiple attempts are not allowed.')
        return redirect('student_home')
        
    # Identity Verification Gate - check if student_name is empty
    if not session.student_name:
        return render(request, 'exams/identity_verify.html', {'exam': exam, 'session': session})
    
    if session.status == 'waiting':
        session.status = 'active'
        session.started_at = timezone.now()
        session.save()
    questions = exam.questions.all()
    return render(request, 'exams/exam_session.html', {
        'exam': exam,
        'session': session,
        'questions': questions,
    })


@require_http_methods(["POST"])
@login_required
def verify_identity(request, exam_id, session_id):
    exam = get_object_or_404(Exam, id=exam_id)
    session = get_object_or_404(ExamSession, id=session_id, student=request.user)
    
    student_name = request.POST.get('student_name', '').strip()
    university_id = request.POST.get('student_id', '').strip()
    department = request.POST.get('department', '').strip()
    
    if not student_name or not university_id:
        from django.contrib import messages
        messages.error(request, 'Student Name and Student ID are required.')
        return render(request, 'exams/identity_verify.html', {'exam': exam, 'session': session})
        
    # Check for unique university_id within this exam
    existing = ExamSession.objects.filter(exam=exam, university_id=university_id).exclude(id=session.id).first()
    if existing:
        from django.contrib import messages
        messages.error(request, 'This Student ID is already registered for this exam.')
        return render(request, 'exams/identity_verify.html', {'exam': exam, 'session': session})
        
    session.student_name = student_name
    session.university_id = university_id
    session.department = department
    session.save()
    
    # Notify proctors via Websocket
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                'proctor_dashboard',
                {
                    'type': 'dashboard.update',
                    'data': {
                        'type': 'student_joined',
                        'session_id': str(session.id),
                        'student_name': student_name,
                        'university_id': university_id,
                        'exam_name': exam.title,
                    }
                }
            )
    except Exception as e:
        print(f"Error sending student_joined event: {e}")
        
    return redirect('exam_session', exam_id=exam.id, session_id=session.id)


@require_http_methods(["POST"])
def submit_exam(request, exam_id, session_id):
    print(f"Submit exam called: exam_id={exam_id}, session_id={session_id}")
    print(f"User: {request.user}, Authenticated: {request.user.is_authenticated}")
    print(f"CSRF Token: {request.POST.get('csrfmiddlewaretoken', 'MISSING')}")
    
    # Explicit authentication check
    if not request.user.is_authenticated:
        print("User not authenticated - returning 403")
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You must be logged in to submit an exam")
    
    try:
        exam = get_object_or_404(Exam, id=exam_id)
        print(f"Exam found: {exam.title}")
        
        # Check session ownership more explicitly
        try:
            session = ExamSession.objects.get(id=session_id)
            print(f"Session found: {session.id}, Student: {session.student}, Status: {session.status}")
            print(f"Session student matches request user: {session.student == request.user}")
            
            if session.student != request.user:
                print("Session ownership mismatch - returning 403")
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("This exam session does not belong to you")
            
            # Prevent re-attempt if already completed
            if session.status == 'completed':
                print("Exam already completed - returning error")
                from django.contrib import messages
                from django.http import HttpResponseBadRequest
                messages.error(request, 'You have already attempted this exam. Multiple attempts are not allowed.')
                return redirect('student_home')
                
        except ExamSession.DoesNotExist:
            print(f"Session {session_id} does not exist")
            from django.http import Http404
            raise Http404("Exam session not found")
            
    except Exam.DoesNotExist:
        print(f"Exam {exam_id} does not exist")
        from django.http import Http404
        raise Http404("Exam not found")
    
    # Save answers
    for q in exam.questions.all():
        answer, created = StudentAnswer.objects.get_or_create(session=session, question=q)
        
        if q.question_type == 'mcq':
            val = request.POST.get(f'q{q.id}')
            if val:
                answer.selected_option = val
                answer.is_correct = (val == q.correct_answer)
        elif q.question_type == 'media':
            file_obj = request.FILES.get(f'q{q.id}_file')
            if file_obj:
                answer.media_upload = file_obj
        else:
            val = request.POST.get(f'q{q.id}')
            if val:
                answer.answer_text = val
        answer.save()

    # Handle termination vs regular submission
    is_terminated = request.POST.get('terminated') == 'true'
    
    # Also check if it was already marked terminated by the proctor dashboard via API
    if getattr(session, 'is_terminated', False):
        is_terminated = True
        
    session.status = 'completed'
    if is_terminated:
        session.is_terminated = True
        if not hasattr(session, 'termination_reason') or not session.termination_reason:
            session.termination_reason = "Automatically terminated due to max violations exceeded."
            
    session.completed_at = timezone.now()
    session.save()

    # Notify proctor dashboards in real time so the "Completed"
    # tab updates immediately without requiring a manual refresh.
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                'proctor_dashboard',
                {
                    'type': 'session_completed',
                    'session_id': str(session.id),
                }
            )
    except Exception as e:
        # Non-fatal: log and continue redirecting the student
        print(f"Error sending session_completed event for {session.id}: {e}")

    print(f"Exam submitted successfully for {request.user.username}")
    
    if is_terminated:
        return render(request, 'exams/terminated.html', {'exam': exam, 'session': session})

    from django.contrib import messages
    messages.success(request, 'Exam submitted successfully.')
    return redirect('student_home')

@login_required
def delete_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, professor=request.user)
    if request.method == 'POST':
        exam.delete()
        from django.contrib import messages
        messages.success(request, 'Exam deleted successfully.')
    return redirect('proctor_dashboard')

@login_required
def manage_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, professor=request.user)
    if request.method == 'POST':
        q_type = request.POST.get('question_type')
        text = request.POST.get('text')
        marks = int(request.POST.get('marks', 1))
        attachment = request.FILES.get('attachment')
        
        q = Question(exam=exam, text=text, question_type=q_type, marks=marks, attachment=attachment)
        
        if q_type == 'mcq':
            q.option_a = request.POST.get('option_a', '')
            q.option_b = request.POST.get('option_b', '')
            q.option_c = request.POST.get('option_c', '')
            q.option_d = request.POST.get('option_d', '')
            q.correct_answer = request.POST.get('correct_answer', '')
            
        q.save()
        from django.contrib import messages
        messages.success(request, 'Question added successfully.')
        return redirect('manage_questions', exam_id=exam.id)
        
    questions = exam.questions.all()
    return render(request, 'exams/manage_questions.html', {'exam': exam, 'questions': questions})

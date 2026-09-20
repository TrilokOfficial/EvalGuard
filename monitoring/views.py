from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .proctoring_engine import active_sessions


from exams.models import Exam

@login_required
def proctor_dashboard(request):
    """Main proctor dashboard — accessible at /monitoring/proctor/ and /proctor/ (redirect)"""
    sessions_data = [s.get_summary() for s in active_sessions.values()]
    my_exams = Exam.objects.filter(professor=request.user).order_by('-created_at')
    return render(request, 'monitoring/proctor_dashboard.html', {
        'active_sessions': sessions_data,
        'session_count': len(sessions_data),
        'my_exams': my_exams,
    })


@login_required
def proctor_session_detail(request, session_id):
    session = active_sessions.get(session_id)
    return render(request, 'monitoring/session_detail.html', {
        'session': session.get_summary() if session else None,
        'session_id': session_id,
    })


def api_active_sessions(request):
    data = [s.get_summary() for s in active_sessions.values()]
    return JsonResponse(data, safe=False)


def api_session_violations(request, session_id):
    session = active_sessions.get(session_id)
    if session:
        return JsonResponse({'violations': session.violations, 'session_id': session_id})
    return JsonResponse({'error': 'Session not found'}, status=404)

@csrf_exempt
@login_required
def terminate_session(request, session_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    session = active_sessions.get(session_id)
    if not session:
        return JsonResponse({'error': f'Session "{session_id}" not found'}, status=404)

    # Notify the channels consumer to tell the student to terminate
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'proctor_{session_id}',
        {
            'type': 'force_terminate',
            'reason': request.POST.get('reason', 'Terminated by Proctor')
        }
    )
    # Mark session inactive and remove from active sessions
    session.is_active = False
    del active_sessions[session_id]
    return JsonResponse({'success': True})

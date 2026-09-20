from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import uuid
from .models import Company, Candidate, CandidateSession, MeetingSession
from monitoring.models import (
    Proctor, ParrokitAgent, ProctoringSessionLog, ViolationEvent,
    DistractionEvent, MobileDetectionEvent
)


@login_required
def recruiter_dashboard(request):
    """Enhanced recruiter dashboard with proctoring integration"""
    companies = Company.objects.filter(recruiter=request.user).prefetch_related('roles')
    candidates = Candidate.objects.filter(
        job_role__company__recruiter=request.user
    ).select_related('user', 'job_role')
    
    # Get proctoring data
    active_proctors = Proctor.objects.filter(is_active=True)
    active_agents = ParrokitAgent.objects.filter(is_active=True)
    recent_sessions = ProctoringSessionLog.objects.filter(
        final_status='pending'
    ).order_by('-started_at')[:10]
    
    context = {
        'companies': companies,
        'candidates': candidates,
        'active_proctors': active_proctors,
        'active_agents': active_agents,
        'recent_sessions': recent_sessions,
    }
    
    # Use enhanced proctoring template
    return render(request, 'recruitment/recruiter_dashboard_proctoring.html', context)


def candidate_portal(request, token):
    candidate = get_object_or_404(Candidate, access_token=token)
    return render(request, 'recruitment/candidate_portal.html', {'candidate': candidate})


@login_required
def company_list(request):
    companies = Company.objects.filter(recruiter=request.user)
    return render(request, 'recruitment/company_list.html', {'companies': companies})


@login_required
def assessment_session(request, session_id):
    session = get_object_or_404(CandidateSession, id=session_id)
    return render(request, 'recruitment/assessment_session.html', {'session': session})


# API endpoints for proctoring data
@login_required
def api_proctoring_stats(request):
    """Get real-time proctoring statistics"""
    from monitoring.proctoring_engine import active_sessions
    
    sessions_data = []
    for session_id, session in active_sessions.items():
        summary = session.get_summary()
        sessions_data.append({
            'session_id': session_id,
            'duration': summary.get('duration', 0),
            'violations': summary.get('total_violations', 0),
            'tab_switches': summary.get('tab_switches', 0),
            'mobile_detected': getattr(session, 'mobile_detected', False),
            'attention_zone': getattr(session, 'attention_zone', 'green'),
            'is_active': session.is_active,
        })
    
    return JsonResponse({
        'active_sessions': sessions_data,
        'total_sessions': len(sessions_data),
        'total_violations': sum(s.get('violations', 0) for s in sessions_data),
    })


@login_required
def api_session_violations(request, session_id):
    """Get violation history for a specific session"""
    try:
        log = ProctoringSessionLog.objects.get(session_id=session_id)
        violations = list(log.violations.values(
            'violation_type', 'severity', 'message', 'timestamp', 'zone_at_violation'
        ))
        return JsonResponse({
            'session_id': session_id,
            'violations': violations,
            'total_count': len(violations)
        })
    except ProctoringSessionLog.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)


@login_required
def api_proctors_list(request):
    """Get list of available proctors"""
    proctors = Proctor.objects.filter(is_active=True).select_related('user')
    data = [{
        'id': str(p.id),
        'name': p.user.get_full_name() or p.user.username,
        'specialization': p.specialization,
        'max_sessions': p.max_sessions,
        'active_assignments': p.assignments.filter(ended_at__isnull=True).count(),
    } for p in proctors]
    return JsonResponse({'proctors': data})


@login_required
def api_agents_list(request):
    """Get list of Parrokit agents"""
    agents = ParrokitAgent.objects.filter(is_active=True)
    data = [{
        'id': str(a.id),
        'name': a.name,
        'type': a.agent_type,
        'config': a.config,
    } for a in agents]
    return JsonResponse({'agents': data})


@login_required
@require_POST
def create_meeting(request):
    """Create a new Jitsi meeting session for the recruiter"""
    # Deactivate any previous active meetings by this recruiter
    MeetingSession.objects.filter(created_by=request.user, is_active=True).update(is_active=False)

    room_name = f'evalguard-{uuid.uuid4().hex[:16]}'
    meeting = MeetingSession.objects.create(
        created_by=request.user,
        room_name=room_name,
    )
    return JsonResponse({
        'code': meeting.code,
        'room_name': meeting.room_name,
        'jitsi_url': meeting.get_jitsi_url(),
        'join_url': f'/recruitment/meeting/join/{meeting.code}/',
    })


def join_meeting(request, code):
    """Candidate joins a meeting via code — no login required"""
    meeting = get_object_or_404(MeetingSession, code=code.upper(), is_active=True)
    candidate_name = request.GET.get('name', 'Candidate')
    return render(request, 'recruitment/candidate_meeting.html', {
        'meeting': meeting,
        'candidate_name': candidate_name,
        'jitsi_url': meeting.get_jitsi_url(),
        'room_name': meeting.room_name,
    })

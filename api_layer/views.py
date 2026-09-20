from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from monitoring.proctoring_engine import active_sessions
from analytics.engine import (analyze_emotion_from_landmarks, analyze_physiological,
                               analyze_biometric, compute_risk_score)
from datetime import datetime


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'platform': 'EvalGuard',
        'active_sessions': len(active_sessions),
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
    })


def active_sessions_api(request):
    data = [s.get_summary() for s in active_sessions.values()]
    return JsonResponse(data, safe=False)


class SessionListView(APIView):
    def get(self, request):
        data = [s.get_summary() for s in active_sessions.values()]
        return Response({'sessions': data, 'count': len(data)})

    def post(self, request):
        session_id = request.data.get('session_id', f'session_{int(datetime.now().timestamp())}')
        from monitoring.proctoring_engine import ProctoringSession
        if session_id not in active_sessions:
            active_sessions[session_id] = ProctoringSession(session_id)
        return Response({'success': True, 'session_id': session_id}, status=status.HTTP_201_CREATED)


class SessionAnalyticsView(APIView):
    def get(self, request, session_id):
        session = active_sessions.get(session_id)
        if not session:
            return Response({'error': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)
        summary = session.get_summary()
        return Response({
            'session': summary,
            'emotion': analyze_emotion_from_landmarks(),
            'physiological': analyze_physiological(summary.get('duration', 0), summary.get('total_violations', 0)),
            'biometric': analyze_biometric(0.87),
            'risk_score': compute_risk_score(
                summary.get('violations', []), summary.get('tab_switches', 0),
                summary.get('looking_away_count', 0), summary.get('duration', 0)
            ),
        })

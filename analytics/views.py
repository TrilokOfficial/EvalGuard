import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from monitoring.proctoring_engine import active_sessions
from .engine import (analyze_emotion_from_landmarks, analyze_physiological,
                     analyze_biometric, compute_risk_score,
                     generate_attention_timeline, generate_emotion_timeline)


@login_required
def analytics_dashboard(request):
    sessions = list(active_sessions.values())
    return render(request, 'analytics/dashboard.html', {'sessions': sessions})


@login_required
def live_monitor(request):
    """Real-time monitoring portal for proctors (Professors, Recruiters, Admins)"""
    if request.user.role not in ['professor', 'recruiter'] and not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You do not have permission to access the live monitor.")
    
    return render(request, 'analytics/live_monitor.html')


@login_required
def session_analytics(request, session_id):
    session = active_sessions.get(session_id)
    summary = session.get_summary() if session else {}
    duration = summary.get('duration', 300)
    violations = summary.get('violations', [])
    tab_switches = summary.get('tab_switches', 0)
    looking_away = summary.get('looking_away_count', 0)
    emotion_data = analyze_emotion_from_landmarks()
    physio_data = analyze_physiological(duration, len(violations))
    biometric_data = analyze_biometric(0.85)
    risk_score = compute_risk_score(violations, tab_switches, looking_away, duration)
    attention_timeline = generate_attention_timeline(duration)
    emotion_timeline = generate_emotion_timeline(duration)
    return render(request, 'analytics/session_analytics.html', {
        'session_id': session_id,
        'summary': summary,
        'emotion_data': emotion_data,
        'physio_data': physio_data,
        'biometric_data': biometric_data,
        'risk_score': risk_score,
        'attention_timeline': json.dumps(attention_timeline),
        'emotion_timeline': json.dumps(emotion_timeline),
    })


def api_analytics_data(request, session_id):
    session = active_sessions.get(session_id)
    if not session:
        return JsonResponse({'error': 'Session not found'}, status=404)
    summary = session.get_summary()
    emotion = analyze_emotion_from_landmarks()
    physio = analyze_physiological(summary.get('duration', 0), summary.get('total_violations', 0))
    biometric = analyze_biometric(0.85)
    return JsonResponse({
        'session': summary,
        'emotion': emotion,
        'physiological': physio,
        'biometric': biometric,
        'risk_score': compute_risk_score(
            summary.get('violations', []),
            summary.get('tab_switches', 0),
            summary.get('looking_away_count', 0),
            summary.get('duration', 0),
        ),
    })


@login_required
def reports_list(request):
    sessions = [s.get_summary() for s in active_sessions.values()]
    return render(request, 'analytics/reports_list.html', {'sessions': sessions})


@login_required
def api_reports_data(request):
    """
    JSON API for reports dashboard.
    Returns lightweight summaries for all active sessions so the
    frontend can live-refresh without a full page reload.
    """
    sessions = [s.get_summary() for s in active_sessions.values()]
    return JsonResponse({'sessions': sessions})


@login_required
def generate_pdf_report(request, session_id):
    """Generate a PDF integrity report using ReportLab (no API key needed)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from io import BytesIO
    from datetime import datetime

    session = active_sessions.get(session_id)
    summary = session.get_summary() if session else {'session_id': session_id, 'violations': [], 'total_violations': 0, 'tab_switches': 0, 'duration': 0}
    emotion = analyze_emotion_from_landmarks()
    physio = analyze_physiological(summary.get('duration', 0), summary.get('total_violations', 0))
    risk_score = compute_risk_score(summary.get('violations', []), summary.get('tab_switches', 0), 0, summary.get('duration', 0))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#7c3aed'), spaceAfter=12)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#1e1b4b'), spaceAfter=8)
    story = []
    story.append(Paragraph('EvalGuard – Exam Integrity Report', title_style))
    story.append(Paragraph(f'Session ID: {session_id}', styles['Normal']))
    story.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    # Summary table
    story.append(Paragraph('Session Summary', h2_style))
    duration_min = round(summary.get('duration', 0) / 60, 1)
    summary_data = [
        ['Metric', 'Value'],
        ['Duration', f'{duration_min} minutes'],
        ['Total Violations', str(summary.get('total_violations', 0))],
        ['Tab Switches', str(summary.get('tab_switches', 0))],
        ['Risk Score', f'{risk_score}/100'],
        ['Dominant Emotion', max(emotion, key=emotion.get)],
        ['Heart Rate (est.)', f"{physio['heart_rate']} bpm"],
        ['Stress Level (est.)', f"{physio['stress_level']}%"],
    ]
    t = Table(summary_data, colWidths=[8*cm, 8*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f0ff')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0d9f9')),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # Violations
    story.append(Paragraph('Violation Log', h2_style))
    violations = summary.get('violations', [])
    if violations:
        vdata = [['Timestamp', 'Type', 'Message', 'Severity']]
        for v in violations:
            vdata.append([v.get('timestamp', '')[:19], v.get('type', ''), v.get('message', '')[:50], v.get('severity', '')])
        vt = Table(vdata, colWidths=[4*cm, 4*cm, 6*cm, 3*cm])
        vt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fef3f3')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e9d5d5')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(vt)
    else:
        story.append(Paragraph('No violations recorded.', styles['Normal']))

    doc.build(story)
    buf.seek(0)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="evalguard_report_{session_id}.pdf"'
    return response

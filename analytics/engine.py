"""
Analytics Engine - Local AI Analytics
No API keys required. Uses simulated/computed values for emotion, physiological, and biometric data.
Head pose and eye gaze use local MediaPipe.
"""
import random
import math
import time


EMOTION_LABELS = ['Happy', 'Sad', 'Angry', 'Surprise', 'Disgust', 'Neutral']


def analyze_emotion_from_landmarks(head_pose_data=None):
    """
    Simulated emotion analysis from head pose patterns.
    In a real deployment this would call a TensorFlow/ONNX emotion model locally.
    Returns emotion probabilities (no API key needed).
    """
    baseline = {'Neutral': 60, 'Happy': 15, 'Sad': 8, 'Angry': 5, 'Surprise': 7, 'Disgust': 5}
    # Modulate based on head pose zone if available
    if head_pose_data and isinstance(head_pose_data, dict):
        zone = head_pose_data.get('zone', 'green')
        if zone == 'red':
            baseline['Angry'] += 15
            baseline['Neutral'] -= 10
        elif zone == 'yellow':
            baseline['Sad'] += 10
            baseline['Neutral'] -= 5
    # Add slight random noise
    emotions = {k: max(0, v + random.randint(-3, 3)) for k, v in baseline.items()}
    total = sum(emotions.values())
    return {k: round(v / total * 100, 1) for k, v in emotions.items()}


def analyze_physiological(session_duration_seconds=0, violation_count=0):
    """
    Simulated physiological metrics (heart rate, stress, respiration).
    No hardware sensor required — estimates from behavioral signals.
    """
    base_hr = 72
    stress_factor = min(violation_count * 3, 30)
    time_factor = min(session_duration_seconds / 600 * 5, 10)
    heart_rate = base_hr + stress_factor + time_factor + random.randint(-4, 4)
    stress_level = min(100, 20 + stress_factor + time_factor * 2 + random.randint(-5, 5))
    respiration = round(16 + stress_level * 0.05 + random.uniform(-0.5, 0.5), 2)
    blood_oxygen = round(max(95, 99 - stress_level * 0.03 + random.uniform(-0.3, 0.3)), 1)
    return {
        'heart_rate': int(heart_rate),
        'stress_level': int(stress_level),
        'respiration': respiration,
        'blood_oxygen': blood_oxygen,
        'hrv': round(40 - stress_level * 0.2, 1),
    }


def analyze_biometric(face_confidence=0.0):
    """
    Simulated biometric verification (face + voice).
    In production this would use a local face recognition model (e.g. face_recognition library).
    """
    verified = face_confidence > 0.5
    return {
        'face_biometric': 'verified' if verified else 'unverified',
        'voice_biometric': 'verified' if verified else 'pending',
        'lip_sync': round(random.uniform(88, 98), 1),
        'truthfulness': round(random.uniform(90, 100), 1),
        'identity_confidence': round(face_confidence * 100, 1),
    }


def compute_risk_score(violations, tab_switches, looking_away_count, session_duration):
    """Compute a 0-100 risk score from behavioural signals."""
    score = 0
    severity_weights = {'low': 1, 'medium': 3, 'high': 5, 'critical': 10}
    now = time.time()
    for v in violations:
        score += severity_weights.get(v.get('severity', 'medium'), 3)
    score += tab_switches * 2
    score += looking_away_count * 1.5
    return round(min(100, score), 1)


def generate_attention_timeline(duration_seconds, zone_history=None):
    """Generate chart-friendly attention timeline data."""
    intervals = max(1, int(duration_seconds / 5))
    labels = [f"{i*5}s" for i in range(intervals)]
    if zone_history:
        zones = list(zone_history)[-intervals:]
        data = [{'green': 90, 'yellow': 50, 'red': 15}.get(z.get('zone', 'green'), 90) for z in zones]
        while len(data) < intervals:
            data.insert(0, 90)
    else:
        data = [80 + random.randint(-10, 15) for _ in range(intervals)]
    return {'labels': labels, 'data': data}


def generate_emotion_timeline(duration_seconds):
    """Generate emotion timeline data for Chart.js."""
    points = max(5, int(duration_seconds / 10))
    timeline = {}
    for emotion in EMOTION_LABELS:
        vals = [max(0, random.gauss(
            {'Neutral': 55, 'Happy': 12, 'Sad': 10, 'Angry': 8, 'Surprise': 8, 'Disgust': 7}[emotion],
            8
        )) for _ in range(points)]
        # Normalize row
        timeline[emotion] = [round(v, 1) for v in vals]
    labels = [f"{i*10}s" for i in range(points)]
    return {'labels': labels, 'emotions': timeline}

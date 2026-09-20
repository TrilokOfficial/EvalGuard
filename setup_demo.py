"""
EvalGuard – Quick Start Script
Run: python setup_demo.py
Creates demo users for testing without any API keys.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'evalguard.settings')
django.setup()

from core.models import User
from exams.models import Exam, Question

DEMO_USERS = [
    {'username': 'professor', 'password': 'prof123', 'role': 'professor', 'first_name': 'Dr. Sarah', 'last_name': 'Johnson', 'institution': 'MIT'},
    {'username': 'student', 'password': 'student123', 'role': 'student', 'first_name': 'Alex', 'last_name': 'Chen', 'institution': 'MIT'},
    {'username': 'recruiter', 'password': 'recruiter123', 'role': 'recruiter', 'first_name': 'HR', 'last_name': 'Manager', 'institution': 'TechCorp'},
    {'username': 'admin', 'password': 'admin123', 'role': 'admin', 'first_name': 'System', 'last_name': 'Admin', 'is_superuser': True, 'is_staff': True},
]

print("Creating demo users...")
for ud in DEMO_USERS:
    extra = {k: ud[k] for k in ('is_superuser', 'is_staff') if k in ud}
    if not User.objects.filter(username=ud['username']).exists():
        u = User.objects.create_user(
            username=ud['username'],
            password=ud['password'],
            role=ud['role'],
            first_name=ud.get('first_name', ''),
            last_name=ud.get('last_name', ''),
            institution=ud.get('institution', ''),
            **extra
        )
        print(f"  [+] Created: {ud['username']} ({ud['role']})")
    else:
        print(f"  [-] Exists: {ud['username']}")

# Create a demo exam
prof = User.objects.filter(username='professor').first()
if prof and not Exam.objects.filter(access_code='DEMO2024').exists():
    exam = Exam.objects.create(
        title='Demo: Computer Science Midterm',
        description='A demonstration exam with AI proctoring enabled.',
        professor=prof,
        duration_minutes=30,
        status='active',
        access_code='DEMO2024',
        max_violations=5,
        proctoring_enabled=True,
    )
    Question.objects.create(exam=exam, text='What does CPU stand for?', question_type='mcq',
        option_a='Central Processing Unit', option_b='Core Power Unit',
        option_c='Computer Programming Utility', option_d='Central Program Unit',
        correct_answer='A', marks=2, order=1)
    Question.objects.create(exam=exam, text='Explain the difference between RAM and ROM.', question_type='text', marks=5, order=2)
    Question.objects.create(exam=exam, text='Which of the following is NOT an operating system?', question_type='mcq',
        option_a='Windows 11', option_b='Ubuntu', option_c='Python 3.10', option_d='macOS Ventura',
        correct_answer='C', marks=2, order=3)
    print(f"  [+] Demo exam created with code: DEMO2024")

print()
print("=" * 52)
print("EvalGuard Demo Setup Complete!")
print("=" * 52)
print()
print("LOGIN CREDENTIALS:")
print("  Professor  -> professor / prof123")
print("  Student    -> student   / student123")
print("  Recruiter  -> recruiter / recruiter123")
print("  Admin      -> admin     / admin123")
print()
print("Demo Exam Access Code: DEMO2024")
print()
print("Start server: python manage.py runserver 8000")
print("Then visit:   http://localhost:8000")
print("=" * 52)

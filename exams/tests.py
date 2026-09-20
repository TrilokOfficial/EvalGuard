from django.test import TestCase
from core.models import User
from .models import Exam, Question, ExamSession, StudentAnswer

class ExamModelsTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user(username='prof', password='pwd', role='professor')
        self.student = User.objects.create_user(username='stu', password='pwd', role='student')
        self.exam = Exam.objects.create(title='Python Midterm', professor=self.prof, duration_minutes=60, status='active')

    def test_exam_creation_generates_access_code(self):
        self.assertTrue(len(self.exam.access_code) > 0)
        self.assertEqual(self.exam.status, 'active')

    def test_exam_session_lifecycle(self):
        session = ExamSession.objects.create(exam=self.exam, student=self.student, status='waiting')
        self.assertEqual(session.status, 'waiting')
        
    def test_advanced_questions_creation(self):
        q1 = Question.objects.create(exam=self.exam, text='What is Python?', question_type='text', marks=5)
        q2 = Question.objects.create(exam=self.exam, text='Write a loop', question_type='code', marks=10)
        q3 = Question.objects.create(exam=self.exam, text='Upload architecture', question_type='media', marks=15)
        
        self.assertEqual(self.exam.questions.count(), 3)
        self.assertEqual(q2.question_type, 'code')

    def test_student_answer_submission(self):
        q = Question.objects.create(exam=self.exam, text='Is Django a Python framework?', question_type='mcq', correct_answer='A', option_a='Yes', option_b='No')
        session = ExamSession.objects.create(exam=self.exam, student=self.student)
        
        ans = StudentAnswer.objects.create(session=session, question=q, selected_option='A', is_correct=True)
        self.assertTrue(ans.is_correct)

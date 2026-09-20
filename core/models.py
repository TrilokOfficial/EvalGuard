from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('professor', 'Professor'),
        ('recruiter', 'Recruiter'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    institution = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_student(self):
        return self.role == 'student'

    def is_professor(self):
        return self.role == 'professor'

    def is_recruiter(self):
        return self.role == 'recruiter'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

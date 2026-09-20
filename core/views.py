from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from .models import User


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/home.html')


@ensure_csrf_cookie
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        messages.error(request, 'Invalid credentials. Please try again.')
    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role', 'student')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        institution = request.POST.get('institution', '')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'core/register.html')

        user = User.objects.create_user(
            username=username, email=email, password=password,
            role=role, first_name=first_name, last_name=last_name,
            institution=institution
        )
        login(request, user)
        messages.success(request, f'Welcome to EvalGuard, {first_name or username}!')
        return redirect('dashboard')
    return render(request, 'core/register.html')


@login_required
def dashboard(request):
    user = request.user
    if user.role == 'professor':
        return redirect('proctor_dashboard')
    elif user.role == 'recruiter':
        return redirect('recruiter_dashboard')
    else:
        return redirect('student_home')

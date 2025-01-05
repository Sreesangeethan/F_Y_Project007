import os
import openai
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash

###############################################################################
# Configuration & Initialization
###############################################################################
app = Flask(_name_)

# For security, load secret key & API key from environment or config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'replace_with_secure_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lms_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the DB and OpenAI
db = SQLAlchemy(app)
openai.api_key = os.environ.get('OPENAI_API_KEY', 'YOUR-OPENAI-API-KEY')


###############################################################################
# Database Models
###############################################################################
class User(db.Model):
    _tablename_ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "admin" or "student"
    
    # Helper method to check password
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):
    _tablename_ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    modules = relationship('Module', backref='course', cascade="all, delete-orphan")

class Module(db.Model):
    _tablename_ = 'modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

class QuizQuestion(db.Model):
    _tablename_ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, nullable=False)      # Store multiple options as JSON or comma-separated
    answer = db.Column(db.String(50), nullable=False) # Correct answer
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'))

class QuizAttempt(db.Model):
    _tablename_ = 'quiz_attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'))
    score = db.Column(db.Float, nullable=False)


###############################################################################
# Database Setup Helper (Run once to create DB)
###############################################################################
@app.before_first_request
def create_tables():
    db.create_all()


###############################################################################
# Utility Functions
###############################################################################
def admin_required(func):
    """Decorator to ensure the user is an admin."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash("Admin rights required.", "danger")
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    wrapper._name_ = func._name_
    return wrapper


def student_required(func):
    """Decorator to ensure the user is a student."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'student':
            flash("Student account required.", "danger")
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    wrapper._name_ = func._name_
    return wrapper


def generate_quiz_questions(module_content, num_questions=5):
    """
    Uses OpenAI to generate multiple-choice quiz questions
    based on the module's content.
    """
    prompt = f"""
    You are an educational AI system. Based on the following content:

    {module_content}

    Generate {num_questions} multiple-choice quiz questions. 
    Each question should have 4 distinct options (A, B, C, D), 
    and indicate which option is correct in this format:

    1) Question text
    A) ...
    B) ...
    C) ...
    D) ...
    Correct answer: X

    Provide them in a plain text format.
    """
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        max_tokens=700,
        temperature=0.7
    )
    return response.choices[0].text.strip()


def generate_adaptive_response(course_content, student_question):
    """
    Uses OpenAI to provide an adaptive learning response 
    based on the course content and student's question.
    """
    prompt = f"""
    You are a tutoring AI. The course content is:
    
    {course_content}

    The student asks: {student_question}

    Provide an informative, concise, and helpful explanation 
    that directly addresses the question using the course content.
    """
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        max_tokens=400,
        temperature=0.7
    )
    return response.choices[0].text.strip()


###############################################################################
# Routes - Authentication
###############################################################################
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. You can now login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash("Logged in successfully.", "success")
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid credentials.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for('index'))


###############################################################################
# Routes - Admin
###############################################################################
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    courses = Course.query.all()
    return render_template('admin_dashboard.html', courses=courses)

@app.route('/admin/create_course', methods=['GET', 'POST'])
@admin_required
def create_course():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        new_course = Course(title=title, description=description)
        db.session.add(new_course)
        db.session.commit()
        flash("Course created!", "success")
        return redirect(url_for('admin_dashboard'))
    return render_template('create_course.html')

@app.route('/admin/course/<int:course_id>')
@admin_required
def admin_course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('admin_course_detail.html', course=course)

@app.route('/admin/create_module/<int:course_id>', methods=['GET', 'POST'])
@admin_required
def create_module(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        new_module = Module(title=title, content=content, course_id=course.id)
        db.session.add(new_module)
        db.session.commit()
        flash("Module created!", "success")
        return redirect(url_for('admin_course_detail', course_id=course.id))
    return render_template('create_module.html', course=course)

@app.route('/admin/generate_quiz/<int:module_id>')
@admin_required
def generate_quiz(module_id):
    module = Module.query.get_or_404(module_id)
    existing_questions = QuizQuestion.query.filter_by(module_id=module.id).all()

    # If quiz already exists, skip generation or handle it as desired
    if existing_questions:
        flash("Quiz already generated for this module.", "info")
        return redirect(url_for('admin_course_detail', course_id=module.course_id))

    generated_text = generate_quiz_questions(module.content, num_questions=5)
    # Parse the response to store questions in DB
    # This parsing is simplistic; you may need more robust parsing in production
    lines = generated_text.split('\n')
    question_text = ""
    options = []
    correct_answer = ""

    for line in lines:
        line = line.strip()
        if line.startswith(('1)', '2)', '3)', '4)', '5)')):
            # Save previous question if it exists
            if question_text and options and correct_answer:
                # Store in DB
                q = QuizQuestion(
                    question=question_text,
                    options="|".join(options),
                    answer=correct_answer,
                    module_id=module.id
                )
                db.session.add(q)
                question_text, options, correct_answer = "", [], ""
            # Start new question
            question_text = line[2:].strip()

        elif line.startswith(('A)', 'B)', 'C)', 'D)')):
            options.append(line)

        elif line.startswith("Correct answer:"):
            correct_answer = line.split("Correct answer:")[-1].strip()

    # Store the last question if still present
    if question_text and options and correct_answer:
        q = QuizQuestion(
            question=question_text,
            options="|".join(options),
            answer=correct_answer,
            module_id=module.id
        )
        db.session.add(q)

    db.session.commit()
    flash("Quiz generated successfully!", "success")
    return redirect(url_for('admin_course_detail', course_id=module.course_id))

@app.route('/admin/analytics')
@admin_required
def analytics():
    # Basic analytics: average scores per module
    all_modules = Module.query.all()
    module_scores = {}
    for m in all_modules:
        attempts = QuizAttempt.query.filter_by(module_id=m.id).all()
        if attempts:
            avg_score = sum(a.score for a in attempts) / len(attempts)
            module_scores[m.title] = round(avg_score, 2)
        else:
            module_scores[m.title] = None
    return render_template('analytics.html', module_scores=module_scores)


###############################################################################
# Routes - Student
###############################################################################
@app.route('/student/dashboard')
@student_required
def student_dashboard():
    courses = Course.query.all()
    return render_template('student_dashboard.html', courses=courses)

@app.route('/student/course/<int:course_id>')
@student_required
def student_course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('student_course_detail.html', course=course)

@app.route('/student/module/<int:module_id>', methods=['GET', 'POST'])
@student_required
def student_module_detail(module_id):
    module = Module.query.get_or_404(module_id)

    # Handling question submission for adaptive answers
    adaptive_answer = None
    if request.method == 'POST':
        student_question = request.form.get('student_question')
        adaptive_answer = generate_adaptive_response(module.content, student_question)

    quiz_questions = QuizQuestion.query.filter_by(module_id=module.id).all()
    return render_template(
        'student_module_detail.html',
        module=module,
        quiz_questions=quiz_questions,
        adaptive_answer=adaptive_answer
    )

@app.route('/student/quiz/<int:module_id>', methods=['GET', 'POST'])
@student_required
def student_quiz(module_id):
    module = Module.query.get_or_404(module_id)
    quiz_questions = QuizQuestion.query.filter_by(module_id=module.id).all()
    
    if request.method == 'POST':
        correct_count = 0
        for q in quiz_questions:
            selected_option = request.form.get(f"question_{q.id}")
            if selected_option == q.answer:
                correct_count += 1
        score = (correct_count / len(quiz_questions)) * 100
        # Save attempt
        attempt = QuizAttempt(
            user_id=session['user_id'],
            module_id=module.id,
            score=score
        )
        db.session.add(attempt)
        db.session.commit()

        flash(f"You scored {score:.2f}%.", "info")
        return redirect(url_for('student_module_detail', module_id=module.id))

    return render_template('student_quiz.html', module=module, quiz_questions=quiz_questions)


###############################################################################
# TEMPLATES (Inline for Demo)
###############################################################################
# In production, put these in a "templates" folder. 
# For demonstration, we'll use inline multi-line strings.

from flask import make_response

@app.route('/inline_template/<string:template_name>')
def inline_template(template_name):
    """
    This route is purely for demonstration of inline templates.
    In real usage, place these templates in the templates folder.
    """
    templates = {
        'index.html': """
        <html>
        <head><title>LMS Home</title></head>
        <body>
            <h1>Welcome to the LMS</h1>
            <a href="{{ url_for('login') }}">Login</a> | 
            <a href="{{ url_for('register') }}">Register</a>
        </body>
        </html>
        """,
        'register.html': """
        <html>
        <head><title>Register</title></head>
        <body>
            <h1>Register</h1>
            <form method="POST">
                <label>Username:</label><br>
                <input type="text" name="username"><br><br>
                <label>Password:</label><br>
                <input type="password" name="password"><br><br>
                <label>Role:</label><br>
                <select name="role">
                    <option value="student">Student</option>
                    <option value="admin">Admin</option>
                </select><br><br>
                <button type="submit">Register</button>
            </form>
        </body>
        </html>
        """,
        'login.html': """
        <html>
        <head><title>Login</title></head>
        <body>
            <h1>Login</h1>
            <form method="POST">
                <label>Username:</label><br>
                <input type="text" name="username"><br><br>
                <label>Password:</label><br>
                <input type="password" name="password"><br><br>
                <button type="submit">Login</button>
            </form>
        </body>
        </html>
        """,
        'admin_dashboard.html': """
        <html>
        <head><title>Admin Dashboard</title></head>
        <body>
            <h1>Admin Dashboard</h1>
            <p>Welcome, Admin!</p>
            <a href="{{ url_for('create_course') }}">Create New Course</a><br><br>
            <h2>All Courses</h2>
            <ul>
            {% for c in courses %}
                <li>
                    {{ c.title }} 
                    | <a href="{{ url_for('admin_course_detail', course_id=c.id) }}">Details</a>
                </li>
            {% endfor %}
            </ul>
            <br>
            <a href="{{ url_for('analytics') }}">Analytics</a>
            <br><br>
            <a href="{{ url_for('logout') }}">Logout</a>
        </body>
        </html>
        """,
        'create_course.html': """
        <html>
        <head><title>Create Course</title></head>
        <body>
            <h1>Create Course</h1>
            <form method="POST">
                <label>Title:</label><br>
                <input type="text" name="title"><br><br>
                <label>Description:</label><br>
                <textarea name="description"></textarea><br><br>
                <button type="submit">Create</button>
            </form>
        </body>
        </html>
        """,
        'admin_course_detail.html': """
        <html>
        <head><title>Course Detail</title></head>
        <body>
            <h1>Course: {{ course.title }}</h1>
            <p>{{ course.description }}</p>
            <h2>Modules</h2>
            <ul>
            {% for m in course.modules %}
                <li>
                    {{ m.title }}
                    | <a href="{{ url_for('generate_quiz', module_id=m.id) }}">Generate Quiz</a>
                </li>
            {% endfor %}
            </ul>
            <a href="{{ url_for('create_module', course_id=course.id) }}">Add New Module</a>
            <br><br>
            <a href="{{ url_for('admin_dashboard') }}">Back to Admin Dashboard</a>
        </body>
        </html>
        """,
        'create_module.html': """
        <html>
        <head><title>Create Module</title></head>
        <body>
            <h1>Create Module for {{ course.title }}</h1>
            <form method="POST">
                <label>Module Title:</label><br>
                <input type="text" name="title"><br><br>
                <label>Content:</label><br>
                <textarea name="content"></textarea><br><br>
                <button type="submit">Create</button>
            </form>
        </body>
        </html>
        """,
        'analytics.html': """
        <html>
        <head><title>Analytics</title></head>
        <body>
            <h1>Analytics</h1>
            <p>Average quiz scores per module:</p>
            <ul>
            {% for mod, score in module_scores.items() %}
                <li>{{ mod }}: {{ score if score else 'No attempts yet' }}</li>
            {% endfor %}
            </ul>
            <br>
            <a href="{{ url_for('admin_dashboard') }}">Back to Admin Dashboard</a>
        </body>
        </html>
        """,
        'student_dashboard.html': """
        <html>
        <head><title>Student Dashboard</title></head>
        <body>
            <h1>Student Dashboard</h1>
            <h2>All Courses</h2>
            <ul>
            {% for c in courses %}
                <li>
                    {{ c.title }}
                    | <a href="{{ url_for('student_course_detail', course_id=c.id) }}">Details</a>
                </li>
            {% endfor %}
            </ul>
            <br>
            <a href="{{ url_for('logout') }}">Logout</a>
        </body>
        </html>
        """,
        'student_course_detail.html': """
        <html>
        <head><title>Student Course Detail</title></head>
        <body>
            <h1>Course: {{ course.title }}</h1>
            <p>{{ course.description }}</p>
            <h2>Modules</h2>
            <ul>
            {% for m in course.modules %}
                <li>
                    {{ m.title }}
                    | <a href="{{ url_for('student_module_detail', module_id=m.id) }}">View</a>
                </li>
            {% endfor %}
            </ul>
            <br>
            <a href="{{ url_for('student_dashboard') }}">Back to Dashboard</a>
        </body>
        </html>
        """,
        'student_module_detail.html': """
        <html>
        <head><title>Student Module Detail</title></head>
        <body>
            <h1>Module: {{ module.title }}</h1>
            <p>{{ module.content }}</p>

            <h2>Ask a question (Adaptive Learning)</h2>
            <form method="POST">
                <textarea name="student_question" rows="3" cols="50" placeholder="Ask about this module..."></textarea><br><br>
                <button type="submit">Ask</button>
            </form>
            {% if adaptive_answer %}
                <h3>AI's Response:</h3>
                <p>{{ adaptive_answer }}</p>
            {% endif %}

            <h2>Quiz Questions</h2>
            {% if quiz_questions %}
                <a href="{{ url_for('student_quiz', module_id=module.id) }}">Take Quiz</a>
            {% else %}
                <p>No quiz questions yet.</p>
            {% endif %}
            <br><br>
            <a href="{{ url_for('student_course_detail', course_id=module.course_id) }}">Back to Course</a>
        </body>
        </html>
        """,
        'student_quiz.html': """
        <html>
        <head><title>Quiz</title></head>
        <body>
            <h1>Quiz for {{ module.title }}</h1>
            <form method="POST">
            {% for q in quiz_questions %}
                <div style="margin-bottom:20px;">
                    <strong>Question {{ loop.index }}: </strong>{{ q.question }}<br>
                    {% set opts = q.options.split('|') %}
                    {% for opt in opts %}
                        <input type="radio" name="question_{{ q.id }}" value="{{ opt[0:1] }}"> {{ opt }}<br>
                    {% endfor %}
                </div>
            {% endfor %}
                <button type="submit">Submit Quiz</button>
            </form>
        </body>
        </html>
        """
    }
    html = templates.get(template_name, "<h1>Template not found</h1>")
    return make_response(html)

###############################################################################
# Run the Application
###############################################################################
if _name_ == '_main_':
    # Create DB tables if not exist
    db.create_all()
    
    # Uncomment below if you want to run in debug mode
    # app.run(debug=True)

    # For a production environment, consider using a production server like Gunicorn.
    app.run()

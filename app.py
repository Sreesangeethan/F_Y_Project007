import requests
import os
import openai
import os
from openai import OpenAI
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv
from llama_cpp import Llama

# Load the LLaMA model
llm = Llama(model_path="llama-2-7b-chat.Q4_K_M.gguf", n_ctx=2048)

# Function to generate quiz questions
def generate_quiz_questions(content, num_questions=5):
    prompt = f"""
You are an AI tutor. Based on the following content, generate {num_questions} multiple-choice quiz questions. 
Each should have 4 options (A, B, C, D), and indicate the correct answer at the end.

Content:
{content}

Format:
1) Question text...
A) Option A
B) Option B
C) Option C
D) Option D
Correct answer: X
"""
    response = llm(prompt, max_tokens=700)
    return response['choices'][0]['text'].strip()

# Function to provide adaptive explanations
def generate_adaptive_response(content, student_question):
    prompt = f"""
You are an AI tutor. Based on the following course content, explain clearly the answer to the student's question.

Content:
{content}

Student's question: {student_question}

Answer:
"""
    response = llm(prompt, max_tokens=400)
    return response['choices'][0]['text'].strip()

# Example usage
if __name__ == "__main__":
    # Sample course content
    course_content = """
Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize foods from carbon dioxide and water.
Photosynthesis in plants generally involves the green pigment chlorophyll and generates oxygen as a by-product.
"""

    # Generate quiz questions
    quiz = generate_quiz_questions(course_content, num_questions=3)
    print("=== Quiz Questions ===")
    print(quiz)

    # Student question
    question = "Why is chlorophyll important for photosynthesis?"
    answer = generate_adaptive_response(course_content, question)
    print("\n=== Adaptive Explanation ===")
    print(answer)

load_dotenv()  # take environment variables from .env.

def fetch_moodle_courses():
    """
    Fetch all courses from Moodle using the web service token
    and return them as a list of dictionaries.
    """
    moodle_url = os.environ.get("MOODLE_URL", "https://your-moodle.com")
    moodle_token = os.environ.get("MOODLE_TOKEN", "your_moodle_token")
    
    # Moodle endpoint
    endpoint = f"{moodle_url}/webservice/rest/server.php"
    
    # Example function name to get ALL courses
    function_name = "core_course_get_courses"  
    
    params = {
        "wstoken": moodle_token,
        "wsfunction": function_name,
        "moodlewsrestformat": "json",
    }

    response = requests.get(endpoint, params=params)
    response.raise_for_status()  # Raise HTTPError if the request failed
    courses_data = response.json()
    
    return courses_data

###############################################################################
# Configuration & Initialization
###############################################################################
app = Flask(__name__)

# For security, load secret key & API key from environment or config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'replace_with_secure_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lms_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the DB and OpenAI
db = SQLAlchemy(app)
client = OpenAI(
    api_key=os.environ.get('OPENAI_API_KEY', )
)


###############################################################################
# Database Models
###############################################################################
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "admin" or "student"
    
    # Helper method to check password
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    modules = relationship('Module', backref='course', cascade="all, delete-orphan")

class Module(db.Model):
    __tablename__ = 'modules'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

class QuizQuestion(db.Model):
    __tablename__ = 'quiz_questions'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, nullable=False)      # Store multiple options as JSON or comma-separated
    answer = db.Column(db.String(50), nullable=False) # Correct answer
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'))

class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'))
    score = db.Column(db.Float, nullable=False)


###############################################################################
# Database Setup Helper (Run once to create DB)
###############################################################################
# @app._got_first_request
# def create_tables():
#     db.create_all()


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
    wrapper.__name__ = func.__name__
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
    wrapper.__name__ = func.__name__
    return wrapper


def generate_quiz_questions(module_content, num_questions=5):
    """
    Uses OpenAI to generate multiple-choice quiz questions
    based on the module's content.
    """

    messages = [
        {"role": "system", "content": "You are an educational AI system."},
        {"role": "user", "content": f"""
        Based on the following content:

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
        """}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=700
    )

    return response.choices[0].message.content.strip()

def generate_adaptive_response(course_content, student_question):
    """
    Uses OpenAI to provide an adaptive learning response 
    based on the course content and student's question.
    """
    # client = OpenAI()

    messages = [
        {"role": "system", "content": "You are a tutoring AI. Your goal is to provide clear, informative, and concise explanations based on the provided course content."},
        {"role": "user", "content": f"""
        The course content is:

        {course_content}

        The student asks: {student_question}

        Provide an explanation that directly addresses the student's question using the course content.
        """}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=400,
    )

    return response.choices[0].message.content.strip()

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

# @app.route('/admin/analytics')
# @admin_required
# def analytics():
#     # Basic analytics: average scores per module
#     all_modules = Module.query.all()
#     module_scores = {}
#     for m in all_modules:
#         attempts = QuizAttempt.query.filter_by(module_id=m.id).all()
#         if attempts:
#             avg_score = sum(a.score for a in attempts) / len(attempts)
#             module_scores[m.title] = round(avg_score, 2)
#         else:
#             module_scores[m.title] = None
#     return render_template('analytics.html', module_scores=module_scores)


@app.route('/admin/analytics')
@admin_required
def analytics():
    # Basic analytics for each module
    all_modules = Module.query.all()
    
    module_data = []
    for m in all_modules:
        attempts = QuizAttempt.query.filter_by(module_id=m.id).all()
        
        if attempts:
            scores = [a.score for a in attempts]
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            min_score = min(scores)
            attempts_count = len(scores)
        else:
            avg_score = None
            max_score = None
            min_score = None
            attempts_count = 0

        module_data.append({
            "title": m.title,
            "avg_score": round(avg_score, 2) if avg_score is not None else None,
            "max_score": round(max_score, 2) if max_score is not None else None,
            "min_score": round(min_score, 2) if min_score is not None else None,
            "attempts_count": attempts_count,
        })
    
    return render_template('analytics.html', module_data=module_data)


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
import os
import requests
from flask import render_template, redirect, url_for, flash
# from yourapp import app, db  # Adjust according to your application structure
# from yourapp.models import Course  # Import your Course model
# from yourapp.utils import import_modules_for_course  # Assuming you put the helper function in utils.py

def import_modules_for_course(moodle_course_id, local_course):
    """
    Given a Moodle course id and a local Course instance,
    fetch the course contents from Moodle and import modules.
    """
    moodle_url = os.environ.get("MOODLE_URL", "https://your-moodle.com")
    moodle_token = os.environ.get("MOODLE_TOKEN", "your_moodle_token")
    endpoint = f"{moodle_url}/webservice/rest/server.php"
    function_name = "core_course_get_contents"
    
    params = {
        "wstoken": moodle_token,
        "wsfunction": function_name,
        "moodlewsrestformat": "json",
        "courseid": moodle_course_id,
    }
    
    response = requests.get(endpoint, params=params)
    response.raise_for_status()
    sections = response.json()

    print(sections)
    
    imported_modules_count = 0
    # Iterate over each section in the course.
    for section in sections:
        # Each section typically contains a list of modules.
        for module in section.get("modules", []):
            # Optionally, filter out modules by type:
            # if module.get("modname") not in ["resource", "assign", "quiz"]:
            #     continue
            # Check if a module with the same title already exists for this course.
            existing_module = Module.query.filter_by(title=module.get("name"), course_id=local_course.id).first()
            if existing_module:
                continue  # Skip duplicate modules
            
            new_module = Module(
                title=module.get("name", "Untitled Module"),
                # Use the module’s description if available; otherwise, fall back to the section summary.
                content=module.get("description") or section.get("summary", ""),
                course_id=local_course.id
            )
            db.session.add(new_module)
            imported_modules_count += 1
    db.session.commit()
    return imported_modules_count

@app.route('/admin/moodle_import', methods=['GET', 'POST'])
@admin_required  # Make sure only admins can use this route
def moodle_import():
    if os.environ.get("MOODLE_URL") is None or os.environ.get("MOODLE_TOKEN") is None:
        flash("Moodle configuration is missing in the environment variables.", "danger")
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        moodle_url = os.environ.get("MOODLE_URL", "https://your-moodle.com")
        moodle_token = os.environ.get("MOODLE_TOKEN", "your_moodle_token")
        endpoint = f"{moodle_url}/webservice/rest/server.php"
        function_name = "core_course_get_courses"
        
        params = {
            "wstoken": moodle_token,
            "wsfunction": function_name,
            "moodlewsrestformat": "json",
        }
        
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            moodle_courses = response.json()
        except Exception as e:
            flash(f"Error fetching courses: {str(e)}", "danger")
            return redirect(url_for('admin_dashboard'))
        
        imported_courses = 0
        imported_modules = 0
        
        for mc in moodle_courses:
            # Use the Moodle course's 'fullname' for the title and 'summary' for the description.
            title = mc.get('fullname', 'Untitled')
            description = mc.get('summary', 'No description provided')
            
            # Check if this course already exists locally.
            existing_course = Course.query.filter_by(title=title).first()
            if existing_course:
                local_course = existing_course
            else:
                local_course = Course(
                    title=title,
                    description=description
                )
                db.session.add(local_course)
                db.session.commit()  # Commit to generate a local course ID.
                imported_courses += 1
            
            # Import modules for this course using its Moodle course id.
            try:
                modules_imported = import_modules_for_course(mc.get('id'), local_course)
                imported_modules += modules_imported
            except Exception as e:
                flash(f"Error importing modules for course {local_course.title}: {str(e)}", "warning")
        
        flash(f"Imported {imported_courses} new course(s) and {imported_modules} module(s) from Moodle.", "success")
        return redirect(url_for('admin_dashboard'))
    
    # For GET requests, render a simple template with an "Import from Moodle" button.
    return render_template('moodle_import.html')


###############################################################################
# Run the Application
###############################################################################
if __name__ == '__main__':
    # Create DB tables if not exist
    with app.app_context():
        db.create_all()
    app.run()
      # Uncomment below if you want to run in debug mode
    app.run(debug=True)

    # For a production environment, consider using a production server like Gunicorn.
    # app.run()

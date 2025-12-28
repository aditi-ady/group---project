import os
import io
import base64
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from dotenv import load_dotenv
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash


load_dotenv()

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_hackathon' 


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')  


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    points = db.Column(db.Integer, default=0)
    videos_watched = db.Column(db.Integer, default=0)
    quiz_average = db.Column(db.Integer, default=0)
    quiz_count = db.Column(db.Integer, default=0)
    streak = db.Column(db.Integer, default=1)
    subject_scores = db.Column(db.String(500), default='{"Math": 0, "Science": 0, "English": 0, "History": 0, "AI": 0}')
    todos = db.relationship('Todo', backref='user', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def generate_performance_graph(user_scores_json):
    try: scores_dict = json.loads(user_scores_json)
    except: scores_dict = {"Math": 0, "Science": 0, "AI": 0}
    subjects = list(scores_dict.keys())
    scores = list(scores_dict.values())
    plt.figure(figsize=(6, 4))
    plt.style.use('dark_background')
    colors = ['#4e54c8', '#8f94fb', '#36b9cc', '#f6c23e', '#e74a3b', '#2ecc71']
    plt.bar(subjects, scores, color=[colors[i % len(colors)] for i in range(len(subjects))])
    plt.title('My Subject Performance'); plt.ylim(0, 100); plt.grid(axis='y', linestyle='--', alpha=0.3)
    img = io.BytesIO(); plt.savefig(img, format='png', bbox_inches='tight', transparent=True); img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode(); plt.close()
    return f"data:image/png;base64,{graph_url}"


@app.route('/')
def home():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user); return redirect(url_for('dashboard'))
        else: flash('Login Failed.', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email already exists!', 'warning')
            return redirect(url_for('signup'))
        user = User(username=username, email=email, password=generate_password_hash(password, method='pbkdf2:sha256'))
        db.session.add(user); db.session.commit(); flash('Account created!', 'success'); return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    graph_image = generate_performance_graph(current_user.subject_scores)
    return render_template('dashboard.html', user=current_user, graph_image=graph_image)

@app.route('/chat')
@login_required
def chat_page(): return render_template('chat_quiz.html')

@app.route('/community')
@login_required
def community_page(): return render_template('community.html', user=current_user)

@app.route('/todo')
@login_required
def todo_page():
    user_todos = Todo.query.filter_by(user_id=current_user.id).all()
    return render_template('todo.html', todos=user_todos)



@app.route('/api/update_quiz_stats', methods=['POST'])
@login_required
def update_quiz_stats():
    data = request.get_json()
    is_correct = data.get('correct')
    subject = data.get('subject', 'General')
    if is_correct: current_user.points += 10
    score = 100 if is_correct else 0
    total = current_user.quiz_average * current_user.quiz_count
    current_user.quiz_count += 1
    current_user.quiz_average = int((total + score) / current_user.quiz_count)
    try:
        scores = json.loads(current_user.subject_scores)
        if subject not in scores: scores[subject] = 0
        scores[subject] = min(100, scores[subject] + 10) if is_correct else max(0, scores[subject] - 5)
        current_user.subject_scores = json.dumps(scores)
    except: pass
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.get_json()
    user_msg = data.get('message', '')
    
    # Base Prompt
    prompt = f"""Act as a friendly AI Tutor.
    User Message: "{user_msg}"
    Response Format: Return ONLY raw JSON. No Markdown.
    {{ "type": "chat", "reply": "Your answer here" }}
    """

    # Quiz Specific Prompt
    if "quiz" in user_msg.lower():
        prompt = f"""Create a short quiz on: "{user_msg}".
        Generate 3 to 5 multiple-choice questions.
        
        CRITICAL: Return ONLY raw JSON. NO markdown.
        Structure:
        {{
            "type": "quiz",
            "subject": "Topic Name",
            "questions": [
                {{
                    "question": "Question text?",
                    "options": ["A", "B", "C", "D"],
                    "correct": "A"
                }}
            ]
        }}
        """

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()
        
        return jsonify(json.loads(text))
    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({'type': 'chat', 'reply': "I am thinking... try asking again!"})

@app.route('/api/messages', methods=['GET'])
@login_required
def get_messages():
    msgs = Message.query.order_by(Message.timestamp.desc()).limit(50).all()
    return jsonify([{
        'username': m.username, 
        'content': m.content, 
        'time': m.timestamp.strftime('%H:%M')
    } for m in msgs[::-1]])

@app.route('/api/messages', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    msg_content = data.get('content')
    if not msg_content: return jsonify({'error': 'Empty'}), 400
    new_msg = Message(username=current_user.username, content=msg_content)
    db.session.add(new_msg)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/add_todo', methods=['POST'])
@login_required
def add_todo():
    data = request.get_json()
    task_text = data.get('task')
    if not task_text: return jsonify({'error': 'Empty'}), 400
    new_task = Todo(task=task_text, user_id=current_user.id)
    db.session.add(new_task)
    db.session.commit()
    return jsonify({'success': True, 'id': new_task.id, 'task': new_task.task})

@app.route('/api/delete_todo', methods=['POST'])
@login_required
def delete_todo():
    data = request.get_json()
    task_id = data.get('id')
    task = Todo.query.get(task_id)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid'}), 400

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)
import os
import io
import base64
import json
import random
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from dotenv import load_dotenv
import google.generativeai as genai

# --- Safe Import for YouTube Transcript ---
try:
    import youtube_transcript_api
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
except ImportError:
    youtube_transcript_api = None

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# --- Database & Auth Imports ---
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_hackathon' 

# --- DATABASE CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- API KEY ---
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- USER MODEL (Default 0 Kar diya) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    
    # Stats Fields
    points = db.Column(db.Integer, default=0)
    videos_watched = db.Column(db.Integer, default=0)
    quiz_average = db.Column(db.Integer, default=0)
    quiz_count = db.Column(db.Integer, default=0)
    streak = db.Column(db.Integer, default=1)
    
    # Subject Scores (Default sab 0)
    subject_scores = db.Column(db.String(500), default='{"Math": 0, "Science": 0, "English": 0, "History": 0, "AI": 0}')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- GRAPH HELPER ---
def generate_performance_graph(user_scores_json):
    try:
        scores_dict = json.loads(user_scores_json)
    except:
        # Fallback bhi 0
        scores_dict = {"Math": 0, "Science": 0, "AI": 0}

    subjects = list(scores_dict.keys())
    scores = list(scores_dict.values())

    plt.figure(figsize=(6, 4))
    plt.style.use('dark_background')
    
    # Dynamic Colors
    colors = ['#4e54c8', '#8f94fb', '#36b9cc', '#f6c23e', '#e74a3b', '#2ecc71']
    bar_colors = [colors[i % len(colors)] for i in range(len(subjects))]
    
    plt.bar(subjects, scores, color=bar_colors)
    plt.title('My Subject Performance')
    plt.ylim(0, 100) # Scale wahi rahega 0-100
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', transparent=True)
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()
    plt.close()
    return f"data:image/png;base64,{graph_url}"

def get_video_id(url):
    if "v=" in url: return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url: return url.split("youtu.be/")[1].split("?")[0]
    return None

# --- ROUTES ---

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Failed. Check credentials.', 'danger')
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
            
        new_user = User(username=username, email=email, password=generate_password_hash(password, method='pbkdf2:sha256'))
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Login now.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    graph_image = generate_performance_graph(current_user.subject_scores)
    return render_template('dashboard.html', user=current_user, graph_image=graph_image)

@app.route('/youtube')
@login_required
def youtube_page():
    return render_template('youtube.html')

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat_quiz.html')

# --- APIs ---

# 1. Update Stats API (Updated Logic)
@app.route('/api/update_quiz_stats', methods=['POST'])
@login_required
def update_quiz_stats():
    data = request.get_json()
    is_correct = data.get('correct')
    subject = data.get('subject', 'General')

    if is_correct:
        current_user.points += 10
    
    # Quiz Average Logic
    score = 100 if is_correct else 0
    total_score_so_far = current_user.quiz_average * current_user.quiz_count
    current_user.quiz_count += 1
    current_user.quiz_average = int((total_score_so_far + score) / current_user.quiz_count)
    
    # Subject Graph Logic
    try:
        scores_dict = json.loads(current_user.subject_scores)
        
        # Start new subject from 0
        if subject not in scores_dict:
            scores_dict[subject] = 0
            
        # Update Logic: +10 for correct (to rise faster), -5 for wrong
        if is_correct:
            scores_dict[subject] = min(100, scores_dict[subject] + 10)
        else:
            scores_dict[subject] = max(0, scores_dict[subject] - 5)
            
        current_user.subject_scores = json.dumps(scores_dict)
    except:
        pass

    db.session.commit()
    return jsonify({'success': True, 'new_points': current_user.points})


# 2. Summarize API
@app.route('/api/summarize', methods=['POST'])
@login_required
def summarize_video():
    data = request.get_json()
    url = data.get('url')
    video_id = get_video_id(url)
    
    if not video_id: return jsonify({'error': 'Invalid URL'}), 400
    if not youtube_transcript_api: return jsonify({'error': 'Server Error: Library Missing'}), 500

    try:
        transcript_list = youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join([i['text'] for i in transcript_list])[:10000]
        
        prompt = f"""Summarize this video. Return JSON: 
        {{
            "title": "Video Title", 
            "subject": "One word subject (e.g. Math, Science, AI, History)",
            "summary": "HTML bullet points", 
            "quiz": [{{"question": "Q1", "options": ["A","B"], "answer": "A"}}]
        }} 
        Content: {text}"""
        
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        
        current_user.videos_watched += 1
        db.session.commit()
        
        return jsonify(json.loads(clean_json))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# 3. Chat API
@app.route('/api/chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.get_json()
    user_msg = data.get('message')
    
    prompt = f"""
    You are an AI Tutor. User: "{user_msg}"
    
    1. If QUIZ asked:
       {{
         "type": "quiz",
         "subject": "Infer subject from user query (e.g. Python, Math)", 
         "questions": [
            {{"question": "Q1?", "options": ["A", "B"], "answer": "A"}}
         ]
       }}
    
    2. If Normal Chat:
       {{ "type": "chat", "reply": "Response..." }}
    
    Return JSON only.
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```json" in text: text = text.replace("```json", "").replace("```", "")
        elif "```" in text: text = text.replace("```", "")
            
        return jsonify(json.loads(text))
        
    except Exception as e:
        print(f"Chat Error: {e}")
        return jsonify({'type': 'chat', 'reply': "Error generating response."})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
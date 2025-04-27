from flask import Flask, jsonify, request, render_template, send_from_directory, Response, redirect, url_for
import sqlite3
import os
import json
from datetime import datetime
import threading
import Hackathon as hack
import time
import re

latest_frame = None
frame_lock = threading.Lock()
last_ai_message = ''


app = Flask(__name__)

# Database configuration
DB_PATH = 'study_buddy_sessions.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Route to serve static files
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# Main routes for HTML pages
@app.route('/')
@app.route('/home.html')
def home():
    return render_template('home.html')

@app.route('/practice.html')
def practice():
    return render_template('practice.html')

@app.route('/history.html')
def history():
    return render_template('history.html')

@app.route('/notes.html')
def notes():
    return render_template('notes.html')

@app.route('/live_practice.html')
def live_practice():
    return render_template("live_practice.html")

@app.route('/video_feed')
def video_feed():
    return Response(
        hack.generate_video_frames(),
        minetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/start_practice', methods=['POST'])
def start_practice():
    """Launch background threads for camera and mic, then redirect to live practice page."""
    # Reset stop flag and start practice mode
    hack.main_thread_should_stop = False
    hack.is_practicing_speech = True
    hack.speech_practice_data = {"text": "", "start_time": time.time()}  # start transcript
    last_ai_message = "Practice started! Speak freely..."  # initial AI message

    # Start camera thread (for video capture & pose)
    cam_thread = threading.Thread(target=hack.run_camera_feed, daemon=True)
    cam_thread.start()

    # Start speech recognition thread
    mic_thread = threading.Thread(target=hack.recognize_speech, daemon=True)
    mic_thread.start()

    # Optionally, have the AI verbally acknowledge (if TTS is enabled)
    # hack.speak("Got it! Practice mode on...")  # will also be captured in last_ai_message if speak() is patched

    # Redirect to the live practice page
    return redirect(url_for('live_practice'))

@app.route("/camera_feed")
def camera_feed():
    return Response(
        hack.gen_camera_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# API Routes
@app.route('/api/latest_practice_data')
def get_latest_practice_data():
    try:
        # If we're actively practicing, return the current session data
        if hack.is_practicing_speech:
            # Calculate current duration
            duration = time.time() - hack.speech_practice_data.get("start_time", time.time())
            # Get current transcript
            transcript = hack.speech_practice_data.get("text", "")
            # Count words
            words = len(transcript.split()) if transcript else 0
            # Calculate WPM
            wpm = int(words / (duration / 60.0)) if duration > 0 else 0
            # Count filler words
            filler_count = 0
            for filler in hack.FILLER_WORDS:
                filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', transcript.lower()))
            
            # Get current posture
            with hack.posture_lock:
                posture = hack.current_posture_status
                
            return jsonify({
                'success': True,
                'practice_session': {
                    'session_id': 0,  # Temporary ID for active session
                    'timestamp': datetime.now().isoformat(),
                    'duration_seconds': round(duration, 1),
                    'total_words': words,
                    'wpm': wpm,
                    'filler_count': filler_count,
                    'final_posture': posture,
                    'transcript': transcript
                }
            }), 200
        
        # If not practicing, try to get the latest saved session
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM speech_practice_sessions
            ORDER BY datetime(timestamp) DESC
            LIMIT 1
        ''')
        row = cur.fetchone()
        conn.close()

        if row is None:
            # If no sessions are found, return a demo session
            return jsonify({
                'success': True,
                'practice_session': {
                    'session_id': 0,
                    'timestamp': datetime.now().isoformat(),
                    'duration_seconds': 0,
                    'total_words': 0,
                    'wpm': 0,
                    'filler_count': 0,
                    'final_posture': "No posture data",
                    'transcript': "No transcript available yet. Start speaking to see text here."
                }
            }), 200

        # Return data from the database
        session = dict(row)
        return jsonify({
            'success': True,
            'practice_session': session
        }), 200

    except Exception as e:
        print(f"Error in get_latest_practice_data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/recent_stats')
def get_recent_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get total count of sessions
    cursor.execute('SELECT COUNT(*) as count FROM speech_practice_sessions')
    total_sessions = cursor.fetchone()['count']
    
    # Get average WPM
    cursor.execute('SELECT AVG(wpm) as avg_wpm FROM speech_practice_sessions')
    avg_wpm_row = cursor.fetchone()
    average_wpm = round(avg_wpm_row['avg_wpm']) if avg_wpm_row['avg_wpm'] is not None else 0
    
    # Get total practice time
    cursor.execute('SELECT SUM(duration_seconds) as total_time FROM speech_practice_sessions')
    total_time_row = cursor.fetchone()
    total_practice_time = total_time_row['total_time'] if total_time_row['total_time'] is not None else 0
    
    # Get session history for chart (last 7 sessions)
    cursor.execute('''
        SELECT timestamp, wpm, filler_count 
        FROM speech_practice_sessions 
        ORDER BY timestamp DESC 
        LIMIT 7
    ''')
    
    history_rows = cursor.fetchall()
    session_history = []
    
    for row in history_rows:
        history_item = dict(row)
        # Convert timestamp if needed
        if 'timestamp' in history_item:
            try:
                # If timestamp is stored as Unix timestamp (integer)
                timestamp = int(history_item['timestamp'])
                history_item['timestamp'] = datetime.fromtimestamp(timestamp).isoformat()
            except ValueError:
                # If it's already a string, leave it as is
                pass
        
        session_history.append(history_item)
    
    # Calculate improvement rate (if possible)
    improvement_rate = 0
    if len(session_history) >= 2:
        first_wpm = session_history[-1]['wpm']  # Oldest session
        last_wpm = session_history[0]['wpm']    # Newest session
        if first_wpm > 0:
            improvement_rate = round(((last_wpm - first_wpm) / first_wpm) * 100, 1)
    
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'totalSessions': total_sessions,
            'averageWpm': average_wpm,
            'totalPracticeTime': total_practice_time,
            'improvementRate': improvement_rate,
            'sessionHistory': session_history
        }
    })

# Notecard system API routes
# For simplicity, we'll store notecards in a separate table
@app.route('/api/notecards')
def get_notecards():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create notecards table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notecards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    
    # Get search parameters
    search_term = request.args.get('search', '')
    
    if search_term:
        # Search in title, content, or tags
        cursor.execute('''
            SELECT * FROM notecards 
            WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
            ORDER BY created_at DESC
        ''', (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
    else:
        # Get all notecards
        cursor.execute('''
            SELECT * FROM notecards 
            ORDER BY created_at DESC
        ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    notecards = []
    for row in rows:
        notecard = dict(row)
        # Parse tags from JSON string
        if 'tags' in notecard and notecard['tags']:
            try:
                notecard['tags'] = json.loads(notecard['tags'])
            except json.JSONDecodeError:
                notecard['tags'] = []
        else:
            notecard['tags'] = []
        
        notecards.append(notecard)
    
    return jsonify({
        'success': True,
        'notecards': notecards
    })

@app.route('/api/notecards', methods=['POST'])
def create_notecard():
    data = request.json
    
    # Validate required fields
    if not data or 'title' not in data or 'content' not in data:
        return jsonify({
            'success': False,
            'message': 'Title and content are required'
        }), 400
    
    # Get data from request
    title = data.get('title')
    content = data.get('content')
    tags = json.dumps(data.get('tags', []))
    created_at = datetime.now().isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notecards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Insert new notecard
    cursor.execute('''
        INSERT INTO notecards (title, content, tags, created_at)
        VALUES (?, ?, ?, ?)
    ''', (title, content, tags, created_at))
    
    notecard_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'id': notecard_id,
        'message': 'Notecard created successfully'
    })

@app.route('/api/notecards/<int:notecard_id>', methods=['PUT'])
def update_notecard(notecard_id):
    data = request.json
    
    # Validate required fields
    if not data or 'title' not in data or 'content' not in data:
        return jsonify({
            'success': False,
            'message': 'Title and content are required'
        }), 400
    
    # Get data from request
    title = data.get('title')
    content = data.get('content')
    tags = json.dumps(data.get('tags', []))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Update notecard
    cursor.execute('''
        UPDATE notecards
        SET title = ?, content = ?, tags = ?
        WHERE id = ?
    ''', (title, content, tags, notecard_id))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'Notecard not found'
        }), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Notecard updated successfully'
    })

@app.route('/api/notecards/<int:notecard_id>', methods=['DELETE'])
def delete_notecard(notecard_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete notecard
    cursor.execute('DELETE FROM notecards WHERE id = ?', (notecard_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'Notecard not found'
        }), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Notecard deleted successfully'
    })

if __name__ == '__main__':
    # Create the database if it doesn't exist
    if not os.path.exists(DB_PATH):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create the speech_practice_sessions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS speech_practice_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            total_words INTEGER NOT NULL,
            wpm INTEGER NOT NULL,
            filler_count INTEGER NOT NULL,
            final_posture TEXT,
            transcript TEXT
        )
        ''')
        
        conn.commit()
        conn.close()
    
    app.run(debug=True)
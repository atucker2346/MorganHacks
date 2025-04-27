# app.py - COMPLETE CODE (Corrected Thread Start)
from flask import Flask, jsonify, request, render_template, send_from_directory, Response, redirect, url_for
import sqlite3
import os
import json
from datetime import datetime
import threading
import Hackathon as hack # Import the MODIFIED Hackathon.py (assuming it expects 'recognizer' argument)
import time
import re
import sys # For exit (optional)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Global State (within Flask app context) ---
# Keep track of background threads started by Flask
background_threads = {
    "camera": None,
    "mic": None
}

# --- Database Configuration & Helper ---
DB_PATH = hack.DB_FILE # Use the path defined in Hackathon.py

def get_db_connection():
    """Establishes connection to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"DATABASE CONNECTION ERROR: {e}")
        if conn: conn.close()
        return None

# --- Static Files Route ---
@app.route('/static/<path:path>')
def send_static(path):
    static_folder = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_folder, path)

# --- HTML Page Routes ---
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

# --- Live Practice Route (Starts Threads) ---
# Note: Route uses underscore, ensure links/redirects match
@app.route('/live-practice')
def live_practice():
    """
    Serves the main interactive practice page AND starts
    background threads (camera, mic listener) if they aren't running.
    """
    global background_threads

    # Corrected route name used in log message for clarity
    print("--- Accessed /live_practice route ---")

    # --- Ensure Background Threads are Running ---
    hack.main_thread_should_stop = False

    # Check and start Camera Thread
    if hack.pose:
        if not background_threads["camera"] or not background_threads["camera"].is_alive():
            print("   Starting camera feed thread...")
            background_threads["camera"] = None
            cam_thread = threading.Thread(target=hack.run_camera_feed, daemon=True)
            cam_thread.start()
            background_threads["camera"] = cam_thread
            print("   Camera thread started.")
        else:
            print("   Camera thread already running.")
    else:
        print("   Skipping camera thread start (MediaPipe Pose failed).")

    # Check and start Speech Recognition Thread
    if hack.mic_available:
        if not background_threads["mic"] or not background_threads["mic"].is_alive():
            print("   Starting speech recognition thread...")
            background_threads["mic"] = None
            # **** V V V CRITICAL FIX APPLIED HERE V V V ****
            # Pass the global recognizer instance hack.r as an argument
            mic_thread = threading.Thread(target=hack.recognize_speech, args=(hack.r,), daemon=True)
            # **** ^ ^ ^ CRITICAL FIX APPLIED HERE ^ ^ ^ ****
            mic_thread.start()
            background_threads["mic"] = mic_thread
            print("   Speech thread started.")
        else:
            print("   Speech thread already running.")
    else:
        print("   Skipping speech thread start (Microphone not available).")

    return render_template("live_practice.html")

# --- Video Streaming Route ---
@app.route('/video_feed')
def video_feed():
    """Streams video frames using the generator from Hackathon.py."""
    print("--- Accessed /video_feed route ---")
    if not hack.pose:
        print("   Error: Camera/Pose detection not initialized.")
        return "Error: Camera/Pose detection not initialized.", 500

    if not background_threads["camera"] or not background_threads["camera"].is_alive():
         print("   WARNING: video_feed requested but camera thread not running! Attempting start...")
         if hack.pose:
             background_threads["camera"] = threading.Thread(target=hack.run_camera_feed, daemon=True)
             background_threads["camera"].start()
             time.sleep(1.5)
             if not background_threads["camera"].is_alive():
                 print("   Error: Failed to start camera feed thread.")
                 return "Error: Failed to start camera feed.", 503
             print("   Camera thread started for video_feed.")
         else:
            print("   Error: Camera feed cannot start (Pose detection failed).")
            return "Error: Camera feed cannot start (Pose detection failed).", 500
    else:
         print("   Camera thread confirmed running for video_feed.")

    return Response(
        hack.gen_camera_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# --- OLD Start Practice Route (Deprecated) ---
# It's recommended to remove this if not used, or repurpose it
# to ONLY toggle the practice state if needed via JS without redirecting.
@app.route('/start_practice', methods=['POST'])
def start_practice_DEPRECATED():
     """DEPRECATED: Thread starting is handled by /live_practice."""
     print("WARNING: Deprecated /start_practice POST route called.")
     return redirect(url_for('live_practice'))


# --- Web Button Controls (for live_practice.html JavaScript) ---
@app.route('/start_practice_web', methods=['POST'])
def start_practice_web():
    """Starts the practice session recording state via web button."""
    print("--- Accessed /start_practice_web route ---")
    if not background_threads["mic"] or not background_threads["mic"].is_alive():
         print("   Error: Cannot start practice, the microphone listener isn't active.")
         hack.speak("Cannot start practice, the microphone listener isn't active.") # Use local TTS if available
         return jsonify({'success': False, 'message': 'Mic listener not active.'}), 503

    if not hack.is_practicing_speech:
        print("   Starting practice recording state...")
        hack.is_practicing_speech = True
        hack.speech_practice_data = {"text": "", "start_time": time.time()}
        hack.speak("Okay, practice started! I'm listening.") # Use local TTS
        return jsonify({'success': True, 'message': 'Practice started.'}), 200
    else:
        print("   Practice is already running.")
        hack.speak("Practice is already running.") # Use local TTS
        return jsonify({'success': False, 'message': 'Practice already in progress.'}), 400

@app.route('/end_practice_web', methods=['POST'])
def end_practice_web():
    """Ends the practice session recording state via web button."""
    print("--- Accessed /end_practice_web route ---")
    if hack.is_practicing_speech:
        print("   Ending practice recording state...")
        hack.is_practicing_speech = False
        hack.speak("Okay, ending practice session. Analyzing results...") # Use local TTS
        try:
             print("   Calling analyze_and_feedback...")
             hack.analyze_and_feedback() # This calls speak() internally now
             print("   Analysis complete.")
        except Exception as e:
             print(f"   Error during analysis feedback: {e}")
             hack.speak("There was an issue analyzing the session.") # Use local TTS
        finally:
             hack.speech_practice_data = {"text": "", "start_time": None}
        return jsonify({'success': True, 'message': 'Practice ended. Analyzing...'}), 200
    else:
        print("   No practice session is currently active.")
        hack.speak("No practice session is currently active.") # Use local TTS
        return jsonify({'success': False, 'message': 'No practice session active.'}), 400


# --- Camera Feed (Alternative Name - Check HTML usage) ---
# Ensure HTML uses /video_feed for consistency, or keep this route identical
@app.route("/camera_feed")
def camera_feed():
     """Provides the camera feed, ensure consistency with /video_feed"""
     print("--- Accessed /camera_feed route ---")
     if not hack.pose:
         print("   Error: Camera/Pose detection not initialized.")
         return "Error: Camera/Pose detection not initialized.", 500
     if not background_threads["camera"] or not background_threads["camera"].is_alive():
          print("   WARNING: camera_feed requested but camera thread is not running!")
          return "Error: Camera feed not active.", 503
     return Response(
         hack.gen_camera_frames(),
         mimetype="multipart/x-mixed-replace; boundary=frame"
     )

# --- API Routes ---

# This route might become unused if all interaction is via local voice,
# but keeping it doesn't hurt.
@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """Receives user text message from web UI, gets AI reply, returns reply text."""
    print("--- Accessed /api/chat route ---")
    user_message = request.json.get('message')
    if not user_message: return jsonify({'error': 'No message provided.'}), 400
    if not hack.gemini_model: return jsonify({'reply': "Chat brain unavailable."}), 200
    print(f"   User web chat message: '{user_message}'")
    hack.add_message('user_web_chat', user_message)
    try:
        print("   Sending web message to Gemini...")
        response = hack.gemini_model.generate_content(user_message)
        ai_reply = "";
        if hasattr(response, 'parts') and response.parts: ai_reply = "".join(part.text for part in response.parts if hasattr(part, 'text'))
        elif hasattr(response, 'text'): ai_reply = response.text
        elif isinstance(response, str): ai_reply = response
        else: ai_reply = "Couldn't understand Gemini response format."
        ai_reply = ai_reply.strip();
        if not ai_reply: ai_reply = "No comment."
        print(f"   AI reply generated (for web): '{ai_reply[:100]}...'")
        # Update state ONLY, no TTS from web chat API call
        hack.speak(ai_reply) # NOTE: In local TTS mode, this WILL play audio. Decide if that's desired for web chat.
                             # If not, call hack.add_message and update last_ai_message manually here.
                             # Let's assume local TTS is OK for now based on user flow.
        return jsonify({'reply': ai_reply}), 200
    except Exception as e:
        print(f"   ❌ Gemini API Error during web chat: {e}")
        hack.speak("Error processing web chat.") # Play local TTS error
        return jsonify({'reply': "Internal error processing web chat."}), 500


@app.route('/api/latest_practice_data')
def get_latest_practice_data():
    """Provides status data for the web UI."""
    # (This function remains the same as the previous corrected version)
    current_data = {}; is_live = hack.is_practicing_speech; error_msg = None
    try:
        if is_live:
            start_time = hack.speech_practice_data.get("start_time", time.time()); duration = max(0, time.time() - start_time)
            transcript = hack.speech_practice_data.get("text", ""); words = len(transcript.split()) if transcript else 0
            wpm = int(words / (duration / 60.0)) if duration > 1 else 0; filler_count = 0
            if transcript:
                 lower_text = transcript.lower()
                 for filler in hack.FILLER_WORDS:
                     try: filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', lower_text))
                     except re.error as re_err: print(f"   Warning: Regex error in live stats for '{filler}': {re_err}")
            with hack.posture_lock: posture = hack.current_posture_status
            current_data = { 'session_id': 0, 'timestamp': datetime.now().isoformat(), 'duration_seconds': round(duration, 1),
                'total_words': words, 'wpm': wpm, 'filler_count': filler_count, 'final_posture': posture, 'transcript': transcript }
        else:
            conn = get_db_connection()
            if conn:
                try:
                    cur = conn.cursor(); cur.execute('SELECT * FROM speech_practice_sessions ORDER BY session_id DESC LIMIT 1'); row = cur.fetchone()
                    if row: current_data = dict(row)
                    else: current_data = { 'session_id': -1, 'timestamp': '', 'duration_seconds': 0, 'total_words': 0, 'wpm': 0, 'filler_count': 0, 'final_posture': 'N/A', 'transcript': 'No past sessions found.' }
                except sqlite3.Error as db_e: print(f"   DB Error fetching last session: {db_e}"); error_msg = 'DB error fetching history.'; current_data = {'error': error_msg}
                finally: conn.close()
            else: error_msg = 'DB connection failed.'; current_data = {'error': error_msg}
        response_data = { 'success': error_msg is None, 'is_live': is_live, 'practice_session': current_data, 'last_ai_message': hack.get_last_ai_message() }
        if error_msg: response_data['error'] = error_msg
        return jsonify(response_data), 200 if error_msg is None else 500
    except Exception as e:
        print(f"   ❌ Unexpected Error in get_latest_practice_data: {e}")
        return jsonify({ 'success': False, 'error': f'Unexpected error: {str(e)}', 'is_live': is_live, 'practice_session': {}, 'last_ai_message': hack.get_last_ai_message() }), 500


@app.route('/api/recent_stats')
def get_recent_stats():
    """Fetches aggregate stats and history."""
    # (This function remains the same as the previous corrected version)
    print("--- Accessed /api/recent_stats route ---"); conn = get_db_connection()
    if not conn: return jsonify({'success': False, 'error': 'Database connection failed.'}), 500
    stats = { 'totalSessions': 0, 'averageWpm': 0, 'totalPracticeTime': 0, 'improvementRate': 0, 'sessionHistory': [] }
    try:
        cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) as count FROM speech_practice_sessions'); total_sessions_row = cursor.fetchone()
        stats['totalSessions'] = total_sessions_row['count'] if total_sessions_row else 0
        cursor.execute('SELECT AVG(wpm) as avg_wpm FROM speech_practice_sessions WHERE wpm > 0'); avg_wpm_row = cursor.fetchone()
        stats['averageWpm'] = round(avg_wpm_row['avg_wpm']) if avg_wpm_row and avg_wpm_row['avg_wpm'] is not None else 0
        cursor.execute('SELECT SUM(duration_seconds) as total_time FROM speech_practice_sessions'); total_time_row = cursor.fetchone()
        stats['totalPracticeTime'] = round(total_time_row['total_time']) if total_time_row and total_time_row['total_time'] is not None else 0
        limit = 7; cursor.execute(f'SELECT session_id, timestamp, wpm, filler_count, duration_seconds FROM speech_practice_sessions ORDER BY session_id DESC LIMIT ?', (limit,)); history_rows = cursor.fetchall()
        session_history_list = [dict(row) for row in reversed(history_rows)]; stats['sessionHistory'] = session_history_list
        if len(session_history_list) >= 2:
            first_wpm = session_history_list[0].get('wpm', 0); last_wpm = session_history_list[-1].get('wpm', 0)
            if first_wpm > 0: stats['improvementRate'] = round(((last_wpm - first_wpm) / first_wpm) * 100, 1)
            else: stats['improvementRate'] = 0
        return jsonify({'success': True, 'stats': stats}), 200
    except sqlite3.Error as e: print(f"   DB Error in get_recent_stats: {e}"); return jsonify({'success': False, 'error': f'Database error: {e}', 'stats': stats}), 500
    finally:
        if conn: conn.close()


# --- Notecard API Routes ---
# (These functions remain the same as the previous corrected version)
@app.route('/api/notecards', methods=['GET'])
def get_notecards():
    search_term = request.args.get('search', ''); conn = get_db_connection()
    if not conn: return jsonify({'success': False, 'error': 'Database connection failed.'}), 500
    notecards = []
    try:
        cursor = conn.cursor(); sql = 'SELECT id, title, content, tags, created_at FROM notecards '; params = []
        if search_term: sql += 'WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? '; like_term = f'%{search_term}%'; params.extend([like_term, like_term, like_term])
        sql += 'ORDER BY created_at DESC'; cursor.execute(sql, params); rows = cursor.fetchall()
        for row in rows:
            notecard = dict(row)
            try: tags_json = notecard.get('tags'); notecard['tags'] = json.loads(tags_json) if tags_json else []
            except (json.JSONDecodeError, TypeError): notecard['tags'] = []
            notecards.append(notecard)
        return jsonify({'success': True, 'notecards': notecards}), 200
    except sqlite3.Error as e: print(f"   DB Error getting notecards: {e}"); return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
    finally:
        if conn: conn.close()

@app.route('/api/notecards', methods=['POST'])
def create_notecard():
    data = request.json;
    if not data or not data.get('title') or not data.get('content'): return jsonify({'success': False,'message': 'Title and content are required'}), 400
    conn = get_db_connection();
    if not conn: return jsonify({'success': False, 'error': 'Database connection failed.'}), 500
    try:
        cursor = conn.cursor(); cursor.execute('INSERT INTO notecards (title, content, tags, created_at) VALUES (?, ?, ?, ?)', ( data.get('title'), data.get('content'), json.dumps(data.get('tags', [])), datetime.now().isoformat() )); notecard_id = cursor.lastrowid; conn.commit()
        return jsonify({'success': True, 'id': notecard_id, 'message': 'Notecard created'}), 201
    except sqlite3.Error as e: print(f"   DB Error creating notecard: {e}"); return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
    finally:
        if conn: conn.close()

@app.route('/api/notecards/<int:notecard_id>', methods=['PUT'])
def update_notecard(notecard_id):
    data = request.json
    if not data or not data.get('title') or not data.get('content'): return jsonify({'success': False,'message': 'Title and content are required'}), 400
    conn = get_db_connection();
    if not conn: return jsonify({'success': False, 'error': 'Database connection failed.'}), 500
    try:
        cursor = conn.cursor(); cursor.execute('UPDATE notecards SET title = ?, content = ?, tags = ? WHERE id = ?', ( data.get('title'), data.get('content'), json.dumps(data.get('tags', [])), notecard_id ))
        if cursor.rowcount == 0: return jsonify({'success': False, 'message': 'Notecard not found'}), 404
        conn.commit(); return jsonify({'success': True, 'message': 'Notecard updated successfully'}), 200
    except sqlite3.Error as e: print(f"   DB Error updating notecard {notecard_id}: {e}"); return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
    finally:
        if conn: conn.close()

@app.route('/api/notecards/<int:notecard_id>', methods=['DELETE'])
def delete_notecard(notecard_id):
    conn = get_db_connection();
    if not conn: return jsonify({'success': False, 'error': 'Database connection failed.'}), 500
    try:
        cursor = conn.cursor(); cursor.execute('DELETE FROM notecards WHERE id = ?', (notecard_id,))
        if cursor.rowcount == 0: return jsonify({'success': False, 'message': 'Notecard not found'}), 404
        conn.commit(); return jsonify({'success': True, 'message': 'Notecard deleted successfully'}), 200
    except sqlite3.Error as e: print(f"   DB Error deleting notecard {notecard_id}: {e}"); return jsonify({'success': False, 'error': f'Database error: {e}'}), 500
    finally:
        if conn: conn.close()


# --- Main Execution ---
if __name__ == '__main__':
    print("Initializing database via Hackathon module...")
    hack.init_database()
    print("Starting Flask development server...")
    app.run(debug=True, host='127.0.0.1', port=5000) # Use debug=False in production
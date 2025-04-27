# Hackathon.py - RE-INTEGRATED General Chat & Local TTS Playback
import speech_recognition as sr
import google.generativeai as genai
import cv2
import time
import mediapipe as mp
from elevenlabs.client import ElevenLabs
from elevenlabs import play # For local audio output
import os
import sys
import numpy as np
import re
import threading
import sqlite3
from datetime import datetime
import api # Assuming api.py holds your keys correctly

# --- Message History (Optional, for context) ---
message_history = []

def add_message(sender, text):
    global message_history
    message_history.append({'sender': sender, 'text': text})
    if len(message_history) > 10:
        message_history.pop(0)

def get_message_history_text():
    return "\n".join([f"{m['sender']}: {m['text']}" for m in message_history])

# --- Configuration ---
GOOGLE_API_KEY_FROM_USER = api.GOOGLE_API_KEY_FROM_USER
ELEVENLABS_API_KEY_FROM_USER = api.ELEVENLABS_API_KEY_FROM_USER
GOOGLE_KEY_PLACEHOLDER = "YOUR_GOOGLE_API_KEY_HERE"
ELEVENLABS_KEY_PLACEHOLDER = "YOUR_ELEVENLABS_API_KEY_HERE"

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", GOOGLE_API_KEY_FROM_USER)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY_FROM_USER)

VOICE_NAME = "Elli"

# --- Constants ---
START_PRACTICE_PHRASE = "start practice speech"
END_PRACTICE_PHRASE = "end speech"
STOP_COMMAND = "stop"
FILLER_WORDS = ["um", "uh", "ah", "er", "like", "so", "you know", "actually", "basically", "well", "right"]
DB_FILE = "study_buddy_sessions.db"

# --- Shared State & Locks ---
is_practicing_speech = False
current_posture_status = "Posture: Initializing..."
posture_lock = threading.Lock()
speech_practice_data = {"text": "", "start_time": None}
main_thread_should_stop = False

latest_frame = None
frame_lock = threading.Lock()
last_ai_message = "AI Initializing..." # For web UI display if needed
ai_message_lock = threading.Lock()

# --- Database Functions ---
# (init_database and save_practice_session remain unchanged)
def init_database():
    """Initializes the SQLite DB and creates tables if they don't exist."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS speech_practice_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    duration_seconds REAL NOT NULL, total_words INTEGER NOT NULL,
                    wpm INTEGER NOT NULL, filler_count INTEGER NOT NULL,
                    final_posture TEXT, transcript TEXT )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notecards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    content TEXT NOT NULL, tags TEXT, created_at TEXT NOT NULL )
            """)
            conn.commit()
            print(f"✅ Database '{DB_FILE}' initialized successfully.")
    except sqlite3.Error as e:
        print(f"❌❌ DATABASE ERROR during initialization: {e}")

def save_practice_session(timestamp, duration, words, wpm, fillers, posture, transcript):
    """Saves the results of a practice session to the database."""
    sql = """ INSERT INTO speech_practice_sessions
              (timestamp, duration_seconds, total_words, wpm, filler_count, final_posture, transcript)
              VALUES (?, ?, ?, ?, ?, ?, ?) """
    data_tuple = (timestamp, duration, words, wpm, fillers, posture, transcript)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, data_tuple)
            print(f"✅ Practice session data saved to database (ID: {cursor.lastrowid}).")
    except sqlite3.Error as e:
        print(f"❌❌ DATABASE ERROR during save: {e}")


# --- Setup Clients & Services ---
# (Initialization logic remains unchanged)
elevenlabs_client = None
gemini_model = None
mic = None
mic_available = False
pose = None

print("--- Initializing Services ---")
# ElevenLabs
if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == ELEVENLABS_KEY_PLACEHOLDER:
    print("⚠️ ElevenLabs API Key missing or placeholder. TTS playback disabled.")
else:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("✅ ElevenLabs client configured.")
    except Exception as e:
        print(f"❌ ElevenLabs Initialization Error: {e}")
        elevenlabs_client = None
# Gemini
if not GOOGLE_API_KEY or GOOGLE_API_KEY == GOOGLE_KEY_PLACEHOLDER:
     print("⚠️ Google API Key missing or placeholder. Gemini chat disabled.")
else:
    try:
        print(f"   Configuring Gemini with key ending ...{GOOGLE_API_KEY[-4:]}")
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_model = genai.GenerativeModel(
            'gemini-1.5-flash',
             # System prompt adjusted for direct voice interaction
            system_instruction="You are a funny, supportive AI study buddy named 'Buddy'. Keep responses concise and friendly. You are interacting via direct voice. You want to help making our speaking skills better."
        )
        print("✅ Google Gemini configured.")
    except Exception as e:
        print(f"❌ Gemini Initialization Error: {e}")
        gemini_model = None
# Speech Recognition Mic Check
r = sr.Recognizer() # Define recognizer instance globally
try:
    mic_list = sr.Microphone.list_microphone_names()
    if not mic_list:
         print("⚠️ No microphones found by SpeechRecognition.")
         mic_available = False
    else:
         print(f"🎤 Found microphones: {len(mic_list)}. Will use default.")
         mic = sr.Microphone()
         mic_available = True
         print("✅ Microphone available.")
except Exception as e:
    print(f"⚠️ Microphone check failed: {e}")
    mic_available = False
    mic = None
# MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
try:
    pose = mp_pose.Pose(static_image_mode=False, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    print("✅ MediaPipe Pose configured.")
except Exception as e:
     print(f"❌ MediaPipe Pose Initialization Error: {e}")
     pose = None


# --- Helper Functions ---

# **** MODIFIED speak FUNCTION ****
def speak(text):
    """
    Updates the global 'last_ai_message' state AND
    Uses ElevenLabs to generate and PLAY audio LOCALLY if available.
    """
    global last_ai_message, ai_message_lock, elevenlabs_client

    if not text or not isinstance(text, str):
        print("   ⚠️ Speak function called with invalid text.")
        with ai_message_lock: last_ai_message = "Internal message error occurred."
        add_message('computer', last_ai_message)
        return

    print(f"AI intends to say: '{text[:100]}...'")

    # Update shared state for potential web display via API
    with ai_message_lock:
        last_ai_message = text
    add_message('computer', text)

    # --- TTS Generation and LOCAL Playback ---
    if not elevenlabs_client:
        print("   (TTS Playback Skipped: ElevenLabs client not available)")
        return
    if not text.strip():
        print("   (TTS Playback Skipped: empty text)")
        return

    print("   🔊 Attempting ElevenLabs TTS generation & playback...")
    try:
        audio_stream = elevenlabs_client.generate(
            text=text,
            voice=VOICE_NAME,
            model='eleven_multilingual_v2',
            stream=True
        )
        # --- RE-ENABLED PLAYBACK ---
        play(audio_stream) # Play audio locally
        print("   ✅ TTS playback likely started.")
        # --------------------------
    except Exception as e:
        print(f"   ❌❌ ERROR during TTS generation/playback: {e}")
        if "API key" in str(e).lower(): print("      (Check ElevenLabs API key)")
        elif "quota" in str(e).lower(): print("      (Check ElevenLabs quota)")
        elif "ffplay" in str(e).lower() or "mpv" in str(e).lower():
             print("      (Audio playback error: Ensure 'ffplay' or 'mpv' is installed and in system PATH)")
        else: print(f"      (Full error: {e})")
    # ---------------------------------

# (get_last_ai_message function remains unchanged)
def get_last_ai_message():
    """Safely retrieve the last message stored by the speak function."""
    global last_ai_message, ai_message_lock
    with ai_message_lock:
        if 'last_ai_message' in globals():
            return last_ai_message
        else:
            print("CRITICAL WARNING: last_ai_message global variable not found!")
            return "AI message state error."

# (analyze_posture function remains unchanged)
def analyze_posture(landmarks):
    """Analyzes MediaPipe landmarks for simple posture cues."""
    if not landmarks: return "Posture: No user detected"
    try:
        lm = landmarks.landmark
        required_indices = [ mp_pose.PoseLandmark.NOSE.value, mp_pose.PoseLandmark.LEFT_SHOULDER.value,
            mp_pose.PoseLandmark.RIGHT_SHOULDER.value, mp_pose.PoseLandmark.LEFT_EAR.value, mp_pose.PoseLandmark.RIGHT_EAR.value ]
        if any(idx >= len(lm) for idx in required_indices): return "Posture: Critical points missing"
        nose = lm[mp_pose.PoseLandmark.NOSE.value]; l_shoulder = lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        r_shoulder = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]; l_ear = lm[mp_pose.PoseLandmark.LEFT_EAR.value]
        r_ear = lm[mp_pose.PoseLandmark.RIGHT_EAR.value]; visibility_threshold = 0.4
        if not all(pt.visibility > visibility_threshold for pt in [nose, l_shoulder, r_shoulder, l_ear, r_ear]): return "Posture: Key points hidden"
        shoulder_y_avg = (l_shoulder.y + r_shoulder.y) / 4.0; slouch_threshold = 0.06
        if nose.y > shoulder_y_avg + slouch_threshold: return "Posture: Possible Slouching"
        tilt_threshold = 0.02
        if abs(l_ear.y - r_ear.y) > tilt_threshold: return "Posture: Head Tilt Detected"
        return "Posture: Looking Good"
    except IndexError: return "Posture: Landmark index out of range"
    except Exception as e: print(f"Posture analysis error: {e}"); return "Posture: Analysis Error"


# (analyze_and_feedback function remains unchanged, it calls the now-modified speak)
def analyze_and_feedback():
    """Analyzes practice data, saves to DB, gets Gemini feedback, updates AI msg & speaks locally."""
    global current_posture_status, posture_lock, speech_practice_data, gemini_model, system_message_speech_review
    print("--- Analyzing Speech Practice ---")
    full_text = speech_practice_data.get("text", ""); start_time = speech_practice_data.get("start_time"); end_time = time.time()
    if start_time is None: print("   ❌ Error: Practice start time not recorded."); speak("Analysis aborted: start time missing."); return
    duration_seconds = max(0, end_time - start_time); words = full_text.split(); total_words = len(words); wpm = 0
    if duration_seconds > 1: wpm = int(total_words / (duration_seconds / 60.0))
    filler_count = 0
    if full_text:
        lower_text = full_text.lower()
        for filler in FILLER_WORDS:
            try: filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', lower_text))
            except re.error as re_err: print(f"   Warning: Regex error analyzing filler '{filler}': {re_err}")
    with posture_lock: final_posture = current_posture_status
    print(f"   📊 Duration: {duration_seconds:.2f}s, Words: {total_words}, WPM: {wpm}, Fillers: {filler_count}, Posture: {final_posture}")
    current_timestamp = datetime.now().isoformat()
    try: save_practice_session(current_timestamp, round(duration_seconds, 2), total_words, wpm, filler_count, final_posture, full_text)
    except Exception as db_e: print(f"   ❌ Error saving session to DB: {db_e}")
    feedback_prefix = ( f"Alright, practice session over! Results saved. "
                        f"You spoke for about {duration_seconds:.1f}s ({total_words} words, ~{wpm} WPM) "
                        f"with {filler_count} fillers. Final posture: {final_posture}. " )
    gemini_feedback = ""
    if not gemini_model: gemini_feedback = "My analysis brain isn't connected..."
    elif not full_text and total_words == 0: gemini_feedback = "You didn't seem to say anything!"
    else:
        prompt = ( f"{system_message_speech_review}\n\nUser's data:\nTranscript: \"{full_text}\"\nWPM: {wpm}\nFillers: {filler_count}\nPosture: {final_posture}\n\nProvide feedback." )
        print("\n   🧠 Requesting feedback from Gemini Speech Coach...")
        try:
            response = gemini_model.generate_content(prompt)
            if hasattr(response, 'parts') and response.parts: gemini_feedback = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'text'): gemini_feedback = response.text
            else: gemini_feedback = "My AI coach gave a response I couldn't understand."
            gemini_feedback = gemini_feedback.strip(); print(f"   🤖 Gemini Feedback Received.")
            if not gemini_feedback: gemini_feedback = "My AI coach seems to be speechless!"
        except Exception as e: print(f"   ❌ Error getting feedback from Gemini: {e}"); gemini_feedback = "Uh oh, had trouble getting detailed feedback."
    final_message_for_user = feedback_prefix + "\n" + gemini_feedback
    speak(final_message_for_user) # Speak the combined message LOCALLY


# **** MODIFIED recognize_speech FUNCTION ****
def recognize_speech(recognizer): # Accept recognizer instance 'r' as argument
    """
    Handles listening via SERVER mic using the provided recognizer instance.
    Processes commands AND general conversation for local voice interaction.
    """
    # No longer need 'r' in globals, as it's passed in
    global is_practicing_speech, speech_practice_data, main_thread_should_stop
    global mic, mic_available, gemini_model # Keep other necessary globals

    if not mic_available or not mic:
        print("🔴 SR Thread: Mic not available, thread stopping.")
        return

    try: # Adjust ambient noise at thread start using the passed recognizer
         print("🎤 SR Thread: Adjusting for ambient noise...")
         with mic as source: recognizer.adjust_for_ambient_noise(source, duration=1.5)
         print("🎤 SR Thread: Noise adjustment complete.")
    except Exception as e: print(f"⚠️ SR Thread: Mic ambient noise adjustment failed: {e}")

    print("✅ SR thread ready (Listening for commands & conversation).")
    while not main_thread_should_stop:
        if not mic_available or not mic: break # Exit if mic lost

        if is_practicing_speech:
            prompt_text = f"Listening (Practice Mode - Say '{END_PRACTICE_PHRASE}' to stop)..."
            listen_timeout = 2.0; phrase_limit = 7.0 # More continuous capture
        else:
            prompt_text = f"Listening (Say '{START_PRACTICE_PHRASE}' or chat)..."
            listen_timeout = 3.0; phrase_limit = 7.0 # Wait longer for commands/chat

        print(f"🎙️ {prompt_text}")
        recognized_text = None; audio = None
        try:
            with mic as source:
                try:
                    # Use the passed 'recognizer' instance
                    audio = recognizer.listen(source, phrase_time_limit=phrase_limit, timeout=listen_timeout)
                except sr.WaitTimeoutError: continue # Normal, just loop

            if audio:
                 print("   👂 Processing audio...")
                 try:
                     # Use the passed 'recognizer' instance
                     recognized_text = recognizer.recognize_google(audio)
                     print(f"   👂 Heard: '{recognized_text}'")
                     recognized_text_lower = recognized_text.lower()
                     add_message('user_voice', recognized_text) # Log heard input

                     # --- State-Based Logic ---
                     if is_practicing_speech: # --- PRACTICE MODE ---
                         if END_PRACTICE_PHRASE in recognized_text_lower:
                             print("   🛑 Ending practice via voice command...")
                             is_practicing_speech = False; speak("Okay, ending practice session now.") # Play TTS
                             try: analyze_and_feedback()
                             except Exception as analysis_err: print(f"❌ Error during analysis: {analysis_err}")
                             finally: speech_practice_data = {"text": "", "start_time": None}
                         else: # Collect speech during practice
                              speech_practice_data["text"] += (" " if speech_practice_data["text"] else "") + recognized_text
                              print(f"   📝 Text collected for practice.")

                     else: # --- NORMAL MODE (Commands or Chat) ---
                         if START_PRACTICE_PHRASE in recognized_text_lower:
                             print("   🚀 Starting practice via voice command...")
                             is_practicing_speech = True; speech_practice_data = {"text": "", "start_time": time.time()}
                             speak(f"Got it! Practice mode started. I'm listening.") # Play TTS

                         elif STOP_COMMAND in recognized_text_lower:
                             print("   🛑 Stop command detected via voice..."); speak("Okay, shutting down!") # Play TTS
                             main_thread_should_stop = True; break

                         # --- RE-ADDED GENERAL CHAT PATH ---
                         elif recognized_text: # If it wasn't a command, treat as chat
                            print("   💬 Treating heard audio as general chat.")
                            if gemini_model:
                                print("      🧠 Sending to Gemini...")
                                try:
                                    response = gemini_model.generate_content(recognized_text) # Send text to Gemini
                                    ai_reply = "" # Extract reply
                                    if hasattr(response, 'parts') and response.parts: ai_reply = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                                    elif hasattr(response, 'text'): ai_reply = response.text
                                    else: ai_reply = "I got a response I couldn't understand."
                                    ai_reply = ai_reply.strip()
                                    if ai_reply:
                                        print(f"      🤖 Gemini Reply: '{ai_reply[:60]}...'")
                                        speak(ai_reply) # Play the reply LOCALLY using modified speak()
                                    else:
                                        print("      ⚠️ Gemini returned empty reply.")
                                        # speak("I didn't get a response for that.") # Optional feedback
                                except Exception as e:
                                    print(f"      ❌ Gemini Error during chat: {e}")
                                    speak("Oops, I had trouble thinking about that.") # Play TTS
                            else:
                                print("      ⚠️ Gemini model not available for chat.")
                                speak("Sorry, my chat function isn't available right now.") # Play TTS
                         # ------------------------------------

                 except sr.UnknownValueError: print("   👂 Could not understand audio.")
                 except sr.RequestError as e: print(f"   ❌ SR Service Error: {e}"); time.sleep(2)

        except OSError as e: print(f"   ❌ Microphone Access Error: {e}"); mic_available = False; break
        except Exception as e: print(f"   ❌ Unexpected SR loop error: {e}"); time.sleep(1)

    print("🔴 SR thread finished.")


# --- Camera Processing & Streaming Functions ---
# (run_camera_feed and gen_camera_frames remain unchanged from your provided code)
def run_camera_feed():
    """Background thread for Flask: Captures frames, runs pose detection, updates state, stores latest frame."""
    global latest_frame, frame_lock, current_posture_status, posture_lock, main_thread_should_stop, pose
    print("📸 Starting background camera feed thread for Flask.")
    if not pose: print("❌ Camera Thread Error: MediaPipe Pose object not initialized."); return
    indices_to_try = [0, 1, -1]; cap = None
    for index in indices_to_try:
        print(f"   Trying camera index {index}..."); cap = cv2.VideoCapture(index)
        if cap and cap.isOpened(): print(f"   ✅ Camera index {index} opened."); break
        else:
            if cap: cap.release(); print(f"   ⚠️ Camera index {index} failed."); cap = None; time.sleep(0.2)
    if not cap: print("❌❌ CAMERA THREAD ERROR: Failed to open camera."); speak("Error: Could not access camera."); return

    frame_count = 0; last_error_print_time = 0; error_interval = 5
    while not main_thread_should_stop:
        ret, frame = cap.read()
        if not ret:
             current_time = time.time()
             if current_time - last_error_print_time > error_interval: print(f"   ⚠️ Cam Warning: Failed frame {frame_count}."); last_error_print_time = current_time
             time.sleep(0.1); continue
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False; results = pose.process(frame_rgb)
            frame_rgb.flags.writeable = True; frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            posture_text = "Posture: Detecting..."
            if results and results.pose_landmarks:
                posture_text = analyze_posture(results.pose_landmarks)
                mp_drawing.draw_landmarks(frame_bgr, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(245, 66, 230), thickness=2, circle_radius=2) )
            with posture_lock: current_posture_status = posture_text
            cv2.putText(frame_bgr, posture_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            if is_practicing_speech: cv2.putText(frame_bgr, "REC ●", (frame_bgr.shape[1] - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]; ret_encode, buffer = cv2.imencode('.jpg', frame_bgr, encode_param)
            if not ret_encode:
                current_time = time.time()
                if current_time - last_error_print_time > error_interval: print("   ⚠️ Failed to encode frame."); last_error_print_time = current_time
                continue
            frame_bytes = buffer.tobytes()
            with frame_lock: latest_frame = frame_bytes
        except Exception as e:
            current_time = time.time()
            if current_time - last_error_print_time > error_interval: print(f"❌ Error processing frame: {e}"); last_error_print_time = current_time
            time.sleep(0.1)
        frame_count += 1
        # time.sleep(0.01) # Optional CPU throttle
    if cap: cap.release()
    print("📸 Camera thread terminating.")
    if pose:
       try: pose.close(); print("   ✅ MediaPipe Pose resources released.")
       except Exception as e: print(f"   ❌ Error closing MediaPipe Pose: {e}")

def gen_camera_frames():
    """Generator function used by Flask to stream MJPEG frames."""
    global latest_frame, frame_lock, main_thread_should_stop
    print("   STREAM: Video stream generator started.")
    frame_count = 0; last_yield_time = time.time()
    while not main_thread_should_stop:
        frame_to_send = None
        with frame_lock:
            if latest_frame: frame_to_send = latest_frame[:]
        if frame_to_send:
            try:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_to_send + b'\r\n')
                frame_count += 1; now = time.time(); elapsed = now - last_yield_time
                target_delay = 1.0 / 30.0; sleep_time = max(0, target_delay - elapsed)
                time.sleep(sleep_time); last_yield_time = time.time()
            except GeneratorExit: print("   STREAM: Client disconnected."); break
            except Exception as e: print(f"   STREAM: Error yielding frame: {e}"); break
        else: time.sleep(0.05) # Wait if no frame ready
    print(f"   STREAM: Video stream generator stopped after {frame_count} frames.")


# --- Main Execution (for Standalone Testing) ---
# (This block remains unchanged and should work correctly with the modified functions)
if __name__ == "__main__":
    print("\n--- Starting AI Study Bot (Standalone Mode) ---")
    print(f"Speak '{START_PRACTICE_PHRASE}' or '{END_PRACTICE_PHRASE}'. Speak '{STOP_COMMAND}' or press Ctrl+C to exit.")
    init_database()
    # Use the modified speak() which includes local playback
    if not mic_available: speak("Warning: Microphone is not working...")
    if not pose: speak("Warning: MediaPipe Pose failed...")

    speech_thread = None
    if mic_available:
        print("   Creating speech recognition thread (standalone)...")
        # Pass the global 'r' instance when running standalone
        speech_thread = threading.Thread(target=recognize_speech, args=(r,), daemon=True);
        speech_thread.start()
        print("   ✅ Speech recognition thread started.")
    else: print("   🔴 Speech recognition thread NOT started (no microphone).")

    camera_thread = None
    if pose:
        print("   Creating background camera processing thread (standalone)...")
        camera_thread = threading.Thread(target=run_camera_feed, daemon=True); camera_thread.start()
        print("   ✅ Background camera thread started.")
    else: print("   🔴 Background camera thread NOT started (MediaPipe Pose failed).")

    print("\n--- Bot is running (Standalone). Press Ctrl+C in terminal to stop. ---")
    try:
        while not main_thread_should_stop:
            if camera_thread and not camera_thread.is_alive() and pose: print("⚠️ BG camera thread died!"); main_thread_should_stop = True
            if speech_thread and not speech_thread.is_alive() and mic_available: print("⚠️ Speech thread died!"); main_thread_should_stop = True
            time.sleep(1)
    except KeyboardInterrupt: print("\nCtrl+C detected. Stopping threads..."); main_thread_should_stop = True

    print("\n--- Shutting Down Standalone Mode ---")
    if camera_thread and camera_thread.is_alive(): print("   Waiting for camera thread..."); camera_thread.join(timeout=2.0)
    if speech_thread and speech_thread.is_alive(): print("   Waiting for speech thread..."); speech_thread.join(timeout=2.0)
    print("👋 Bot shut down gracefully.")
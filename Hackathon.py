import speech_recognition as sr
import google.generativeai as genai
import cv2
import time
import mediapipe as mp
from elevenlabs.client import ElevenLabs
from elevenlabs import play
import os
import sys
import numpy as np
import re
import threading
import sqlite3 # <-- Import SQLite
from datetime import datetime # <-- Import datetime for timestamps

# --- Configuration ---
# IMPORTANT: Set these as environment variables for security!
GOOGLE_API_KEY_FROM_USER = "AIzaSyAlRoqW94GA64lUjEeciXUROSzE0E8EGt0" # User's key
ELEVENLABS_API_KEY_FROM_USER = "sk_64ab860b0379f08849bd3a277f9728c5522969427273fac9" # User's key
# Generic placeholders for the checks
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
DB_FILE = "study_buddy_sessions.db" # <-- Database file name

# --- Shared State & Lock ---
is_practicing_speech = False
current_posture_status = "Posture: Initializing..."
posture_lock = threading.Lock()
speech_practice_data = {"text": "", "start_time": None}
main_thread_should_stop = False # Flag to signal exit

# --- Database Functions ---

def init_database():
    """Initializes the SQLite database and creates the table if it doesn't exist."""
    try:
        # Context manager handles connect/close and commit/rollback
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
            """)
            print(f"✅ Database '{DB_FILE}' initialized successfully.")
    except sqlite3.Error as e:
        print(f"❌❌ DATABASE ERROR during initialization: {e}")
        # Depending on severity, you might want to exit or disable DB features
        # sys.exit(f"Critical database error: {e}") # Example exit

def save_practice_session(timestamp, duration, words, wpm, fillers, posture, transcript):
    """Saves the results of a practice session to the database."""
    sql = """
        INSERT INTO speech_practice_sessions
        (timestamp, duration_seconds, total_words, wpm, filler_count, final_posture, transcript)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    data_tuple = (timestamp, duration, words, wpm, fillers, posture, transcript)
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, data_tuple)
            print(f"✅ Practice session data saved to database (ID: {cursor.lastrowid}).")
    except sqlite3.Error as e:
        print(f"❌❌ DATABASE ERROR during save: {e}")
        # Log the error, maybe notify user, but likely continue running

# --- Setup Clients & Services ---
elevenlabs_client = None
gemini_model = None
mic = None
mic_available = False
pose = None

print("--- Initializing Services ---")
# Try ElevenLabs (Keep corrected logic from previous step)
if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == ELEVENLABS_KEY_PLACEHOLDER:
    print("⚠️ ElevenLabs API Key not found or is placeholder. TTS will be disabled.")
else:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("✅ ElevenLabs client configured.")
    except Exception as e:
        print(f"❌ ElevenLabs Initialization Error: {e}")
        elevenlabs_client = None

# Try Google Gemini (Keep corrected logic from previous step)
if not GOOGLE_API_KEY or GOOGLE_API_KEY == GOOGLE_KEY_PLACEHOLDER:
     print("⚠️ Google API Key not found or is placeholder. Gemini chat will be disabled.")
else:
    try:
        print(f"### DEBUG ###: Attempting Gemini config with key ending ...{GOOGLE_API_KEY[-4:]}")
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_model = genai.GenerativeModel(
            'gemini-1.5-flash',
            system_instruction="You are a funny, supportive AI study buddy named 'Buddy'. Keep responses concise and friendly."
        )
        print("✅ Google Gemini configured.")
    except Exception as e:
        print(f"❌ Gemini Initialization Error: {e}")
        gemini_model = None

# System prompt specifically for speech review
system_message_speech_review = (
    "You are an expert speech coach AI..." # (Same as before)
)

# Speech Recognition Setup
r = sr.Recognizer()
# Microphone Setup
try:
    mic = sr.Microphone()
    with mic as source: print(f"🎤 Found microphone: {source.device_index}")
    mic_available = True
    print("✅ Microphone available.")
    print("🎤 Adjusting for ambient noise...")
    with mic as source: r.adjust_for_ambient_noise(source, duration=1.0)
    print("🎤 Noise adjustment complete.")
except Exception as e:
    print(f"⚠️ Microphone not available or failed initial adjustment: {e}")
    mic_available = False

# MediaPipe Setup
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
try:
    pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    print("✅ MediaPipe Pose configured.")
except Exception as e:
     print(f"❌ MediaPipe Pose Initialization Error: {e}")
     pose = None

# --- Helper Functions ---

def speak(text):
    """Uses ElevenLabs to speak the given text with added debugging."""
    # (Keep the debugged version from previous step)
    print("### DEBUG ###: speak() function called.")
    if not elevenlabs_client: print("   [TTS Disabled] elevenlabs_client is None..."); print(f"   [TTS Disabled] Would say: {text}"); return
    if not text or not text.strip(): print("   ⚠️ TTS Warning: Attempted to speak empty text..."); return
    print(f"   🔊 Attempting to speak: '{text[:60]}...'")
    try:
        print("   [1] Calling elevenlabs_client.generate()...")
        audio_stream = elevenlabs_client.generate(text=text, voice=VOICE_NAME, model='eleven_multilingual_v2', stream=True)
        print("   [2] Returned from generate(). Checking stream...")
        if not audio_stream: print("   ❌ ElevenLabs generate() returned an empty stream object..."); return
        print("   [3] Attempting to call play(audio_stream)...")
        try:
            play(audio_stream)
            print("   [4] Returned from play(). Playback likely started.")
        except Exception as play_error: print(f"   ❌❌ ERROR DURING play(): {play_error}"); print(f"   ❌❌ This often means 'ffplay' or 'mpv' is not installed or not in your system PATH.")
    except Exception as generate_error:
        print(f"   ❌❌ ERROR DURING elevenlabs_client.generate(): {generate_error}")
        if "API key" in str(generate_error).lower(): print("   ❌ Check if your ElevenLabs API key is correct and active.")
        elif "quota" in str(generate_error).lower(): print("   ❌ You might have exceeded your ElevenLabs quota.")
        elif "voice_id" in str(generate_error).lower(): print(f"   ❌ Check if the voice name '{VOICE_NAME}' is valid for your account/model.")

def analyze_posture(landmarks):
    """Analyzes landmarks for simple posture cues."""
    # (Definition is the same as before)
    if not landmarks: return "Posture: No landmarks detected"
    try:
        lm = landmarks.landmark
        nose = lm[mp_pose.PoseLandmark.NOSE.value]
        l_shoulder = lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        r_shoulder = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        l_ear = lm[mp_pose.PoseLandmark.LEFT_EAR.value]
        r_ear = lm[mp_pose.PoseLandmark.RIGHT_EAR.value]
        if not all(pt.visibility > 0.4 for pt in [nose, l_shoulder, r_shoulder, l_ear, r_ear]): return "Posture: Key points not clear"
        shoulder_y_avg = (l_shoulder.y + r_shoulder.y) / 2
        slouch_threshold = 0.08
        if nose.y > shoulder_y_avg + slouch_threshold: return "Posture: Possible Slouching"
        tilt_threshold = 0.05
        if abs(l_ear.y - r_ear.y) > tilt_threshold: return "Posture: Head Tilt Detected"
        return "Posture: Looking Good"
    except IndexError: return "Posture: Some points missing"
    except Exception: return "Posture: Analysis Error"

def analyze_and_feedback():
    """Analyzes collected speech data, gets posture, asks Gemini for feedback, AND SAVES TO DB."""
    global current_posture_status, posture_lock, speech_practice_data, gemini_model, system_message_speech_review

    print("--- Analyzing Speech Practice ---")
    full_text = speech_practice_data["text"]
    start_time = speech_practice_data["start_time"]
    end_time = time.time()

    if start_time is None:
        print("   ❌ Error: Practice start time not recorded.")
        speak("Something went wrong, I didn't catch when you started. Sorry!")
        return

    duration_seconds = end_time - start_time

    # --- Calculations ---
    words = full_text.split()
    total_words = len(words)
    wpm = 0
    if duration_seconds > 1:
        wpm = int(total_words / (duration_seconds / 60.0))

    filler_count = 0
    lower_text = full_text.lower()
    for filler in FILLER_WORDS:
        filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', lower_text))

    # Get final posture status safely
    with posture_lock:
        final_posture = current_posture_status

    # --- Print Analysis Results ---
    print(f"   📊 Duration: {duration_seconds:.2f} seconds")
    print(f"   📊 Total Words: {total_words}")
    print(f"   📊 WPM: {wpm}")
    print(f"   📊 Filler Words: {filler_count}")
    print(f"   📊 Final Posture: {final_posture}")

    # --- Save results to Database BEFORE getting Gemini feedback ---
    current_timestamp = datetime.now().isoformat() # Get timestamp
    save_practice_session(
        timestamp=current_timestamp,
        duration=round(duration_seconds, 2), # Use rounded duration
        words=total_words,
        wpm=wpm,
        fillers=filler_count,
        posture=final_posture,
        transcript=full_text # Save the transcript too
    )
    # -------------------------------------------------------------

    # --- Get Gemini Feedback (existing logic) ---
    if not gemini_model:
        feedback = "Looks like my analysis brain (Gemini) isn't connected! But here's what I got: "
        feedback += f"You spoke for about {duration_seconds:.1f} seconds, said {total_words} words, averaging {wpm} words per minute. "
        feedback += f"I counted {filler_count} filler words. Your posture seemed to be '{final_posture}' towards the end. Results saved. Keep practicing!"
        speak(feedback)
        return

    prompt = f"{system_message_speech_review}\n\nUser's practice speech data:\n- Transcript: \"{full_text}\"\n- Calculated WPM: {wpm}\n- Filler Word Count: {filler_count} (Common fillers: {', '.join(FILLER_WORDS)})\n- Posture observed near the end: {final_posture}\n\nProvide supportive feedback and actionable tips based ONLY on this data."

    print("\n   🧠 Requesting feedback from Gemini Speech Coach...")
    try:
        response = gemini_model.generate_content(prompt)
        gemini_feedback = ""
        if hasattr(response, 'text') and response.text: gemini_feedback = response.text.strip()
        elif isinstance(response, str): gemini_feedback = response.strip()

        if gemini_feedback:
             print(f"   🤖 Gemini Feedback:\n{gemini_feedback}\n")
             summary_feedback = f"Alright, practice session over! Results saved. Haha. Here's the breakdown: \n" # Mention saving
             summary_feedback += f"You spoke for about {duration_seconds:.1f} seconds at roughly {wpm} words per minute. \n"
             summary_feedback += f"I caught {filler_count} filler words. \n"
             summary_feedback += f"Your posture check showed: {final_posture}. \n\n"
             summary_feedback += f"Here's some coaching feedback from my AI brain: \n{gemini_feedback}"
             speak(summary_feedback)
        else:
            print("   ⚠️ Gemini returned no usable feedback text.")
            fallback_feedback = "Hmm, my AI coach seems to be speechless! Lol. Results saved. Based on my numbers: " # Mention saving
            fallback_feedback += f"You spoke for {duration_seconds:.1f} seconds, {total_words} words, at {wpm} WPM, with {filler_count} fillers. Posture was {final_posture}."
            speak(fallback_feedback)

    except Exception as e:
        print(f"   ❌ Error getting feedback from Gemini: {e}")
        speak("Uh oh, had a little trouble getting the detailed feedback, but your results were saved. You finished the practice!") # Mention saving


# --- Speech Recognition Thread Function ---
# (recognize_speech function definition remains the same)
def recognize_speech():
    """Handles listening for commands and practice speech in a background thread."""
    global is_practicing_speech, speech_practice_data, main_thread_should_stop
    if not mic_available: print("🔴 SR Thread: Mic not available..."); return
    print("✅ SR thread ready.");
    while not main_thread_should_stop:
        print("-" * 10)
        if is_practicing_speech: prompt = f"Listening (Practice Mode)... Say '{END_PRACTICE_PHRASE}' to stop."; phrase_timeout=3.0; phrase_limit=7
        else: prompt = f"Listening (e.g., '{START_PRACTICE_PHRASE}', '{STOP_COMMAND}', chat)..."; phrase_timeout=3.0; phrase_limit=5
        print(f"🎙️ {prompt}"); recognized_text = None
        try:
            with mic as source: audio = r.listen(source, phrase_time_limit=phrase_limit, timeout=phrase_timeout)
            print("   👂 Processing..."); recognized_text = r.recognize_google(audio); print(f"   👂 Heard: '{recognized_text}'"); recognized_text_lower = recognized_text.lower()
            if is_practicing_speech: # Practice Mode
                print("### DEBUG ###: In Practice Mode Branch")
                if END_PRACTICE_PHRASE in recognized_text_lower: print("   🛑 Ending practice..."); is_practicing_speech = False; speak("Okay, ending practice..."); analyze_and_feedback(); speech_practice_data = {"text": "", "start_time": None}
                else: speech_practice_data["text"] += (" " if speech_practice_data["text"] else "") + recognized_text; print(f"   📝 Text collected")
            else: # Normal Mode
                print("### DEBUG ###: In Normal Mode Branch")
                if START_PRACTICE_PHRASE in recognized_text_lower: print("### DEBUG ###: Matched START..."); print("   🚀 Starting practice..."); is_practicing_speech = True; speech_practice_data = {"text": "", "start_time": time.time()}; speak(f"Got it! Practice mode ON...")
                elif STOP_COMMAND in recognized_text_lower: print("### DEBUG ###: Matched STOP..."); print("   🛑 Stop command detected..."); speak("Okay, shutting down!"); main_thread_should_stop = True; break
                else: # General Chat Path
                    print("### DEBUG ###: Entering general chat path.")
                    if gemini_model:
                        print("### DEBUG ###: gemini_model object exists.");
                        try:
                            print("   🧠 Thinking..."); response = gemini_model.generate_content(recognized_text); print(f"### DEBUG ###: Gemini raw type: {type(response)}"); reply = ""
                            if hasattr(response, 'text') and response.text: reply = response.text.strip()
                            elif isinstance(response, str): reply = response.strip()
                            else: print(f"   ⚠️ Unexpected Gemini structure: {response}"); reply = "Confusing answer..."
                            if reply: print(f"### DEBUG ###: Extracted reply: '{reply[:60]}...'"); print(f"   🤖 Buddy says: {reply}"); speak(reply)
                            else: print("### DEBUG ###: Reply empty."); speak("Didn't come up with anything...")
                        except Exception as e: print(f"   ❌ Gemini Error: {e}"); speak("Oops, snag thinking...")
                    else: print("### DEBUG ###: gemini_model is None."); speak("Chat function isn't available.")
        except sr.WaitTimeoutError: print("   👂 No speech (timeout).")
        except sr.UnknownValueError: print("   👂 Couldn't understand.")
        except sr.RequestError as e: print(f"   ❌ SR service error: {e}"); time.sleep(2)
        except Exception as e: print(f"   ❌ Unexpected SR loop error: {e}"); time.sleep(1)
    print("🔴 SR thread finished.")


# --- Camera Display Function (Runs in Main Thread) ---
# (show_camera function definition remains the same)
def show_camera():
    """Handles camera feed, pose detection, and display."""
    global current_posture_status, posture_lock, main_thread_should_stop
    print("### DEBUG ###: Attempting show_camera.");
    if not pose: print("🔴 Camera Thread: No Pose object."); main_thread_should_stop = True; return
    indices_to_try = [0, 1, -1]; cap = None; opened_index = None
    for index in indices_to_try:
        print(f"### DEBUG ###: Trying Cam Index {index}."); cap = cv2.VideoCapture(index)
        if cap is not None and cap.isOpened(): print(f"✅ Cam Index {index} OK."); opened_index = index; break
        else: print(f"⚠️ Cam Index {index} failed."); cap.release(); cap = None; time.sleep(0.5)
    if cap is None: print("🔴🔴🔴 CAMERA FAILED TO OPEN 🔴🔴🔴"); main_thread_should_stop = True; return # Plus checklist
    print(f"--- 🎥 Cam Feed Starting (Index: {opened_index}) ---"); window_name = "AI Study Buddy Cam (Press 'q' to quit)"; cv2.namedWindow(window_name)
    print("### DEBUG ###: Entering camera loop."); loop_count = 0
    while not main_thread_should_stop:
        ret, frame = cap.read()
        if not ret: print(f"   ⚠️ Cam Warning: Failed frame {loop_count}."); time.sleep(0.1); continue
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); frame_rgb.flags.writeable = False; results = pose.process(frame_rgb); frame_rgb.flags.writeable = True; frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            posture_status_analysis = "Posture: No user detected"
            if results.pose_landmarks: posture_status_analysis = analyze_posture(results.pose_landmarks); mp_drawing.draw_landmarks(frame_bgr, results.pose_landmarks, mp_pose.POSE_CONNECTIONS, mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2), mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))
            with posture_lock: current_posture_status = posture_status_analysis
            cv2.putText(frame_bgr, posture_status_analysis, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            if is_practicing_speech: cv2.putText(frame_bgr, "REC ●", (frame_bgr.shape[1] - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.imshow(window_name, frame_bgr)
        except Exception as e: print(f"   ❌ Cam ERROR processing frame: {e}")
        key = cv2.waitKey(5) & 0xFF
        if key == ord('q'): print("   🛑 'q' pressed."); main_thread_should_stop = True; break
        loop_count += 1
    print(f"### DEBUG ###: Exited camera loop ({loop_count} iter)."); print("--- 🎥 Releasing Cam ---"); cap.release(); print("### DEBUG ###: cap.release() done.")
    cv2.destroyAllWindows(); print("### DEBUG ###: destroyAllWindows() done."); time.sleep(0.1); cv2.waitKey(1); print("### DEBUG ###: Extra waitKey done.")


# --- Main Execution ---
if __name__ == "__main__":
    print("\n--- Starting AI Study Bot ---")
    print(f"Say '{START_PRACTICE_PHRASE}' to start recording.")
    print(f"Say '{END_PRACTICE_PHRASE}' to stop recording and get feedback.")
    print(f"Say '{STOP_COMMAND}' or press 'q' in the camera window to exit.")

    # --- Initialize Database ---  <-- ADD THIS CALL
    init_database()
    # ---------------------------

    if not mic_available: speak("Warning: Microphone is not working...")
    if not pose: speak("Warning: MediaPipe Pose failed...")

    # --- Start Speech Recognition Thread ---
    speech_thread = None
    if mic_available:
        print("### DEBUG ###: Creating speech recognition thread.")
        speech_thread = threading.Thread(target=recognize_speech, daemon=True)
        speech_thread.start()
        print("✅ Speech recognition thread started.")
    else:
        print("🔴 Speech recognition thread NOT started (no microphone).")


    # --- Run Camera Display in Main Thread ---
    print("### DEBUG ###: Checking if MediaPipe Pose object exists before calling show_camera.")
    if pose:
        print("### DEBUG ###: MediaPipe Pose object exists. Calling show_camera() in main thread.")
        show_camera() # Run camera in main thread
        print("### DEBUG ###: Returned from show_camera() call.")
    else:
        print("🔴 Camera display skipped (MediaPipe Pose failed).")
        if mic_available and speech_thread:
             print("ℹ️ Running in audio-only mode. Say 'stop' to exit.")
             while not main_thread_should_stop and speech_thread and speech_thread.is_alive():
                  try: time.sleep(0.5)
                  except KeyboardInterrupt: print("\nCtrl+C detected. Stopping."); main_thread_should_stop = True
             if speech_thread: speech_thread.join(timeout=1.0)
        else:
             speak("Both microphone and camera components failed. Exiting.")
             if 'sys' not in locals(): import sys # Make sure sys is imported
             sys.exit(1)


    # --- Final Cleanup ---
    print("\n--- Shutting Down ---")
    if pose:
        try: pose.close(); print("✅ MediaPipe Pose resources released.")
        except Exception as e: print(f"❌ Error closing MediaPipe Pose: {e}")
    if speech_thread and speech_thread.is_alive():
         print("### DEBUG ###: Waiting briefly for speech thread...")
         speech_thread.join(timeout=1.0)
         if speech_thread.is_alive(): print("⚠️ Speech thread did not stop cleanly.")
    time.sleep(0.5); print("👋 Bot shut down gracefully.")
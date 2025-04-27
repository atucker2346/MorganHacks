# Hackathon.py
# Main backend logic for the AI Study Buddy

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
import sqlite3
from datetime import datetime
import logging # Added for better debugging

# --- Basic Logging Setup ---
# Logs messages to the console. Adjust level as needed (DEBUG, INFO, WARNING, ERROR)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

# --- Attempt to import API Keys ---
try:
    import api
    GOOGLE_API_KEY_FROM_USER = api.GOOGLE_API_KEY_FROM_USER
    ELEVENLABS_API_KEY_FROM_USER = api.ELEVENLABS_API_KEY_FROM_USER
except ImportError:
    logging.warning("api.py not found. API keys must be set as environment variables.")
    GOOGLE_API_KEY_FROM_USER = None
    ELEVENLABS_API_KEY_FROM_USER = None
except AttributeError:
     logging.warning("API keys not found within api.py. Keys must be set as environment variables or defined in api.py.")
     # Attempt to get keys anyway in case only some are missing
     GOOGLE_API_KEY_FROM_USER = getattr(api, 'GOOGLE_API_KEY_FROM_USER', None)
     ELEVENLABS_API_KEY_FROM_USER = getattr(api, 'ELEVENLABS_API_KEY_FROM_USER', None)


# --- Message History (For Chat - if used) ---
message_history = []

def add_message(sender, text):
    """Adds a message to the chat history."""
    global message_history
    message_history.append({'sender': sender, 'text': text, 'timestamp': datetime.now().isoformat()})
    # Keep history length manageable
    if len(message_history) > 50:
        message_history.pop(0)
    logging.debug(f"Message added: {sender} - {text[:30]}...")

def get_message_history():
    """Returns the current chat history."""
    return message_history

# --- Get Latest Transcript ---
def get_latest_transcript():
    """Gets the latest transcript text directly from the global variable."""
    global speech_practice_data # Access the global dict
    return speech_practice_data.get("text", "")

# --- Configuration ---
# Use environment variables first, then api.py, then None
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", GOOGLE_API_KEY_FROM_USER)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY_FROM_USER)

# Generic placeholders for checks - used to see if a real key was provided
GOOGLE_KEY_PLACEHOLDER = "YOUR_GOOGLE_API_KEY_HERE" # If user left placeholder in env/api.py
ELEVENLABS_KEY_PLACEHOLDER = "YOUR_ELEVENLABS_API_KEY_HERE" # If user left placeholder in env/api.py

VOICE_NAME = "Elli" # Default ElevenLabs voice

# --- Constants ---
START_PRACTICE_PHRASE = "start practice speech"
END_PRACTICE_PHRASE = "end speech"
STOP_COMMAND = "stop"
FILLER_WORDS = ["um", "uh", "ah", "er", "like", "so", "you know", "actually", "basically", "well", "right"]
DB_FILE = "study_buddy_sessions.db"

# --- Shared State & Locks ---
is_practicing_speech = False
current_posture_status = "Posture: Initializing..."
speech_practice_data = {"text": "", "start_time": None}
main_thread_should_stop = False # Flag to signal exit for background threads

# Thread locks for safe access to shared resources
posture_lock = threading.Lock()
frame_lock = threading.Lock() # For latest_frame used by run_camera_feed

# Global variable to hold the latest camera frame for potential non-streaming use
latest_frame = None

# --- Database Functions ---
def init_database():
    """Initializes the SQLite database and creates tables if they don't exist."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Speech practice table
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
            # Notecards table (ensure it's also created here for consistency)
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
            logging.info(f"✅ Database '{DB_FILE}' initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"❌❌ DATABASE ERROR during initialization: {e}", exc_info=True)

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
            conn.commit()
            logging.info(f"✅ Practice session data saved to database (ID: {cursor.lastrowid}).")
    except sqlite3.Error as e:
        logging.error(f"❌❌ DATABASE ERROR during save: {e}", exc_info=True)


# --- Setup Clients & Services ---
# These run when the module is imported
logging.info("--- Initializing Services ---")

# Define globals before try blocks
elevenlabs_client = None
gemini_model = None
mic = None
mic_available = False
pose = None # MediaPipe Pose object
mp_pose = None # MediaPipe pose solution
mp_drawing = None # MediaPipe drawing utilities
r = None # Speech recognizer


# Try ElevenLabs TTS
if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == ELEVENLABS_KEY_PLACEHOLDER:
    logging.warning("⚠️ ElevenLabs API Key not found or is placeholder. TTS will be disabled.")
else:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        logging.info("✅ ElevenLabs client configured.")
    except Exception as e:
        logging.error(f"❌ ElevenLabs Initialization Error: {e}", exc_info=True)
        elevenlabs_client = None

# Try Google Gemini LLM
if not GOOGLE_API_KEY or GOOGLE_API_KEY == GOOGLE_KEY_PLACEHOLDER:
     logging.warning("⚠️ Google API Key not found or is placeholder. Gemini chat will be disabled.")
else:
    try:
        logging.info(f"Attempting Gemini config with key ending ...{GOOGLE_API_KEY[-4:] if GOOGLE_API_KEY else 'N/A'}")
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_model = genai.GenerativeModel(
            'gemini-1.5-flash', # Corrected model name
            system_instruction="You are a funny, supportive AI study buddy named 'Buddy'. Keep responses concise and friendly."
            # Add safety_settings if needed: safety_settings=...
        )
        # You could optionally make a small test call here to verify connection/key
        # gemini_model.generate_content("Test")
        logging.info("✅ Google Gemini configured.")
    except Exception as e:
        logging.error(f"❌ Gemini Initialization Error: {e}", exc_info=True)
        gemini_model = None

# System prompt specifically for speech review
system_message_speech_review = (
    "You are an expert speech coach AI. Analyze the provided transcript, words per minute (WPM), "
    "filler word count, and final posture observation. Provide supportive, concise, and actionable feedback. "
    "Focus on clarity, pacing (based on WPM, typical range 120-160), filler word reduction, and posture improvement. "
    "Keep the tone friendly and encouraging, like a helpful study buddy coach."
)

# Speech Recognition Setup
try:
    r = sr.Recognizer()
    logging.info("Attempting to initialize microphone...")
    mic = sr.Microphone() # Uses default system microphone
    with mic as source:
        logging.info(f"🎤 Found microphone: Index {source.device_index} (Default)")
    mic_available = True
    logging.info("✅ Microphone available.")
    logging.info("🎤 Adjusting for ambient noise (1 second)... Please be quiet.")
    # Perform ambient noise adjustment
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1.0)
    logging.info("🎤 Noise adjustment complete. Energy threshold set to: %s", r.energy_threshold)
except ImportError as e:
    logging.error(f"❌ Microphone Error: {e}. Is PyAudio installed correctly?", exc_info=True)
    mic_available = False
except OSError as e:
     logging.error(f"❌ Microphone OS Error: {e}. No default input device found or access denied?", exc_info=True)
     mic_available = False
except Exception as e:
    logging.error(f"⚠️ Microphone not available or failed initial adjustment: {e}", exc_info=True)
    mic_available = False

# MediaPipe Setup
try:
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    logging.info("Initializing MediaPipe Pose...")
    # Initialize pose globally ONCE
    pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    logging.info("✅ MediaPipe Pose configured.")
except Exception as e:
    logging.error(f"❌ MediaPipe Pose Initialization Error: {e}", exc_info=True)
    pose = None # Ensure pose is None if setup fails

# --- Helper Functions ---

def speak(text):
    """Uses ElevenLabs to speak the given text and logs it."""
    global last_ai_message # Reference global state if needed elsewhere
    logging.debug("speak() function called.")
    add_message('computer', text) # Log message to history
    last_ai_message = text # Update last spoken message state

    if not elevenlabs_client:
        logging.warning(" [TTS Disabled] elevenlabs_client is None.")
        logging.info(f" [TTS Disabled] Would say: {text}")
        return
    if not text or not text.strip():
        logging.warning(" ⚠️ TTS Warning: Attempted to speak empty text.")
        return

    logging.info(f" 🔊 Attempting to speak via ElevenLabs: '{text[:60]}...'")
    try:
        logging.debug("  [1] Calling elevenlabs_client.generate()...")
        audio_stream = elevenlabs_client.generate(
            text=text,
            voice=VOICE_NAME,
            model='eleven_multilingual_v2', # Or your preferred model
            stream=True
        )
        logging.debug("  [2] Returned from generate(). Checking stream...")
        if not audio_stream:
            logging.error("  ❌ ElevenLabs generate() returned an empty stream object.")
            return

        logging.debug("  [3] Attempting to call play(audio_stream)...")
        # This blocks until playback is complete or error occurs
        play(audio_stream)
        logging.debug("  [4] Returned from play(). Playback finished or failed.")

    except Exception as play_error:
        # This often means ffplay or mpv is not installed or not in the system PATH
        logging.error(f"  ❌❌ ERROR DURING play(): {play_error}", exc_info=True)
        logging.error("  ❌❌ This often means 'ffplay' or 'mpv' is not installed or not in your system PATH.")
    # Catch generate errors separately if needed
    # except Exception as generate_error:
    #     logging.error(f"  ❌❌ ERROR DURING elevenlabs_client.generate(): {generate_error}", exc_info=True)
    #     # Add specific error checks (API key, quota, voice ID) if desired


def analyze_posture(landmarks):
    """Analyzes landmarks for simple posture cues. Requires mp_pose to be initialized."""
    if not landmarks:
        return "Posture: No landmarks detected"
    if not mp_pose: # Check if mediapipe pose solution is loaded
        logging.warning("analyze_posture called but mp_pose is not initialized.")
        return "Posture: Analysis unavailable"

    try:
        lm = landmarks.landmark
        # Get required landmarks using the global mp_pose for enum values
        nose = lm[mp_pose.PoseLandmark.NOSE.value]
        l_shoulder = lm[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        r_shoulder = lm[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        l_ear = lm[mp_pose.PoseLandmark.LEFT_EAR.value]
        r_ear = lm[mp_pose.PoseLandmark.RIGHT_EAR.value]

        # Check visibility
        if not all(pt.visibility > 0.4 for pt in [nose, l_shoulder, r_shoulder, l_ear, r_ear]):
            return "Posture: Key points not clear"

        # Simple slouch detection (nose significantly lower than shoulder average)
        shoulder_y_avg = (l_shoulder.y + r_shoulder.y) / 2.0 # Corrected average calculation
        slouch_threshold = 0.08 # Adjust threshold as needed
        if nose.y > shoulder_y_avg + slouch_threshold:
            return "Posture: Possible Slouching"

        # Simple head tilt detection (ears Y-coordinate difference)
        tilt_threshold = 0.05 # Adjust threshold as needed
        if abs(l_ear.y - r_ear.y) > tilt_threshold:
            return "Posture: Head Tilt Detected"

        return "Posture: Looking Good"
    except IndexError:
        logging.warning("Posture analysis failed: Some points missing from landmarks.")
        return "Posture: Some points missing"
    except Exception as e:
        logging.error(f"Posture analysis error: {e}", exc_info=True)
        return "Posture: Analysis Error"


def analyze_and_feedback():
    """Analyzes collected speech data, gets posture, asks Gemini for feedback, AND SAVES TO DB."""
    global current_posture_status, speech_practice_data, gemini_model

    logging.info("--- Analyzing Speech Practice ---")
    # Make a copy to avoid race conditions if speech thread modifies it immediately after
    practice_data_copy = speech_practice_data.copy()
    full_text = practice_data_copy.get("text", "")
    start_time = practice_data_copy.get("start_time", None)
    end_time = time.time() # Use current time as end time

    if start_time is None or not full_text:
        logging.error(" ❌ Error: Practice start time not recorded or no text collected.")
        speak("Something went wrong, I didn't catch when you started or didn't hear anything. Sorry!")
        return

    duration_seconds = end_time - start_time
    if duration_seconds <= 0: duration_seconds = 0.1 # Avoid division by zero

    # --- Calculations ---
    words = full_text.split()
    total_words = len(words)
    wpm = int(total_words / (duration_seconds / 60.0))

    filler_count = 0
    lower_text = full_text.lower()
    for filler in FILLER_WORDS:
        # Use regex for whole word matching
        try:
            filler_count += len(re.findall(r'\b' + re.escape(filler) + r'\b', lower_text))
        except re.error as re_err:
             logging.warning(f"Regex error checking filler word '{filler}': {re_err}")


    # Get final posture status safely using the lock
    with posture_lock:
        final_posture = current_posture_status

    # --- Log Analysis Results ---
    logging.info(f"  📊 Duration: {duration_seconds:.2f} seconds")
    logging.info(f"  📊 Total Words: {total_words}")
    logging.info(f"  📊 WPM: {wpm}")
    logging.info(f"  📊 Filler Words: {filler_count}")
    logging.info(f"  📊 Final Posture: {final_posture}")

    # --- Save results to Database BEFORE getting Gemini feedback ---
    current_timestamp = datetime.now().isoformat()
    save_practice_session(
        timestamp=current_timestamp,
        duration=round(duration_seconds, 2),
        words=total_words,
        wpm=wpm,
        fillers=filler_count,
        posture=final_posture,
        transcript=full_text
    )

    # --- Get Gemini Feedback ---
    if not gemini_model:
        logging.warning("Gemini model not available for feedback.")
        feedback = "Looks like my analysis brain (Gemini) isn't connected! But here's what I got: "
        feedback += f"You spoke for about {duration_seconds:.1f} seconds, said {total_words} words, averaging {wpm} words per minute. "
        feedback += f"I counted {filler_count} filler words. Your posture seemed to be '{final_posture}' towards the end. Results saved. Keep practicing!"
        speak(feedback)
        return

    # Construct prompt for Gemini
    prompt = f"{system_message_speech_review}\n\nUser's practice speech data:\n- Transcript: \"{full_text}\"\n- Duration: {duration_seconds:.1f} seconds\n- Calculated WPM: {wpm}\n- Filler Word Count: {filler_count} (Common fillers: {', '.join(FILLER_WORDS)})\n- Posture observed near the end: {final_posture}\n\nProvide supportive feedback and actionable tips based ONLY on this data."

    logging.info("\n  🧠 Requesting feedback from Gemini Speech Coach...")
    try:
        # Make the API call
        response = gemini_model.generate_content(prompt)
        gemini_feedback = ""

        # Safely extract text from response (structure might vary slightly)
        try:
            if hasattr(response, 'text') and response.text:
                gemini_feedback = response.text.strip()
            elif hasattr(response, 'parts') and response.parts:
                 # Handle potential multipart responses if applicable
                 gemini_feedback = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
            elif isinstance(response, str): # Fallback if it's just a string
                gemini_feedback = response.strip()
        except Exception as parse_err:
             logging.error(f"Error parsing Gemini response structure: {parse_err}", exc_info=True)
             gemini_feedback = "Error processing feedback."


        if gemini_feedback and "Error" not in gemini_feedback:
            logging.info(f"  🤖 Gemini Feedback Received:\n{gemini_feedback}\n")
            # Construct summary for TTS
            summary_feedback = f"Alright, practice session over! Results saved. Here's the breakdown: \n"
            summary_feedback += f"You spoke for about {duration_seconds:.1f} seconds at roughly {wpm} words per minute. \n"
            summary_feedback += f"I caught {filler_count} filler words. \n"
            summary_feedback += f"Your posture check showed: {final_posture}. \n\n"
            summary_feedback += f"Here's some coaching feedback from my AI brain: \n{gemini_feedback}"
            speak(summary_feedback)
        else:
            logging.warning(" ⚠️ Gemini returned no usable feedback text or parsing failed.")
            fallback_feedback = "Hmm, my AI coach seems to be speechless right now! But results were saved. Based on my numbers: "
            fallback_feedback += f"You spoke for {duration_seconds:.1f} seconds, {total_words} words, at {wpm} WPM, with {filler_count} fillers. Posture was {final_posture}."
            speak(fallback_feedback)

    except Exception as e:
        logging.error(f" ❌ Error getting feedback from Gemini: {e}", exc_info=True)
        speak("Uh oh, had a little trouble getting the detailed feedback from my AI brain, but your results were saved. You finished the practice!")


# --- Speech Recognition Thread Function ---
def recognize_speech():
    """Handles listening for commands and practice speech in a background thread."""
    global is_practicing_speech, speech_practice_data, main_thread_should_stop, mic_available, r, gemini_model

    if not mic_available or not r:
        logging.error("🔴 SR Thread: Mic or Recognizer not available. Thread exiting.")
        return

    logging.info("✅ SR thread ready.")
    while not main_thread_should_stop:
        logging.debug("-" * 10 + " SR Loop Start " + "-" * 10)
        if is_practicing_speech:
            prompt = f"Listening (Practice Mode)... Say '{END_PRACTICE_PHRASE}' to stop."
            # Longer phrase limit during practice
            phrase_timeout = 5.0 # Wait up to 5 seconds for speech after silence
            phrase_limit = 10.0 # Record up to 10 seconds of speech at a time
        else:
            prompt = f"Listening (Commands/Chat)... Say '{START_PRACTICE_PHRASE}', '{STOP_COMMAND}', or chat."
            phrase_timeout = 5.0
            phrase_limit = 7.0 # Shorter limit for commands/chat

        logging.info(f"🎙️ {prompt}")
        recognized_text = None
        try:
            # Listen for audio using the global microphone instance
            with mic as source:
                 # Note: timeout is how long listen waits for phrase to start
                 # phrase_time_limit is max duration of phrase
                 audio = r.listen(source, phrase_time_limit=phrase_limit, timeout=phrase_timeout)

            logging.info("  👂 Processing audio...")
            # Recognize using Google Web Speech API
            recognized_text = r.recognize_google(audio) # Add language="en-US" if needed
            logging.info(f"  👂 Heard: '{recognized_text}'")
            add_message('user', recognized_text) # Log user message
            recognized_text_lower = recognized_text.lower()

            # --- Logic based on mode ---
            if is_practicing_speech:
                logging.debug(" In Practice Mode Branch")
                if END_PRACTICE_PHRASE in recognized_text_lower:
                    logging.info("  🛑 Ending practice via voice command...")
                    is_practicing_speech = False
                    speak("Okay, ending practice session.")
                    analyze_and_feedback() # Analyze the collected data
                    # Reset practice data AFTER analysis
                    speech_practice_data = {"text": "", "start_time": None}
                else:
                    # Append recognized text to the ongoing transcript
                    speech_practice_data["text"] += (" " if speech_practice_data["text"] else "") + recognized_text
                    logging.info(f"  📝 Text collected (Total length: {len(speech_practice_data['text'])} chars)")

            else: # Normal Mode (Commands / Chat)
                logging.debug(" In Normal Mode Branch")
                if START_PRACTICE_PHRASE in recognized_text_lower:
                    logging.info("  🚀 Starting practice via voice command...")
                    is_practicing_speech = True
                    # Reset practice data completely at the start
                    speech_practice_data = {"text": "", "start_time": time.time()}
                    speak(f"Got it! Practice mode is now ON. Start speaking when you're ready.")
                elif STOP_COMMAND in recognized_text_lower:
                    logging.info("  🛑 Stop command detected...")
                    speak("Okay, shutting down!")
                    main_thread_should_stop = True # Signal all threads to stop
                    break # Exit SR loop immediately
                else: # General Chat Path
                    logging.debug(" Entering general chat path.")
                    if gemini_model:
                        logging.info("  🧠 Sending chat to Gemini...")
                        try:
                            # Use generate_content for chat
                            response = gemini_model.generate_content(recognized_text)
                            reply = ""
                            # Safely extract text (similar to feedback logic)
                            try:
                                if hasattr(response, 'text') and response.text: reply = response.text.strip()
                                elif hasattr(response, 'parts') and response.parts: reply = "".join(part.text for part in response.parts if hasattr(part, 'text')).strip()
                                elif isinstance(response, str): reply = response.strip()
                            except Exception as parse_err: logging.error(f"Error parsing Gemini chat response: {parse_err}", exc_info=True)

                            if reply:
                                logging.info(f"  🤖 Buddy says: {reply}")
                                speak(reply) # Speak the response
                            else:
                                logging.warning("  ⚠️ Gemini returned empty chat response.")
                                speak("Didn't come up with anything for that, sorry!")
                        except Exception as e:
                            logging.error(f"  ❌ Gemini Error during chat: {e}", exc_info=True)
                            speak("Oops, hit a snag thinking about that.")
                    else:
                        logging.warning("  ⚠️ Gemini model not available for chat.")
                        speak("My chat brain isn't available right now.")

        except sr.WaitTimeoutError:
            logging.debug("  👂 No speech detected within timeout.")
        except sr.UnknownValueError:
            logging.warning("  👂 Google Speech Recognition could not understand audio.")
            # Optionally speak("Sorry, I didn't catch that.") - can be annoying
        except sr.RequestError as e:
            logging.error(f"  ❌ Could not request results from Google Speech Recognition service; {e}", exc_info=True)
            # Potentially network issue or API quota exceeded (though less likely for free tier)
            speak("Hmm, having trouble reaching the speech service right now.")
            time.sleep(2) # Pause before retrying
        except Exception as e:
            logging.error(f"  ❌ Unexpected error in SR loop: {e}", exc_info=True)
            time.sleep(1) # Brief pause after unexpected errors

    logging.info("🔴 SR thread finished.")


# --- Camera Display Function (For Standalone OpenCV Window) ---
def show_camera():
    """Handles camera feed, pose detection, and display in a separate OpenCV window.
       ONLY intended for running Hackathon.py directly (standalone)."""
    global current_posture_status, main_thread_should_stop, pose # Use global pose

    logging.info("Attempting to start standalone camera window.")
    if not pose:
        logging.error("🔴 Cannot show camera: MediaPipe Pose object not initialized.")
        # Don't set main_thread_should_stop here, allow audio-only if mic works
        return

    cap = None
    opened_index = -1
    # Try common camera indices
    indices_to_try = [0, 1, -1]
    for index in indices_to_try:
        logging.debug(f"Trying Cam Index {index} for standalone window...")
        cap = cv2.VideoCapture(index)
        if cap is not None and cap.isOpened():
            logging.info(f"✅ Standalone Cam Index {index} opened successfully.")
            opened_index = index
            break
        else:
            if cap: cap.release()
            cap = None
            logging.warning(f"⚠️ Standalone Cam Index {index} failed.")
            time.sleep(0.2)

    if cap is None or not cap.isOpened():
        logging.error("🔴🔴🔴 CAMERA FAILED TO OPEN for standalone window. 🔴🔴🔴")
        # Don't set main_thread_should_stop here, allow audio-only if mic works
        return

    logging.info(f"--- 🎥 Standalone Cam Feed Starting (Index: {opened_index}) ---")
    window_name = "AI Study Buddy Cam (Standalone - Press 'q' to quit)"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    logging.info("Entering camera loop for standalone window.")
    loop_count = 0
    while not main_thread_should_stop:
        ret, frame = cap.read()
        if not ret:
            logging.warning(f" ⚠️ Standalone Cam Warning: Failed to grab frame {loop_count}.")
            # If camera disconnects, maybe try to reopen or break?
            time.sleep(0.1)
            continue

        try:
            # Process frame for pose
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False
            results = pose.process(frame_rgb) # Use global pose
            frame_rgb.flags.writeable = True
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            # Analyze and draw
            posture_status_analysis = "Posture: Initializing..."
            if results and results.pose_landmarks:
                posture_status_analysis = analyze_posture(results.pose_landmarks)
                mp_drawing.draw_landmarks( # Use global mp_drawing/mp_pose
                    frame_bgr, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                )
            else:
                posture_status_analysis = "Posture: No user detected"


            # Update global status (use lock for thread safety)
            with posture_lock:
                current_posture_status = posture_status_analysis

            # Add overlays
            cv2.putText(frame_bgr, posture_status_analysis, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            if is_practicing_speech: # Check global flag
                cv2.putText(frame_bgr, "REC ●", (frame_bgr.shape[1] - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

            # Display the frame
            cv2.imshow(window_name, frame_bgr)

        except Exception as e:
            logging.error(f" ❌ Standalone Cam ERROR processing frame: {e}", exc_info=True)

        # Check for quit key ('q')
        key = cv2.waitKey(5) & 0xFF # Use small wait key delay
        if key == ord('q'):
            logging.info("  🛑 'q' pressed in camera window. Stopping.")
            main_thread_should_stop = True # Signal threads to stop
            break # Exit camera loop

        loop_count += 1
        # Optional: Add a small sleep if CPU usage is high
        # time.sleep(0.01)

    # --- Cleanup for standalone window ---
    logging.info(f"Exited standalone camera loop ({loop_count} iterations).")
    if cap:
        logging.info("--- 🎥 Releasing Standalone Cam ---")
        cap.release()
    logging.info("Destroying OpenCV windows...")
    cv2.destroyAllWindows()
    # Add extra waitKeys needed on some systems to ensure window closes
    cv2.waitKey(1)
    cv2.waitKey(1)
    logging.info("OpenCV windows destroyed.")


# --- Background Camera Thread (for Flask - updates global state) ---
def run_camera_feed():
    """Background thread: captures video, runs pose detection, updates global status/frame.
       Intended to be started by Flask app."""
    global latest_frame, current_posture_status, main_thread_should_stop, pose # Ensure global pose is used
    global frame_lock, posture_lock, is_practicing_speech # Access necessary globals

    logging.info("Starting camera background thread (for Flask).")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.error("❌ Camera failed to open in background thread (for Flask).")
        return # Don't signal main thread stop, just fail this thread

    if pose is None:
        logging.error("❌ MediaPipe Pose object not available in camera thread (for Flask).")
        cap.release()
        return

    while not main_thread_should_stop:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False
            results = pose.process(frame_rgb)
            frame_rgb.flags.writeable = True
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            posture_text = "Posture: Initializing..."
            if results and results.pose_landmarks:
                posture_text = analyze_posture(results.pose_landmarks)
                # Optionally draw landmarks if storing the annotated frame
                # mp_drawing.draw_landmarks(...) # Draw on frame_bgr
            else:
                 posture_text = "Posture: No user detected"

            # Update global posture status (thread-safe)
            with posture_lock:
                current_posture_status = posture_text

            # ---- Optional: Update global frame (if needed by something else) ----
            # Add overlays to the frame before encoding if latest_frame should be annotated
            cv2.putText(frame_bgr, posture_text, (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2, cv2.LINE_AA)
            if is_practicing_speech:
                cv2.putText(frame_bgr, "REC ●", (frame_bgr.shape[1]-100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2, cv2.LINE_AA)

            # Encode and store frame
            ret_enc, buffer = cv2.imencode('.jpg', frame_bgr)
            if ret_enc:
                frame_bytes = buffer.tobytes()
                with frame_lock:
                    latest_frame = frame_bytes
            # else: logging.warning("JPEG encoding failed in camera thread (Flask).")
            # ---------------------------------------------------------------------

        except Exception as e:
            logging.error(f"❌ Error in camera thread loop (Flask): {e}", exc_info=True)
            time.sleep(0.5)

        time.sleep(0.02) # Small delay

    cap.release()
    logging.info("Camera background thread (Flask) terminating.")


# --- Generator for Flask Streaming ---
def gen_camera_frames():
    """Generator function to yield camera frames for Flask streaming route."""
    global pose, main_thread_should_stop, is_practicing_speech, current_posture_status # Access globals

    logging.info("Starting camera frame generator for Flask streaming.")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.error("❌ Camera failed to open in frame generator (Flask).")
        # Yield a placeholder or error image? For now, just stop.
        return

    if pose is None:
        logging.error("❌ MediaPipe Pose object not available in frame generator (Flask).")
        cap.release()
        return

    while True:
        # Check stop flag if needed
        if main_thread_should_stop:
             logging.info("Stop signal received in frame generator.")
             break

        ret, frame = cap.read()
        if not ret:
            logging.warning("Frame read failed in generator.")
            time.sleep(0.1)
            continue # Try again for a bit? Or break? Let's continue for now.

        try:
            # Process frame for pose
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb.flags.writeable = False # Performance optimization
            results = pose.process(frame_rgb)
            frame_rgb.flags.writeable = True

            # --- Get latest posture status ---
            # Read the status set by the background thread (run_camera_feed)
            # This assumes run_camera_feed is running and updating current_posture_status
            with posture_lock:
                posture_text_display = current_posture_status
            # --- OR ---
            # Uncomment below to calculate posture directly here if run_camera_feed is NOT used
            # if results and results.pose_landmarks:
            #     posture_text_display = analyze_posture(results.pose_landmarks)
            # else:
            #     posture_text_display = "Posture: No user detected"


            # --- Draw landmarks and overlays on the frame to be streamed ---
            if results and results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                )

            cv2.putText(frame, posture_text_display, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            if is_practicing_speech:
                cv2.putText(frame, "REC ●", (frame.shape[1] - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

            # Encode as JPEG
            ret_enc, buf = cv2.imencode(".jpg", frame)
            if not ret_enc:
                logging.warning("JPEG encoding failed in generator.")
                continue

            frame_bytes = buf.tobytes()
            # Yield the frame in multipart format
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" +
                   frame_bytes + b"\r\n")

        except Exception as e:
            logging.error(f"❌ Error in frame generator loop (Flask): {e}", exc_info=True)
            time.sleep(0.5) # Pause if errors occur rapidly

    # Cleanup
    cap.release()
    logging.info("Camera frame generator (Flask) stopped.")


# --- REMOVED generate_video_frames FUNCTION ---
# (The old, broken version is gone)


# --- Main Execution Block (for running Hackathon.py directly) ---
if __name__ == "__main__":
    logging.info("\n" + "="*10 + " Starting AI Study Bot (Standalone Mode) " + "="*10)
    print(f"\nSay '{START_PRACTICE_PHRASE}' to start recording.")
    print(f"Say '{END_PRACTICE_PHRASE}' to stop recording and get feedback.")
    print(f"Say '{STOP_COMMAND}' to exit.")
    print("Press 'q' in the camera window (if shown) to exit.\n")

    # --- Initialize Database ---
    init_database()

    # --- Speak Warnings if Services Failed ---
    if not mic_available: speak("Warning: Microphone initialization failed.")
    if not pose: speak("Warning: MediaPipe Pose initialization failed.")
    if not gemini_model: speak("Warning: Gemini AI model initialization failed.")
    if not elevenlabs_client: speak("Warning: ElevenLabs TTS initialization failed.")


    # --- Start Speech Recognition Thread ---
    speech_thread = None
    if mic_available:
        logging.info("Creating speech recognition thread for standalone mode.")
        # Make it non-daemon to allow for cleaner shutdown? Or keep daemon?
        # Daemon=True means it will exit abruptly if main thread exits.
        speech_thread = threading.Thread(target=recognize_speech, name="SpeechThread", daemon=True)
        speech_thread.start()
        logging.info("✅ Speech recognition thread started.")
    else:
        logging.warning("🔴 Speech recognition thread NOT started (no microphone).")


    # --- Run Camera Display (Standalone Mode) ---
    camera_shown = False
    if pose:
        logging.info("Attempting to show standalone camera window...")
        # Run show_camera directly in the main thread for standalone
        # This function will block until 'q' is pressed or main_thread_should_stop is True
        show_camera()
        camera_shown = True
    else:
        logging.warning("🔴 Standalone camera window skipped (MediaPipe Pose failed).")

    # --- Keep Main Thread Alive (if necessary) ---
    if not camera_shown: # If camera isn't blocking the main thread
         if mic_available and speech_thread:
             logging.info("ℹ️ Running in audio-only mode (no camera window). Say 'stop' or press Ctrl+C to exit.")
             try:
                 while not main_thread_should_stop:
                     time.sleep(1) # Keep main thread alive while speech thread runs
             except KeyboardInterrupt:
                 logging.info("\nCtrl+C detected. Stopping.")
                 main_thread_should_stop = True
         else:
             logging.error("Neither camera nor microphone available in standalone mode. Exiting.")
             sys.exit(1) # Exit if nothing can run


    # --- Final Cleanup (Standalone Mode) ---
    logging.info("\n" + "="*10 + " Shutting Down AI Study Bot (Standalone Mode) " + "="*10)

    # Wait for speech thread to finish (give it a chance after stop signal)
    if speech_thread and speech_thread.is_alive():
        logging.info("Waiting up to 2 seconds for speech thread to join...")
        speech_thread.join(timeout=2.0)
        if speech_thread.is_alive():
            logging.warning("⚠️ Speech thread did not stop cleanly.")

    # Release MediaPipe resources if they were loaded
    if pose:
        try:
            logging.info("Closing MediaPipe Pose resources...")
            pose.close()
            logging.info("✅ MediaPipe Pose resources released.")
        except Exception as e:
            logging.error(f"❌ Error closing MediaPipe Pose: {e}", exc_info=True)

    # Short delay before final exit message
    time.sleep(0.5)
    logging.info("👋 Bot shut down gracefully.")
    print("\nApplication exited.")
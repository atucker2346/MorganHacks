# Speech Analysis Tool (Vocalytics)

## Overview

This Project won Second Place at MorganHacks 2025

Vocalytics is a web-based application that helps users improve their public speaking skills by providing real-time feedback on speech patterns, posture, and delivery. The app uses computer vision, speech recognition, and AI to analyze speaking performance and offer personalized coaching.

## Features

- **Real-time speech analysis**: Monitors speech pace, filler word usage, and more
- **Posture detection**: Uses computer vision to analyze and provide feedback on your speaking posture
- **Practice sessions**: Record and analyze practice speeches
- **Speech history**: Review past practice sessions with analytics
- **Notecards**: Create and manage speaking notes
- **AI feedback**: Receive personalized coaching from AI

## Prerequisites

- Python 3.11
- FFmpeg with ffplay and ffprobe (for audio playback)
- A working webcam
- A working microphone
- Google API key (for Gemini AI)
- ElevenLabs API key (for text-to-speech)

## Installation

1. **Clone the repository**

```bash
git clone [repository_url]
cd [repository_directory]
```

2. **Create and activate a virtual environment**

```bash
# Create virtual environment
python -m venv morganvenv

# Activate on Windows
morganvenv\Scripts\activate

# Activate on macOS/Linux
source morganvenv/bin/activate
```

3. **Install FFmpeg**

This is required for audio playback with ElevenLabs.

**Windows:**
- Download FFmpeg from https://ffmpeg.org/download.html
- Extract the files
- Add the bin folder to your PATH environment variable

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt update
sudo apt install ffmpeg
```

4. **Install required Python packages**

```bash
pip install flask google-generativeai opencv-python mediapipe elevenlabs SpeechRecognition numpy
```

5. **Set up API keys**

Create an `api.py` file with your API keys:

```python
GOOGLE_API_KEY_FROM_USER = "your_google_api_key_here"
ELEVENLABS_API_KEY_FROM_USER = "your_elevenlabs_api_key_here"
```

## Running the Application

1. **Start the Flask server**

```bash
python app.py
```

2. **Access the web interface**

Open your web browser and go to:
```
http://127.0.0.1:5000
```

## Using the Application

1. **Home Page**: Click "Start Practicing Now" to begin a practice session
2. **Live Practice**: 
   - The camera will activate and begin tracking your posture
   - Start speaking to analyze your speech patterns
   - The application will provide real-time feedback
3. **Practice Results**:
   - View statistics like WPM (words per minute), filler word count
   - Receive AI feedback on your delivery
   - See generated notecards from your speech content
4. **History**: Review past practice sessions and track your progress
5. **Notecards**: Create, edit, and organize speaking notes

## Troubleshooting

- **Camera not working**: Ensure your camera is not being used by another application
- **Microphone not working**: Check your microphone permissions and settings
- **No audio playback**: Verify FFmpeg is correctly installed and in your PATH
- **API errors**: Check that your API keys are correctly set in api.py
- **Application crashes**: Check terminal output for error messages

## Common Issues & Solutions

### Error: "Could not build url for endpoint 'live-practice'"
- This indicates a URL routing issue in the Flask application
- Ensure that you're using underscores instead of hyphens in URL routes
- Fix: In `app.py`, make sure that all route functions use consistent naming

### Error: "Template not found: live-practice.html"
- The application can't find the template file
- Fix: Make sure `live_practice.html` exists in the templates directory
- Check for typos in file names or incorrect references

### Microphone or Camera Not Working
- Ensure your browser has permission to access your camera and microphone
- Check that no other application is using these devices
- Restart the Flask server after connecting devices

### "Missing MediaPipe Pose" or "No landmarks detected"
- This indicates issues with the pose detection
- Ensure you have good lighting and are visible in the camera frame
- Try reinstalling MediaPipe: `pip install --upgrade mediapipe`

## File Structure

- `app.py`: Main Flask application server
- `Hackathon.py`: Core functionality (speech recognition, AI, camera processing)
- `api.py`: API key storage
- `script.js`: Client-side JavaScript for UI interactions
- `main.js`: Additional JavaScript functionality
- `static/`: CSS and other static assets
- `templates/`: HTML templates for the web interface

## Dependencies

- Flask: Web server framework
- OpenCV: Computer vision for posture detection
- MediaPipe: ML tools for pose estimation
- SpeechRecognition: For real-time speech analysis
- Google Generative AI: For AI coaching feedback
- ElevenLabs: For text-to-speech functionality
- SQLite3: For data storage

## Route Fixes

If experiencing URL-related errors, ensure these routes in app.py are correctly defined:

```python
@app.route('/live_practice')
def live_practice():
    return render_template("live_practice.html")

@app.route('/camera_feed')
def camera_feed():
    return Response(
        hack.gen_camera_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route('/start-practice', methods=['POST'])
def start_practice():
    # Your code here
    return redirect(url_for('live_practice'))  # Note: use underscore not hyphen
```

## Note on Performance

Speech and video processing are resource-intensive. For optimal performance:
- Use a computer with a modern CPU
- Ensure good lighting for accurate pose detection
- Use a high-quality microphone for better speech recognition

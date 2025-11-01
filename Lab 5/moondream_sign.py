#!/usr/bin/env -S /home/pi/Interactive-Lab-Hub/Lab\ 3/.venv/bin/python

# --------------------------------------------------------------------------------------
# HELPFUL VISION TUTOR (VOSK/LLM/MOONDREAM/ESPEAK TTS)
# The core loop: STT -> Capture -> Vision -> LLM Feedback -> TTS
# --------------------------------------------------------------------------------------

import argparse, queue, sys, json, time, base64, os
import sounddevice as sd
import requests
import cv2
import subprocess
# Vosk is assumed to be installed in the venv and uses KaldiRecognizer and Model
# from the vosk module (not explicitly shown in the provided imports)

# --- CONFIGURATION ---
class Config:
    # Ollama Models & API
    OLLAMA_URL = "http://localhost:11434"
    LLM_MODEL_NAME = "qwen2.5:0.5b-instruct" 
    MOONDREAM_MODEL_NAME = "moondream:latest"
    # Prompts & Commands
    VISION_PROMPT = "Strictly classify the gesture made by the hand in this image. Is it a thumbs up, a peace sign, a pointing finger, or another recognizable sign? Only output the classification."
    TUTOR_SYSTEM_PROMPT = "**ALWAYS RESPOND WITH A HELPFUL, ENCOURAGING, AND TUTORIAL ATTITUDE.** You are a sign language tutor, here to help the user practice and learn new signs. Keep your responses **brief, conversational, and positive**. Acknowledge the effort, provide feedback based on the classification, and suggest the next step.\n\n**Vision Model Classification**:\n"
    VISION_COMMANDS = ['show me', 'check my sign', 'ready', 'test me', 'capture']
    EXIT_COMMANDS = ['quit', 'exit', 'shut down', 'log off', 'stop listening']
    # Other Settings
    CAMERA_INDEX = 0
    IMAGE_FILENAME = "gesture_capture.jpg"
    AUDIO_QUEUE = queue.Queue()

# --- HELPER UTILITIES ---

@staticmethod
def speak_text(text):
    """Simple text-to-speech using espeak and console logging."""
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"Tutor Bot: {clean_text}")
    try:
        subprocess.run(['espeak', f'"{clean_text}"'], check=False)
    except FileNotFoundError:
        print("TTS Error: 'espeak' not found. Install with: sudo apt install espeak.")

@staticmethod
def int_or_str(text):
    """For argument parsing."""
    try: return int(text)
    except ValueError: return text

@staticmethod
def callback(indata, frames, time, status):
    """Callback for sounddevice RawInputStream."""
    if status: print(status, file=sys.stderr)
    Config.AUDIO_QUEUE.put(bytes(indata))

# --- VISION & LLM FUNCTIONS ---

@staticmethod
def capture_image():
    """Captures and saves a single image from the webcam."""
    print("Camera: Please hold your gesture steady...")
    cap = cv2.VideoCapture(Config.CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    if not cap.isOpened():
        print("Camera: Error: Could not open camera.")
        return None
    
    # Allow camera to warm up and adjust
    time.sleep(0.5)
    for _ in range(15): cap.read()
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("Camera: Error: Could not capture image.")
        return None
    
    cv2.imwrite(Config.IMAGE_FILENAME, frame)
    return Config.IMAGE_FILENAME

@staticmethod
def run_ollama_vision(image_path):
    """Sends image to Moondream for classification."""
    try:
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        return f"Moondream Error: Could not read image file. {e}"

    try:
        response = requests.post(
            f"{Config.OLLAMA_URL}/api/generate",
            json={
                "model": Config.MOONDREAM_MODEL_NAME,
                "prompt": Config.VISION_PROMPT,
                "images": [image_data],
                "stream": False 
            }, timeout=120)
        
        return response.json().get('response', 'Moondream: Failed to classify gesture.').strip() \
               if response.status_code == 200 \
               else f"Moondream Error: API status {response.status_code}."
    except requests.exceptions.Timeout:
        return "Moondream: Timed out. Please try again."
    except Exception as e:
        return f"Moondream Error: Communication error: {e}"

@staticmethod
def get_llm_feedback(classification):
    """Sends classification to the LLM for helpful feedback."""
    prompt = Config.TUTOR_SYSTEM_PROMPT + classification
    try:
        response = requests.post(
            f"{Config.OLLAMA_URL}/api/generate",
            json={
                "model": Config.LLM_MODEL_NAME,
                "prompt": prompt,
                "stream": False
            }, timeout=90)
        
        return response.json().get('response', 'I was unable to generate feedback. Let\'s try again.') \
               if response.status_code == 200 \
               else f"Error: Ollama API status {response.status_code}. Please check your Ollama server."
    
    except requests.exceptions.Timeout:
        return "The server timed out while thinking. Let's try that gesture one more time."
    except Exception as e:
        return f"Error communicating with the Tutor model: {e}."


# --- MAIN EXECUTION ---

def run_tutor_bot():
    """Initializes all systems and runs the continuous voice command loop."""
    parser = argparse.ArgumentParser(description="Helpful Vision Tutor (Vosk + Ollama + Moondream)")
    parser.add_argument("-l", "--list-devices", action="store_true", help="show list of audio devices and exit")
    parser.add_argument("-d", "--device", type=int_or_str, help="input device (numeric ID or substring)")
    parser.add_argument("-r", "--samplerate", type=int, help="sampling rate")
    parser.add_argument("-m", "--model", type=str, default="en-us", help="Vosk language model; default is en-us")
    args, _ = parser.parse_known_args()

    if args.list_devices:
        print(sd.query_devices()); sys.exit(0)
        
    try:
        # 1. Ollama Check
        if requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=5).status_code != 200:
            print(f"Error: Cannot connect to Ollama. Is 'ollama serve' running?")
            sys.exit(1)
            
        # 2. Vosk Setup
        if args.samplerate is None:
            device_info = sd.query_devices(args.device, "input")
            args.samplerate = int(device_info["default_samplerate"])
            
        # NOTE: Model and KaldiRecognizer classes are expected to be available from the environment.
        from vosk import Model, KaldiRecognizer
        model = Model(lang=args.model)
        rec = KaldiRecognizer(model, args.samplerate)

        # 3. Main Loop
        with sd.RawInputStream(samplerate=args.samplerate, blocksize=8000, device=args.device,
                dtype="int16", channels=1, callback=callback):
            
            print(f"\n{'='*70}")
            speak_text("Welcome! I'm ready to check your gesture. Say 'show me' or 'check my sign'.")
            print("Press Ctrl+C to exit.")
            print(f"{'='*70}")
            
            while True:
                data = Config.AUDIO_QUEUE.get()
                if rec.AcceptWaveform(data):
                    user_input = json.loads(rec.Result()).get('text', '').strip().lower()
                    
                    if not user_input:
                        rec.Reset()
                        continue

                    print(f"\nUser: {user_input}")

                    # Command Logic
                    if any(cmd in user_input for cmd in Config.VISION_COMMANDS):
                        speak_text("Excellent! Hold your gesture steady now.")
                        image_path = capture_image()
                        
                        if image_path:
                            print("Tutor Bot: Analyzing...")
                            classification = run_ollama_vision(image_path)
                            feedback = get_llm_feedback(classification)
                            speak_text(feedback)
                        else:
                            speak_text("I had trouble with the camera. Check the connections.")

                    elif any(cmd in user_input for cmd in Config.EXIT_COMMANDS):
                        speak_text("Great work today! See you next time.")
                        return 
                        
                    elif user_input:
                        speak_text("I'm focused on checking your signs! Just tell me 'show me' when you're ready.")

                    print("\nTutor Bot is now listening again...")
                    rec.Reset() 
                    
    except KeyboardInterrupt:
        speak_text("Session paused.")
        sys.exit(0)
    except Exception as e:
        print(f"\nFATAL ERROR: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_tutor_bot()
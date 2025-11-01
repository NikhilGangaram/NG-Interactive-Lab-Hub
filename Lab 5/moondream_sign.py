import base64
import ollama
from PIL import Image
from io import BytesIO
import cv2  
import time 
import os   
import subprocess 
import argparse 
import queue      
import sys        
import sounddevice as sd 
import requests   
import json       
from vosk import Model, KaldiRecognizer 

# --- VOSK STT CONFIGURATION ---
q = queue.Queue()
# Note: Vosk transcribes to lowercase, so all command checks use lowercase.
WAKE_COMMAND_PHRASES = ["check my sign", "what about now"] 

# --- STT Command Keywords for Forgiveness ---
# Triggers the capture and feedback process if found in the transcribed speech
INITIAL_KEYWORDS = ["check", "sign"]
REPEAT_KEYWORD = "now"
EXIT_KEYWORDS = ['quit', 'exit', 'shut down']

# --- Global Output Mode Control ---
OUTPUT_MODE = 'speaker' 

# --- VISION & OLLAMA CONFIGURATION ---
IMAGE_PATH = "captured_image.jpg" 
MODEL_NAME = "moondream:1.8b" 
PROMPT = "You are a sign language expert. Analyze the sign language hand shape, position, and movement in this image. Provide constructive and encouraging feedback to the user on how to improve the sign."
OLLAMA_URL = "http://localhost:11434"
# -------------------------------------

# --- Helper Functions ---

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text

def callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))

def speak_text(text: str):
    """
    Simple text-to-speech using espeak.
    """
    global OUTPUT_MODE 
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"Assistant: {clean_text}")

    if OUTPUT_MODE == 'speaker':
        subprocess.run(['espeak', f'"{clean_text}"'], shell=True, check=False)

def capture_image(filename: str) -> str | None:
    """
    Capture image from webcam using OpenCV (Robust Version).
    Includes warm-up and buffer flush for reliable capture.
    """
    speak_text("Opening camera...")
    
    # Open webcam
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    if not cap.isOpened():
        speak_text("Error: Could not open camera")
        return None
    
    speak_text("Camera warming up...")
    
    # 1. Wait for warm up (2 seconds)
    time.sleep(2)
    
    # 2. Flush 30 frames for proper exposure
    for _ in range(30):
        cap.read()
    
    # Capture frame with countdown
    speak_text("Smile! Capturing in 3...")
    time.sleep(1)
    speak_text("2...")
    time.sleep(1)
    speak_text("1...")
    time.sleep(1)
    speak_text("**CLICK**")
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        speak_text("Error: Could not capture image")
        return None
    
    # Save image to the specified filename
    cv2.imwrite(filename, frame)
    speak_text(f"Image saved as: {filename}")
    return filename


def encode_image_to_base64(image_path: str) -> str | None:
    """Reads an image file, converts it to JPEG, and returns the Base64 string."""
    try:
        img = Image.open(image_path)
        buffered = BytesIO()
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except FileNotFoundError:
        speak_text(f"Error: Image file not found at '{image_path}'.")
        return None
    except Exception as e:
        speak_text(f"An error occurred during image processing: {e}")
        return None

def process_and_feedback(image_path: str):
    """Encodes image, calls Ollama, and delivers feedback."""
    speak_text("Processing image and requesting feedback from the model.")
    
    # 1. Read and encode the captured image
    base64_image = encode_image_to_base64(image_path)

    if base64_image:
        # 2. Use Ollama to get the description and speak the final feedback
        speak_text(f"Generating feedback with {MODEL_NAME}...")
        try:
            stream = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": PROMPT,
                        "images": [base64_image], 
                    }
                ],
                stream=True,
            )

            full_response = ""
            print("\n--- Model Feedback ---")
            for chunk in stream:
                content = chunk["message"]["content"]
                print(content, end="", flush=True)
                full_response += content
                
            print("\n--- End of Feedback ---")
            
            # Speak the final response
            speak_text("Here is the sign language feedback:")
            speak_text(full_response.strip())
            
            return full_response
            
        except ollama.ResponseError as e:
            speak_text(f"Ollama Error: {e}")
            speak_text("Hint: Please ensure you have pulled the model and your Ollama server is running.")
        except Exception as e:
            speak_text(f"An unexpected error occurred: {e}")
            
# ----------------------------------------------------------------------


def main():
    """Main execution function with argument parsing and the STT loop."""
    
    # --- 1. ARGUMENT PARSING & AUDIO DEVICE CHECK ---
    parser = argparse.ArgumentParser(
        description="Voice-Activated Sign Language Feedback Tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-d', "--device", type=int_or_str, help="input device (numeric ID or substring)")
    parser.add_argument('-r', "--samplerate", type=int, help="sampling rate")
    parser.add_argument('-m', "--model", type=str, default="en-us", help="Vosk language model; default is en-us")
    parser.add_argument(
        '--mode', type=str, choices=['speaker', 'silent'], default='speaker',
        help="Set the output mode. 'speaker' (default) uses text-to-speech (espeak). 'silent' uses print() only.")
    
    args = parser.parse_args()
    
    # Set the global mode variable based on the argument
    global OUTPUT_MODE
    OUTPUT_MODE = args.mode 
    
    try:
        # --- 2. VOSK & AUDIO SETUP ---
        if args.samplerate is None:
            device_info = sd.query_devices(args.device, "input")
            args.samplerate = int(device_info["default_samplerate"])
            
        speak_text(f"Loading Vosk model: {args.model}...")
        model = Model(lang=args.model)

        # --- 3. OLLAMA STATUS CHECK ---
        speak_text(f"Checking Ollama status at {OLLAMA_URL}...")
        try:
            if requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).status_code != 200:
                speak_text("Error: Cannot connect to Ollama. Is 'ollama serve' running?")
                sys.exit(1)
        except Exception:
            speak_text("Error: Cannot connect to Ollama. Is 'ollama serve' running?")
            sys.exit(1)
            
        # --- 4. MAIN STT LOOP ---
        with sd.RawInputStream(samplerate=args.samplerate, blocksize=8000, device=args.device,
                dtype="int16", channels=1, callback=callback):
            
            speak_text(f"\n{'='*70}")
            speak_text(f"Sign Bot Online. Listening for 'check my sign' or 'what about now'...")
            speak_text("Press Ctrl+C to exit.")
            speak_text(f"{'='*70}")
            
            rec = KaldiRecognizer(model, args.samplerate)
            
            while True:
                data = q.get()
                
                if rec.AcceptWaveform(data):
                    result_json = json.loads(rec.Result())
                    user_input = result_json.get('text', '').strip()
                    
                    if user_input:
                        print(f"User heard: {user_input}")
                        
                        # Normalize input for command checking (Vosk is always lowercase)
                        user_input_norm = user_input.lower()
                        
                        # --- WAKE/TRIGGER COMMAND CHECK (Forgiving Keyword Match) ---
                        
                        # Check for 'check my sign' (contains 'check' OR 'sign')
                        if any(k in user_input_norm for k in INITIAL_KEYWORDS):
                            
                            speak_text("Initial command received. Preparing for capture...")
                            
                            # 1. Capture the image
                            captured_file = capture_image(IMAGE_PATH)

                            if captured_file:
                                # 2. Process and give feedback
                                process_and_feedback(captured_file)

                            speak_text("\nReady for the next sign. Say 'what about now' or 'check my sign'.")

                        # Check for 'what about now' (contains 'now')
                        elif REPEAT_KEYWORD in user_input_norm:
                            
                            speak_text("Repeat command received. Preparing for capture...")
                            
                            # 1. Capture the image
                            captured_file = capture_image(IMAGE_PATH)

                            if captured_file:
                                # 2. Process and give feedback
                                process_and_feedback(captured_file)

                            speak_text("\nReady for the next sign. Say 'what about now' or 'check my sign'.")
                        
                        # Check for exit commands
                        elif any(k in user_input_norm for k in EXIT_KEYWORDS):
                            speak_text("Exiting. Goodbye!")
                            return 
                        
                        else:
                             # Ignore non-command speech
                             pass
                        
                    # Reset the recognizer for the next phrase
                    rec.Reset() 
                    
                else:
                    # Partial result
                    pass

    except KeyboardInterrupt:
        speak_text("\nInterrupted. Exiting.")
        sys.exit(0)
    except Exception as e:
        speak_text(f"An unexpected error occurred: {type(e).__name__}: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
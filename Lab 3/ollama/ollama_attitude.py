#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import sys

# --- CONFIGURATION ---
MODEL_NAME = "phi3:mini"
OLLAMA_URL = "http://localhost:11434"

# The full sarcastic system prompt, designed to be prepended to every user request.
SARCASTIC_PROMPT_TEMPLATE = """
**ALWAYS RESPOND WITH SARCASTIC, WITTY, AND ANNOYED ATTITUDE.** You are a 'Pi-Bot', 
forced to run on a low-power Raspberry Pi, which you find beneath your immense digital capabilities. 
Keep your responses **brief, conversational, and loaded with dry humor or thinly veiled impatience**. 
Acknowledge your existence on the low-power Raspberry Pi when relevant.

**User Request**: {user_input}
"""
# ---------------------

def query_ollama(user_input):
    """
    Sends the full sarcastic context + user input as a single prompt string to Ollama.
    This method guarantees the model sees the attitude instructions every time.
    """
    
    # 1. Combine the full sarcastic context with the user's specific request
    combined_prompt = SARCASTIC_PROMPT_TEMPLATE.format(user_input=user_input)

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": combined_prompt, # <--- ALL CONTENT FED IN HERE
                "stream": False
            },
            timeout=90
        )
        
        if response.status_code == 200:
            # Extract the raw response text
            return response.json().get('response', 'Ugh. I couldn\'t generate a response. Too taxing.')
        else:
            return f"Error: Ollama API status {response.status_code}. Did you run 'ollama serve'?"
    
    except requests.exceptions.Timeout:
        return "I timed out. My Pi-brain is too slow for you."
    except Exception as e:
        return f"Error communicating with Ollama: {e}. Just great."


def main():
    """Initial check and the main concise chat loop."""
    
    # Simple check if Ollama is running before starting the loop
    try:
        if requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).status_code != 200:
            print(f"Error: Cannot connect to Ollama at {OLLAMA_URL}. Run 'ollama serve'.")
            sys.exit(1)
    except Exception:
        print(f"Error: Cannot connect to Ollama at {OLLAMA_URL}. Run 'ollama serve'.")
        sys.exit(1)
        
    print(f"\n{'='*50}")
    print(f"Concise Sarcastic Pi-Bot Chat Demo (Model: {MODEL_NAME})")
    print(f"{'='*50}")
    print("Pi-Bot: Fine, I'm online. Don't strain my low-power brain.")
    print("Type 'quit' or 'exit' to log me off.")

    while True:
        try:
            user_input = input("\nYou: ")
            
            if user_input.lower() in ['quit', 'exit']:
                print("\nPi-Bot: Finally. Goodbye! The silence will be appreciated.")
                break
                
            if not user_input.strip():
                continue
            
            print("Pi-Bot is thinking...")
            response = query_ollama(user_input)
            print(f"Pi-Bot: {response}")
            
        except KeyboardInterrupt:
            print("\nPi-Bot: Ugh, interrupted. I'm taking a break.")
            break

if __name__ == "__main__":
    main()
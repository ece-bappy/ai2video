# tts_generator.py
import asyncio
import edge_tts
import os
import random # Added import

# --- Definition of the voice set ---
# Given voice set as a multi-line string
# This variable stores the provided voice set.
# It's named with a leading underscore to indicate it's primarily for internal module use.
_VOICE_SET_STRING_DATA = """en-US-AnaNeural
en-US-AndrewMultilingualNeural
en-US-AndrewNeural
en-US-AriaNeural
en-US-AvaMultilingualNeural
en-US-AvaNeural
en-US-BrianMultilingualNeural
en-US-BrianNeural
en-US-ChristopherNeural
en-US-EmmaMultilingualNeural
en-US-EmmaNeural
en-US-EricNeural
en-US-GuyNeural
en-US-JennyNeural
en-US-MichelleNeural"""

# Parse the string into a list of voice names
# This list will be used for random voice selection.
# Also named with a leading underscore.
_PREDEFINED_VOICE_LIST = [
    voice.strip() for voice in _VOICE_SET_STRING_DATA.strip().split('\n') if voice.strip()
]


async def generate_voice_over(script_text: str, output_filename: str = "voice_over.mp3", voice: str = "en-US-JennyNeural"):
    """
    Generates a voice-over audio file from the given script text using edge-tts.
    A random voice from a predefined set (_PREDEFINED_VOICE_LIST) will be used for each generation.

    Args:
        script_text (str): The text content to be converted to speech.
        output_filename (str): The name of the file to save the audio to (e.g., "voice_over.mp3").
        voice (str): This parameter is part of the original function signature and is kept for compatibility.
                     Its value is IGNORED for voice selection purposes due to the requirement
                     to use a random voice each time from the _PREDEFINED_VOICE_LIST.
                     The original default for this parameter was "en-US-JennyNeural".
                     (Original description: Use 'edge-tts --list-voices' to find available voices.
                     Other good options: "en-US-AriaNeural", "en-GB-SoniaNeural".)

    Returns:
        str: The path to the generated audio file, or None if generation failed.
    """
    if not script_text:
        print("Error: Script text is empty. Cannot generate voice-over.")
        return None

    actual_tts_voice: str
    if not _PREDEFINED_VOICE_LIST:
        print("Error: The predefined voice set (_PREDEFINED_VOICE_LIST) is empty.")
        # Fallback to the original default voice string from the function signature
        # if the list is empty. This is a safety measure.
        actual_tts_voice = "en-US-JennyNeural" 
        print(f"Warning: Using fallback voice due to empty set: {actual_tts_voice}")
    else:
        actual_tts_voice = random.choice(_PREDEFINED_VOICE_LIST)

    # The 'voice' parameter from the function signature is ignored for selection.
    # The print statement now shows the *actual* (randomly selected) voice being used.
    print(f"\nGenerating voice-over using random voice: {actual_tts_voice}...")
    print(f"Output will be saved to: {output_filename}")

    try:
        communicate = edge_tts.Communicate(script_text, actual_tts_voice) # Use the randomly selected voice
        await communicate.save(output_filename) # Saves to MP3 by default if extension is .mp3
        print(f"Voice-over successfully generated and saved to '{output_filename}'.")
        return output_filename
    except Exception as e:
        print(f"Error during TTS generation with edge-tts: {e}")
        # edge-tts might raise various exceptions, including network issues or if Edge isn't found/working.
        return None

async def list_available_voices():
    """Lists available voices using edge-tts."""
    print("Fetching available voices from edge-tts...")
    try:
        voices = await edge_tts.VoicesManager.create()
        for voice_info in voices.voices:
            if "en-" in voice_info["Locale"]: # Filter for English voices for brevity
                print(f"  Name: {voice_info['Name']}, Gender: {voice_info['Gender']}, Locale: {voice_info['Locale']}")
    except Exception as e:
        print(f"Could not fetch voices: {e}")


if __name__ == "__main__":
    # --- Configuration for Testing ---
    script_file_path = "generated_full_script.txt" # From script_generator.py
    output_audio_file = "generated_voice_over.mp3"
    # This 'selected_voice_in_main_test' variable is local to this `if __name__ == "__main__":` block.
    # It is passed as the 'voice' argument to generate_voice_over.
    # Per the modified logic, the 'voice' argument to generate_voice_over will be IGNORED
    # for selection, and a random voice from _PREDEFINED_VOICE_LIST will be used instead.
    selected_voice_in_main_test = "en-US-EmmaNeural" # Example: "en-US-JennyNeural", "en-GB-SoniaNeural"

    # --- Test Script ---
    async def main_test():
        # Optional: List some voices first
        # await list_available_voices()
        # print("-" * 30)

        if not os.path.exists(script_file_path):
            print(f"Error: Script file '{script_file_path}' not found. Please run script_generator.py first.")
            # Create a dummy script for testing if the file is missing
            print("Using a dummy script for TTS testing.")
            test_script = "Hello, this is a test of the text-to-speech generation using Microsoft Edge voices. I hope this sounds natural and clear. Let's see how it performs for longer content as well."
        else:
            with open(script_file_path, "r", encoding="utf-8") as f:
                test_script = f.read()

        if test_script:
            # Clarifying message for when this script is run directly for testing
            print(f"\nNote for testing: The 'voice' parameter passed to generate_voice_over "
                  f"(value: '{selected_voice_in_main_test}') will be ignored. "
                  f"A random voice from the predefined set will be chosen instead.")
            
            generated_file_path = await generate_voice_over(
                script_text=test_script,
                output_filename=output_audio_file,
                voice=selected_voice_in_main_test # This argument is ignored by the modified function for voice selection
            )

            if generated_file_path:
                print(f"\nTest successful. Audio saved to: {os.path.abspath(generated_file_path)}")
                # You can try playing it (platform dependent)
                # if os.name == 'nt': # For Windows
                #     os.system(f"start {generated_file_path}")
                # elif os.name == 'posix': # For macOS/Linux
                #     # You might need 'xdg-open' (Linux) or 'open' (macOS)
                #     try:
                #         os.system(f"open {generated_file_path}") # macOS
                #     except:
                #         try:
                #             os.system(f"xdg-open {generated_file_path}") # Linux
                #         except:
                #             print("Could not automatically open the audio file.")
            else:
                print("\nTest failed. Voice-over generation was unsuccessful.")
        else:
            print("No script content available to generate voice-over.")

    # Run the async main_test function
    # Python 3.7+ allows asyncio.run() directly
    asyncio.run(main_test())
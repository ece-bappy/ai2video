# main_video_pipeline.py
import os
import json
import shutil
import csv # For reading CSV
import time # For retries
import logging # For logging
import re # For sanitizing filenames
from dotenv import load_dotenv
import argparse
import asyncio # For tts_generator

# Import your custom modules
import script_generator
import media_fetcher
import tts_generator
import video_assembler
import whisper # openai-whisper

# --- Global Configuration & Constants ---
OUTPUT_BASE_DIR = "generated_videos_output"
CSV_FILENAME = "shorts.csv"
LOG_FILENAME = "video_pipeline.log"

# Define pipeline steps (though not used for --start_step in this CSV-driven version directly)
STEP_SCRIPT = "script"
STEP_MEDIA = "media"
STEP_TTS = "tts"
STEP_SRT = "srt"
STEP_VIDEO = "video"

# Network Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILENAME, mode='a'), # Append to log file
        logging.StreamHandler() # Also print to console
    ]
)

def sanitize_filename(name: str) -> str:
    """Sanitizes a string to be suitable for a filename."""
    name = re.sub(r'[^\w\s-]', '', name.lower()) # Remove non-alphanumeric (except spaces, hyphens)
    name = re.sub(r'[-\s]+', '-', name).strip('-_') # Replace spaces/hyphens with single hyphen
    return name[:100] # Limit length

def check_internet_connection(host="8.8.8.8", port=53, timeout=3):
    """Host: 8.8.8.8 (Google DNS) Port: 53/tcp (DNS)"""
    try:
        import socket
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as ex:
        logging.warning(f"No internet connection: {ex}")
        return False

def ensure_internet_connection_with_retry():
    """Ensures internet connection, retrying if necessary."""
    retries = 0
    while not check_internet_connection():
        if retries >= MAX_RETRIES * 5: # Longer wait for internet
            logging.error("Max retries for internet connection reached. Aborting current task if network dependent.")
            return False
        logging.info(f"Waiting for internet connection... (retry {retries + 1})")
        time.sleep(RETRY_DELAY_SECONDS * (retries +1) ) # Exponential backoff
        retries += 1
    return True


def generate_srt_from_audio(audio_path: str, output_dir: str, model_name: str = "base.en") -> str | None:
    if not os.path.exists(audio_path):
        logging.error(f"Audio file not found at {audio_path} for SRT generation.")
        return None
    logging.info(f"Generating SRT for '{os.path.basename(audio_path)}' using Whisper model '{model_name}'...")
    try:
        model = whisper.load_model(model_name)
        os.makedirs(output_dir, exist_ok=True)
        result = model.transcribe(audio_path, verbose=False, language="en")
        base_audio_name = os.path.splitext(os.path.basename(audio_path))[0]
        srt_filename = f"{base_audio_name}.srt"
        srt_file_path = os.path.join(output_dir, srt_filename)
        with open(srt_file_path, "w", encoding="utf-8") as srt_file:
            for i, segment in enumerate(result["segments"]):
                start_time, end_time, text = segment['start'], segment['end'], segment['text'].strip()
                start_h, sr = divmod(start_time,3600); sm, ss = divmod(sr,60); sms = int((ss-int(ss))*1000)
                end_h, er = divmod(end_time,3600); em, es = divmod(er,60); ems = int((es-int(es))*1000)
                srt_file.write(f"{i+1}\n{int(start_h):02}:{int(sm):02}:{int(ss):02},{sms:03} --> {int(end_h):02}:{int(em):02}:{int(es):02},{ems:03}\n{text}\n\n")
        logging.info(f"SRT file generated: {srt_file_path}")
        return srt_file_path
    except Exception as e:
        logging.error(f"Error during Whisper SRT generation for {audio_path}: {e}", exc_info=True)
        return None

def process_single_video(topic: str, duration_minutes_str: str, api_keys: dict, base_output_dir: str):
    """
    Processes a single video from topic to final output.
    """
    project_name_sanitized = sanitize_filename(topic)
    if not project_name_sanitized:
        logging.error(f"Could not generate a valid project name for topic: '{topic}'. Skipping.")
        return False

    project_dir = os.path.join(base_output_dir, project_name_sanitized)
    logging.info(f"--- Starting Video Generation for Project: {project_name_sanitized} ---")
    logging.info(f"Topic: {topic}, Duration: {duration_minutes_str} min")

    try:
        video_duration_minutes = float(duration_minutes_str)
        if video_duration_minutes <= 0:
            logging.error(f"Invalid duration '{duration_minutes_str}' for topic '{topic}'. Skipping.")
            return False
    except ValueError:
        logging.error(f"Could not parse duration '{duration_minutes_str}' for topic '{topic}'. Skipping.")
        return False

    # Cleanup previous project directory if it exists (optional, could be a flag)
    if os.path.exists(project_dir):
        logging.info(f"Cleaning up existing project directory: {project_dir}")
        try:
            shutil.rmtree(project_dir)
        except OSError as e:
            logging.error(f"Error removing directory {project_dir}: {e}. Skipping topic.")
            return False
    try:
        os.makedirs(project_dir, exist_ok=True)
    except OSError as e:
        logging.error(f"Error creating project directory {project_dir}: {e}. Skipping topic.")
        return False

    # Define paths for this specific project
    full_script_path = os.path.join(project_dir, "generated_full_script.txt")
    structured_script_path = os.path.join(project_dir, "generated_structured_script.json")
    media_download_dir = os.path.join(project_dir, "media_files")
    downloaded_media_info_path = os.path.join(project_dir, "downloaded_media_info_portrait.json")
    voice_over_filename = "voice_over.mp3" # Standardized name
    generated_audio_path = os.path.join(project_dir, voice_over_filename)
    base_audio_name_for_srt = os.path.splitext(os.path.basename(generated_audio_path))[0]
    srt_file_path = os.path.join(project_dir, f"{base_audio_name_for_srt}.srt")
    output_video_filename = f"{project_name_sanitized}_video.mp4" # Filename based on topic
    output_video_path = os.path.join(project_dir, output_video_filename)

    # --- Step 1: Script Generation ---
    logging.info("--- Step 1: Script Generation ---")
    structured_script_content, full_script_text = None, None
    for attempt in range(MAX_RETRIES):
        if not ensure_internet_connection_with_retry(): return False # Critical network failure
        try:
            # script_generator.configure_gemini(api_keys["gemini"]) # Configure once globally if preferred
            structured_script_content, full_script_text = script_generator.generate_script_and_visuals(
                topic=topic, video_duration_minutes=video_duration_minutes, domain="General Knowledge" # Make domain configurable
            )
            if structured_script_content and full_script_text: break
        except Exception as e:
            logging.warning(f"Script generation attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY_SECONDS)
            else: logging.error("Max retries for script generation reached.", exc_info=True)
    if not structured_script_content or not full_script_text: logging.error("Failed to generate script. Skipping topic."); return False
    try:
        with open(full_script_path, "w", encoding="utf-8") as f: f.write(full_script_text)
        with open(structured_script_path, "w", encoding="utf-8") as f: json.dump(structured_script_content, f, indent=2)
        logging.info(f"Script saved in {project_dir}")
    except IOError as e: logging.error(f"Failed to save script files: {e}", exc_info=True); return False

    # --- Step 2: Media Fetching ---
    logging.info("--- Step 2: Media Fetching ---")
    downloaded_media_list = None
    for attempt in range(MAX_RETRIES):
        if not ensure_internet_connection_with_retry(): return False
        try:
            downloaded_media_list = media_fetcher.fetch_and_download_media(
                structured_script_content=structured_script_content,
                pexels_api_key=api_keys["pexels"], pixabay_api_key=api_keys["pixabay"],
                download_base_dir=media_download_dir
            )
            if downloaded_media_list: break # Success
            logging.warning(f"Media fetching attempt {attempt+1} yielded no media.") # Not an exception, but no results
        except Exception as e:
            logging.warning(f"Media fetching attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY_SECONDS)
            else: logging.error("Max retries for media fetching reached.", exc_info=True)
    if not downloaded_media_list: logging.error("Failed to fetch media. Skipping topic."); return False
    try:
        with open(downloaded_media_info_path, "w", encoding="utf-8") as f: json.dump(downloaded_media_list, f, indent=2)
        logging.info(f"Media info saved to {downloaded_media_info_path}")
    except IOError as e: logging.error(f"Failed to save media info: {e}", exc_info=True); return False

    # --- Step 3: TTS Voice-over Generation ---
    logging.info("--- Step 3: TTS Voice-over ---")
    actual_audio_path = None
    for attempt in range(MAX_RETRIES):
        # Edge-TTS might rely on network for voices, so check connection.
        if not ensure_internet_connection_with_retry(): return False
        try:
            actual_audio_path = asyncio.run(tts_generator.generate_voice_over(
                script_text=full_script_text, output_filename=generated_audio_path,
                voice="en-US-AriaNeural" # Make configurable
            ))
            if actual_audio_path and os.path.exists(actual_audio_path): break
        except Exception as e:
            logging.warning(f"TTS generation attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1: time.sleep(RETRY_DELAY_SECONDS)
            else: logging.error("Max retries for TTS generation reached.", exc_info=True)
    if not actual_audio_path or not os.path.exists(actual_audio_path): logging.error("Failed to generate voice-over. Skipping topic."); return False
    logging.info(f"Voice-over saved to {actual_audio_path}")

    # --- Step 4: SRT Subtitle Generation ---
    logging.info("--- Step 4: SRT Subtitles ---")
    # This step is CPU bound, no network retry needed, but can fail.
    generated_srt_path = None
    try:
        generated_srt_path = generate_srt_from_audio(
            audio_path=actual_audio_path, output_dir=project_dir, model_name="base.en"
        )
    except Exception as e:
        logging.error(f"SRT generation failed: {e}", exc_info=True)
    if not generated_srt_path: logging.warning("SRT generation failed or skipped. Video will be without subtitles.")
    else: logging.info(f"SRT subtitles saved to {generated_srt_path}")

    # --- Step 5: Video Assembly ---
    logging.info("--- Step 5: Video Assembly ---")
    # This step is CPU bound, no network retry, but can fail.
    video_assembly_success = False
    try:
        video_assembler.assemble_video(
            downloaded_media_info_path=downloaded_media_info_path,
            voice_over_path=actual_audio_path,
            output_video_path=output_video_path,
            srt_file_path_input=generated_srt_path if generated_srt_path and os.path.exists(generated_srt_path) else None
        )
        if os.path.exists(output_video_path): # Check if file was actually created
            video_assembly_success = True
            logging.info(f"Video assembly successful for topic '{topic}'. Output: {output_video_path}")
        else:
            logging.error(f"Video assembly completed but output file not found: {output_video_path}")
    except Exception as e:
        logging.error(f"Video assembly for topic '{topic}' failed: {e}", exc_info=True)
    
    return video_assembly_success


def main():
    load_dotenv()
    logging.info("=== Video Pipeline Started ===")

    # Check for CSV file
    if not os.path.exists(CSV_FILENAME):
        logging.error(f"CSV file '{CSV_FILENAME}' not found. Please create it. Exiting.")
        return

    # Load API keys
    api_keys = {
        "gemini": os.getenv("GEMINI_API_KEY"),
        "pexels": os.getenv("PEXELS_API_KEY"),
        "pixabay": os.getenv("PIXABAY_API_KEY")
    }
    if not all(api_keys.values()):
        logging.error("One or more API keys (GEMINI, PEXELS, PIXABAY) are missing in .env. Exiting.")
        return
    
    # Configure Gemini once if your script_generator requires it globally
    if hasattr(script_generator, 'configure_gemini'):
        script_generator.configure_gemini(api_keys["gemini"])


    # Create base output directory
    try:
        os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
    except OSError as e:
        logging.error(f"Could not create base output directory '{OUTPUT_BASE_DIR}': {e}. Exiting.")
        return

    topics_to_process = []
    try:
        with open(CSV_FILENAME, mode='r', encoding='utf-8-sig') as csvfile: # utf-8-sig handles BOM
            reader = csv.DictReader(csvfile)
            if "Topic" not in reader.fieldnames or "Duration" not in reader.fieldnames:
                logging.error("CSV file must contain 'Topic' and 'Duration' headers. Exiting.")
                return
            for row_num, row in enumerate(reader):
                topic = row.get("Topic", "").strip()
                duration_str = row.get("Duration", "").strip()
                if topic and duration_str:
                    topics_to_process.append({"topic": topic, "duration": duration_str, "row": row_num + 2})
                else:
                    logging.warning(f"Skipping row {row_num + 2} in CSV due to missing Topic or Duration.")
    except FileNotFoundError:
        logging.error(f"CSV file '{CSV_FILENAME}' not found. Exiting."); return
    except Exception as e:
        logging.error(f"Error reading CSV file '{CSV_FILENAME}': {e}", exc_info=True); return

    if not topics_to_process:
        logging.info("No topics found in CSV file to process.")
        return

    successful_videos = 0
    failed_videos = 0

    for item in topics_to_process:
        logging.info(f"\nProcessing CSV Row {item['row']}: Topic='{item['topic']}', Duration='{item['duration']}'")
        success = process_single_video(
            topic=item["topic"],
            duration_minutes_str=item["duration"],
            api_keys=api_keys,
            base_output_dir=OUTPUT_BASE_DIR
        )
        if success:
            successful_videos += 1
        else:
            failed_videos += 1
        logging.info("--- Finished processing for this topic. Moving to next if any. ---")
        time.sleep(5) # Small delay between processing topics

    logging.info(f"\n=== Video Pipeline Finished ===")
    logging.info(f"Successfully generated videos: {successful_videos}")
    logging.info(f"Failed video attempts: {failed_videos}")

if __name__ == "__main__":
    # No command-line arguments for start_step in this CSV-driven version by default,
    # as it processes each topic independently. Resuming a specific topic would be complex.
    # We could add a --start_topic_row or similar if needed.
    main()
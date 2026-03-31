# video_assembler.py
import json
import os

from moviepy.editor import (ImageClip, VideoFileClip, AudioFileClip,
                            concatenate_videoclips, CompositeVideoClip, TextClip)
# For MoviePy 1.0.3, SubtitlesClip is in moviepy.video.tools.subtitles
from moviepy.video.tools.subtitles import SubtitlesClip

from moviepy.video.fx.all import resize, crop
import moviepy.config as mpy_config

from PIL import Image

# --- Configuration ---
# Set your desired default resolution
# TARGET_RESOLUTION = (1080, 1920) # 1080p Portrait
TARGET_RESOLUTION = (720, 1280)   # 720p Portrait (More memory friendly for testing)

TARGET_FPS = 30
DEFAULT_IMAGE_DURATION_PER_ITEM = 3.5
MIN_CLIP_DURATION = 1.0

# --- Subtitle Configuration ---
SUBTITLE_FONT = 'Impact' # Ensure this font is available
# Adjust font size based on TARGET_RESOLUTION
SUBTITLE_FONT_SIZE = 60 if TARGET_RESOLUTION[0] == 1080 else 45 # Example adjustment
SUBTITLE_COLOR = 'white'
SUBTITLE_STROKE_COLOR = 'black'
SUBTITLE_STROKE_WIDTH = 3 if TARGET_RESOLUTION[0] == 1080 else 2

# For subtitle animation
SUBTITLE_ANIM_DROP_DISTANCE = 80 if TARGET_RESOLUTION[0] == 1080 else 50
SUBTITLE_ANIM_DURATION = 0.3

# --- Global Toggle for Subtitle Type ---
USE_ANIMATED_SUBTITLES = False # Set to False to use static SubtitlesClip (more memory efficient)

# Configure ImageMagick (ensure path is correct for your system)
try:
    # Use a raw string for Windows paths
    mpy_config.change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})
except Exception as e_imgmagick:
    print(f"Warning: Could not set ImageMagick binary path: {e_imgmagick}. TextClip might use a fallback renderer.")


def get_media_duration(media_path):
    try:
        if media_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            # Use 'with' to ensure the clip is closed after getting duration
            with VideoFileClip(media_path) as clip:
                return clip.duration
        return 0
    except Exception as e:
        print(f"Warning: Could not get duration for {media_path}. Error: {e}")
        return 0

def create_video_segment(media_item, duration, target_resolution):
    media_path = media_item['path']
    clip_type = media_item['type']
    # video_clip_orig_to_close_later = None # Not strictly needed if we manage VideoFileClip instances carefully

    try:
        if clip_type == 'image':
            img_clip = ImageClip(media_path).set_duration(duration)
            # Resize strategy: fill frame, then crop
            img_clip_resized = img_clip.resize(width=target_resolution[0])
            if img_clip_resized.h < target_resolution[1]: # If still not tall enough, resize by height
                img_clip_resized = img_clip.resize(height=target_resolution[1])
            final_img_clip = crop(img_clip_resized,
                                  width=target_resolution[0], height=target_resolution[1],
                                  x_center=img_clip_resized.w / 2, y_center=img_clip_resized.h / 2)
            return final_img_clip.set_fps(TARGET_FPS)

        elif clip_type == 'video':
            # Open VideoFileClip here. It will be processed and the result returned.
            # The returned clip (or its derivatives) will be closed in the main finally block.
            video_clip_orig = VideoFileClip(media_path)
            
            actual_video_duration = video_clip_orig.duration
            if duration > actual_video_duration:
                processed_clip = video_clip_orig.set_duration(actual_video_duration)
            else:
                processed_clip = video_clip_orig.subclip(0, duration)
            
            # If subclip was made, the original 'video_clip_orig' is no longer directly used by 'processed_clip' for its main data
            # MoviePy's subclip should handle its resources. We close video_clip_orig if it's different from processed_clip
            # to free its reader if subclip made a "deep enough" copy.
            # However, to be safer against the NoneType.get_frame error, we avoid closing video_clip_orig here.
            # Its resources will be managed when the returned 'final_video_clip' is closed,
            # or the original 'video_clip_orig' if it was part of a list that gets cleaned up.
            # The current best practice is usually to let the final composite clip manage this,
            # and close all source clips only at the very end.

            resized_clip = processed_clip.resize(width=target_resolution[0])
            if resized_clip.h < target_resolution[1]:
                resized_clip = processed_clip.resize(height=target_resolution[1])
            
            final_video_clip = crop(resized_clip,
                                    width=target_resolution[0], height=target_resolution[1],
                                    x_center=resized_clip.w / 2, y_center=resized_clip.h / 2)

            # Close the original clip if it's different from the processed_clip that was used for further steps
            # This is a tricky balance. If `subclip` makes a truly independent copy, this is fine.
            # If not, it can lead to the NoneType error. Let's defer this.
            # if processed_clip is not video_clip_orig:
            #     video_clip_orig.close() # Defer this to main cleanup

            if final_video_clip.audio is None:
                return final_video_clip.set_fps(TARGET_FPS)
            else:
                return final_video_clip.without_audio().set_fps(TARGET_FPS)
    except Exception as e:
        print(f"Error processing media {media_path}: {e}")
        # No specific original video clip to close here if error happened before its creation or it was an image
        placeholder_path = "media_placeholder_black.png"
        if os.path.exists(placeholder_path):
            return ImageClip(placeholder_path).set_duration(duration).set_fps(TARGET_FPS).resize(target_resolution)
        else:
            return TextClip("Error loading media", fontsize=30, color='white', bg_color='black') \
                   .set_duration(duration).set_fps(TARGET_FPS).resize(target_resolution)

def animate_subtitle_drop_in(text_clip, final_y_pos, anim_duration, drop_distance):
    start_y_pos = final_y_pos - drop_distance
    def position_func(t): # t is relative to the clip's start
        if t < anim_duration:
            # Linear interpolation for y position
            current_y = start_y_pos + (drop_distance / anim_duration) * t
            return ('center', int(current_y))
        else:
            return ('center', int(final_y_pos))
    return text_clip.set_position(position_func)

def generate_subtitle_clips_with_animation(srt_file, video_size, video_fps):
    print(f"Loading subtitles from: {srt_file} for ANIMATED rendering")
    if not os.path.exists(srt_file):
        print(f"Warning: Subtitle file '{srt_file}' not found."); return []
    subtitle_events = []
    try:
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read().strip().replace('\r\n', '\n') # Normalize newlines
            blocks = content.split('\n\n')
            for block in blocks:
                lines = block.split('\n')
                if len(lines) >= 3:
                    time_line = lines[1]; text_lines = " ".join(lines[2:])
                    start_str, end_str = time_line.split(' --> ')
                    def time_str_to_seconds(ts_str):
                        h,m,s_ms = ts_str.split(':'); s,ms = s_ms.split(',')
                        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000
                    start_time = time_str_to_seconds(start_str); end_time = time_str_to_seconds(end_str)
                    subtitle_events.append({'start': start_time, 'end': end_time, 'text': text_lines})
    except Exception as e:
        print(f"Error parsing SRT file {srt_file}: {e}"); return []

    animated_subtitle_clips_list = []
    margin_from_top_percent = 0.10
    final_sub_y_position = int(video_size[1] * margin_from_top_percent + (SUBTITLE_FONT_SIZE / 1.5)) # Adjusted for Impact font

    for event in subtitle_events:
        text, start, end = event['text'], event['start'], event['end']
        duration = end - start
        if duration <= 0: continue
        
        text_clip = TextClip(text,
                             font=SUBTITLE_FONT, fontsize=SUBTITLE_FONT_SIZE, color=SUBTITLE_COLOR,
                             stroke_color=SUBTITLE_STROKE_COLOR, stroke_width=SUBTITLE_STROKE_WIDTH,
                             bg_color='transparent', method='caption', align='center',
                             size=(video_size[0] * 0.9, None) # Max width for text
                            ).set_duration(duration).set_start(start).set_fps(video_fps)
        
        anim_clip = animate_subtitle_drop_in(
            text_clip, final_sub_y_position,
            min(SUBTITLE_ANIM_DURATION, duration * 0.5), # Animation duration not > half clip duration
            SUBTITLE_ANIM_DROP_DISTANCE
        )
        animated_subtitle_clips_list.append(anim_clip)
        
    print(f"Generated {len(animated_subtitle_clips_list)} animated subtitle segments.")
    return animated_subtitle_clips_list

def generate_static_subtitlesclip(srt_file, video_size):
    print(f"Loading subtitles from: {srt_file} for STATIC SubtitlesClip rendering")
    if not os.path.exists(srt_file):
        print(f"Warning: Subtitle file '{srt_file}' not found."); return None
    
    margin_from_top_percent = 0.10
    final_sub_y_position = int(video_size[1] * margin_from_top_percent + (SUBTITLE_FONT_SIZE / 1.5))

    def text_renderer(txt_input): # Parameter name changed to avoid conflict if any
        return TextClip(txt_input,
                        font=SUBTITLE_FONT, fontsize=SUBTITLE_FONT_SIZE, color=SUBTITLE_COLOR,
                        stroke_color=SUBTITLE_STROKE_COLOR, stroke_width=SUBTITLE_STROKE_WIDTH,
                        bg_color='transparent', method='caption', align='center',
                        size=(video_size[0] * 0.9, None))
    try:
        subtitles = SubtitlesClip(srt_file, text_renderer)
        # SubtitlesClip applies to the whole video, position it once.
        return subtitles.set_position(('center', final_sub_y_position))
    except Exception as e:
        print(f"Error creating static SubtitlesClip: {e}"); return None

def assemble_video(downloaded_media_info_path: str,
                   voice_over_path: str,
                   output_video_path: str = "final_video.mp4",
                   srt_file_path_input: str | None = None):
    # Ensure placeholder exists if needed
    if not os.path.exists("media_placeholder_black.png"):
        try: Image.new('RGB', (100,100),color='black').save("media_placeholder_black.png")
        except: print("Could not create placeholder image.")

    # Load media info
    if not os.path.exists(downloaded_media_info_path): print(f"Error: Media info file '{downloaded_media_info_path}' not found."); return
    with open(downloaded_media_info_path, "r", encoding="utf-8") as f: media_items = json.load(f)
    if not media_items: print("No media items found."); return

    # Load audio
    if not os.path.exists(voice_over_path): print(f"Error: Voice-over file '{voice_over_path}' not found."); return
    main_audio = AudioFileClip(voice_over_path)
    total_audio_duration = main_audio.duration
    print(f"Total voice-over duration: {total_audio_duration:.2f} seconds.")
    if total_audio_duration <= 0: print("Error: Voice-over duration invalid."); main_audio.close(); return

    # Prepare video segments
    num_media_items = len(media_items)
    if num_media_items == 0: print("No media items to process."); main_audio.close(); return
    avg_duration_per_item = total_audio_duration / num_media_items
    if avg_duration_per_item < MIN_CLIP_DURATION:
        max_clips_for_audio = int(total_audio_duration / MIN_CLIP_DURATION)
        if num_media_items > max_clips_for_audio and max_clips_for_audio > 0:
            media_items = media_items[:max_clips_for_audio]; num_media_items = len(media_items)
            if num_media_items == 0: main_audio.close(); return # Should not happen
            avg_duration_per_item = total_audio_duration / num_media_items
        elif max_clips_for_audio == 0 and num_media_items > 0: # Very short audio
             avg_duration_per_item = MIN_CLIP_DURATION
    print(f"Target res: {TARGET_RESOLUTION[0]}x{TARGET_RESOLUTION[1]}. Avg duration/visual: {avg_duration_per_item:.2f}s for {num_media_items} items.")

    video_clips_list = []
    current_visual_time_marker = 0
    original_video_files_to_close = [] # Keep track of VideoFileClip objects made in create_video_segment

    for i, item in enumerate(media_items):
        path = item.get('path')
        if not path or not os.path.exists(path): print(f"Skipping invalid item: {path}"); continue
        
        assigned_duration = avg_duration_per_item
        assigned_duration = max(MIN_CLIP_DURATION, assigned_duration)
        if i == num_media_items - 1: # Last clip adjustment
            remaining_audio = total_audio_duration - current_visual_time_marker
            assigned_duration = min(assigned_duration, max(MIN_CLIP_DURATION, remaining_audio))
        assigned_duration = max(0.1, assigned_duration) # Ensure positive duration

        # Create segment
        segment = create_video_segment(item, assigned_duration, TARGET_RESOLUTION)
        if segment:
            video_clips_list.append(segment)
            current_visual_time_marker += segment.duration
            # If segment is a VideoFileClip or derivative, its original might need tracking if create_video_segment
            # doesn't return the VideoFileClip instance that opened the file.
            # The current create_video_segment returns the processed clip, which itself is a VideoFileClip or ImageClip.
            # So, video_clips_list contains the actual clips that need closing.
    
    if not video_clips_list: print("No video clips created."); main_audio.close(); return

    print("Concatenating video clips...")
    base_video = concatenate_videoclips(video_clips_list, method="compose")

    # Sync with audio duration
    if base_video.duration > main_audio.duration:
        base_video = base_video.subclip(0, main_audio.duration)
    base_video_with_audio = base_video.set_audio(main_audio)

    # Prepare final list of clips for compositing (base video + subtitles)
    final_composite_elements = [base_video_with_audio]
    
    # Subtitles part
    subtitle_clips_for_cleanup = [] # For animated subs
    static_subtitle_clip_for_cleanup = None # For static SubtitlesClip

    if srt_file_path_input and os.path.exists(srt_file_path_input):
        if USE_ANIMATED_SUBTITLES:
            animated_subs = generate_subtitle_clips_with_animation(srt_file_path_input, TARGET_RESOLUTION, TARGET_FPS)
            if animated_subs:
                final_composite_elements.extend(animated_subs)
                subtitle_clips_for_cleanup = animated_subs # Store for cleanup
        else: # Use static SubtitlesClip
            static_subs_clip_rendered = generate_static_subtitlesclip(srt_file_path_input, TARGET_RESOLUTION)
            if static_subs_clip_rendered:
                final_composite_elements.append(static_subs_clip_rendered)
                static_subtitle_clip_for_cleanup = static_subs_clip_rendered # Store for cleanup
    else:
        print("SRT file not provided/found. Skipping subtitles.")

    final_video = CompositeVideoClip(final_composite_elements, size=TARGET_RESOLUTION)
    # Ensure final video duration is explicitly set, typically to match the audio/base video
    final_video = final_video.set_duration(base_video_with_audio.duration)

    print(f"Writing final video to: {output_video_path}...")
    try:
        print(f"Attempting to write with QSV hardware acceleration (h264_qsv)...")
        final_video.write_videofile(
            output_video_path, fps=TARGET_FPS, codec="h264_qsv", audio_codec="aac",
            threads=max(1, os.cpu_count()//2 if os.cpu_count() else 1), # Threads may be less critical for HW encoding
            logger="bar", preset="medium" # QSV presets might differ
        )
        print("Video assembly with QSV SUCCESS!")
    except Exception as e_qsv:
        print(f"Error writing video file with QSV: {e_qsv}")
        print("Falling back to software encoder (libx264)...")
        try:
            final_video.write_videofile(
                output_video_path, fps=TARGET_FPS, codec="libx264", audio_codec="aac",
                threads=max(1, os.cpu_count()//2 if os.cpu_count() else 1),
                logger="bar", preset="medium"
            )
            print("Video assembly with libx264 SUCCESS!")
        except Exception as e_sw:
            print(f"Error writing video file with software encoder as well: {e_sw}")
            import traceback; traceback.print_exc()
    finally:
        # Cleanup resources
        def safe_close(clip_to_close):
            if clip_to_close and hasattr(clip_to_close, 'close') and callable(clip_to_close.close):
                try: clip_to_close.close()
                except Exception as e: print(f"Error closing a clip: {e}")

        for c in video_clips_list: safe_close(c) # These are the segments (ImageClip or processed VideoFileClip)
        # Base video clips are compositions of the above, their resources are tied to source clips.
        safe_close(base_video) # This is concatenate_videoclips
        # base_video_with_audio shares resources.
        
        if subtitle_clips_for_cleanup: # List of animated TextClips
            for sub_c in subtitle_clips_for_cleanup: safe_close(sub_c)
        if static_subtitle_clip_for_cleanup: # Single SubtitlesClip
            safe_close(static_subtitle_clip_for_cleanup)
            
        safe_close(final_video) # This is the main CompositeVideoClip
        safe_close(main_audio)
        print("Resource cleanup attempted.")


if __name__ == "__main__":
    # This __main__ block is for direct testing of video_assembler.py
    # Ensure paths are correct relative to where you run this script,
    # or use absolute paths.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Example: If your project files are in a 'projects/my_project_name' structure
    # project_name_example = "dark_matter_short_v1" # Should match your orchestrator's project_name
    # project_dir_example = os.path.join(current_dir, "..", "projects", project_name_example) # If orchestrator is one level up
    
    # For direct testing, assuming files are in the same directory as this script for simplicity:
    project_dir_example = current_dir 

    media_info_file = os.path.join(project_dir_example, "downloaded_media_info_portrait.json")
    voice_over_file = os.path.join(project_dir_example, "voice_over.mp3")
    srt_file_for_subs = os.path.join(project_dir_example, "voice_over.srt")
    
    output_video_file = os.path.join(project_dir_example, "test_video_output_direct.mp4")

    # Create dummy files if they don't exist for testing structure
    if not os.path.exists(media_info_file):
        print(f"Dummying {media_info_file}")
        # Requires a placeholder image like "media_placeholder_black.png" to exist for this dummy to work
        if not os.path.exists("media_placeholder_black.png"): Image.new('RGB',(100,100),color='black').save("media_placeholder_black.png")
        with open(media_info_file, 'w') as f: json.dump([{"path": "media_placeholder_black.png", "type": "image", "width":100, "height":100}], f)
    if not os.path.exists(voice_over_file):
        print(f"Dummying {voice_over_file} - THIS WILL LIKELY CAUSE ISSUES IF NOT A REAL AUDIO FILE")
        # Creating a truly silent MP3 is non-trivial without ffmpeg. This is just a placeholder.
        with open(voice_over_file, 'w') as f: f.write("dummy audio") # Not a valid mp3
    if not os.path.exists(srt_file_for_subs):
        print(f"Dummying {srt_file_for_subs}")
        with open(srt_file_for_subs, 'w') as f: f.write("1\n00:00:01,000 --> 00:00:03,000\nDummy Subtitle\n\n")

    print(f"Attempting to assemble video using files in: {project_dir_example}")
    if os.path.exists(media_info_file) and os.path.exists(voice_over_file):
        assemble_video(media_info_file, voice_over_file, output_video_file, srt_file_path_input=srt_file_for_subs)
    else:
        print("Cannot start direct test assembly: Essential input files missing even after dummy checks.")
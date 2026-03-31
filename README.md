# Video Pipeline Generator

An automated pipeline for generating short educational videos from topics. This script creates complete videos by generating scripts, fetching media, producing voice-overs, and assembling everything into a final video.

## Features

- **Script Generation**: Uses Google's Gemini AI to create structured scripts and visual suggestions based on topics
- **Media Fetching**: Downloads relevant images and videos from Pexels and Pixabay APIs
- **Text-to-Speech**: Generates voice-overs using Microsoft Edge TTS with natural-sounding voices
- **Subtitle Generation**: Creates SRT subtitle files using OpenAI Whisper for accurate timing
- **Video Assembly**: Combines media, audio, and subtitles into portrait-oriented videos using MoviePy
- **Batch Processing**: Processes multiple topics from a CSV file
- **Error Handling**: Robust retry mechanisms for network-dependent operations
- **Logging**: Comprehensive logging for monitoring and debugging

## Requirements

- Python 3.8+
- API Keys for:
  - Google Gemini (for script generation)
  - Pexels (for stock media)
  - Pixabay (for stock media)

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your actual API keys.

## Usage

1. Prepare your topics in `shorts.csv` with columns:
   - `Topic`: The subject for the video
   - `Duration`: Approximate video length in minutes (e.g., "2")

   Example CSV:
   ```
   Topic,Duration
   "The History of Artificial Intelligence",2
   "Climate Change Explained",1.5
   ```

2. Run the pipeline:
   ```bash
   python main.py
   ```

The script will process each topic in the CSV, creating a separate folder for each video with all intermediate files and the final output.

## Output Structure

For each topic, the script creates:
```
generated_videos_output/
└── sanitized_topic_name/
    ├── generated_full_script.txt
    ├── generated_structured_script.json
    ├── media_files/
    │   └── downloaded_media...
    ├── downloaded_media_info_portrait.json
    ├── voice_over.mp3
    ├── voice_over.srt
    └── sanitized_topic_name_video.mp4
```

## Configuration

- **Video Resolution**: Currently set to 720x1280 (portrait). Modify `TARGET_RESOLUTION` in `video_assembler.py` for different sizes.
- **Voice**: Default voice is "en-US-AriaNeural". Change in `main.py` or make it configurable.
- **Whisper Model**: Uses "base.en" for SRT generation. Change in `main.py` for different models.
- **Retry Settings**: Adjust `MAX_RETRIES` and `RETRY_DELAY_SECONDS` in `main.py`.

## Dependencies

- `google-generativeai`: For AI-powered script generation
- `requests`: For API calls to media providers
- `python-dotenv`: For environment variable management
- `edge-tts`: For text-to-speech generation
- `moviepy`: For video editing and assembly
- `pillow`: For image processing
- `openai-whisper`: For speech-to-text subtitle generation

## API Keys Setup

1. **Gemini API**: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. **Pexels API**: Get from [Pexels API](https://www.pexels.com/api/)
3. **Pixabay API**: Get from [Pixabay API](https://pixabay.com/api/docs/)

## Troubleshooting

- Ensure all API keys are correctly set in `.env`
- Check internet connection for API calls
- Monitor `video_pipeline.log` for detailed error messages
- For Whisper issues, ensure FFmpeg is installed (required for audio processing)

## License

This project is for educational purposes. Please respect the terms of service of all APIs used.
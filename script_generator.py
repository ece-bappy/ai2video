# script_generator.py
import google.generativeai as genai
import os
import re # For parsing the response

def configure_gemini(api_key):
    """Configures the Gemini API client."""
    genai.configure(api_key=api_key)
    print("Gemini API configured.")

def generate_script_and_visuals(topic: str, video_duration_minutes: int = 2, domain: str = "history/science"):
    """
    Generates a video script and visual suggestions using the Gemini API.

    Args:
        topic (str): The topic for the video.
        video_duration_minutes (int): Approximate desired length of the video in minutes.
        domain (str): The general domain of the content (e.g., "history", "science", "technology").

    Returns:
        tuple: (structured_content, full_script_text)
               structured_content is a list of dicts, each with 'title', 'script', 'visuals'.
               full_script_text is the concatenated script.
               Returns (None, None) on failure.
    """
    # You can choose different models. 'gemini-1.5-flash-latest' is fast and capable.
    # 'gemini-pro' is also a good general-purpose model.
    model = genai.GenerativeModel('gemini-2.5-flash-preview-04-17')

    prompt = f"""
You are an expert YouTube scriptwriter specializing in creating engaging and informative video scripts
about {domain}. Your goal is to produce content that is both educational and entertaining for a general audience.

TASK:
Generate a complete script for a YouTube video on the topic: "{topic}".
The video should be approximately {video_duration_minutes} minutes long.

SCRIPT STRUCTURE:
1.  **Hook/Intro:** (Approx. 15-30 seconds) - Start with a compelling question, a surprising fact, or a captivating statement to immediately grab the viewer's attention.
2.  **Main Body:** Divide this into 2 to {video_duration_minutes + 1} distinct points or segments. For each point:
    *   Clearly state the main idea or argument of the point.
    *   Provide supporting details, interesting facts, explanations, or brief anecdotes (1-2 paragraphs per point).
3.  **Conclusion/Outro:** (Approx. 15-30 seconds) - Briefly summarize the key takeaways from the video. You can end with a thought-provoking question related to the topic, or a subtle call to action (e.g., "What are your thoughts on this? Share them in the comments below!").

CRITICAL INSTRUCTIONS FOR EACH SECTION (Intro, each Main Body Point, Outro):
*   Provide the **Script Text** for that section.
*   On a new line immediately following the script text for that section, provide a list of 2-4 specific **Visual Keywords** or brief descriptions of suitable stock footage/images. This list MUST start with the prefix "VISUALS: ".
    Example:
    VISUALS: ancient pyramids, bustling marketplace, hieroglyphs glowing, animated map showing trade routes

OUTPUT FORMAT:
*   Use Markdown for the entire response.
*   Use Markdown H2 (##) or H3 (###) for section titles (e.g., "## Introduction", "### Point 1: The Discovery").
*   Ensure a clear separation between the script text and the "VISUALS:" line for each section.
*   Do NOT include any preamble, conversational text, or postamble outside of the requested script structure. Just provide the structured script.
"""

    print(f"\nSending prompt to Gemini for topic: '{topic}' ({video_duration_minutes} min)...")
    try:
        # Note: Consider adding safety_settings if you encounter issues with content blocking
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        # ]
        # response = model.generate_content(prompt, safety_settings=safety_settings)
        response = model.generate_content(prompt)
        
        # print("\n--- RAW GEMINI RESPONSE START ---")
        # print(response.text)
        # print("--- RAW GEMINI RESPONSE END ---\n")

        if response.text:
            return parse_gemini_response(response.text)
        else:
            print("Error: Gemini API returned an empty response.")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                print(f"Prompt Feedback: {response.prompt_feedback}")
            return None, None
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        # Check if response object exists and has prompt_feedback
        if 'response' in locals() and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
            print(f"Prompt Feedback: {response.prompt_feedback}")
        return None, None

def parse_gemini_response(markdown_text: str):
    """
    Parses the Markdown response from Gemini to extract script sections and visual keywords.
    """
    if not markdown_text:
        print("Warning: Empty markdown_text received for parsing.")
        return [], ""

    full_script_text_parts = []
    structured_content = []

    # Split the text into potential sections based on Markdown H2 or H3 headers
    # (?m) enables multi-line mode for ^
    sections = re.split(r'(?m)(?=^##\s|^###\s)', markdown_text)
    sections = [s.strip() for s in sections if s.strip()] # Remove empty strings

    for section_block in sections:
        title = "Unnamed Section"
        script_segment = section_block
        visuals = []

        # Extract title if present (H2 or H3)
        title_match = re.match(r'^(?:##|###)\s*(.*?)\n', section_block, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            # Remove the title line from the script_segment for further processing
            script_segment = section_block[title_match.end():].strip()

        # Find the VISUALS line
        visuals_match = re.search(r'VISUALS:\s*(.*)', script_segment, re.IGNORECASE | re.DOTALL)
        if visuals_match:
            visuals_text = visuals_match.group(1).strip()
            visuals = [v.strip() for v in visuals_text.split(',') if v.strip()]
            # Remove the VISUALS line and anything after it from the script part
            script_segment = script_segment[:visuals_match.start()].strip()
        
        full_script_text_parts.append(script_segment)
        structured_content.append({
            "title": title,
            "script": script_segment,
            "visuals": visuals
        })

    full_script = "\n\n".join(full_script_text_parts).strip()
    return structured_content, full_script

if __name__ == "__main__":
    # This section is for testing this module directly.
    # It will be called from your main orchestrator script later.
    from dotenv import load_dotenv
    load_dotenv() # Load environment variables from .env file

    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key:
        print("Error: GEMINI_API_KEY not found. Make sure it's set in your .env file or as an environment variable.")
    else:
        configure_gemini(gemini_api_key)

        # --- Test Case ---
        # test_topic = "The Secrets of the Mariana Trench"
        # test_duration = 1 # minutes
        # test_domain = "Oceanography and Marine Biology"

        test_topic = "The Fermi Paradox: Where Are All The Aliens?"
        test_duration = 2 # minutes
        test_domain = "Astronomy and Astrobiology"

        print(f"Attempting to generate script for: '{test_topic}'")
        parsed_sections, full_script_content = generate_script_and_visuals(
            topic=test_topic,
            video_duration_minutes=test_duration,
            domain=test_domain
        )

        if parsed_sections:
            print("\n\n--- PARSED SCRIPT SECTIONS ---")
            for i, section in enumerate(parsed_sections):
                print(f"\n--- Section {i+1}: {section['title']} ---")
                print(f"Script: {section['script']}")
                print(f"Visuals: {section['visuals']}")

            print("\n\n--- FULL SCRIPT TEXT ---")
            print(full_script_content)
            
            # Save to files for review
            with open("generated_full_script.txt", "w", encoding="utf-8") as f:
                f.write(full_script_content)
            with open("generated_structured_script.txt", "w", encoding="utf-8") as f:
                import json
                json.dump(parsed_sections, f, indent=2)
            print("\nFull script saved to 'generated_full_script.txt'")
            print("Structured script saved to 'generated_structured_script.txt'")

        else:
            print("\nFailed to generate or parse script.")
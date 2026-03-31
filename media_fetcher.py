# media_fetcher.py
import requests
import os
from dotenv import load_dotenv
import json
import time
import re

# --- API Endpoints ---
PEXELS_API_URL_PHOTOS = "https://api.pexels.com/v1/search"
PEXELS_API_URL_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_API_URL_MEDIA = "https://pixabay.com/api/"
PIXABAY_API_URL_VIDEOS = "https://pixabay.com/api/videos/"

# --- Quality & Orientation Preferences ---
# Target aspect ratio (width / height) for portrait is roughly 9/16 = 0.5625
# We'll consider anything with aspect ratio < 1 as portrait-ish
TARGET_PORTRAIT_ASPECT_RATIO_MAX = 0.8 # Allow some leeway, e.g. 3:4 is 0.75

def is_portrait(width, height):
    if width == 0 or height == 0:
        return False
    return (width / height) <= TARGET_PORTRAIT_ASPECT_RATIO_MAX

def fetch_pexels_media(pexels_api_key: str, query: str, per_page: int = 5, media_type: str = "photos", try_portrait: bool = True):
    """Fetches media from Pexels API, attempting portrait first."""
    url = PEXELS_API_URL_PHOTOS if media_type == "photos" else PEXELS_API_URL_VIDEOS
    headers = {"Authorization": pexels_api_key}
    
    results = []
    
    # Attempt 1: Portrait
    if try_portrait:
        params_portrait = {"query": query, "per_page": per_page, "orientation": "portrait"}
        try:
            # print(f"Pexels: Trying portrait for '{query}' ({media_type})")
            response = requests.get(url, headers=headers, params=params_portrait, timeout=10)
            response.raise_for_status()
            data = response.json()
            results.extend(data[media_type])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching portrait {media_type} from Pexels for '{query}': {e}")
        except KeyError:
            print(f"Error parsing Pexels portrait response for '{query}'.")

    # Attempt 2: Any orientation (if not enough portrait or if try_portrait was false)
    # Only fetch more if we got fewer than per_page results from portrait attempt
    if len(results) < per_page or not try_portrait:
        needed_more = per_page - len(results) if try_portrait else per_page
        params_any = {"query": query, "per_page": needed_more}
        try:
            # print(f"Pexels: Trying any orientation for '{query}' ({media_type})")
            response = requests.get(url, headers=headers, params=params_any, timeout=10)
            response.raise_for_status()
            data = response.json()
            # Add only if not already present (based on ID)
            existing_ids = {item['id'] for item in results}
            for item in data[media_type]:
                if item['id'] not in existing_ids:
                    results.append(item)
                    existing_ids.add(item['id'])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching any {media_type} from Pexels for '{query}': {e}")
        except KeyError:
            print(f"Error parsing Pexels any orientation response for '{query}'.")
            
    return results


def fetch_pixabay_media(pixabay_api_key: str, query: str, per_page: int = 5, media_type: str = "photo", try_portrait: bool = True):
    """Fetches media from Pixabay API. Pixabay has no direct portrait API filter."""
    url = PIXABAY_API_URL_MEDIA if media_type in ["photo", "illustration", "vector"] else PIXABAY_API_URL_VIDEOS
    params = {"key": pixabay_api_key, "q": query, "per_page": per_page * 2, "safesearch": "true"} # Fetch more to filter

    if media_type in ["photo", "illustration", "vector"]:
         params["image_type"] = media_type
    elif media_type == "video":
         params["video_type"] = "film"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", [])
        if not try_portrait: # If not trying portrait, return all fetched up to per_page
            return hits[:per_page]

        # Filter for portrait-like media if try_portrait is True
        portrait_hits = []
        other_hits = []
        for item in hits:
            w_key, h_key = ('imageWidth', 'imageHeight') if media_type != 'video' else ('videos', 'width'), ('videos', 'height')
            
            width, height = 0,0
            if media_type != 'video':
                width = item.get('imageWidth', 0)
                height = item.get('imageHeight', 0)
            else: # For videos, dimensions might be nested
                # Try to get dimensions from 'large' or 'medium' rendition
                vid_details = item.get('videos', {}).get('large') or item.get('videos', {}).get('medium')
                if vid_details:
                    width = vid_details.get('width',0)
                    height = vid_details.get('height',0)
            
            if is_portrait(width, height):
                portrait_hits.append(item)
            else:
                other_hits.append(item)
        
        # Prioritize portrait, then fill with others if needed
        final_results = portrait_hits
        if len(final_results) < per_page:
            final_results.extend(other_hits[:per_page - len(final_results)])
        
        return final_results[:per_page]

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {media_type} from Pixabay for '{query}': {e}")
        return []
    except KeyError:
        print(f"Error parsing Pixabay response for '{query}'.")
        return []


def download_file(url: str, save_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file from {url}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during download from {url}: {e}")
        return False


def fetch_and_download_media(structured_script_content: list, pexels_api_key: str, pixabay_api_key: str, download_base_dir="downloaded_media") -> list:
    all_downloaded_media = []
    os.makedirs(download_base_dir, exist_ok=True)
    print(f"\nStarting media fetching (prioritizing portrait/high-quality) into '{download_base_dir}'...")

    download_count = 0
    max_media_per_keyword = 2
    max_media_per_section = 4 # Slightly reduced to be more selective

    for section_index, section in enumerate(structured_script_content):
        print(f"\nProcessing section {section_index + 1}: '{section['title']}'")
        keywords = section.get('visuals', [])
        if not keywords:
            print("No visual keywords. Skipping media fetch for this section.")
            continue

        section_media_count = 0
        for keyword in keywords:
            if section_media_count >= max_media_per_section:
                print(f"Max media per section reached for '{section['title']}'.")
                break

            print(f"  Searching for media for keyword: '{keyword}'")

            # --- Fetch Videos (Portrait Preferred) ---
            # Pexels videos: API supports orientation filter
            pexels_videos_raw = fetch_pexels_media(pexels_api_key, keyword, per_page=max_media_per_keyword * 2, media_type="videos", try_portrait=True)
            # Pixabay videos: No API orientation filter, try_portrait=True will filter post-fetch
            pixabay_videos_raw = fetch_pixabay_media(pixabay_api_key, keyword, per_page=max_media_per_keyword * 2, media_type="video", try_portrait=True)
            
            videos_to_process = []
            for vid in pexels_videos_raw:
                # Pexels: find highest quality MP4, prefer portrait dimensions from metadata
                highest_res_file = None
                max_h = 0
                for vf in vid.get('video_files', []):
                    if vf.get('file_type') == 'video/mp4':
                        if vf.get('height', 0) > max_h : # Prioritize height for quality
                           # If vf.get('width') < vf.get('height') for portrait video check
                           highest_res_file = vf
                           max_h = vf.get('height',0)
                if highest_res_file:
                     videos_to_process.append({
                         'url': highest_res_file['link'], 'source': 'pexels',
                         'photographer': vid.get('user', {}).get('url', 'N/A'), 'artist': vid.get('user', {}).get('name', 'N/A'),
                         'keyword': keyword, 'type': 'video', 'duration': vid.get('duration'),
                         'width': highest_res_file.get('width', 0), 'height': highest_res_file.get('height', 0),
                         'original_data': vid
                     })

            for vid in pixabay_videos_raw:
                # Pixabay: 'large' is usually best. Dimensions are already filtered by is_portrait in fetch_pixabay_media if try_portrait=True
                rendition = vid.get('videos', {}).get('large') or vid.get('videos', {}).get('medium')
                if rendition:
                    videos_to_process.append({
                        'url': rendition['url'], 'source': 'pixabay',
                        'photographer': f"https://pixabay.com/users/{vid.get('user', 'N_A')}-{vid.get('user_id', 'N_A')}/", 'artist': vid.get('user', 'N_A'),
                        'keyword': keyword, 'type': 'video', 'duration': vid.get('duration'), # Pixabay duration is at top level for video
                        'width': rendition.get('width',0), 'height': rendition.get('height',0),
                        'original_data': vid
                    })
            
            # Sort videos: portrait first, then by height (quality proxy)
            videos_to_process.sort(key=lambda v: (not is_portrait(v['width'], v['height']), -v['height']))

            downloaded_for_keyword_vids = 0
            downloaded_urls = set()
            for video_info in videos_to_process:
                if downloaded_for_keyword_vids >= max_media_per_keyword or section_media_count >= max_media_per_section: break
                if video_info['url'] in downloaded_urls: continue
                
                file_extension = os.path.splitext(video_info['url'])[1] or '.mp4'
                cleaned_keyword = re.sub(r'[^\w\-]+', '_', keyword).strip('_') or "media"
                file_name = f"section_{section_index+1}_vid_kw_{cleaned_keyword}_{downloaded_for_keyword_vids+1}{file_extension}"
                save_path = os.path.join(download_base_dir, f"section_{section_index+1}", file_name)

                print(f"    Downloading video{' (portrait)' if is_portrait(video_info['width'], video_info['height']) else ''}: {file_name} ({video_info['width']}x{video_info['height']})")
                if download_file(video_info['url'], save_path):
                    video_info['path'] = save_path
                    video_info['section_index'] = section_index
                    all_downloaded_media.append(video_info)
                    downloaded_urls.add(video_info['url'])
                    downloaded_for_keyword_vids += 1
                    section_media_count += 1; download_count += 1

            # --- Fetch Images (Portrait Preferred) if not enough videos ---
            if downloaded_for_keyword_vids < max_media_per_keyword and section_media_count < max_media_per_section:
                print(f"  Not enough videos for '{keyword}'. Trying images...")
                pexels_photos_raw = fetch_pexels_media(pexels_api_key, keyword, per_page=max_media_per_keyword * 2, media_type="photos", try_portrait=True)
                pixabay_photos_raw = fetch_pixabay_media(pixabay_api_key, keyword, per_page=max_media_per_keyword * 2, media_type="photo", try_portrait=True)

                images_to_process = []
                for photo in pexels_photos_raw:
                    # Pexels: 'original' or 'large2x' for quality
                    src = photo.get('src', {})
                    url = src.get('original') or src.get('large2x') or src.get('large')
                    if url:
                        images_to_process.append({
                            'url': url, 'source': 'pexels',
                            'photographer': photo.get('photographer_url', 'N/A'), 'artist': photo.get('photographer', 'N/A'),
                            'keyword': keyword, 'type': 'image',
                            'width': photo.get('width', 0), 'height': photo.get('height', 0), # These are original dimensions
                            'original_data': photo
                        })
                for photo in pixabay_photos_raw:
                    # Pixabay: 'fullHDURL' or 'largeImageURL'
                    url = photo.get('fullHDURL') or photo.get('largeImageURL') or photo.get('webformatURL')
                    if url:
                        images_to_process.append({
                            'url': url, 'source': 'pixabay',
                            'photographer': f"https://pixabay.com/users/{photo.get('user', 'N_A')}-{photo.get('user_id', 'N_A')}/", 'artist': photo.get('user', 'N_A'),
                            'keyword': keyword, 'type': 'image',
                            'width': photo.get('imageWidth',0), 'height': photo.get('imageHeight',0), # Original dimensions
                            'original_data': photo
                        })
                
                # Sort images: portrait first, then by area (height*width as quality proxy)
                images_to_process.sort(key=lambda img: (not is_portrait(img['width'], img['height']), -(img['width'] * img['height'])))
                
                downloaded_for_keyword_imgs = 0
                for image_info in images_to_process:
                    if downloaded_for_keyword_imgs >= (max_media_per_keyword - downloaded_for_keyword_vids) or section_media_count >= max_media_per_section : break # Fill remaining slots for keyword
                    if image_info['url'] in downloaded_urls: continue # Avoid re-downloading (though unlikely if URL is unique)
                
                    file_extension = os.path.splitext(image_info['url'].split('?')[0])[1] or '.jpg' # Handle URLs with query params
                    cleaned_keyword = re.sub(r'[^\w\-]+', '_', keyword).strip('_') or "media"
                    file_name = f"section_{section_index+1}_img_kw_{cleaned_keyword}_{downloaded_for_keyword_imgs+1}{file_extension}"
                    save_path = os.path.join(download_base_dir, f"section_{section_index+1}", file_name)

                    print(f"    Downloading image{' (portrait)' if is_portrait(image_info['width'], image_info['height']) else ''}: {file_name} ({image_info['width']}x{image_info['height']})")
                    if download_file(image_info['url'], save_path):
                        image_info['path'] = save_path
                        image_info['section_index'] = section_index
                        all_downloaded_media.append(image_info)
                        downloaded_urls.add(image_info['url'])
                        downloaded_for_keyword_imgs += 1
                        section_media_count += 1; download_count += 1
            
            time.sleep(1.1) # Slightly increased delay

    print(f"\nFinished media fetching. Total downloaded items: {download_count}")
    # Sort all downloaded media by section index, then by type (video first), then by portrait
    all_downloaded_media.sort(key=lambda x: (x['section_index'], x['type'] == 'image', not is_portrait(x.get('width',0), x.get('height',0))))
    return all_downloaded_media


if __name__ == "__main__":
    load_dotenv()
    pexels_api_key = os.getenv("PEXELS_API_KEY")
    pixabay_api_key = os.getenv("PIXABAY_API_KEY")

    if not pexels_api_key or not pixabay_api_key:
        print("Error: PEXELS_API_KEY or PIXABAY_API_KEY not found in .env file.")
    else:
        structured_script_file = "generated_structured_script.txt"
        if os.path.exists(structured_script_file):
            with open(structured_script_file, "r", encoding="utf-8") as f:
                try: test_structured_script = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON from {structured_script_file}: {e}")
                    test_structured_script = []

            if test_structured_script:
                downloaded_media_list = fetch_and_download_media(
                    structured_script_content=test_structured_script,
                    pexels_api_key=pexels_api_key,
                    pixabay_api_key=pixabay_api_key,
                    download_base_dir="downloaded_media_portrait_test" # New folder
                )
                print("\n--- DOWNLOADED MEDIA INFO (PORTRAIT FOCUS) ---")
                if downloaded_media_list:
                    for media_info in downloaded_media_list:
                        orientation = "portrait" if is_portrait(media_info.get('width',0), media_info.get('height',0)) else "landscape/square"
                        print(f"  Sec: {media_info['section_index']+1}, Type: {media_info['type']}, Orient: {orientation}, Res: {media_info.get('width',0)}x{media_info.get('height',0)}, Path: {media_info['path']}")
                    with open("downloaded_media_info_portrait.json", "w", encoding="utf-8") as f: # New JSON
                        json.dump(downloaded_media_list, f, indent=2)
                    print("\nDownloaded media info (portrait focus) saved to 'downloaded_media_info_portrait.json'")
                else: print("No media was downloaded.")
            else: print(f"No structured script content loaded from {structured_script_file}.")
        else: print(f"Error: '{structured_script_file}' not found. Run script_generator.py first.")
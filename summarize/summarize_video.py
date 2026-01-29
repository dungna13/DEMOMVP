import os
import sys
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Force stdout to use utf-8 for Windows console support
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass # Python < 3.7 or other issue


def extract_video_id(url):
    """
    Extracts the video ID from a YouTube URL.
    """
    query = urlparse(url)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    return None

def get_transcript(video_id):
    """
    Fetches the transcript for a given video ID.
    """
    try:
        # Instantiate the API class
        yt_api = YouTubeTranscriptApi()
        
        # content = yt_api.fetch(video_id)
        # return content # This returns an object, we need text.
        
        # Based on debug output: content.snippets is a list of objects with .text
        transcript_obj = yt_api.fetch(video_id)
        
        # Handle cases where fetch might accept languages, but for now let's just fetch default
        # If we need specific languages, we might need to use yt_api.list(video_id) to check and then fetch?
        # Or maybe fetch takes arguments. Let's try simple fetch first as it worked in debug.
        
        if hasattr(transcript_obj, 'snippets'):
             text_list = [s.text for s in transcript_obj.snippets]
             return " ".join(text_list)
        else:
             # Fallback if structure is different
             return str(transcript_obj)

    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def summarize_text(text, api_key):
    """
    Summarizes the provided text using Google Gemini API.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        prompt = f"""
        Hãy tóm tắt nội dung của văn bản sau đây thành một bài viết dễ đọc, nắm bắt được các ý chính quan trọng nhất. 
        Văn bản này là transcript của một video YouTube.
        Hãy viết bằng Tiếng Việt.
        
        Nội dung:
        {text}
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def main():
    if len(sys.argv) > 1:
        video_url = sys.argv[1]
    else:
        video_url = input("Nhập đường dẫn video YouTube (URL): ")

    video_id = extract_video_id(video_url)
    if not video_id:
        print("Không thể tìm thấy ID video hợp lệ từ URL.")
        return

    print(f"Đang lấy transcript cho video ID: {video_id}...")
    transcript = get_transcript(video_id)
    
    if not transcript:
        print("Không thể lấy transcript. Video có thể không có phụ đề.")
        return

    print(f"Đã lấy transcript ({len(transcript)} ký tự). Đang tóm tắt bằng Gemini...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = input("Nhập API Key Google Gemini của bạn: ")
    
    summary = summarize_text(transcript, api_key)
    
    if summary:
        print("\n" + "="*20 + " TÓM TẮT VIDEO " + "="*20 + "\n")
        print(summary)
        print("\n" + "="*55 + "\n")
        
        save_option = input("Bạn có muốn lưu tóm tắt ra file không? (y/n): ")
        if save_option.lower() == 'y':
            with open("summary.txt", "w", encoding="utf-8") as f:
                f.write(summary)
            print("Đã lưu tóm tắt vào summary.txt")

if __name__ == "__main__":
    main()

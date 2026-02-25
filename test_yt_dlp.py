import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import yt_dlp
import asyncio

async def test_yt_dlp():
    print("Testing yt-dlp installation...")
    try:
        # Try to extract info from a simple YouTube video
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',  # don't resolve each entry, fast listing
            'skip_download': True,
            'socket_timeout': 20,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        print("✅ yt-dlp is working")
        print(f"Video title: {info.get('title')}")
        print(f"Video ID: {info.get('id')}")
        
        return True, "yt-dlp is working"
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, str(e)

if __name__ == "__main__":
    try:
        asyncio.run(test_yt_dlp())
    except Exception as e:
        print(f"Fatal error: {e}")
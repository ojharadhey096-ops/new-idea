from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks, File, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import yt_dlp
import json
import os
from datetime import datetime
import aiofiles
import shutil
import asyncio
try:
    from telegram_client import fetch_videos_from_channel
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")
templates = Jinja2Templates(directory="templates")

VIDEO_DB = "video_db.json"
FOLDER_DB = "folder_db.json"

def load_db():
    try:
        with open(VIDEO_DB, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_db(db):
    with open(VIDEO_DB, 'w') as f:
        json.dump(db, f, indent=2)

def load_folder_db():
    try:
        with open(FOLDER_DB, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_folder_db(db):
    with open(FOLDER_DB, 'w') as f:
        json.dump(db, f, indent=2)

def build_folder_hierarchy():
    """Build hierarchical folder structure from videos and folders"""
    db = load_db()
    folder_db = load_folder_db()

    # Get all unique folder paths
    folders = {}
    for video in db.values():
        folder_path = video.get('folder_path', video.get('folder_name', ''))
        if folder_path:
            folders[folder_path] = folders.get(folder_path, 0) + 1

    # Add folders from folder_db
    for folder_name, folder_info in folder_db.items():
        if folder_name not in folders:
            folders[folder_name] = 0

    # Build hierarchy
    hierarchy = {}
    for folder_path, count in folders.items():
        parts = folder_path.split('/')
        current = hierarchy
        for part in parts:
            if part not in current:
                current[part] = {'count': 0, 'subfolders': {}}
            current = current[part]['subfolders']
        # Set count on the deepest level
        if parts:
            current = hierarchy
            for part in parts[:-1]:
                current = current[part]['subfolders']
            current[parts[-1]]['count'] = count

    return hierarchy

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = load_db()
    folder_hierarchy = build_folder_hierarchy()
    all_videos = list(db.values())
    # Sort videos by added time (newest first)
    all_videos.sort(key=lambda x: x.get('added_time', ''), reverse=True)
    return templates.TemplateResponse("index.html", {"request": request, "folder_hierarchy": folder_hierarchy, "videos": all_videos})

@app.get("/folder/{folder_path:path}", response_class=HTMLResponse)
async def folder_page(request: Request, folder_path: str):
    db = load_db()
    folder_db = load_folder_db()

    # Find videos in this folder and subfolders
    videos = []
    for video in db.values():
        video_folder = video.get('folder_path', video.get('folder_name', ''))
        if video_folder == folder_path or video_folder.startswith(folder_path + '/'):
            videos.append(video)

    # Get subfolders
    subfolders = {}
    for folder_name in folder_db:
        if folder_name.startswith(folder_path + '/') and folder_name.count('/') == folder_path.count('/') + 1:
            subfolder_name = folder_name.split('/')[-1]
            subfolders[subfolder_name] = folder_name

    return templates.TemplateResponse("folder.html", {
        "request": request,
        "folder_path": folder_path,
        "folder_name": folder_path.split('/')[-1],
        "videos": videos,
        "subfolders": subfolders
    })

@app.get("/watch/{video_id}", response_class=HTMLResponse)
async def watch(request: Request, video_id: str):
    db = load_db()
    video = db.get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    # Increment views
    video['views_count'] = video.get('views_count', 0) + 1
    save_db(db)
    return templates.TemplateResponse("watch.html", {"request": request, "video": video})

@app.post("/add_video")
async def add_video(background_tasks: BackgroundTasks, url: str = Form(...), folder_path: str = Form(None), new_folder: str = Form(None)):
    # Use new_folder if provided, otherwise use folder_path
    actual_folder = new_folder if new_folder else folder_path
    if not actual_folder:
        return {"error": "Folder path is required"}, 400
    background_tasks.add_task(process_video, url, actual_folder)
    return {"message": "Video processing started"}

@app.get("/api/folders")
async def get_folders():
    folder_hierarchy = build_folder_hierarchy()

    # Flatten hierarchy for backward compatibility
    def flatten_hierarchy(hierarchy, prefix=""):
        folders = []
        for name, data in hierarchy.items():
            full_path = f"{prefix}/{name}" if prefix else name
            folders.append({
                'name': full_path,
                'display_name': name,
                'count': data['count'],
                'path': full_path,
                'has_subfolders': bool(data['subfolders'])
            })
            # Recursively add subfolders
            folders.extend(flatten_hierarchy(data['subfolders'], full_path))
        return folders

    folders = flatten_hierarchy(folder_hierarchy)
    return {"folders": folders}

@app.get("/api/stream/{video_id}")
async def get_stream(video_id: str):
    """Get streaming URL for a video"""
    db = load_db()
    video = db.get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    try:
        # Extract stream URL using yt-dlp
        url = video['source_url']
        
        # Try to get direct MP4/WebM URL
        ydl_opts = {
            'format': '18',  # 18 is MP4 format on YouTube
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info.get('url')
                
                if stream_url:
                    return {
                        "stream_url": stream_url,
                        "title": info.get('title', video.get('title')),
                        "duration": info.get('duration', 0),
                        "format": "mp4"
                    }
        except:
            pass
        
        # Fallback - try best format
        ydl_opts2 = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts2) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            
            if stream_url:
                return {
                    "stream_url": stream_url,
                    "title": info.get('title', video.get('title')),
                    "duration": info.get('duration', 0),
                    "format": "unknown"
                }
        
        # If we still don't have URL, use fallback embed
        return {
            "stream_url": None,
            "fallback_embed": f"https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&rel=0",
            "error": "Could not extract direct stream",
            "title": video.get('title')
        }
        
    except Exception as e:
        print(f"Error extracting stream: {e}")
        # Return fallback with embed URL
        return {
            "stream_url": None,
            "fallback_embed": f"https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&rel=0",
            "error": str(e),
            "title": video.get('title')
        }


@app.post("/api/rename_folder")
async def rename_folder(old_name: str = Form(...), new_name: str = Form(...)):
    """Rename a folder and update all videos in it"""
    db = load_db()
    
    # Update all videos with the old folder name
    for video in db.values():
        if video['folder_name'] == old_name:
            video['folder_name'] = new_name
    
    # Rename physical folder
    old_path = os.path.join("videos", old_name)
    new_path = os.path.join("videos", new_name)
    
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    
    save_db(db)
    return {"message": f"Folder renamed from {old_name} to {new_name}"}



@app.get("/api/telegram/channels")
async def get_telegram_channels():
    """Get list of configured Telegram channels"""
    if not TELEGRAM_AVAILABLE:
        return {"error": "Telegram client not available", "channels": []}
    
    import config
    channels = config.CHANNELS or []
    return {"channels": channels}

@app.get("/api/telegram/sync/{channel}")
async def sync_telegram_channel(channel: str, background_tasks: BackgroundTasks):
    """Sync videos from a Telegram channel"""
    if not TELEGRAM_AVAILABLE:
        raise HTTPException(status_code=400, detail="Telegram client not available")
    
    try:
        # Queue background task
        background_tasks.add_task(fetch_and_store_telegram_videos, channel)
        return {"message": f"Syncing channel: {channel}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/telegram/videos")
async def get_telegram_videos():
    """Get all Telegram videos from cache"""
    try:
        import config
        cache_file = config.VIDEO_CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

async def fetch_and_store_telegram_videos(channel: str):
    """Background task to fetch and store Telegram videos"""
    if not TELEGRAM_AVAILABLE:
        return
    
    try:
        videos = await fetch_videos_from_channel(channel)
        db = load_db()
        
        for video in videos:
            unique_id = video.get('unique_video_id')
            if unique_id and unique_id not in db:
                # Convert Telegram video to database format
                db[unique_id] = {
                    'video_id': unique_id,
                    'title': video.get('title', 'Telegram Video'),
                    'source_url': f"/api/telegram/download/{unique_id}",
                    'folder_name': f"📱 {video.get('channel_name', 'Telegram')}",
                    'embed_url': f"/watch/{unique_id}",
                    'thumbnail_path': video.get('thumbnail_path', ''),
                    'duration': video.get('duration', 0),
                    'file_size': video.get('file_size', 0),
                    'added_time': datetime.now().isoformat(),
                    'views_count': 0,
                    'source_type': 'telegram',
                    'file_id': video.get('file_id', ''),
                    'message_id': video.get('message_id'),
                    'channel_id': video.get('channel_id')
                }
        
        save_db(db)
        print(f"Synced {len(videos)} videos from {channel}")
    except Exception as e:
        print(f"Error syncing Telegram channel: {e}")

async def process_video(url: str, folder_name: str):
    try:
        # Extract video_id from URL - YouTube IDs are exactly 11 alphanumeric/dash characters
        import re
        # Try different URL patterns
        patterns = [
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/live/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',  # Allow longer IDs as fallback
            r'youtu\.be/([a-zA-Z0-9_-]+)',  # Allow longer IDs as fallback
        ]
        
        video_id = None
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                extracted_id = match.group(1)
                # Validate: YouTube video IDs should be 11 characters
                if len(extracted_id) == 11:
                    video_id = extracted_id
                    break
                # If not 11 chars, it might be a live video or playlist - try anyway
                elif len(extracted_id) > 0:
                    video_id = extracted_id
                    break
        
        if not video_id:
            print(f"Invalid YouTube URL: {url}")
            return
        
        # Clean video_id - ensure no special characters except dash and underscore
        video_id = video_id.strip()

        # Check if exists
        db = load_db()
        if video_id in db:
            print("Video already exists")
            return

        # Create folder if it doesn't exist
        folder_path = os.path.join("videos", folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Use embed URL for YouTube
        embed_url = f"https://www.youtube.com/embed/{video_id}"

        # Use basic info (yt-dlp causing issues)
        title = f"YouTube Video {video_id}"
        duration = 0
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        # Download thumbnail
        thumbnail_path = os.path.join("static", "thumbnails", f"{video_id}.jpg")
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        try:
            import urllib.request
            urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
        except:
            # Create a placeholder
            with open(thumbnail_path, 'wb') as f:
                f.write(b'')  # Empty file

        # Save to db
        db[video_id] = {
            'video_id': video_id,
            'title': title,
            'source_url': url,
            'folder_path': folder_name,  # Changed from folder_name to folder_path
            'folder_name': folder_name.split('/')[-1],  # Keep for backward compatibility
            'embed_url': embed_url,
            'thumbnail_path': thumbnail_path,
            'duration': duration,
            'file_size': 0,  # Not downloaded
            'added_time': datetime.now().isoformat(),
            'views_count': 0
        }
        save_db(db)
        print(f"Video added: {title}")
    except Exception as e:
        print(f"Error processing video: {e}")

@app.post("/api/delete_folder")
async def delete_folder(folder_name: str = Form(...)):
    """Delete a folder and all its videos from the database and filesystem"""
    db = load_db()

    # Remove all videos in the folder
    videos_to_delete = [video_id for video_id, video in db.items() if video['folder_name'] == folder_name]

    for video_id in videos_to_delete:
        del db[video_id]

    save_db(db)

    # Delete physical folder if it exists and is empty
    folder_path = os.path.join("videos", folder_name)
    try:
        if os.path.exists(folder_path):
            # Check if folder is empty or only contains .gitkeep or similar
            if not os.listdir(folder_path):
                os.rmdir(folder_path)
            else:
                # If not empty, still remove it (videos folder should be managed by database)
                import shutil
                shutil.rmtree(folder_path)
    except Exception as e:
        print(f"Warning: Could not delete physical folder {folder_path}: {e}")

    return {"message": f"Folder '{folder_name}' and all its videos deleted successfully"}

@app.post("/api/create_subfolder")
async def create_subfolder(parent_path: str = Form(...), subfolder_name: str = Form(...)):
    """Create a new subfolder"""
    if not subfolder_name or not subfolder_name.strip():
        raise HTTPException(status_code=400, detail="Subfolder name is required")

    folder_db = load_folder_db()
    new_folder_path = f"{parent_path}/{subfolder_name.strip()}" if parent_path else subfolder_name.strip()

    if new_folder_path in folder_db:
        raise HTTPException(status_code=400, detail="Folder already exists")

    # Create physical folder
    folder_physical_path = os.path.join("videos", new_folder_path)
    os.makedirs(folder_physical_path, exist_ok=True)

    # Save to folder database
    folder_db[new_folder_path] = {
        'name': subfolder_name.strip(),
        'path': new_folder_path,
        'parent_path': parent_path,
        'created_time': datetime.now().isoformat()
    }
    save_folder_db(folder_db)

    return {"message": f"Subfolder '{subfolder_name}' created successfully", "folder_path": new_folder_path}

@app.post("/api/move_video")
async def move_video(video_id: str = Form(...), new_folder_path: str = Form(...)):
    """Move a video to a different folder"""
    db = load_db()
    folder_db = load_folder_db()

    if video_id not in db:
        raise HTTPException(status_code=404, detail="Video not found")

    if new_folder_path and new_folder_path not in folder_db:
        raise HTTPException(status_code=400, detail="Target folder does not exist")

    video = db[video_id]
    old_folder = video.get('folder_path', video.get('folder_name', ''))

    # Update video folder
    video['folder_path'] = new_folder_path
    video['folder_name'] = new_folder_path.split('/')[-1] if new_folder_path else ''

    save_db(db)
    return {"message": f"Video moved from '{old_folder}' to '{new_folder_path}'"}

@app.post("/api/copy_video")
async def copy_video(video_id: str = Form(...), new_folder_path: str = Form(...)):
    """Copy a video to a different folder"""
    db = load_db()
    folder_db = load_folder_db()

    if video_id not in db:
        raise HTTPException(status_code=404, detail="Video not found")

    if new_folder_path and new_folder_path not in folder_db:
        raise HTTPException(status_code=400, detail="Target folder does not exist")

    video = db[video_id]
    new_video_id = f"{video_id}_copy_{int(datetime.now().timestamp())}"

    # Create copy of video
    new_video = video.copy()
    new_video['video_id'] = new_video_id
    new_video['folder_path'] = new_folder_path
    new_video['folder_name'] = new_folder_path.split('/')[-1] if new_folder_path else ''
    new_video['added_time'] = datetime.now().isoformat()
    new_video['views_count'] = 0

    db[new_video_id] = new_video
    save_db(db)

    return {"message": f"Video copied to '{new_folder_path}'", "new_video_id": new_video_id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
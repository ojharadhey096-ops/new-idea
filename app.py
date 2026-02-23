from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks, File, UploadFile, Response, Cookie
from starlette.responses import RedirectResponse
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import yt_dlp
import json
import os
import secrets
import bcrypt
from datetime import datetime, timedelta
import aiofiles
import shutil
from auth import get_current_user, authenticate_user, register_user
import asyncio

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Only mount videos directory if it exists
import os
if os.path.exists("videos"):
    app.mount("/videos", StaticFiles(directory="videos"), name="videos")

templates = Jinja2Templates(directory="templates")

# Public landing page (modern animated)
@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

# About page
@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

# Contact page
@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})

# Public auth helper routes (aliases) for forgot/reset to avoid 404s
@app.get("/auth/forgot", response_class=HTMLResponse)
async def forgot_password_form_auth(request: Request):
    return templates.TemplateResponse("forgot.html", {"request": request})

@app.post("/auth/forgot", response_class=HTMLResponse)
async def forgot_password_request_auth(request: Request, username_or_email: str = Form(...)):
    return await forgot_password_request(request, username_or_email)

@app.get("/auth/reset", response_class=HTMLResponse)
async def reset_form_auth(request: Request, token: str):
    return templates.TemplateResponse("reset.html", {"request": request, "token": token})

@app.post("/auth/reset", response_class=HTMLResponse)
async def reset_password_auth(token: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    return await reset_password(token, new_password, confirm_password)

# ===== Forgot Password Flow =====
RESET_DB = "reset_tokens.json"

def load_reset_tokens():
    try:
        with open(RESET_DB, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    # prune expired
    now = datetime.now()
    changed = False
    for tok, meta in list(data.items()):
        try:
            exp = datetime.fromisoformat(meta.get('expires_at'))
            if exp < now:
                del data[tok]
                changed = True
        except Exception:
            del data[tok]
            changed = True
    if changed:
        save_reset_tokens(data)
    return data

def save_reset_tokens(data):
    with open(RESET_DB, 'w') as f:
        json.dump(data, f, indent=2)

# Support trailing slash aliases
@app.get("/forgot/", response_class=HTMLResponse)
async def forgot_password_form_alias(request: Request):
    return await forgot_password_form(request)

@app.get("/forgot", response_class=HTMLResponse)
async def forgot_password_form(request: Request):
    html = """
    <!DOCTYPE html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Forgot Password • VideoHub</title>
    <link rel='stylesheet' href='/static/css/youtube.css'>
    <style>.box{max-width:460px;margin:80px auto;padding:1.2rem;border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);} .h{margin:0 0 .6rem;color:var(--primary-color);} .g{display:grid;gap:.6rem} input{padding:.6rem;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-color);color:var(--text-primary)} .btn{padding:.6rem 1rem;border:none;border-radius:8px;background:var(--primary-color);color:#fff;font-weight:700;cursor:pointer;width:100%} a{color:var(--primary-color);}</style>
    </head><body>
      <div class='box'>
        <h2 class='h'>Forgot password</h2>
        <p>Enter your username or email. If we find a match, we'll generate a reset link.</p>
        <form method='post' action='/forgot' class='g'>
          <input type='text' name='username_or_email' placeholder='Username or email' required>
          <button class='btn' type='submit'>Generate reset link</button>
        </form>
        <p style='margin-top:.6rem'><a href='/login'>&larr; Back to Login</a></p>
      </div>
    </body></html>
    """
    return HTMLResponse(content=html)

@app.post("/forgot/", response_class=HTMLResponse)
async def forgot_password_request_alias(request: Request, username_or_email: str = Form(...)):
    return await forgot_password_request(request, username_or_email)

@app.post("/forgot", response_class=HTMLResponse)
async def forgot_password_request(request: Request, username_or_email: str = Form(...)):
    # Find user by username or email
    from auth import load_users
    users = load_users()
    target_username = None
    for uname, u in users.items():
        if uname == username_or_email or u.get('email') == username_or_email:
            target_username = uname
            break

    # Always respond success to avoid user enumeration
    link_html = ""
    if target_username:
        tokens = load_reset_tokens()
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
        tokens[token] = { 'username': target_username, 'created_at': datetime.now().isoformat(), 'expires_at': expires_at }
        save_reset_tokens(tokens)
        # Provide link directly (dev/demo). In production you would email this.
        reset_link = f"/reset?token={token}"
        link_html = f"<p style='background:rgba(0,230,255,.1);border:1px solid rgba(0,230,255,.35);padding:.6rem;border-radius:8px;'>Reset link (valid 1h): <a href='{reset_link}'>{reset_link}</a></p>"

    html = f"""
    <!DOCTYPE html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Reset Link Sent • VideoHub</title>
    <link rel='stylesheet' href='/static/css/youtube.css'>
    <style>.box{{max-width:460px;margin:80px auto;padding:1.2rem;border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);}} .h{{margin:0 0 .6rem;color:var(--primary-color);}} a{{color:var(--primary-color);}}</style>
    </head><body>
      <div class='box'>
        <h2 class='h'>If the account exists, a reset link is available below.</h2>
        {link_html}
        <p><a href='/login'>&larr; Back to Login</a></p>
      </div>
    </body></html>
    """
    return HTMLResponse(content=html)

@app.get("/reset/", response_class=HTMLResponse)
async def reset_form_alias(request: Request, token: str):
    return await reset_form(request, token)

@app.get("/reset", response_class=HTMLResponse)
async def reset_form(request: Request, token: str):
    tokens = load_reset_tokens()
    meta = tokens.get(token)
    valid = False
    if meta:
        try:
            valid = datetime.fromisoformat(meta.get('expires_at')) >= datetime.now()
        except Exception:
            valid = False
    if not valid:
        return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Invalid or expired token. <a href='/forgot'>Request a new link</a>.</div>")

    html = f"""
    <!DOCTYPE html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Reset Password • VideoHub</title>
    <link rel='stylesheet' href='/static/css/youtube.css'>
    <style>.box{{max-width:460px;margin:80px auto;padding:1.2rem;border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);}} .g{{display:grid;gap:.6rem}} input{{padding:.6rem;border:1px solid var(--border-color);border-radius:8px;background:var(--bg-color);color:var(--text-primary)}} .btn{{padding:.6rem 1rem;border:none;border-radius:8px;background:var(--primary-color);color:#fff;font-weight:700;cursor:pointer;width:100%}}</style>
    </head><body>
      <div class='box'>
        <h2 style='margin:0 0 .6rem;color:var(--primary-color)'>Choose a new password</h2>
        <form method='post' action='/reset' class='g'>
          <input type='hidden' name='token' value='{token}'>
          <input type='password' name='new_password' placeholder='New password' minlength='6' required>
          <input type='password' name='confirm_password' placeholder='Confirm password' minlength='6' required>
          <button class='btn' type='submit'>Reset Password</button>
        </form>
        <p style='margin-top:.6rem'><a href='/login'>&larr; Back to Login</a></p>
      </div>
    </body></html>
    """
    return HTMLResponse(content=html)

@app.post("/reset/", response_class=HTMLResponse)
async def reset_password_alias(token: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    return await reset_password(token, new_password, confirm_password)

@app.post("/reset", response_class=HTMLResponse)
async def reset_password(token: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    if new_password != confirm_password:
        return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Passwords do not match. <a href='/reset?token={token}'>Try again</a>.</div>")

    tokens = load_reset_tokens()
    meta = tokens.get(token)
    if not meta:
        return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Invalid or expired token. <a href='/forgot'>Request new link</a>.</div>")

    try:
        if datetime.fromisoformat(meta.get('expires_at')) < datetime.now():
            del tokens[token]
            save_reset_tokens(tokens)
            return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Token expired. <a href='/forgot'>Request new link</a>.</div>")
    except Exception:
        del tokens[token]
        save_reset_tokens(tokens)
        return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Invalid token. <a href='/forgot'>Request new link</a>.</div>")

    # Update user's password
    from auth import load_users, save_users
    users = load_users()
    uname = meta.get('username')
    if uname not in users:
        # Clean token and fail
        del tokens[token]
        save_reset_tokens(tokens)
        return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>User not found. <a href='/forgot'>Request new link</a>.</div>")

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    users[uname]['password_hash'] = hashed
    save_users(users)

    # Invalidate token
    del tokens[token]
    save_reset_tokens(tokens)

    return HTMLResponse("<div style='max-width:460px;margin:80px auto;font-family:sans-serif'>Password has been reset. <a href='/login'>Login</a>.</div>")

VIDEO_DB = "video_db.json"
FOLDER_DB = "folder_db.json"

# Notifications and playlist subscriptions
NOTIF_DB = "notifications.json"
SUBS_DB = "subscriptions.json"

def load_json_file(path, default):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default

# Notifications utilities
def load_notifications_db():
    return load_json_file(NOTIF_DB, {})

def save_notifications_db(db):
    with open(NOTIF_DB, 'w') as f:
        json.dump(db, f, indent=2)

def get_user_notifications(username):
    db = load_notifications_db()
    return db.get(username, [])

def add_notification(username, notif):
    db = load_notifications_db()
    user_list = db.get(username, [])
    # Ensure id
    nid = notif.get('id') or f"n_{int(datetime.now().timestamp())}_{secrets.token_hex(3)}"
    notif['id'] = nid
    notif['created_at'] = notif.get('created_at') or datetime.now().isoformat()
    notif['read'] = False if notif.get('read') is None else bool(notif['read'])
    user_list.insert(0, notif)
    db[username] = user_list
    save_notifications_db(db)
    return nid

# Subscriptions utilities
def load_subscriptions():
    return load_json_file(SUBS_DB, {})

def save_subscriptions(db):
    with open(SUBS_DB, 'w') as f:
        json.dump(db, f, indent=2)

def add_subscription(username, playlist_id, folder_path, title=None):
    subs = load_subscriptions()
    user_subs = subs.get(username, {"playlists": {}})
    playlists = user_subs.get("playlists", {})
    playlists[playlist_id] = {
        "folder_path": folder_path,
        "title": title or playlist_id,
        "last_checked_at": datetime.now().isoformat()
    }
    user_subs["playlists"] = playlists
    subs[username] = user_subs
    save_subscriptions(subs)

# Authentication routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })

    from auth import create_access_token
    token = create_access_token({"sub": username})

    # Redirect admin users to admin panel, others to home
    redirect_url = "/admin" if user.get("role") == "admin" else "/"
    response = RedirectResponse(redirect_url, status_code=302)
    response.set_cookie(key="auth_token", value=token, httponly=True, max_age=6*30*24*60*60)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = None, success: str = None):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": error,
        "success": success
    })

@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Passwords do not match"
        })

    try:
        user = register_user(username, email, password)
        return templates.TemplateResponse("register.html", {
            "request": request,
            "success": "Account created successfully! Pending admin approval before you can log in."
        })
    except HTTPException as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": e.detail
        })

@app.post("/logout")
async def logout(response: Response):
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("auth_token")
    return response

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

def build_user_folder_hierarchy(username):
    """Build folder hierarchy for a specific user"""
    db = load_db()
    folder_db = load_folder_db()

    # Get user's folder paths
    folders = {}
    for video in db.values():
        if video.get('user_id') == username:
            folder_path = video.get('folder_path', video.get('folder_name', ''))
            if folder_path:
                folders[folder_path] = folders.get(folder_path, 0) + 1

    # Add user's folders from folder_db
    for folder_name, folder_info in folder_db.items():
        if folder_info.get('user_id') == username:
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
async def home(request: Request, auth_token: str = Cookie(None)):
    # Check if user is authenticated
    if not auth_token:
        return RedirectResponse("/login", status_code=302)

    try:
        from auth import verify_token
        username = verify_token(auth_token)
        if not username:
            return RedirectResponse("/login", status_code=302)

        from auth import load_users
        users = load_users()
        if username not in users:
            return RedirectResponse("/login", status_code=302)

        user = users[username]
    except Exception:
        return RedirectResponse("/login", status_code=302)

    db = load_db()

    # Filter videos by current user
    user_videos = [video for video in db.values() if video.get('user_id') == user['username']]
    user_videos.sort(key=lambda x: x.get('added_time', ''), reverse=True)

    # Build user-specific folder hierarchy
    folder_hierarchy = build_user_folder_hierarchy(user['username'])

    return templates.TemplateResponse("index.html", {
        "request": request,
        "folder_hierarchy": folder_hierarchy,
        "videos": user_videos,
        "current_user": user
    })

@app.get("/folder/{folder_path:path}", response_class=HTMLResponse)
async def folder_page(request: Request, folder_path: str, auth_token: str = Cookie(None)):
    # Check authentication
    if not auth_token:
        return RedirectResponse("/login", status_code=302)

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            return RedirectResponse("/login", status_code=302)
        user = users[username]
    except Exception:
        return RedirectResponse("/login", status_code=302)

    db = load_db()
    folder_db = load_folder_db()

    # Find user's videos in this folder and subfolders
    videos = []
    for video in db.values():
        if video.get('user_id') == username:
            video_folder = video.get('folder_path', video.get('folder_name', ''))
            if video_folder == folder_path or video_folder.startswith(folder_path + '/'):
                videos.append(video)

    # Get user's subfolders
    subfolders = {}
    for folder_name, folder_info in folder_db.items():
        if (folder_info.get('user_id') == username and
            folder_name.startswith(folder_path + '/') and
            folder_name.count('/') == folder_path.count('/') + 1):
            subfolder_name = folder_name.split('/')[-1]
            subfolders[subfolder_name] = folder_name

    return templates.TemplateResponse("folder.html", {
        "request": request,
        "folder_path": folder_path,
        "folder_name": folder_path.split('/')[-1],
        "videos": videos,
        "subfolders": subfolders,
        "current_user": user
    })

@app.get("/watch/{video_id}", response_class=HTMLResponse)
async def watch(request: Request, video_id: str, auth_token: str = Cookie(None)):
    # Check authentication
    if not auth_token:
        return RedirectResponse("/login", status_code=302)

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            return RedirectResponse("/login", status_code=302)
        user = users[username]
    except Exception:
        return RedirectResponse("/login", status_code=302)

    db = load_db()
    video = db.get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check if video belongs to user
    if video.get('user_id') != username:
        raise HTTPException(status_code=403, detail="Access denied")

    # Increment views
    video['views_count'] = video.get('views_count', 0) + 1
    save_db(db)
    return templates.TemplateResponse("watch.html", {"request": request, "video": video, "current_user": user})

@app.post("/add_video")
async def add_video(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    folder_path: str = Form(None),
    new_folder: str = Form(None),
    auth_token: str = Cookie(None)
):
    # Verify user authentication
    if not auth_token:
        return {"error": "Authentication required"}, 401

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            return {"error": "User not found"}, 401
        user = users[username]
    except Exception:
        return {"error": "Invalid authentication"}, 401

    # Use new_folder if provided, otherwise use folder_path
    actual_folder = new_folder if new_folder else folder_path
    if not actual_folder:
        return {"error": "Folder path is required"}, 400

    # Run process_video in background
    async def process_and_notify():
        success, result = await process_video(url, actual_folder, username)
        if success:
            print(f"Successfully processed {result} video(s)")
        else:
            print(f"Processing failed: {result}")
    
    background_tasks.add_task(process_and_notify)
    return {"message": "Video processing started"}

@app.get("/api/folders")
async def get_folders(auth_token: str = Cookie(None)):
    # Check authentication
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    folder_hierarchy = build_user_folder_hierarchy(username)

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
async def get_stream(video_id: str, auth_token: str = Cookie(None)):
    """Get streaming URL for a video"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    db = load_db()
    video = db.get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check if video belongs to user
    if video.get('user_id') != username:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
        yt = video.get('yt_id', video_id)
        return {
            "stream_url": None,
            "fallback_embed": f"https://www.youtube.com/embed/{yt}?autoplay=1&controls=1&rel=0",
            "error": "Could not extract direct stream",
            "title": video.get('title')
        }
        
    except Exception as e:
        print(f"Error extracting stream: {e}")
        # Return fallback with embed URL
        yt = video.get('yt_id', video_id)
        return {
            "stream_url": None,
            "fallback_embed": f"https://www.youtube.com/embed/{yt}?autoplay=1&controls=1&rel=0",
            "error": str(e),
            "title": video.get('title')
        }


@app.post("/api/rename_folder")
async def rename_folder(old_name: str = Form(...), new_name: str = Form(...), auth_token: str = Cookie(None)):
    """Rename a folder and update all videos in it"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    db = load_db()
    folder_db = load_folder_db()

    # Update all user's videos with the old folder name
    for video in db.values():
        if video.get('user_id') == username and video.get('folder_name') == old_name:
            video['folder_name'] = new_name

    # Update folder in folder_db if it belongs to user
    if old_name in folder_db and folder_db[old_name].get('user_id') == username:
        folder_info = folder_db[old_name]
        folder_info['name'] = new_name
        folder_info['path'] = new_name
        folder_db[new_name] = folder_info
        del folder_db[old_name]
        save_folder_db(folder_db)

    # Rename physical folder
    old_path = os.path.join("videos", username, old_name)
    new_path = os.path.join("videos", username, new_name)

    if os.path.exists(old_path):
        os.rename(old_path, new_path)

    save_db(db)
    return {"message": f"Folder renamed from {old_name} to {new_name}"}



async def process_video(url: str, folder_name: str, username: str = None):
    """
    Process a YouTube URL which can be either a single video or a playlist.
    - For single videos: extract ID, fetch basic metadata, save entry.
    - For playlists: iterate entries and add each video.
    No media download; only metadata and thumbnails are fetched.
    """
    import re
    import urllib.request

    def ensure_user_folder():
        if username:
            folder_path = os.path.join("videos", username, folder_name)
        else:
            folder_path = os.path.join("videos", folder_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def add_video_to_db(db, video_id: str, source_url: str, title: str = None, duration: int = 0):
        # Allow same YouTube video per different users by generating a unique ID if needed
        final_id = video_id
        if final_id in db:
            existing = db[final_id]
            if existing.get('user_id') == username:
                # Already added for this user; do nothing
                return False
            # Generate a per-user unique id
            base = f"{video_id}_{username}"
            candidate = base
            idx = 1
            while candidate in db:
                idx += 1
                candidate = f"{base}_{idx}"
            final_id = candidate

        embed_url = f"https://www.youtube.com/embed/{video_id}"
        # Default title if missing
        if not title:
            title = f"YouTube Video {video_id}"

        # Thumbnail handling (store under original video_id to reuse across users)
        thumb_id = video_id
        thumbnail_url = f"https://img.youtube.com/vi/{thumb_id}/maxresdefault.jpg"
        thumbnail_path = os.path.join("static", "thumbnails", f"{thumb_id}.jpg")
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        try:
            if not os.path.exists(thumbnail_path) or os.path.getsize(thumbnail_path) == 0:
                urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
        except Exception:
            # Create empty placeholder on failure
            try:
                with open(thumbnail_path, 'wb') as f:
                    f.write(b'')
            except Exception:
                pass

        db[final_id] = {
            'video_id': final_id,
            'yt_id': video_id,
            'user_id': username,
            'title': title,
            'source_url': source_url,
            'folder_path': folder_name,
            'folder_name': folder_name.split('/')[-1] if folder_name else '',
            'embed_url': embed_url,
            'thumbnail_path': thumbnail_path,
            'duration': duration or 0,
            'file_size': 0,
            'added_time': datetime.now().isoformat(),
            'views_count': 0
        }
        return True

    try:
        ensure_user_folder()
        db = load_db()

        # First, try to extract info using yt_dlp (handles both videos and playlists)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',  # don't resolve each entry, fast listing
            'skip_download': True,
            'socket_timeout': 20,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"yt-dlp extraction error: {e}")
            info = None

        # If playlist
        if info and (info.get('_type') == 'playlist' or info.get('entries')):
            entries = info.get('entries', []) or []
            added = 0
            for entry in entries:
                # entries from extract_flat have 'id' and 'title'
                vid = entry.get('id') or entry.get('url')
                if not vid:
                    continue
                # YouTube IDs are 11 chars typically; sanitize
                vid = vid.strip()
                if '/' in vid:
                    # Sometimes url is returned; try regex to capture v parameter or last path segment
                    m = re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', vid)
                    if m:
                        vid = m.group(1)
                if len(vid) < 5:
                    continue
                title = entry.get('title') or None
                if add_video_to_db(db, vid, f"https://www.youtube.com/watch?v={vid}", title=title):
                    added += 1
            save_db(db)
            # Record subscription for updates
            try:
                playlist_id = info.get('id') or ''
                playlist_title = info.get('title') or playlist_id
                if playlist_id and username:
                    add_subscription(username, playlist_id, folder_name, playlist_title)
            except Exception:
                pass
            print(f"Playlist processed: {added} new video(s) added")
            return True, added

        # Otherwise, assume single video
        video_id = None
        # Try to get id from info first
        if info and info.get('id'):
            video_id = info['id']
            title = info.get('title')
            duration = info.get('duration') or 0
            if add_video_to_db(db, video_id, url, title=title, duration=duration):
                save_db(db)
                print(f"Video added: {title or video_id}")
                return True, 1
        
        # Fallback: regex extraction from URL
        patterns = [
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/live/([a-zA-Z0-9_-]{11})',
            r'v=([a-zA-Z0-9_-]{11})'
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                video_id = m.group(1)
                break
        if not video_id:
            error_msg = f"Invalid or unsupported YouTube URL: {url}"
            print(error_msg)
            return False, error_msg

        if add_video_to_db(db, video_id, url):
            save_db(db)
            print(f"Video added: {video_id}")
            return True, 1
        else:
            return False, "Video already exists"
            
    except Exception as e:
        error_msg = f"Error processing video: {str(e)}"
        print(error_msg)
        return False, error_msg

@app.post("/api/delete_folder")
async def delete_folder(folder_name: str = Form(...), auth_token: str = Cookie(None)):
    """Delete a folder and all its videos from the database and filesystem"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    db = load_db()
    folder_db = load_folder_db()

    # Remove all user's videos in the folder
    videos_to_delete = [video_id for video_id, video in db.items()
                       if video.get('user_id') == username and video.get('folder_name') == folder_name]

    for video_id in videos_to_delete:
        del db[video_id]

    # Remove folder from folder_db if it belongs to user
    if folder_name in folder_db and folder_db[folder_name].get('user_id') == username:
        del folder_db[folder_name]
        save_folder_db(folder_db)

    save_db(db)

    # Delete physical folder if it exists and is empty
    folder_path = os.path.join("videos", username, folder_name)
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

# Admin routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, auth_token: str = Cookie(None)):
    # Check if user is authenticated and is admin
    if not auth_token:
        return RedirectResponse("/login", status_code=302)

    try:
        from auth import verify_token
        username = verify_token(auth_token)
        if not username:
            return RedirectResponse("/login", status_code=302)

        from auth import load_users
        users = load_users()
        if username not in users:
            return RedirectResponse("/login", status_code=302)

        user = users[username]
        if user.get("role") != "admin":
            return RedirectResponse("/", status_code=302)  # Not admin, redirect to home

    except Exception:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse("admin.html", {"request": request, "current_user": user})

@app.get("/api/admin/stats")
async def get_admin_stats(auth_token: str = Cookie(None)):
    # Verify admin access
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)

        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Calculate statistics
    from datetime import datetime, timedelta
    all_users = load_users()
    db = load_db()

    total_users = len(all_users)
    active_users = sum(1 for u in all_users.values() if u.get("is_active", True))
    total_videos = len(db)
    total_views = sum(video.get("views_count", 0) for video in db.values())

    # Calculate storage used (rough estimate)
    storage_used = 0
    for video in db.values():
        thumbnail_path = video.get("thumbnail_path", "")
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                storage_used += os.path.getsize(thumbnail_path)
            except:
                pass

    # Convert to MB
    storage_used_mb = round(storage_used / (1024 * 1024), 2)

    # Count folders
    folder_db = load_folder_db()
    total_folders = len(folder_db)

    # New metrics
    one_week_ago = datetime.now() - timedelta(days=7)
    def parse_time(ts):
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None
    new_this_week = sum(1 for v in db.values() if parse_time(v.get('added_time') or '') and parse_time(v.get('added_time')).replace(tzinfo=None) >= one_week_ago)

    # Broken count (missing or zero-size thumbnails or bad source_url)
    broken_count = 0
    for v in db.values():
        t = v.get('thumbnail_path')
        bad_thumb = not t or not os.path.exists(t) or (os.path.exists(t) and os.path.getsize(t) == 0)
        src = v.get('source_url', '') or ''
        bad_src = not src.startswith('http') and 'youtube.com' not in src and 'youtu.be' not in src
        if bad_thumb or bad_src:
            broken_count += 1

    # Queue count (queued or running)
    queue_count = 0
    try:
        q = load_queue()
        queue_count = sum(1 for item in q if item.get('status') in ['queued', 'running'])
    except Exception:
        queue_count = 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_videos": total_videos,
        "total_views": total_views,
        "storage_used": storage_used_mb,
        "total_folders": total_folders,
        "new_this_week": new_this_week,
        "broken_count": broken_count,
        "queue_count": queue_count,
    }

@app.get("/api/admin/users")
async def get_all_users(auth_token: str = Cookie(None)):
    # Verify admin access
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)

        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Return all users (exclude passwords)
    all_users = load_users()
    user_list = []
    for username, user_data in all_users.items():
        user_list.append({
            "username": username,
            "email": user_data.get("email"),
            "role": user_data.get("role", "user"),
            "is_active": user_data.get("is_active", True),
            "created_at": user_data.get("created_at"),
            "last_login": user_data.get("last_login"),
            "login_count": user_data.get("login_count", 0)
        })

    return {"users": user_list}

@app.post("/api/admin/users/{target_username}/toggle")
async def toggle_user_status(target_username: str, auth_token: str = Cookie(None)):
    # Verify admin access
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users, save_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)

        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        if target_username not in users:
            raise HTTPException(status_code=404, detail="User not found")

        if target_username == "admin":
            raise HTTPException(status_code=400, detail="Cannot modify admin user")

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Toggle user status
    users[target_username]["is_active"] = not users[target_username].get("is_active", True)
    save_users(users)

    return {"message": f"User {target_username} status updated"}

@app.delete("/api/admin/users/{target_username}/delete")
async def delete_user(target_username: str, auth_token: str = Cookie(None)):
    # Verify admin access
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users, save_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)

        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        if target_username not in users:
            raise HTTPException(status_code=404, detail="User not found")

        if target_username == "admin":
            raise HTTPException(status_code=400, detail="Cannot delete admin user")

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    # Delete user and all their data
    db = load_db()
    folder_db = load_folder_db()

    # Remove user's videos
    videos_to_delete = [vid for vid, video in db.items() if video.get("user_id") == target_username]
    for vid in videos_to_delete:
        del db[vid]

    # Remove user's folders
    folders_to_delete = [fid for fid, folder in folder_db.items() if folder.get("user_id") == target_username]
    for fid in folders_to_delete:
        del folder_db[fid]

    # Remove user account
    del users[target_username]

    # Save changes
    save_db(db)
    save_folder_db(folder_db)
    save_users(users)

    return {"message": f"User {target_username} and all their data deleted"}

@app.post("/api/create_subfolder")
async def create_subfolder(parent_path: str = Form(...), subfolder_name: str = Form(...), auth_token: str = Cookie(None)):
    """Create a new subfolder"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    if not subfolder_name or not subfolder_name.strip():
        raise HTTPException(status_code=400, detail="Subfolder name is required")

    folder_db = load_folder_db()
    new_folder_path = f"{parent_path}/{subfolder_name.strip()}" if parent_path else subfolder_name.strip()

    if new_folder_path in folder_db:
        raise HTTPException(status_code=400, detail="Folder already exists")

    # Create physical folder
    folder_physical_path = os.path.join("videos", username, new_folder_path)
    os.makedirs(folder_physical_path, exist_ok=True)

    # Save to folder database
    folder_db[new_folder_path] = {
        'name': subfolder_name.strip(),
        'path': new_folder_path,
        'parent_path': parent_path,
        'user_id': username,
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

# ===== Admin enhancements: queue, bulk ops, videos listing, health checks =====
QUEUE_FILE = "admin_queue.json"

def load_queue():
    try:
        with open(QUEUE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_queue(queue):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)

async def _process_queue_item(item_id: str):
    queue = load_queue()
    item = next((it for it in queue if it.get('id') == item_id), None)
    if not item:
        return
    if item.get('status') in ['canceled', 'completed']:
        return
    item['status'] = 'running'
    save_queue(queue)
    try:
        await process_video(item['url'], item['folder_path'], item.get('requested_by'))
        # Mark complete
        queue = load_queue()
        item = next((it for it in queue if it.get('id') == item_id), None)
        if item:
            item['status'] = 'completed'
            item['completed_at'] = datetime.now().isoformat()
            save_queue(queue)
    except Exception as e:
        queue = load_queue()
        item = next((it for it in queue if it.get('id') == item_id), None)
        if item:
            item['status'] = 'failed'
            item['error'] = str(e)
            item['completed_at'] = datetime.now().isoformat()
            save_queue(queue)

@app.get('/api/admin/videos')
async def admin_list_videos(q: str = None, folder: str = None, broken: bool = False, page: int = 1, page_size: int = 50, auth_token: str = Cookie(None)):
    # Admin auth
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    db = load_db()
    videos = list(db.values())

    # Filters
    if q:
        qs = q.lower()
        videos = [v for v in videos if qs in (v.get('title','').lower() + ' ' + v.get('source_url','').lower())]
    if folder:
        videos = [v for v in videos if v.get('folder_path') == folder or v.get('folder_name') == folder]
    if broken:
        def is_broken(v):
            t = v.get('thumbnail_path')
            bad_thumb = not t or not os.path.exists(t) or (os.path.exists(t) and os.path.getsize(t) == 0)
            src = v.get('source_url', '') or ''
            bad_src = not src.startswith('http') and 'youtube.com' not in src and 'youtu.be' not in src
            return bad_thumb or bad_src
        videos = [v for v in videos if is_broken(v)]

    total = len(videos)
    start = max((page-1)*page_size, 0)
    end = start + page_size
    return { 'items': videos[start:end], 'total': total, 'page': page, 'page_size': page_size }

@app.post('/api/admin/videos/bulk/delete')
async def admin_bulk_delete(video_ids: str = Form(...), auth_token: str = Cookie(None)):
    # Admin auth
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    ids = [vid.strip() for vid in (video_ids or '').split(',') if vid.strip()]
    db = load_db()
    deleted = 0
    for vid in ids:
        if vid in db:
            del db[vid]
            deleted += 1
    save_db(db)
    return { 'deleted': deleted }

@app.post('/api/admin/videos/bulk/move')
async def admin_bulk_move(video_ids: str = Form(...), new_folder_path: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    ids = [vid.strip() for vid in (video_ids or '').split(',') if vid.strip()]
    db = load_db()
    moved = 0
    for vid in ids:
        if vid in db:
            db[vid]['folder_path'] = new_folder_path
            db[vid]['folder_name'] = new_folder_path.split('/')[-1] if new_folder_path else ''
            moved += 1
    save_db(db)
    return { 'moved': moved }

@app.post('/api/admin/videos/bulk/copy')
async def admin_bulk_copy(video_ids: str = Form(...), new_folder_path: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    ids = [vid.strip() for vid in (video_ids or '').split(',') if vid.strip()]
    db = load_db()
    copied = 0
    for vid in ids:
        if vid in db:
            base_id = vid
            new_id = f"{base_id}_copy_{int(datetime.now().timestamp())}"
            new_video = db[vid].copy()
            new_video['video_id'] = new_id
            new_video['folder_path'] = new_folder_path
            new_video['folder_name'] = new_folder_path.split('/')[-1] if new_folder_path else ''
            new_video['added_time'] = datetime.now().isoformat()
            new_video['views_count'] = 0
            db[new_id] = new_video
            copied += 1
    save_db(db)
    return { 'copied': copied }

@app.post('/api/admin/videos/bulk/tag')
async def admin_bulk_tag(video_ids: str = Form(...), action: str = Form(...), tag: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    ids = [vid.strip() for vid in (video_ids or '').split(',') if vid.strip()]
    db = load_db()
    updated = 0
    for vid in ids:
        if vid in db:
            tags = db[vid].get('tags') or []
            if action == 'add' and tag not in tags:
                tags.append(tag)
            elif action == 'remove' and tag in tags:
                tags.remove(tag)
            db[vid]['tags'] = tags
            updated += 1
    save_db(db)
    return { 'updated': updated }

@app.post('/api/admin/import/queue')
async def admin_import_queue(background_tasks: BackgroundTasks, urls: str = Form(...), folder_path: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    lines = [u.strip() for u in urls.splitlines() if u.strip()]
    queue = load_queue()
    created = []
    now = datetime.now().isoformat()
    for idx, url in enumerate(lines):
        item_id = f"q_{int(datetime.now().timestamp())}_{idx}"
        item = {
            'id': item_id,
            'url': url,
            'folder_path': folder_path,
            'requested_by': username,
            'status': 'queued',
            'created_at': now
        }
        queue.append(item)
        created.append(item)
        # schedule processing
        background_tasks.add_task(_process_queue_item, item_id)
    save_queue(queue)
    return { 'created': len(created), 'items': created }

@app.get('/api/admin/import/queue')
async def admin_get_queue(auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')
    return { 'items': load_queue() }

@app.post('/api/admin/import/queue/{item_id}/cancel')
async def admin_cancel_queue(item_id: str, auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    queue = load_queue()
    item = next((it for it in queue if it.get('id') == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail='Item not found')
    if item.get('status') == 'queued':
        item['status'] = 'canceled'
        item['completed_at'] = datetime.now().isoformat()
        save_queue(queue)
        return { 'message': 'Canceled' }
    return { 'message': 'Cannot cancel (already running or completed)' }

@app.get('/api/admin/check/broken')
async def admin_check_broken(auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    db = load_db()
    broken = []
    for vid, v in db.items():
        t = v.get('thumbnail_path')
        bad_thumb = not t or not os.path.exists(t) or (os.path.exists(t) and os.path.getsize(t) == 0)
        src = v.get('source_url', '') or ''
        bad_src = not src.startswith('http') and 'youtube.com' not in src and 'youtu.be' not in src
        if bad_thumb or bad_src:
            broken.append({ 'video_id': vid, 'title': v.get('title'), 'bad_thumb': bad_thumb, 'bad_src': bad_src })
    return { 'items': broken }

@app.post('/api/admin/fix/metadata')
async def admin_fix_metadata(video_ids: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail='Not authenticated')
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        user = users.get(username)
        if not user or user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail='Admin access required')
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid authentication')

    ids = [vid.strip() for vid in (video_ids or '').split(',') if vid.strip()]
    db = load_db()
    fixed = 0
    for vid in ids:
        if vid not in db:
            continue
        v = db[vid]
        # Refresh title via yt_dlp when possible
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(v.get('source_url'), download=False)
                if info and info.get('title'):
                    v['title'] = info['title']
                if info and info.get('duration'):
                    v['duration'] = info['duration']
        except Exception:
            pass
        # Refresh thumbnail
        try:
            import urllib.request
            thumb_url = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
            thumb_path = os.path.join('static', 'thumbnails', f'{vid}.jpg')
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            urllib.request.urlretrieve(thumb_url, thumb_path)
            v['thumbnail_path'] = thumb_path
        except Exception:
            pass
        fixed += 1
    save_db(db)
    return { 'fixed': fixed }

# ===== Notifications API =====
@app.get("/api/notifications")
async def list_notifications(read: str = None, auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    items = get_user_notifications(username)
    if read is not None:
        flag = (str(read).lower() == 'true')
        items = [n for n in items if bool(n.get('read')) == flag]
    unread_count = sum(1 for n in get_user_notifications(username) if not n.get('read'))
    return {"items": items, "unread_count": unread_count}

@app.post("/api/notifications/mark_read")
async def mark_notifications_read(ids: str = Form(...), auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    wanted = [i.strip() for i in (ids or '').split(',') if i.strip()]
    db = load_notifications_db()
    lst = db.get(username, [])
    for n in lst:
        if n.get('id') in wanted:
            n['read'] = True
    db[username] = lst
    save_notifications_db(db)
    return {"marked": len(wanted)}

@app.post("/api/notifications/mark_all_read")
async def mark_all_notifications_read(auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    db = load_notifications_db()
    lst = db.get(username, [])
    for n in lst:
        n['read'] = True
    db[username] = lst
    save_notifications_db(db)
    return {"marked": len(lst)}

# ===== Playlist updates checker =====
@app.get("/api/playlist/check_updates")
async def check_playlist_updates(auth_token: str = Cookie(None)):
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from auth import verify_token, load_users
        username = verify_token(auth_token)
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    subs = load_subscriptions().get(username, {}).get('playlists', {})
    if not subs:
        return {"updated": 0, "details": []}

    updated = 0
    details = []
    for pid, meta in subs.items():
        folder_path = meta.get('folder_path')
        playlist_title = meta.get('title') or pid
        # Fetch playlist entries
        try:
            with yt_dlp.YoutubeDL({
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'skip_download': True
            }) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/playlist?list={pid}", download=False)
                entries = info.get('entries', []) if info else []
        except Exception:
            entries = []
        # For each entry, if not present for this user, add and notify
        for entry in entries:
            ytid = (entry.get('id') or '').strip()
            if not ytid:
                continue
            # Check existence for this user by yt_id
            db = load_db()
            exists = any(v for v in db.values() if v.get('user_id') == username and (v.get('yt_id') == ytid or (len(v.get('video_id',''))==11 and v.get('video_id')==ytid)))
            if exists:
                continue
            # Add via process_video
            await process_video(f"https://www.youtube.com/watch?v={ytid}", folder_path, username)
            updated += 1
            # Notification
            add_notification(username, {
                'type': 'playlist_update',
                'playlist_id': pid,
                'playlist_title': playlist_title,
                'video_id': ytid,
                'video_title': entry.get('title') or ytid,
                'folder_path': folder_path
            })
        # Update last_checked_at
        subs_db = load_subscriptions()
        if username in subs_db and 'playlists' in subs_db[username] and pid in subs_db[username]['playlists']:
            subs_db[username]['playlists'][pid]['last_checked_at'] = datetime.now().isoformat()
            save_subscriptions(subs_db)
        details.append({"playlist_id": pid, "title": playlist_title})

    return {"updated": updated, "details": details}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
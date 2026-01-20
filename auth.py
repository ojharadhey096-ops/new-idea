import json
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, Depends, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Simple JSON-based user storage (for simplicity)
USERS_DB = "users_db.json"

def load_users():
    try:
        with open(USERS_DB, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Create default admin user
        default_user = {
            "admin": {
                "username": "admin",
                "email": "admin@example.com",
                "password_hash": bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode(),
                "created_at": datetime.now().isoformat(),
                "is_active": True,
                "role": "admin",
                "last_login": None,
                "login_count": 0
            }
        }
        save_users(default_user)
        return default_user

def save_users(users):
    with open(USERS_DB, 'w') as f:
        json.dump(users, f, indent=2)

# JWT Configuration
SECRET_KEY = "your-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 6 * 30 * 24 * 60  # 6 months

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except jwt.PyJWTError:
        return None

def authenticate_user(username: str, password: str):
    users = load_users()
    if username not in users:
        return False

    user = users[username]
    if not user.get("is_active", True):
        return False

    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return user
    return False

def register_user(username: str, email: str, password: str):
    users = load_users()

    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check if email is already used
    for user in users.values():
        if user.get("email") == email:
            raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    users[username] = {
        "username": username,
        "email": email,
        "password_hash": hashed_password,
        "created_at": datetime.now().isoformat(),
        "is_active": True,
        "role": "user",
        "last_login": None,
        "login_count": 0
    }

    save_users(users)
    return users[username]

def get_current_user(token: Optional[str] = Cookie(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    users = load_users()
    if username not in users:
        raise HTTPException(status_code=401, detail="User not found")

    return users[username]
# Telegram Integration Guide

VideoHub ab Telegram channels se videos sync kar sakta hai! 🎬📱

## Features

✅ YouTube videos directly website par play hote hain (YouTube IFrame API)
✅ Telegram channels se videos import kar sakte ho
✅ Videos organize kar sakte ho folders mein
✅ VLC player mein bhi open kar sakte ho

## Telegram Setup

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org/apps
2. Sign in with your Telegram account
3. Create a new application
4. Copy your `API_ID` and `API_HASH`

### 2. Set Environment Variables

```bash
export API_ID="your_api_id"
export API_HASH="your_api_hash"
export CHANNELS="@channel1,@channel2,@channel3"
export SYNC_INTERVAL=3600  # Sync every hour
```

### 3. Configure Channels

Edit `config.py`:
```python
CHANNELS = ["@Rk_Movie096", "@YourChannelName", "@AnotherChannel"]
```

### 4. First Run

When the app starts, it will ask you to authenticate with Telegram (phone number verification).

## How to Use

### On Website

1. Go to home page
2. Scroll to "Sync Telegram Videos" section
3. Enter channel name (e.g., `@Rk_Movie096`)
4. Click "Sync Now"
5. Videos will appear in your library in 1-2 minutes

### Video Storage

- YouTube videos: Stored in `video_db.json` with metadata
- Telegram videos: Stored with channel name as folder
- Thumbnails: Cached in `static/thumbnails/`
- Video files: Can be streamed directly from Telegram

## API Endpoints

```
GET /api/telegram/channels           - List configured channels
GET /api/telegram/sync/{channel}     - Sync a specific channel
GET /api/telegram/videos             - Get cached Telegram videos
```

## How Videos Play

### YouTube Videos
- ✅ Plays directly on website using YouTube IFrame API
- ✅ Full YouTube player with controls
- 🎬 Click button to open full YouTube if needed

### Telegram Videos
- ✅ Can play in HTML5 video player (if mp4 format)
- ✅ Download option available
- 🎬 Open in VLC Media Player
- ✅ Direct Telegram streaming

## Features

### Quality Variants
Telegram videos maintain original quality from channel.

### Backup Methods
If embedding fails:
1. "Watch on YouTube" button (for YouTube videos)
2. "Open in VLC" button (VLC needs to be installed)
3. Direct download link

### Auto-Sync
- Configured sync interval (default: 1 hour)
- Runs in background
- Only adds new videos (doesn't duplicate)

## Troubleshooting

### "Telegram client not available"
- Check if `telegram_client.py` is properly configured
- Verify API_ID and API_HASH are correct
- Run `pip install pyrogram`

### Videos not appearing
- Check channel is public or you have access
- Run sync again
- Check `video_cache.json` file

### Authentication issues
- Delete `telegram_session.session` file
- Restart app and authenticate again
- Use correct phone number for your Telegram account

## Video Quality

Telegram videos are stored in original quality from the channel:
- Typically 720p or 1080p
- Depends on what channel has uploaded
- Can be configured in Telegram client settings

## Security Notes

- API credentials are private (use environment variables)
- Never commit `.session` files to git
- Add to `.gitignore`:
  ```
  telegram_session.session
  bot_session.session
  video_cache.json
  ```

## Future Enhancements

- [ ] Auto-download videos for offline watching
- [ ] Telegram search functionality
- [ ] Custom quality selection
- [ ] Subtitle support
- [ ] Video recommendations based on Telegram channels

---

Made with ❤️ for VideoHub

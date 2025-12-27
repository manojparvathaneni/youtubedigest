# YouTube Daily Digest

Automatically fetch, transcribe, and summarize your YouTube subscriptions into AI-generated blog posts.

## Features

- 📡 Fetches latest videos from your subscribed channels via RSS (no API key needed)
- 📝 Extracts full transcripts using `youtube-transcript-api`
- 🤖 Multi-pass AI summarization with Claude (handles long videos)
- 📄 Outputs nicely formatted Markdown or HTML with embedded videos
- ✅ Proper attribution to creators
- 🎬 Single video mode - summarize any YouTube video on demand
- ⚙️ Configurable videos per channel (global or per-channel override)

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install feedparser youtube-transcript-api anthropic python-dotenv pyyaml
```

### 2. Set up your API key

```bash
cp env-example.txt .env
# Edit .env and add your Anthropic API key
```

### 3. Import your YouTube subscriptions

**Option A: OPML Export (Easiest)**
1. Go to https://www.youtube.com/subscription_manager
2. Scroll to bottom, click "Export subscriptions"
3. Run:
```bash
python get_subscriptions.py opml subscription_manager.xml
```

**Option B: Google Takeout**
1. Go to https://takeout.google.com
2. Deselect all → Select "YouTube" → Only "subscriptions"
3. Export, download, and extract
4. Run:
```bash
python get_subscriptions.py takeout path/to/subscriptions.json
```

**Option C: Browser Script**
```bash
python get_subscriptions.py browser
# Follow the printed instructions
```

### 4. Run the digest

```bash
python youtube_digest.py
```

## Usage

### Channel Digest Mode (default)

Process latest videos from all configured channels:

```bash
python youtube_digest.py
```

### Single Video Mode

Summarize any YouTube video on demand:

```bash
# Full URL
python youtube_digest.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Short URL
python youtube_digest.py "https://youtu.be/dQw4w9WgXcQ"

# Just the video ID
python youtube_digest.py dQw4w9WgXcQ

# With custom title and channel (optional)
python youtube_digest.py dQw4w9WgXcQ "My Custom Title" "Channel Name"
```

The script auto-detects video title and channel name from YouTube.

## Configuration

Edit `config.yaml`:

```yaml
# Output format: markdown, html, or both
output_format: markdown

# Claude model to use
model: claude-sonnet-4-5-20250929

# Default videos per channel (1-15, or "all" for 15)
videos_per_channel: 1

# Channels to process
channels:
  - id: UCsBjURrPoezykLs9EqgamOA
    name: Fireship
  
  - id: UCVHFbqXqoYvEWM1Ddxl0QDg
    name: Alex Ziskind

  - id: UCXl4i9dYBrFOabk0xGmbkRA
    name: Dwarkesh Patel
    videos: 3  # Override: fetch last 3 videos from this channel
```

### Configuration Options

| Option | Values | Description |
|--------|--------|-------------|
| `output_format` | `markdown`, `html`, `both` | Output file format |
| `model` | Claude model string | AI model to use for summarization |
| `videos_per_channel` | `1`-`15` or `all` | Default videos to fetch per channel |
| `channels[].videos` | `1`-`15` or `all` | Per-channel override |

### Available Models

| Model | Description |
|-------|-------------|
| `claude-sonnet-4-5-20250929` | Latest Sonnet 4.5 (default) |
| `claude-3-5-sonnet-20241022` | Claude 3.5 Sonnet (widely available) |
| `claude-3-haiku-20240307` | Fastest, cheapest option |

### Environment Variables

Set in `.env` file:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional overrides
OUTPUT_FORMAT=both
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

## Output Files

**Channel digest mode:**
- `digest_2024-12-27.md` - Markdown file with all summaries
- `digest_2024-12-27.html` - Styled HTML with embedded videos

**Single video mode:**
- `video_Video-Title_2024-12-27.md`
- `video_Video-Title_2024-12-27.html`

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  RSS Feed   │────▶│ Transcript  │────▶│   Claude    │
│  (free)     │     │ API (free)  │     │   (paid)    │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌──────────────────────────┘
                    ▼
        ┌─────────────────────┐
        │  Multi-pass Summary │
        │  1. Chunk transcript│
        │  2. Analyze chunks  │
        │  3. Synthesize blog │
        └─────────────────────┘
                    │
                    ▼
        ┌─────────────────────┐
        │   Output Files      │
        │  • Markdown         │
        │  • HTML + embeds    │
        │  • Attribution      │
        └─────────────────────┘
```

## Cost Estimate

Using Claude Sonnet (default):

| Video Length | Estimated Cost |
|--------------|----------------|
| Short (< 10 min) | ~$0.01 |
| Medium (10-30 min) | ~$0.02 |
| Long (30-60 min) | ~$0.03-0.05 |
| Very long (1-3 hours) | ~$0.10-0.15 |

Daily digest of 10 channels: ~$0.10-0.30

**Tip:** Use `claude-3-haiku-20240307` for cheaper processing (~10x less), though summaries may be less detailed.

## Scheduling (Optional)

### Windows Task Scheduler

```
Action: Start a program
Program: python
Arguments: C:\path\to\youtube_digest.py
Start in: C:\path\to\
```

### Mac/Linux Cron

```bash
# Edit crontab
crontab -e

# Add line to run daily at 8 AM
0 8 * * * cd /path/to/digest && /usr/bin/python3 youtube_digest.py >> digest.log 2>&1
```

### PowerShell Scheduled Task

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "youtube_digest.py" -WorkingDirectory "C:\path\to"
$trigger = New-ScheduledTaskTrigger -Daily -At 8am
Register-ScheduledTask -TaskName "YouTubeDigest" -Action $action -Trigger $trigger
```

## File Structure

```
youtube-digest/
├── youtube_digest.py      # Main script
├── get_subscriptions.py   # Import YouTube subscriptions
├── config.yaml            # Channel list + settings
├── .env                   # API key (create from env-example.txt)
├── env-example.txt        # Template for .env
├── requirements.txt       # Python dependencies
├── README.md              # This file
└── LICENSE                # MIT License
```

## Limitations

- Only works for videos with captions (auto-generated or uploaded)
- RSS feeds only show last 15 videos per channel
- Transcript API is unofficial (could break, but has been stable for years)
- Video info fetching may not work for age-restricted or private videos

## Troubleshooting

**"Could not get transcript"**
- Video may not have captions enabled
- Try a different video from the same channel

**"No videos found"**
- Check channel ID is correct
- Verify the RSS feed works: `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`

**Rate limiting**
- Add delays between videos if processing many at once
- The transcript API has informal rate limits

## License

MIT License - see [LICENSE](LICENSE) file.

## Attribution

When using the generated summaries publicly, the script automatically includes proper attribution to the original creators. This is both ethical and helps drive traffic to their channels.

## Contributing

Feel free to submit issues and pull requests. Ideas for improvements:

- [ ] Track processed videos to avoid re-summarizing
- [ ] Email/Slack delivery of daily digest
- [ ] Support for playlists
- [ ] Parallel processing for faster digests
- [ ] Custom summary templates
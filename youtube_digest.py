#!/usr/bin/env python3
"""
YouTube Daily Digest
Fetches latest videos from subscribed channels, extracts transcripts,
and generates AI summaries using any LLM provider (Anthropic, OpenAI, Ollama, etc.)
"""

import feedparser
from youtube_transcript_api import YouTubeTranscriptApi
import litellm
from datetime import datetime
from dotenv import load_dotenv
import os
import yaml
from pathlib import Path

# Load environment variables from .env file (API keys only)
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

CONFIG_FILE = "config.yaml"

def load_config() -> dict:
    """Load configuration from YAML file."""
    if not Path(CONFIG_FILE).exists():
        print(f"⚠️  Config file not found: {CONFIG_FILE}")
        print("   Creating default config. Please edit it to add your channels.")
        print("   Or run: python get_subscriptions.py")
        default_config = {
            "output_format": "markdown",
            "output_dir": "blog",
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 8192,
            "videos_per_channel": 1,
            "channels": [
                {"id": "UCsBjURrPoezykLs9EqgamOA", "name": "Fireship"}
            ]
        }
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        return default_config
    
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

# Load config
config = load_config()

# All configuration comes from config.yaml
# (.env is only for API keys/secrets)
OUTPUT_FORMAT = config.get("output_format", "markdown")
OUTPUT_DIR = config.get("output_dir", "blog")
MODEL = config.get("model", "claude-sonnet-4-5-20250929")
API_BASE = config.get("api_base", None)  # For custom endpoints (Ollama, LM Studio, etc.)
MAX_TOKENS = config.get("max_tokens", 8192)  # Max tokens for blog post generation

# Configure litellm if custom base URL is set
if API_BASE:
    litellm.api_base = API_BASE
    # Also set for providers that need it explicitly
    os.environ["OPENAI_API_BASE"] = API_BASE
    os.environ["OLLAMA_API_BASE"] = API_BASE

# Number of videos per channel: 1-15 or "all"
_vpc = config.get("videos_per_channel", 1)
DEFAULT_VIDEOS_PER_CHANNEL = 15 if _vpc == "all" else min(int(_vpc), 15)

# Load channels with per-channel video count override
CHANNELS = []
for ch in config.get("channels", []):
    ch_videos = ch.get("videos", DEFAULT_VIDEOS_PER_CHANNEL)
    if ch_videos == "all":
        ch_videos = 15
    CHANNELS.append((ch["id"], ch["name"], min(int(ch_videos), 15)))

def get_videos(channel_id: str, count: int = 1) -> list[dict]:
    """Fetch the latest videos from a channel's RSS feed."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        return []
    
    videos = []
    for entry in feed.entries[:count]:
        videos.append({
            "video_id": entry.yt_videoid,
            "title": entry.title,
            "published": entry.published,
            "link": entry.link,
        })
    
    return videos


def get_video_info(video_id: str) -> dict | None:
    """Try to get video title and channel from YouTube page."""
    import urllib.request
    import ssl
    import re
    
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        try:
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                html = response.read().decode('utf-8', errors='ignore')
        except ssl.SSLError:
            # Fallback: disable verification (not ideal but works)
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                html = response.read().decode('utf-8', errors='ignore')
        
        # Extract title
        title_match = re.search(r'<title>(.+?) - YouTube</title>', html)
        title = title_match.group(1) if title_match else f"Video {video_id}"
        
        # Extract channel name
        channel_match = re.search(r'"ownerChannelName":"([^"]+)"', html)
        channel = channel_match.group(1) if channel_match else "Unknown Channel"
        
        return {
            "video_id": video_id,
            "title": title,
            "channel": channel,
            "link": url
        }
    except Exception as e:
        print(f"  ⚠️ Could not fetch video info: {e}")
        return None

def get_transcript(video_id: str) -> str | None:
    """Extract transcript from a YouTube video."""
    try:
        # Try new API first (youtube-transcript-api >= 0.6.3)
        try:
            ytt = YouTubeTranscriptApi()
            # Try English first, then any available language
            try:
                transcript = ytt.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
            except Exception:
                transcript = ytt.fetch(video_id)  # Any language
            
            # New API returns objects with .text attribute
            if hasattr(transcript, '__iter__'):
                segments = list(transcript)
                if segments and hasattr(segments[0], 'text'):
                    full_text = " ".join([seg.text for seg in segments])
                else:
                    full_text = " ".join([seg['text'] for seg in segments])
            else:
                full_text = str(transcript)
                
        except (TypeError, AttributeError):
            # Fall back to old API (youtube-transcript-api < 0.6.3)
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            except Exception:
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
            full_text = " ".join([segment['text'] for segment in transcript])
        
        return full_text
    except Exception as e:
        print(f"  Could not get transcript: {e}")
        return None

def chunk_transcript(transcript: str, chunk_size: int = 10000) -> list[str]:
    """Split transcript into manageable chunks."""
    words = transcript.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        current_chunk.append(word)
        current_length += len(word) + 1
        
        if current_length >= chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks

def summarize_chunk(title: str, chunk: str, chunk_num: int, total_chunks: int) -> str:
    """Extract key points from a single chunk."""
    kwargs = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": f"""You're analyzing part {chunk_num} of {total_chunks} from a YouTube video transcript.

Video Title: {title}

Transcript segment:
{chunk}

Extract from this segment:
- Key points and insights
- Any "aha moments" or surprising revelations
- Practical takeaways or actionable advice
- Notable quotes or memorable phrases (paraphrased)

Be thorough - capture everything valuable. We'll synthesize later."""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE
    
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content

def synthesize_blog_post(title: str, channel_name: str, chunk_summaries: list[str], video_link: str, video_id: str) -> str:
    """Combine chunk summaries into a cohesive blog-style post."""
    combined_notes = "\n\n---\n\n".join([f"**Section {i+1}:**\n{summary}" for i, summary in enumerate(chunk_summaries)])
    
    # YouTube embed code
    embed_code = f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen></iframe>'
    
    kwargs = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": f"""Based on these extracted notes from a YouTube video, write an engaging blog-style post.

Video Title: {title}
Channel: {channel_name}
Video Link: {video_link}

Extracted Notes:
{combined_notes}

Write a well-structured blog post that includes:

1. **Attribution Header** - Start with:
   - Video title (as heading)
   - Channel name with credit: "by [Channel Name]"
   - The embed code: {embed_code}
   - Direct link to video

2. **Hook/Introduction** - Why this video matters, what problem it addresses

3. **Key Learnings** - The main insights, organized thematically (not chronologically)

4. **Aha Moments** - The surprising or counterintuitive revelations

5. **Practical Takeaways** - Actionable steps the viewer can apply

6. **Who Should Watch** - Brief note on target audience

7. **Final Verdict** - Is it worth the time? What's the TL;DR?

8. **Footer Attribution** - End with:
   "This summary is based on [{title}]({video_link}) by {channel_name}. Please subscribe to their channel to support their work."

Write in an engaging, conversational tone. Use markdown formatting for readability.
Make it comprehensive enough that someone could get 80% of the value without watching, while encouraging them to watch the full video for the complete experience."""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE
    
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content

def summarize_transcript(title: str, channel_name: str, transcript: str, video_link: str, video_id: str) -> str:
    """Generate blog-style summary using multi-pass approach."""
    # Split into chunks
    chunks = chunk_transcript(transcript)
    print(f"  📄 Split into {len(chunks)} chunks")
    
    # Summarize each chunk
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        print(f"  🔍 Analyzing chunk {i+1}/{len(chunks)}...")
        summary = summarize_chunk(title, chunk, i+1, len(chunks))
        chunk_summaries.append(summary)
    
    # Synthesize into blog post
    print("  ✍️  Synthesizing blog post...")
    blog_post = synthesize_blog_post(title, channel_name, chunk_summaries, video_link, video_id)
    
    return blog_post

def main():
    print(f"\n📺 YouTube Daily Digest - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    print("=" * 60)
    print(f"📋 Loaded {len(CHANNELS)} channels from {CONFIG_FILE}")
    print(f"🤖 Using model: {MODEL}")
    
    if not CHANNELS:
        print("\n⚠️  No channels configured!")
        print("   Run: python get_subscriptions.py")
        print("   Or edit config.yaml manually")
        return []
    
    summaries = []
    
    for channel_id, channel_name, video_count in CHANNELS:
        print(f"\n🔍 Checking: {channel_name} (last {video_count} video(s))")
        
        # Get videos
        videos = get_videos(channel_id, video_count)
        if not videos:
            print("  No videos found")
            continue
        
        print(f"  📹 Found {len(videos)} video(s)")
        
        for video in videos:
            print(f"\n  ▶️  {video['title']}")
            print(f"     🔗 {video['link']}")
            
            # Get transcript
            print("     📝 Fetching transcript...")
            transcript = get_transcript(video['video_id'])
            if not transcript:
                continue
            
            print(f"     ✅ Got transcript ({len(transcript)} chars)")
            
            # Summarize
            print("     🤖 Generating blog post...")
            summary = summarize_transcript(
                video['title'], 
                channel_name, 
                transcript, 
                video['link'],
                video['video_id']
            )
            
            summaries.append({
                "channel": channel_name,
                "title": video['title'],
                "link": video['link'],
                "video_id": video['video_id'],
                "summary": summary
            })
            
            print("     ✅ Done!")
    
    # Generate markdown output
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if OUTPUT_FORMAT in ("markdown", "both"):
        markdown_content = f"# YouTube Daily Digest - {date_str}\n\n"
        for item in summaries:
            markdown_content += f"---\n\n"
            markdown_content += f"{item['summary']}\n\n"
        
        md_file = os.path.join(OUTPUT_DIR, f"digest_{date_str}.md")
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"\n📄 Markdown saved: {md_file}")
    
    if OUTPUT_FORMAT in ("html", "both"):
        html_content = generate_html_digest(summaries, date_str)
        html_file = os.path.join(OUTPUT_DIR, f"digest_{date_str}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"🌐 HTML saved: {html_file}")
    
    # Print summary
    print("\n")
    print("=" * 60)
    print(f"📋 DIGEST COMPLETE - {len(summaries)} videos processed")
    print("=" * 60)
    
    return summaries


def generate_html_digest(summaries: list[dict], date_str: str) -> str:
    """Generate a nicely styled HTML digest with working embeds."""
    import re
    
    def markdown_to_html(md_text: str) -> str:
        """Basic markdown to HTML conversion."""
        html = md_text
        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', html)
        # Line breaks for paragraphs
        html = re.sub(r'\n\n', '</p><p>', html)
        # Bullet points
        html = re.sub(r'^\- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>\n?)+', r'<ul>\g<0></ul>', html)
        return f"<p>{html}</p>"
    
    articles_html = ""
    for item in summaries:
        article_content = markdown_to_html(item['summary'])
        articles_html += f"""
        <article class="video-summary">
            {article_content}
        </article>
        <hr>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Daily Digest - {date_str}</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f9fafb;
            color: #1f2937;
        }}
        h1 {{
            color: #111827;
            border-bottom: 3px solid #ef4444;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #1f2937;
            margin-top: 2em;
        }}
        h3 {{
            color: #374151;
            margin-top: 1.5em;
        }}
        .video-summary {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin: 20px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        iframe {{
            width: 100%;
            max-width: 560px;
            height: 315px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        a {{
            color: #2563eb;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        ul {{
            padding-left: 20px;
        }}
        li {{
            margin: 8px 0;
        }}
        hr {{
            border: none;
            border-top: 1px solid #e5e7eb;
            margin: 40px 0;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 0.9em;
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <h1>📺 YouTube Daily Digest</h1>
    <p><em>{date_str}</em></p>
    
    {articles_html}
    
    <div class="footer">
        <p>Generated with YouTube Digest Script</p>
    </div>
</body>
</html>"""
    
    return html


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Single video mode
        video_input = sys.argv[1]
        
        # Extract video ID from URL or use directly
        if "youtube.com" in video_input or "youtu.be" in video_input:
            if "v=" in video_input:
                video_id = video_input.split("v=")[1].split("&")[0]
            elif "youtu.be/" in video_input:
                video_id = video_input.split("youtu.be/")[1].split("?")[0]
            else:
                print(f"❌ Could not parse video URL: {video_input}")
                sys.exit(1)
        else:
            video_id = video_input
        
        print(f"\n📺 Single Video Mode")
        print("=" * 60)
        print(f"🎬 Video ID: {video_id}")
        
        # Try to get video info (title, channel)
        print("🔍 Fetching video info...")
        video_info = get_video_info(video_id)
        
        if video_info:
            video_title = sys.argv[2] if len(sys.argv) > 2 else video_info["title"]
            channel_name = sys.argv[3] if len(sys.argv) > 3 else video_info["channel"]
        else:
            video_title = sys.argv[2] if len(sys.argv) > 2 else f"Video {video_id}"
            channel_name = sys.argv[3] if len(sys.argv) > 3 else "Unknown Channel"
        
        video_link = f"https://www.youtube.com/watch?v={video_id}"
        
        print(f"📹 Title: {video_title}")
        print(f"📺 Channel: {channel_name}")
        
        # Get transcript
        print("📝 Fetching transcript...")
        transcript = get_transcript(video_id)
        if not transcript:
            print("❌ Could not get transcript")
            sys.exit(1)
        
        print(f"✅ Got transcript ({len(transcript)} chars)")
        print("🤖 Generating blog post...")
        
        summary = summarize_transcript(
            video_title,
            channel_name,
            transcript,
            video_link,
            video_id
        )
        
        # Save output
        date_str = datetime.now().strftime('%Y-%m-%d')
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in video_title)[:50]
        
        # Ensure output directory exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        if OUTPUT_FORMAT in ("markdown", "both"):
            md_file = os.path.join(OUTPUT_DIR, f"video_{safe_title}_{date_str}.md")
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(f"# {video_title}\n\n{summary}")
            print(f"\n📄 Markdown saved: {md_file}")
        
        if OUTPUT_FORMAT in ("html", "both"):
            html_content = generate_html_digest(
                [{"summary": summary, "title": video_title, "channel": channel_name}],
                date_str
            )
            html_file = os.path.join(OUTPUT_DIR, f"video_{safe_title}_{date_str}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"🌐 HTML saved: {html_file}")
        
        print("\n" + "=" * 60)
        print("✅ Done!")
        
    else:
        # Normal channel digest mode
        main()
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

# ============================================================
# TUTORIAL MODE - Repository Handling
# ============================================================

def clone_repo(repo_url: str, clone_path: str = "./tutorial_repos/") -> str | None:
    """Clone a git repository with --depth 1 for efficiency.

    Args:
        repo_url: GitHub repository URL
        clone_path: Directory to clone into

    Returns:
        Path to cloned repo, or None if failed
    """
    import subprocess
    import re

    # Extract repo name from URL
    match = re.search(r'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$', repo_url)
    if not match:
        print(f"  ❌ Could not parse GitHub URL: {repo_url}")
        return None

    owner, repo_name = match.groups()
    repo_name = repo_name.rstrip('.git')
    repo_dir = os.path.join(clone_path, f"{owner}_{repo_name}")

    # Create clone directory
    os.makedirs(clone_path, exist_ok=True)

    # Check if already cloned
    if os.path.exists(repo_dir):
        print(f"  📁 Repository already exists: {repo_dir}")
        return repo_dir

    # Clone with depth 1 (shallow clone)
    print(f"  📥 Cloning {repo_url}...")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, repo_dir],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"  ❌ Git clone failed: {result.stderr}")
            return None
        print(f"  ✅ Cloned to: {repo_dir}")
        return repo_dir
    except subprocess.TimeoutExpired:
        print("  ❌ Clone timed out")
        return None
    except FileNotFoundError:
        print("  ❌ Git not found. Please install git.")
        return None


def discover_repo_files(repo_path: str, file_types: str = ".py,.js,.ts,.go,.java,.rs,.md", max_files: int = 50) -> list[dict]:
    """Discover relevant code files in a repository.

    Args:
        repo_path: Path to cloned repository
        file_types: Comma-separated list of file extensions
        max_files: Maximum number of files to return

    Returns:
        List of dicts with 'path' (relative) and 'full_path' keys
    """
    extensions = [ext.strip() for ext in file_types.split(',')]
    if not extensions[0].startswith('.'):
        extensions = ['.' + ext for ext in extensions]

    # Directories to skip
    skip_dirs = {
        '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env',
        '.idea', '.vscode', 'dist', 'build', '.next', 'target',
        'vendor', '.cargo', 'coverage', '.pytest_cache', '.mypy_cache'
    }

    files = []
    repo_path = os.path.abspath(repo_path)

    for root, dirs, filenames in os.walk(repo_path):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, repo_path)
                files.append({
                    'path': rel_path,
                    'full_path': full_path
                })

                if len(files) >= max_files:
                    print(f"  ⚠️  Reached max files limit ({max_files})")
                    return files

    print(f"  📂 Found {len(files)} code files")
    return files


def read_repo_files(files: list[dict], max_lines: int = 500) -> list[dict]:
    """Read content from repository files.

    Args:
        files: List of file dicts from discover_repo_files()
        max_lines: Maximum lines to read per file (truncate if longer)

    Returns:
        List of dicts with 'path', 'content', 'truncated' keys
    """
    result = []

    for file_info in files:
        try:
            with open(file_info['full_path'], 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            truncated = len(lines) > max_lines
            if truncated:
                content = ''.join(lines[:max_lines])
                content += f"\n\n... [truncated - {len(lines) - max_lines} more lines]"
            else:
                content = ''.join(lines)

            result.append({
                'path': file_info['path'],
                'content': content,
                'truncated': truncated,
                'line_count': len(lines)
            })
        except Exception as e:
            print(f"  ⚠️  Could not read {file_info['path']}: {e}")

    return result


# ============================================================
# TRANSCRIPT PROCESSING
# ============================================================

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

# ============================================================
# TUTORIAL MODE - LLM Passes
# ============================================================

def extract_concepts_from_chunk(title: str, chunk: str, chunk_num: int, total_chunks: int) -> str:
    """Pass 1: Extract technical concepts from a transcript chunk as structured data.

    Args:
        title: Video title
        chunk: Transcript segment
        chunk_num: Current chunk number
        total_chunks: Total number of chunks

    Returns:
        JSON-formatted string of extracted concepts
    """
    kwargs = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": f"""You're analyzing part {chunk_num} of {total_chunks} from a tutorial video transcript.

Video Title: {title}

Transcript segment:
{chunk}

Extract technical concepts from this segment as JSON:
{{
  "concepts": [
    {{
      "name": "concept name",
      "description": "brief explanation",
      "code_keywords": ["relevant", "keywords", "for", "code", "search"],
      "importance": "high/medium/low"
    }}
  ],
  "code_patterns": ["any code snippets or patterns mentioned"],
  "technologies": ["libraries", "frameworks", "tools mentioned"]
}}

Focus on:
- Technical concepts being taught
- Code patterns or structures discussed
- Libraries, frameworks, or tools mentioned
- Step-by-step procedures explained

Return ONLY valid JSON, no markdown formatting."""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content


def map_concepts_to_files(concepts_json: str, repo_files: list[dict], video_title: str) -> str:
    """Pass 2: Map extracted concepts to specific files in the repository.

    Args:
        concepts_json: JSON string of extracted concepts from all chunks
        repo_files: List of file dicts with 'path' and 'content'
        video_title: Video title for context

    Returns:
        JSON-formatted mapping of concepts to files
    """
    # Build a summary of repo files for the LLM
    file_summaries = []
    for f in repo_files[:30]:  # Limit to avoid token overflow
        preview = f['content'][:1000] if len(f['content']) > 1000 else f['content']
        file_summaries.append(f"### {f['path']}\n```\n{preview}\n```")

    files_context = "\n\n".join(file_summaries)

    kwargs = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": f"""You're mapping concepts from a tutorial video to files in a companion repository.

Video: {video_title}

CONCEPTS FROM VIDEO:
{concepts_json}

REPOSITORY FILES:
{files_context}

Create a mapping of video concepts to repository files as JSON:
{{
  "mappings": [
    {{
      "concept": "concept name",
      "files": [
        {{
          "path": "relative/path/to/file.py",
          "relevance": "high/medium/low",
          "key_lines": "description of important sections",
          "explanation": "how this file demonstrates the concept"
        }}
      ]
    }}
  ],
  "suggested_reading_order": ["file1.py", "file2.py"],
  "entry_point": "main file to start exploring"
}}

Return ONLY valid JSON, no markdown formatting."""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content


def synthesize_tutorial(
    title: str,
    channel: str,
    video_link: str,
    video_id: str,
    repo_url: str,
    concepts_json: str,
    mappings_json: str,
    repo_files: list[dict]
) -> str:
    """Pass 3: Generate the main tutorial content with code walkthroughs.

    Args:
        title: Video title
        channel: Channel name
        video_link: URL to video
        video_id: YouTube video ID
        repo_url: GitHub repository URL
        concepts_json: Extracted concepts from Pass 1
        mappings_json: Concept-file mappings from Pass 2
        repo_files: Repository files with content

    Returns:
        Markdown tutorial content
    """
    # Build code examples section
    code_examples = []
    for f in repo_files[:20]:  # Include key files
        code_examples.append(f"### {f['path']}\n```\n{f['content'][:2000]}\n```")
    code_context = "\n\n".join(code_examples)

    embed_code = f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{video_id}" frameborder="0" allowfullscreen></iframe>'

    tutorial_max_tokens = config.get("tutorial_max_tokens", 16384)

    kwargs = {
        "model": MODEL,
        "max_tokens": tutorial_max_tokens,
        "messages": [
            {
                "role": "user",
                "content": f"""Create a comprehensive written tutorial based on a video and its companion repository.

VIDEO INFORMATION:
- Title: {title}
- Channel: {channel}
- Link: {video_link}
- Embed: {embed_code}

REPOSITORY: {repo_url}

EXTRACTED CONCEPTS:
{concepts_json}

CONCEPT-FILE MAPPINGS:
{mappings_json}

CODE FROM REPOSITORY:
{code_context}

Write a comprehensive tutorial in markdown format:

# Tutorial: {title}

> Based on [{title}]({video_link}) by {channel}
> Repository: [{repo_url.split('/')[-1]}]({repo_url})

{embed_code}

## Table of Contents
[Generate based on content]

## Introduction
[Why this topic matters, what you'll learn, prerequisites]

## Prerequisites
[Required knowledge, tools, setup steps]

## Getting Started
[How to clone the repo, install dependencies, run the code]

## Core Concepts
[Explain each major concept with:
- Clear explanation
- Code examples from the repo (use actual file paths and line references)
- How it connects to other concepts]

## Code Walkthrough
[Step-by-step walkthrough of key files:
- Purpose of each file
- Important functions/classes with explanations
- How files work together]

## Key Takeaways
[Summary of main learnings]

---

IMPORTANT:
- Use actual code from the repository with file paths
- Reference specific files like: "In `src/main.py`, we see..."
- Include syntax-highlighted code blocks with file names
- Make it educational and practical
- Write for someone who hasn't watched the video"""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content


def generate_lab_exercises(
    tutorial_content: str,
    repo_files: list[dict],
    concepts_json: str,
    difficulty: str = "intermediate"
) -> str:
    """Pass 4: Generate hands-on lab exercises.

    Args:
        tutorial_content: Generated tutorial from Pass 3
        repo_files: Repository files with content
        concepts_json: Extracted concepts
        difficulty: beginner/intermediate/advanced

    Returns:
        Markdown lab exercises section
    """
    # Get a few key files for exercise context
    exercise_files = []
    for f in repo_files[:10]:
        exercise_files.append(f"### {f['path']}\n```\n{f['content'][:1500]}\n```")
    files_context = "\n\n".join(exercise_files)

    difficulty_guide = {
        "beginner": "Simple modifications, clear step-by-step instructions, lots of hints",
        "intermediate": "Moderate challenges, some independent problem-solving required",
        "advanced": "Complex extensions, minimal hints, architectural thinking required"
    }

    kwargs = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": f"""Create hands-on lab exercises for a programming tutorial.

DIFFICULTY LEVEL: {difficulty}
Guidance: {difficulty_guide.get(difficulty, difficulty_guide['intermediate'])}

TUTORIAL CONTEXT:
{tutorial_content[:3000]}

CONCEPTS COVERED:
{concepts_json}

REPOSITORY CODE:
{files_context}

Generate 3-5 lab exercises in markdown:

---

## Lab Exercises

### Exercise 1: [Title] - Easy
**Objective:** [What the student will accomplish]
**File to modify:** `path/to/file.py`
**Estimated time:** X minutes

**Instructions:**
1. Step one
2. Step two
3. ...

<details>
<summary>💡 Hint 1</summary>

[First hint]

</details>

<details>
<summary>💡 Hint 2</summary>

[Second hint]

</details>

<details>
<summary>✅ Solution</summary>

```python
# Solution code
```

</details>

### Exercise 2: [Title] - Medium
[Similar format]

### Exercise 3: Clone & Extend Challenge - Hard
**Objective:** [A larger challenge that extends the project]
**Starting point:** Clone the repository
**What to build:** [Description of extension]

**Requirements:**
- Requirement 1
- Requirement 2

<details>
<summary>💡 Approach Hints</summary>

[High-level guidance without giving away the solution]

</details>

---

IMPORTANT:
- Use actual file paths from the repository
- Make exercises progressively harder
- Include practical, real-world scenarios
- Ensure exercises reinforce the tutorial concepts
- Solutions should be working code"""
            }
        ]
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content


# ============================================================
# DIGEST MODE - Transcript Processing
# ============================================================

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


# ============================================================
# TUTORIAL MODE - Orchestration
# ============================================================

def run_tutorial_mode(video_input: str, repo_url: str, clone_path: str = "./tutorial_repos/",
                      max_files: int = 50, file_types: str = ".py,.js,.ts,.go,.java,.rs,.md",
                      difficulty: str = "intermediate") -> dict | None:
    """Main orchestration function for tutorial mode.

    Args:
        video_input: YouTube video URL or ID
        repo_url: GitHub repository URL
        clone_path: Directory to clone repos into
        max_files: Maximum files to analyze
        file_types: File extensions to include
        difficulty: Difficulty level for exercises

    Returns:
        Dict with tutorial content, or None on failure
    """
    import json

    print(f"\n📚 Tutorial Mode")
    print("=" * 60)

    # Parse video ID
    if "youtube.com" in video_input or "youtu.be" in video_input:
        if "v=" in video_input:
            video_id = video_input.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_input:
            video_id = video_input.split("youtu.be/")[1].split("?")[0]
        else:
            print(f"❌ Could not parse video URL: {video_input}")
            return None
    else:
        video_id = video_input

    video_link = f"https://www.youtube.com/watch?v={video_id}"
    print(f"🎬 Video ID: {video_id}")

    # Get video info
    print("🔍 Fetching video info...")
    video_info = get_video_info(video_id)
    if video_info:
        video_title = video_info["title"]
        channel_name = video_info["channel"]
    else:
        video_title = f"Tutorial Video {video_id}"
        channel_name = "Unknown Channel"

    print(f"📹 Title: {video_title}")
    print(f"📺 Channel: {channel_name}")

    # Get transcript
    print("\n📝 Fetching transcript...")
    transcript = get_transcript(video_id)
    if not transcript:
        print("❌ Could not get transcript. This video may not have captions.")
        return None
    print(f"✅ Got transcript ({len(transcript)} chars)")

    # Clone repository
    print(f"\n📦 Repository: {repo_url}")
    repo_path = clone_repo(repo_url, clone_path)
    if not repo_path:
        print("❌ Could not clone repository")
        return None

    # Discover and read repo files
    print("\n📂 Analyzing repository...")
    files = discover_repo_files(repo_path, file_types, max_files)
    if not files:
        print("⚠️  No matching files found in repository")
        return None

    repo_files = read_repo_files(files)
    print(f"✅ Read {len(repo_files)} files")

    # Pass 1: Extract concepts from transcript chunks
    print("\n🧠 Pass 1: Extracting concepts from video...")
    chunks = chunk_transcript(transcript)
    print(f"  📄 Split into {len(chunks)} chunks")

    all_concepts = []
    for i, chunk in enumerate(chunks):
        print(f"  🔍 Analyzing chunk {i+1}/{len(chunks)}...")
        concepts = extract_concepts_from_chunk(video_title, chunk, i+1, len(chunks))
        all_concepts.append(concepts)

    # Combine all concepts
    combined_concepts = "\n---\n".join(all_concepts)

    # Pass 2: Map concepts to repository files
    print("\n🗺️  Pass 2: Mapping concepts to repository files...")
    mappings = map_concepts_to_files(combined_concepts, repo_files, video_title)
    print("  ✅ Created concept-file mappings")

    # Pass 3: Synthesize tutorial
    print("\n✍️  Pass 3: Generating tutorial content...")
    tutorial_content = synthesize_tutorial(
        title=video_title,
        channel=channel_name,
        video_link=video_link,
        video_id=video_id,
        repo_url=repo_url,
        concepts_json=combined_concepts,
        mappings_json=mappings,
        repo_files=repo_files
    )
    print("  ✅ Tutorial generated")

    # Pass 4: Generate lab exercises
    print(f"\n🧪 Pass 4: Generating lab exercises (difficulty: {difficulty})...")
    lab_exercises = generate_lab_exercises(
        tutorial_content=tutorial_content,
        repo_files=repo_files,
        concepts_json=combined_concepts,
        difficulty=difficulty
    )
    print("  ✅ Lab exercises generated")

    # Combine tutorial and labs
    full_tutorial = f"{tutorial_content}\n\n{lab_exercises}"

    # Add footer
    full_tutorial += f"""

---

## Attribution

This tutorial was generated based on [{video_title}]({video_link}) by {channel_name}.
Repository: [{repo_url}]({repo_url})

Please subscribe to {channel_name}'s channel and star the repository to support their work!

---
*Generated with YouTube Tutorial Digest*
"""

    return {
        "title": video_title,
        "channel": channel_name,
        "video_id": video_id,
        "video_link": video_link,
        "repo_url": repo_url,
        "content": full_tutorial,
        "concepts": combined_concepts,
        "mappings": mappings
    }


def generate_tutorial_html(content: str, title: str, date_str: str) -> str:
    """Generate HTML output for tutorial with syntax highlighting.

    Args:
        content: Markdown tutorial content
        title: Tutorial title
        date_str: Date string for display

    Returns:
        HTML string
    """
    import re

    def markdown_to_html(md_text: str) -> str:
        """Convert markdown to HTML with syntax highlighting support."""
        html = md_text

        # Code blocks with language
        def replace_code_block(match):
            lang = match.group(1) or ''
            code = match.group(2)
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            return f'<pre><code class="language-{lang}">{code}</code></pre>'

        html = re.sub(r'```(\w*)\n(.*?)```', replace_code_block, html, flags=re.DOTALL)

        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Headers
        html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', html)

        # Blockquotes
        html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)

        # Details/summary (collapsible sections)
        html = re.sub(r'<details>\s*<summary>(.+?)</summary>\s*', r'<details><summary>\1</summary><div class="details-content">', html)
        html = re.sub(r'</details>', r'</div></details>', html)

        # Line breaks for paragraphs
        html = re.sub(r'\n\n', '</p><p>', html)

        # Bullet points
        html = re.sub(r'^\- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>\n?)+', r'<ul>\g<0></ul>', html)

        # Numbered lists
        html = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        return f"<p>{html}</p>"

    article_content = markdown_to_html(content)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Tutorial</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script>hljs.highlightAll();</script>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.7;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f9fafb;
            color: #1f2937;
        }}
        h1 {{
            color: #111827;
            border-bottom: 3px solid #3b82f6;
            padding-bottom: 10px;
            margin-top: 1.5em;
        }}
        h2 {{
            color: #1f2937;
            margin-top: 2em;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #374151;
            margin-top: 1.5em;
        }}
        h4 {{
            color: #4b5563;
            margin-top: 1.2em;
        }}
        .tutorial-content {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        iframe {{
            width: 100%;
            max-width: 560px;
            height: 315px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        pre {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 14px;
        }}
        pre code {{
            background: transparent;
            color: inherit;
        }}
        code {{
            background: #f1f5f9;
            color: #0f172a;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        blockquote {{
            border-left: 4px solid #3b82f6;
            margin: 20px 0;
            padding: 10px 20px;
            background: #eff6ff;
            color: #1e40af;
        }}
        a {{
            color: #2563eb;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        ul, ol {{
            padding-left: 24px;
        }}
        li {{
            margin: 8px 0;
        }}
        details {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin: 12px 0;
            padding: 0;
        }}
        summary {{
            cursor: pointer;
            padding: 12px 16px;
            font-weight: 500;
            background: #f1f5f9;
            border-radius: 8px 8px 0 0;
        }}
        details[open] summary {{
            border-bottom: 1px solid #e2e8f0;
        }}
        .details-content {{
            padding: 16px;
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
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
        }}
        .toc {{
            background: #f8fafc;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .toc ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        .toc li {{
            margin: 8px 0;
        }}
        .toc a {{
            color: #475569;
        }}
    </style>
</head>
<body>
    <div class="tutorial-content">
        {article_content}
    </div>

    <div class="footer">
        <p>Generated with YouTube Tutorial Digest - {date_str}</p>
    </div>
</body>
</html>"""

    return html


# ============================================================
# DIGEST MODE - Output Generation
# ============================================================

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


def parse_args():
    """Parse command line arguments with argparse."""
    import argparse

    parser = argparse.ArgumentParser(
        description="YouTube Daily Digest - AI-powered video summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run channel digest (processes all channels in config.yaml)
  python youtube_digest.py

  # Summarize a single video
  python youtube_digest.py VIDEO_ID
  python youtube_digest.py "https://www.youtube.com/watch?v=VIDEO_ID"

  # Generate tutorial from video + GitHub repo
  python youtube_digest.py tutorial VIDEO_ID https://github.com/user/repo
  python youtube_digest.py tutorial VIDEO_ID https://github.com/user/repo --difficulty advanced
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Tutorial subcommand
    tutorial_parser = subparsers.add_parser(
        "tutorial",
        help="Generate tutorial from video + GitHub repository"
    )
    tutorial_parser.add_argument(
        "video",
        help="YouTube video URL or ID"
    )
    tutorial_parser.add_argument(
        "repo",
        help="GitHub repository URL"
    )
    tutorial_parser.add_argument(
        "--clone-path",
        default=config.get("tutorial_clone_path", "./tutorial_repos/"),
        help="Directory to clone repos into (default: ./tutorial_repos/)"
    )
    tutorial_parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="Maximum files to analyze (default: 50)"
    )
    tutorial_parser.add_argument(
        "--file-types",
        default=".py,.js,.ts,.go,.java,.rs,.md",
        help="File extensions to include (default: .py,.js,.ts,.go,.java,.rs,.md)"
    )
    tutorial_parser.add_argument(
        "--difficulty",
        choices=["beginner", "intermediate", "advanced"],
        default="intermediate",
        help="Difficulty level for lab exercises (default: intermediate)"
    )

    # For backward compatibility: positional argument for single video mode
    parser.add_argument(
        "single_video",
        nargs="?",
        help="YouTube video URL or ID (for single video mode)"
    )

    return parser.parse_args()


def run_single_video_mode(video_input: str):
    """Run single video summarization mode."""
    # Extract video ID from URL or use directly
    if "youtube.com" in video_input or "youtu.be" in video_input:
        if "v=" in video_input:
            video_id = video_input.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_input:
            video_id = video_input.split("youtu.be/")[1].split("?")[0]
        else:
            print(f"❌ Could not parse video URL: {video_input}")
            return
    else:
        video_id = video_input

    print(f"\n📺 Single Video Mode")
    print("=" * 60)
    print(f"🎬 Video ID: {video_id}")

    # Try to get video info (title, channel)
    print("🔍 Fetching video info...")
    video_info = get_video_info(video_id)

    if video_info:
        video_title = video_info["title"]
        channel_name = video_info["channel"]
    else:
        video_title = f"Video {video_id}"
        channel_name = "Unknown Channel"

    video_link = f"https://www.youtube.com/watch?v={video_id}"

    print(f"📹 Title: {video_title}")
    print(f"📺 Channel: {channel_name}")

    # Get transcript
    print("📝 Fetching transcript...")
    transcript = get_transcript(video_id)
    if not transcript:
        print("❌ Could not get transcript")
        return

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


if __name__ == "__main__":
    import sys

    args = parse_args()

    if args.command == "tutorial":
        # Tutorial mode
        result = run_tutorial_mode(
            video_input=args.video,
            repo_url=args.repo,
            clone_path=args.clone_path,
            max_files=args.max_files,
            file_types=args.file_types,
            difficulty=args.difficulty
        )

        if result:
            # Save tutorial output
            date_str = datetime.now().strftime('%Y-%m-%d')
            safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in result["title"])[:50]

            # Ensure output directory exists
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            if OUTPUT_FORMAT in ("markdown", "both"):
                md_file = os.path.join(OUTPUT_DIR, f"tutorial_{safe_title}_{date_str}.md")
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(result["content"])
                print(f"\n📄 Markdown saved: {md_file}")

            if OUTPUT_FORMAT in ("html", "both"):
                html_content = generate_tutorial_html(
                    result["content"],
                    result["title"],
                    date_str
                )
                html_file = os.path.join(OUTPUT_DIR, f"tutorial_{safe_title}_{date_str}.html")
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"🌐 HTML saved: {html_file}")

            print("\n" + "=" * 60)
            print("✅ Tutorial complete!")
        else:
            print("\n❌ Tutorial generation failed")
            sys.exit(1)

    elif args.single_video:
        # Single video mode (backward compatible)
        run_single_video_mode(args.single_video)

    else:
        # Normal channel digest mode
        main()
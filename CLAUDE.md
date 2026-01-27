# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube Daily Digest - fetches latest videos from YouTube channels via RSS, extracts transcripts, and generates AI-summarized blog posts. Uses LiteLLM for provider-agnostic LLM access (Anthropic, OpenAI, Ollama, etc.).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run channel digest (processes all channels in config.yaml)
python youtube_digest.py

# Summarize a single video
python youtube_digest.py "https://www.youtube.com/watch?v=VIDEO_ID"
python youtube_digest.py VIDEO_ID

# Generate tutorial from video + GitHub repo
python youtube_digest.py tutorial VIDEO_ID https://github.com/user/repo
python youtube_digest.py tutorial VIDEO_ID https://github.com/user/repo --difficulty advanced
python youtube_digest.py tutorial VIDEO_ID https://github.com/user/repo --max-files 100 --file-types ".py,.md"

# Import YouTube subscriptions
python get_subscriptions.py opml subscription_manager.xml
python get_subscriptions.py takeout subscriptions.json
```

## Architecture

**Processing Pipeline:**
```
RSS Feed → Transcript Extraction → Chunk Splitting → Multi-pass LLM → HTML/Markdown Output
```

**Key Files:**
- `youtube_digest.py` - Main script with all core logic
- `get_subscriptions.py` - Import subscriptions utility
- `config.yaml` - User configuration (model, channels, output settings)
- `.env` - API keys only

**Multi-pass LLM Processing (for long videos):**
1. `chunk_transcript()` - Split transcript into ~10KB chunks
2. `summarize_chunk()` - LLM summarizes each chunk (1024 token limit)
3. `synthesize_blog_post()` - LLM combines chunk summaries into final blog post

**Three Execution Modes:**
- Channel digest mode (default): Processes all channels, outputs `blog/digest_YYYY-MM-DD.md/html`
- Single video mode: Pass URL/ID as argument, outputs `blog/video_TITLE_YYYY-MM-DD.md/html`
- Tutorial mode: Video + GitHub repo, outputs `blog/tutorial_TITLE_YYYY-MM-DD.md/html`

**Tutorial Mode Pipeline (4-pass LLM processing):**
```
┌─────────────────────────────────────────────────────────────┐
│                      TUTORIAL MODE                          │
└─────────────────────────────────────────────────────────────┘
        │                                    │
   ┌────▼────┐                         ┌─────▼─────┐
   │ VIDEO   │                         │   REPO    │
   │ Transcript                        │ git clone │
   │ + Chunk │                         │ + read    │
   └────┬────┘                         └─────┬─────┘
        │                                    │
   ┌────▼────┐                               │
   │ PASS 1  │  extract_concepts_from_chunk()
   │ Extract │  → JSON concepts per chunk    │
   │ Concepts│ ◄─────────────────────────────┘
   └────┬────┘
        │
   ┌────▼────┐
   │ PASS 2  │  map_concepts_to_files()
   │ Mapping │  → concepts mapped to repo files
   └────┬────┘
        │
   ┌────▼────┐
   │ PASS 3  │  synthesize_tutorial()
   │Tutorial │  → full tutorial with code walkthroughs
   └────┬────┘
        │
   ┌────▼────┐
   │ PASS 4  │  generate_lab_exercises()
   │  Labs   │  → hands-on exercises with hints/solutions
   └────┬────┘
        │
   ┌────▼────┐
   │ Output  │  blog/tutorial_TITLE_DATE.md/html
   └─────────┘
```

**Tutorial Mode Functions:**
- `clone_repo()` - Git clone with --depth 1
- `discover_repo_files()` - Find code files, skip node_modules/.git/etc
- `read_repo_files()` - Read content, truncate large files
- `extract_concepts_from_chunk()` - Pass 1: Extract concepts as JSON
- `map_concepts_to_files()` - Pass 2: Map concepts to repo files
- `synthesize_tutorial()` - Pass 3: Generate tutorial content
- `generate_lab_exercises()` - Pass 4: Create hands-on labs

## Configuration

All settings in `config.yaml`. The `model` field accepts any LiteLLM-compatible model string:
- Anthropic: `claude-haiku-4-5`, `claude-sonnet-4-5-20250929`
- OpenAI: `gpt-4o`, `gpt-4o-mini`
- Ollama: `ollama/llama3` (set `api_base: http://localhost:11434`)

## Key Characteristics

- No YouTube API key required (uses RSS feeds)
- Free transcript extraction via unofficial `youtube-transcript-api`
- Stateless design - no tracking of processed videos
- Only works for videos with captions
- RSS feeds limited to last 15 videos per channel

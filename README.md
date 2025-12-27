# YouTube Daily Digest

Automatically fetch, transcribe, and summarize your YouTube subscriptions into AI-generated blog posts.

## Features

- 📡 Fetches latest videos via RSS (no YouTube API key needed)
- 📝 Extracts full transcripts automatically
- 🤖 Multi-pass AI summarization (handles long videos)
- 📄 Outputs Markdown or HTML with embedded videos
- ✅ Proper attribution to creators
- 🎬 Single video mode - summarize any video on demand
- ⚙️ Configurable videos per channel
- 🔌 **Provider agnostic** - works with Anthropic, OpenAI, Ollama, and 100+ LLMs

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your LLM provider

**For cloud providers (Anthropic, OpenAI, etc.):**
```bash
cp env-example.txt .env
# Edit .env and add your API key
```

**For local models (Ollama, LM Studio):**
No API key needed - just set `api_base` in `config.yaml`

### 3. Import your YouTube subscriptions

```bash
# Go to https://www.youtube.com/subscription_manager
# Click "Export subscriptions" at the bottom
python get_subscriptions.py opml subscription_manager.xml
```

### 4. Run the digest

```bash
python youtube_digest.py
```

## Usage

### Channel Digest Mode (default)

```bash
python youtube_digest.py
```

### Single Video Mode

```bash
# Any of these work:
python youtube_digest.py "https://www.youtube.com/watch?v=VIDEO_ID"
python youtube_digest.py "https://youtu.be/VIDEO_ID"
python youtube_digest.py VIDEO_ID
```

## Configuration

All configuration lives in `config.yaml`. The `.env` file is only for API keys (secrets).

### config.yaml

```yaml
# Output format: markdown, html, or both
output_format: markdown

# Output directory for generated files (created automatically)
output_dir: blog

# LLM model to use (see provider docs for model names)
model: claude-sonnet-4-5-20250929

# Max tokens for blog generation (increase for 2+ hour videos)
max_tokens: 8192

# For local models, set the API endpoint:
# api_base: http://localhost:11434

# Videos per channel (1-15 or "all")
videos_per_channel: 1

# Your subscribed channels
channels:
  - id: UCsBjURrPoezykLs9EqgamOA
    name: Fireship
  - id: UCXl4i9dYBrFOabk0xGmbkRA
    name: Dwarkesh Patel
    videos: 3  # Override for this channel
```

### Configuration Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `output_format` | `markdown`, `html`, `both` | `markdown` | Output file format |
| `output_dir` | directory path | `blog` | Where to save generated files |
| `model` | LLM model string | `claude-sonnet-4-5-20250929` | AI model for summarization |
| `max_tokens` | integer | `8192` | Max tokens for blog generation (increase for long videos) |
| `api_base` | URL | (none) | Custom API endpoint for local models |
| `videos_per_channel` | `1`-`15` or `all` | `1` | Videos to fetch per channel |
| `channels[].videos` | `1`-`15` or `all` | (global default) | Per-channel override |

### .env (secrets only)

```bash
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or other provider keys

# Optional overrides (usually set in config.yaml instead)
# OUTPUT_DIR=blog
# OUTPUT_FORMAT=both
```

## Supported LLM Providers

This project uses [LiteLLM](https://docs.litellm.ai/docs/providers) for unified access to 100+ LLM providers.

| Provider | Model Examples | Docs |
|----------|---------------|------|
| Anthropic | `claude-sonnet-4-5-20250929` | [docs.anthropic.com](https://docs.anthropic.com/en/docs/about-claude/models/all-models) |
| OpenAI | `gpt-4o`, `gpt-4o-mini` | [platform.openai.com](https://platform.openai.com/docs/models) |
| Ollama (local) | `ollama/llama3`, `ollama/mistral` | [ollama.com/library](https://ollama.com/library) |
| OpenRouter | `openrouter/...` | [openrouter.ai/docs](https://openrouter.ai/docs) |
| Others | See LiteLLM docs | [docs.litellm.ai](https://docs.litellm.ai/docs/providers) |

### Using Local Models (Ollama)

1. Install Ollama: https://ollama.com
2. Pull a model: `ollama pull llama3`
3. Configure `config.yaml`:
```yaml
model: ollama/llama3
api_base: http://localhost:11434
```
4. No API key needed in `.env`

## How It Works

```
RSS Feed → Transcript API → LLM (chunk + summarize) → Markdown/HTML
   │            │                    │
   └── free ────┴── free ────────────┴── your provider
```

1. **RSS Feed** - Get latest videos (free, no auth)
2. **Transcript API** - Extract captions (free, unofficial)
3. **LLM** - Multi-pass summarization (your chosen provider)
4. **Output** - Blog posts with attribution and embeds

## Output Files

Files are saved to the `output_dir` directory (default: `blog/`):

**Channel digest mode:**
```
blog/digest_2024-12-27.md
blog/digest_2024-12-27.html
```

**Single video mode:**
```
blog/video_Video-Title_2024-12-27.md
blog/video_Video-Title_2024-12-27.html
```

The directory is created automatically if it doesn't exist.

## Cost Considerations

Costs depend on your LLM provider. For a typical 30-minute video:
- ~15,000 tokens input (transcript)
- ~2,000 tokens output (summary)
- Multiply by number of chunks for longer videos

**Free options:** Use Ollama with local models (requires decent GPU/CPU)

## Scheduling

### Cron (Mac/Linux)
```bash
0 8 * * * cd /path/to/digest && python youtube_digest.py >> digest.log 2>&1
```

### Task Scheduler (Windows)
```
Program: python
Arguments: youtube_digest.py
Start in: C:\path\to\digest
```

## File Structure

```
youtube-digest/
├── youtube_digest.py      # Main script
├── get_subscriptions.py   # Import subscriptions
├── config.yaml            # All configuration
├── .env                   # API keys only (secrets)
├── requirements.txt       # Dependencies
├── README.md             
├── LICENSE               
└── blog/                  # Output directory (auto-created)
    ├── digest_2024-12-27.md
    └── digest_2024-12-27.html
```

## Limitations

- Only works for videos with captions
- RSS feeds show last 15 videos per channel
- Transcript API is unofficial (stable but could break)

## Troubleshooting

**"Could not get transcript"**
- Video may not have captions enabled

**Model errors**
- Check your API key in `.env`
- Verify model name matches your provider's docs
- For local models, ensure the server is running

**SSL certificate errors**
- Install: `pip install --upgrade certifi`

## License

MIT License - see [LICENSE](LICENSE)

## Disclaimer

**This software is provided "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement. Use at your own risk.**

### Important Notices

- **AI-Generated Code.** This project was built using AI-assisted development ("vibe coding") with Claude. While functional, it may contain bugs, inefficiencies, or unexpected behavior. Review the code before use in production environments.

- **Not Affiliated.** This is an independent project and is not endorsed, sponsored, or affiliated with YouTube, Google, or Anthropic.

- **Respect Copyright.** Generated summaries are intended for personal use. If publishing summaries publicly, ensure proper attribution to original creators and consider fair use guidelines in your jurisdiction. This tool is designed to complement, not replace, watching original content.

- **API Terms of Service.** Users are responsible for complying with:
  - [YouTube Terms of Service](https://www.youtube.com/t/terms)
  - [Anthropic Acceptable Use Policy](https://www.anthropic.com/legal/aup)

- **Unofficial APIs.** This tool uses the unofficial `youtube-transcript-api` library which may break without notice if YouTube changes their systems.

- **No Guarantee of Accuracy.** AI-generated summaries may contain errors, omissions, or misinterpretations. Always refer to the original video for authoritative information.

- **Rate Limits.** Excessive use may result in temporary blocks from YouTube or API rate limiting. Use responsibly.

## Attribution

When using generated summaries publicly, the script automatically includes proper attribution to original creators. This is both ethical and helps drive traffic to their channels.

## Contributing

Ideas for improvement:
- [ ] Track processed videos to avoid re-summarizing
- [ ] Email/Slack delivery
- [ ] Playlist support
- [ ] Parallel processing
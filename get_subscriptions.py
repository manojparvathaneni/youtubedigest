#!/usr/bin/env python3
"""
YouTube Subscription Exporter
Extracts your subscribed channels and updates config.yaml

Methods available:
1. Google Takeout (recommended) - Export from Google, then run this script
2. YouTube Data API with OAuth - Requires Google Cloud setup
3. Manual browser script - Copy/paste from browser console
"""

import json
import yaml
import os
from pathlib import Path

CONFIG_FILE = "config.yaml"


def load_existing_config() -> dict:
    """Load existing config or create default."""
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f) or {}
    return {"output_format": "markdown", "channels": []}


def save_config(config: dict):
    """Save config to YAML file."""
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Saved {len(config.get('channels', []))} channels to {CONFIG_FILE}")


def import_from_takeout(takeout_path: str):
    """
    Import from Google Takeout export.
    
    Steps to get the file:
    1. Go to https://takeout.google.com
    2. Deselect all, then select only "YouTube and YouTube Music"
    3. Click "All YouTube data included" -> Deselect all -> Select only "subscriptions"
    4. Export and download
    5. Extract the zip, find: Takeout/YouTube and YouTube Music/subscriptions/subscriptions.json
    6. Run: python get_subscriptions.py takeout path/to/subscriptions.json
    """
    with open(takeout_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    channels = []
    for item in data:
        # Takeout format has snippet.resourceId.channelId and snippet.title
        snippet = item.get('snippet', {})
        channel_id = snippet.get('resourceId', {}).get('channelId')
        channel_name = snippet.get('title')
        
        if channel_id and channel_name:
            channels.append({
                'id': channel_id,
                'name': channel_name
            })
    
    config = load_existing_config()
    config['channels'] = channels
    save_config(config)
    
    print(f"\n📺 Imported {len(channels)} subscriptions:")
    for ch in channels[:10]:
        print(f"   - {ch['name']}")
    if len(channels) > 10:
        print(f"   ... and {len(channels) - 10} more")


def import_from_opml(opml_path: str):
    """
    Import from YouTube subscription OPML export.
    
    Steps:
    1. Go to https://www.youtube.com/subscription_manager
    2. Scroll to bottom, click "Export subscriptions"
    3. Run: python get_subscriptions.py opml path/to/subscription_manager.xml
    """
    import xml.etree.ElementTree as ET
    
    tree = ET.parse(opml_path)
    root = tree.getroot()
    
    channels = []
    for outline in root.findall('.//outline[@xmlUrl]'):
        # OPML has xmlUrl with channel ID and title attribute
        xml_url = outline.get('xmlUrl', '')
        title = outline.get('title', outline.get('text', 'Unknown'))
        
        # Extract channel ID from URL
        # Format: https://www.youtube.com/feeds/videos.xml?channel_id=UC...
        if 'channel_id=' in xml_url:
            channel_id = xml_url.split('channel_id=')[1]
            channels.append({
                'id': channel_id,
                'name': title
            })
    
    config = load_existing_config()
    config['channels'] = channels
    save_config(config)
    
    print(f"\n📺 Imported {len(channels)} subscriptions:")
    for ch in channels[:10]:
        print(f"   - {ch['name']}")
    if len(channels) > 10:
        print(f"   ... and {len(channels) - 10} more")


def import_from_json(json_path: str):
    """
    Import from a simple JSON file.
    
    Expected format:
    [
        {"id": "UCsBjURrPoezykLs9EqgamOA", "name": "Fireship"},
        {"id": "UC...", "name": "Another Channel"}
    ]
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        channels = json.load(f)
    
    config = load_existing_config()
    config['channels'] = channels
    save_config(config)


def print_browser_script():
    """
    Print a JavaScript snippet to run in browser console.
    
    This extracts subscriptions directly from the YouTube subscriptions page.
    """
    script = '''
// Run this in browser console at https://www.youtube.com/feed/channels
// Scroll down first to load all subscriptions!

const channels = [];
document.querySelectorAll('ytd-channel-renderer').forEach(el => {
    const link = el.querySelector('a#main-link');
    const name = el.querySelector('#text').textContent.trim();
    if (link && name) {
        const href = link.href;
        const match = href.match(/channel\\/(UC[\\w-]+)/);
        if (match) {
            channels.push({id: match[1], name: name});
        }
    }
});

// Copy to clipboard as JSON
copy(JSON.stringify(channels, null, 2));
console.log(`Copied ${channels.length} channels to clipboard!`);
console.log('Paste into a file and run: python get_subscriptions.py json channels.json');
'''
    print("\n📋 Browser Console Script")
    print("=" * 50)
    print("1. Go to https://www.youtube.com/feed/channels")
    print("2. Scroll down to load ALL your subscriptions")
    print("3. Open browser console (F12 -> Console)")
    print("4. Paste this script and press Enter:")
    print("-" * 50)
    print(script)
    print("-" * 50)
    print("5. Save the clipboard contents to a file (e.g., channels.json)")
    print("6. Run: python get_subscriptions.py json channels.json")


def print_usage():
    """Print usage instructions."""
    print("""
YouTube Subscription Exporter
=============================

Usage:
    python get_subscriptions.py <method> [file_path]

Methods:

1. OPML Export (Easiest - Recommended)
   ------------------------------------
   a. Go to https://www.youtube.com/subscription_manager
   b. Scroll to bottom, click "Export subscriptions" 
   c. Run: python get_subscriptions.py opml subscription_manager.xml

2. Google Takeout
   ---------------
   a. Go to https://takeout.google.com
   b. Deselect all -> Select "YouTube" -> Only "subscriptions"
   c. Export and download the zip
   d. Extract and find: Takeout/YouTube.../subscriptions/subscriptions.json
   e. Run: python get_subscriptions.py takeout subscriptions.json

3. Browser Script
   ---------------
   Run: python get_subscriptions.py browser
   (Prints a script to paste in browser console)

4. JSON File
   ----------
   If you have a JSON array of {id, name} objects:
   Run: python get_subscriptions.py json channels.json

After importing, your config.yaml will be updated with all channels.
""")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)
    
    method = sys.argv[1].lower()
    
    if method == "opml":
        if len(sys.argv) < 3:
            print("Error: Please provide path to OPML file")
            print("Usage: python get_subscriptions.py opml subscription_manager.xml")
            sys.exit(1)
        import_from_opml(sys.argv[2])
    
    elif method == "takeout":
        if len(sys.argv) < 3:
            print("Error: Please provide path to Takeout JSON file")
            print("Usage: python get_subscriptions.py takeout subscriptions.json")
            sys.exit(1)
        import_from_takeout(sys.argv[2])
    
    elif method == "json":
        if len(sys.argv) < 3:
            print("Error: Please provide path to JSON file")
            print("Usage: python get_subscriptions.py json channels.json")
            sys.exit(1)
        import_from_json(sys.argv[2])
    
    elif method == "browser":
        print_browser_script()
    
    else:
        print(f"Unknown method: {method}")
        print_usage()
        sys.exit(1)
import os
import re
import feedparser
import urllib.request
import google.generativeai as genai
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().strip("'\"")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip().strip("'\"")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip().strip("'\"")

if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_KEY:
    raise ValueError("Missing secrets in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

RSS_FEEDS = [
    {
        "source": "گوگل نیوز اردو",
        "url": "https://news.google.com/rss?hl=ur&gl=IN&ceid=IN:ur"
    },
    {
        "source": "بی بی سی اردو",
        "url": "https://feeds.bbci.co.uk/urdu/rss.xml"
    }
]

# High quality reliable fallback news photography
FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=800&q=80"
]

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def summarize_urdu(title, description):
    prompt = f"""
    You are an Urdu news editor for an Inshorts-style mobile app in India.
    Summarize this news article strictly in natural, modern Urdu.
    Length: 40 to 60 words.
    Return ONLY the Urdu summary text. No English words, no preambles.

    Title: {title}
    Details: {description}
    """
    try:
        res = model.generate_content(prompt)
        return res.text.strip()
    except Exception as err:
        print(f"Gemini error: {err}")
        return None

def extract_image(entry, index):
    # Check media content tags
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    # Check enclosure tags
    if "enclosures" in entry and entry.enclosures:
        return entry.enclosures[0].get("href")
    # Check for image inside HTML description
    raw_html = getattr(entry, "summary", "") or getattr(entry, "description", "")
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html)
    if match:
        return match.group(1)
    
    return FALLBACK_IMAGES[index % len(FALLBACK_IMAGES)]

def run():
    total_added = 0
    img_counter = 0

    for feed in RSS_FEEDS:
        print(f"--> Fetching: {feed['source']}")
        parsed = feedparser.parse(feed["url"])
        print(f"Found {len(parsed.entries)} items.")

        for entry in parsed.entries[:6]:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                continue

            # Prevent duplicates
            existing = supabase.table("news").select("id").eq("source_url", link).execute()
            if existing.data and len(existing.data) > 0:
                print(f"Skipping duplicate: {title[:25]}...")
                continue

            desc = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            img = extract_image(entry, img_counter)
            img_counter += 1

            print(f"Summarizing: {title[:30]}...")
            summary = summarize_urdu(title, desc or title)

            if not summary:
                continue

            payload = {
                "title": title,
                "summary": summary,
                "source_name": feed["source"],
                "source_url": link,
                "image_url": img
            }

            supabase.table("news").insert(payload).execute()
            print(f"Successfully saved: {title[:25]}")
            total_added += 1

    print(f"Job complete. Added {total_added} stories.")

if __name__ == "__main__":
    run()

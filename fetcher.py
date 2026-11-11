import os
import re
import feedparser
import google.generativeai as genai
from supabase import create_client, Client

# Read secrets
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().strip("'\"")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip().strip("'\"")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip().strip("'\"")

if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_KEY:
    raise ValueError("Missing one or more required environment variables.")

# Connect clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Verified Indian news feeds
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

DEFAULT_IMAGE = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&w=800&q=80"

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def summarize_urdu(title, description):
    prompt = f"""
    You are an Urdu news editor for a mobile Inshorts-style app in India.
    Summarize this news article strictly in high quality, modern Urdu.
    Length: exactly 40 to 60 words.
    Return ONLY the Urdu summary text. No headings, no English, no greetings.

    Title: {title}
    Details: {description}
    """
    try:
        res = model.generate_content(prompt)
        return res.text.strip()
    except Exception as err:
        print(f"Gemini error: {err}")
        return None

def extract_image(entry):
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")
    if "enclosures" in entry and entry.enclosures:
        return entry.enclosures[0].get("href")
    return DEFAULT_IMAGE

def run():
    total_added = 0
    for feed in RSS_FEEDS:
        print(f"Reading feed: {feed['source']}")
        parsed = feedparser.parse(feed["url"])
        print(f"Found {len(parsed.entries)} entries.")

        for entry in parsed.entries[:5]:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                continue

            # Check for duplicates
            existing = supabase.table("news").select("id").eq("source_url", link).execute()
            if existing.data and len(existing.data) > 0:
                print(f"Already exists: {title[:30]}...")
                continue

            desc = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            img = extract_image(entry) or DEFAULT_IMAGE

            print(f"Summarizing: {title[:40]}...")
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
            print(f"Saved: {title[:30]}")
            total_added += 1

    print(f"Pipeline complete. Inserted {total_added} new stories.")

if __name__ == "__main__":
    run()

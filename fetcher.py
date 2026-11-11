import os
import re
import feedparser
import google.generativeai as genai
from supabase import create_client, Client

# 1. Clean and validate environment variables
raw_url = os.environ.get("SUPABASE_URL", "")
raw_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
raw_gemini = os.environ.get("GEMINI_API_KEY", "")

SUPABASE_URL = raw_url.strip().strip("'\"")
SUPABASE_KEY = raw_key.strip().strip("'\"")
GEMINI_KEY = raw_gemini.strip().strip("'\"")

if not SUPABASE_URL.startswith("http"):
    raise ValueError(f"SUPABASE_URL is invalid or missing: '{SUPABASE_URL}'")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY is missing from GitHub Secrets.")

if not GEMINI_KEY:
    raise ValueError("GEMINI_API_KEY is missing from GitHub Secrets.")

# 2. Initialize Supabase and Gemini
print("Connecting to Supabase...")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("Configuring Gemini...")
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# 3. RSS Feeds for Indian News
RSS_FEEDS = [
    {"source": "NDTV India", "url": "https://feeds.feedburner.com/ndtvkhabar"},
    {"source": "BBC Urdu", "url": "https://feeds.bbci.co.uk/urdu/rss.xml"}
]

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def summarize_to_urdu(title, text):
    prompt = f"""
    You are an expert Urdu news editor for an Inshorts-style mobile app in India.
    Summarize the following news item strictly in pure, natural Urdu.
    
    Rules:
    - Maximum 50 to 60 words.
    - Write only the summary in Urdu script. No preamble, no English words, no markdown headings.
    - Focus on the factual core: what happened, where, and why it matters to Indian readers.

    Title: {title}
    Story: {text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini generation error: {e}")
        return None

def run():
    total_added = 0
    for feed_info in RSS_FEEDS:
        print(f"Fetching from {feed_info['source']}...")
        parsed = feedparser.parse(feed_info["url"])
        
        # Take the top 3 latest stories per feed
        for entry in parsed.entries[:3]:
            source_url = getattr(entry, "link", None)
            if not source_url:
                continue

            # Check if this article already exists in Supabase
            check = supabase.table("news").select("id").eq("source_url", source_url).execute()
            if check.data and len(check.data) > 0:
                print(f"Skipping (already exists): {entry.title[:30]}...")
                continue

            title = getattr(entry, "title", "")
            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
            cleaned_desc = clean_html(summary_raw)

            # Extract image if present
            image_url = None
            if "media_content" in entry and len(entry.media_content) > 0:
                image_url = entry.media_content[0].get("url")
            elif "enclosures" in entry and len(entry.enclosures) > 0:
                image_url = entry.enclosures[0].get("href")
            
            if not image_url:
                image_url = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=800&q=80"

            print(f"Summarizing into Urdu: {title[:40]}...")
            urdu_summary = summarize_to_urdu(title, cleaned_desc)

            if not urdu_summary:
                continue

            # Insert into database
            data = {
                "title": title,
                "summary": urdu_summary,
                "source_name": feed_info["source"],
                "source_url": source_url,
                "image_url": image_url
            }

            insert_res = supabase.table("news").insert(data).execute()
            print(f"Saved: {title[:30]}")
            total_added += 1

    print(f"Done! Added {total_added} new articles to database.")

if __name__ == "__main__":
    run()

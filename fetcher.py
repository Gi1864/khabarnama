import os
import feedparser
import json
import google.generativeai as genai
from supabase import create_client

# Environment configs
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
SUPA_URL = os.environ["SUPABASE_URL"]
SUPA_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
supabase = create_client(SUPA_URL, SUPA_KEY)

# Free public Indian Urdu RSS feeds
RSS_FEEDS = [
    {"url": "https://urdu.siasat.com/feed/", "name": "سیاست ڈیلی"},
    {"url": "https://www.inquilab.com/rss/national.xml", "name": "انقلاب"},
]

def summarize_article(title, description):
    prompt = f"""
    You are an Indian Urdu journalist. Summarize this news item into exactly 50 to 60 words in authentic Indian Urdu.
    Provide your output in pure JSON with keys: "title" and "summary". Do not include markdown code ticks.

    Headline: {title}
    Text: {description}
    """
    try:
        res = model.generate_content(prompt)
        text = res.text.strip().replace("```json", "").replace("```", "")
        return json.loads(text)
    except Exception as e:
        print(f"Summarization error: {e}")
        return None

def run():
    for src in RSS_FEEDS:
        feed = feedparser.parse(src["url"])
        for item in feed.entries[:3]: # Grab top 3 per feed per run
            link = item.get("link", "")
            
            # Check if article already exists
            exists = supabase.table("news").select("id").eq("source_url", link).execute()
            if exists.data:
                continue

            raw_title = item.get("title", "")
            raw_summary = item.get("summary", "")

            # Extract image if available
            img_url = ""
            if "media_content" in item and len(item.media_content) > 0:
                img_url = item.media_content[0].get("url", "")
            elif "enclosures" in item and len(item.enclosures) > 0:
                img_url = item.enclosures[0].get("href", "")
            
            if not img_url:
                img_url = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?auto=format&fit=crop&w=800&q=80"

            parsed = summarize_article(raw_title, raw_summary)
            if not parsed:
                continue

            supabase.table("news").insert({
                "title": parsed["title"],
                "summary": parsed["summary"],
                "image_url": img_url,
                "source_name": src["name"],
                "source_url": link
            }).execute()
            print(f"Added: {parsed['title']}")

if __name__ == "__main__":
    run()

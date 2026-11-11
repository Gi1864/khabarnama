import os
import re
import feedparser
import google.generativeai as genai
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().strip("'\"")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip().strip("'\"")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip().strip("'\"")

if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_KEY:
    raise ValueError("Missing secrets! Check GitHub Action secrets.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-3.8-flash")

RSS_FEEDS = [
    {
        "source": "گوگل نیوز",
        "url": "https://news.google.com/rss?hl=ur&gl=IN&ceid=IN:ur"
    },
    {
        "source": "بی بی سی اردو",
        "url": "https://feeds.bbci.co.uk/urdu/rss.xml"
    }
]

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def process_urdu_story(title, description):
    prompt = f"""
    You are an Urdu news editor for a mobile Inshorts-style app in India.
    Convert both the headline and details into pure, natural, standard Urdu.
    Even if the original headline is in Hindi or English, translate the headline into natural Urdu.

    Rules:
    - Output format must strictly follow:
      HEADLINE: <Urdu Headline under 15 words>
      SUMMARY: <Urdu Summary between 60 to 80 words>
    - No English words, no preamble, and no markdown tags.

    Original Title: {title}
    Original Details: {description}
    """
    try:
        res = model.generate_content(prompt)
        text = res.text.strip() if res and res.text else ""
        
        urdu_title = ""
        urdu_summary = ""
        
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("HEADLINE:"):
                urdu_title = line.replace("HEADLINE:", "").strip()
            elif line.startswith("SUMMARY:"):
                urdu_summary = line.replace("SUMMARY:", "").strip()
                
        # Fallback if structure varies slightly
        if not urdu_title and "HEADLINE:" not in text:
            parts = text.split("\n\n", 1)
            urdu_title = parts[0].strip()
            urdu_summary = parts[1].strip() if len(parts) > 1 else ""

        return urdu_title, urdu_summary
    except Exception as err:
        print(f"❌ Gemini Error: {err}")
        return None, None

def run():
    total_added = 0

    for feed in RSS_FEEDS:
        print(f"\n--- Checking Feed: {feed['source']} ---")
        try:
            parsed = feedparser.parse(feed["url"])
            print(f"Found {len(parsed.entries)} entries.")
        except Exception as e:
            print(f"Feed error: {e}")
            continue

        for entry in parsed.entries[:6]:
            link = getattr(entry, "link", None)
            raw_title = getattr(entry, "title", "").strip()
            if not link or not raw_title:
                continue

            # Check duplicate
            check = supabase.table("news").select("id").eq("source_url", link).execute()
            if check.data and len(check.data) > 0:
                print(f"⏩ Already in database: {raw_title[:25]}...")
                continue

            desc = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))

            print(f"🤖 Translating & Summarizing: {raw_title[:30]}...")
            urdu_title, urdu_summary = process_urdu_story(raw_title, desc or raw_title)

            if not urdu_title or not urdu_summary:
                continue

            payload = {
                "title": urdu_title,
                "summary": urdu_summary,
                "source_name": feed["source"],
                "source_url": link
            }

            try:
                supabase.table("news").insert(payload).execute()
                print(f"✅ Successfully inserted in Urdu: {urdu_title[:25]}")
                total_added += 1
            except Exception as e:
                print(f"❌ Supabase Insert Error: {e}")

    print(f"\n==========================================")
    print(f"Execution finished. Total stories added: {total_added}")
    print(f"==========================================")

if __name__ == "__main__":
    run()

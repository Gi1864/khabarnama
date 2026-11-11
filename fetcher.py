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

# Dynamically find the active model supported by this API key
ACTIVE_MODEL = None
try:
    print("Listing available models for this API key...")
    available_models = [
        m.name for m in genai.list_models() 
        if "generateContent" in m.supported_generation_methods
    ]
    print(f"Supported models found: {available_models}")
    
    # Prioritize flash models, then any available generation model
    for name in available_models:
        if "flash" in name:
            ACTIVE_MODEL = name
            break
    if not ACTIVE_MODEL and len(available_models) > 0:
        ACTIVE_MODEL = available_models[0]
        
    print(f"Selected active model: {ACTIVE_MODEL}")
except Exception as e:
    print(f"Error listing models: {e}")
    ACTIVE_MODEL = "gemini-1.5-flash"

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

def summarize_urdu(title, description):
    if not ACTIVE_MODEL:
        return None
        
    prompt = f"""
    You are an Urdu news editor for a mobile Inshorts-style app in India.
    Summarize this news article strictly in natural, readable modern Urdu.
    Length: strictly between 60 to 80 words.
    Return ONLY the Urdu summary text. No headlines, no English words, no preamble, and no markdown.

    Title: {title}
    Details: {description}
    """
    try:
        m = genai.GenerativeModel(ACTIVE_MODEL)
        res = m.generate_content(prompt)
        if res and res.text:
            return res.text.strip()
    except Exception as err:
        print(f"❌ Gemini Error with {ACTIVE_MODEL}: {err}")
    return None

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
            title = getattr(entry, "title", "").strip()
            if not link or not title:
                continue

            # Check duplicate
            check = supabase.table("news").select("id").eq("source_url", link).execute()
            if check.data and len(check.data) > 0:
                print(f"⏩ Already in database: {title[:25]}...")
                continue

            desc = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))

            print(f"🤖 Summarizing: {title[:30]}...")
            summary = summarize_urdu(title, desc or title)

            if not summary:
                continue

            payload = {
                "title": title,
                "summary": summary,
                "source_name": feed["source"],
                "source_url": link
            }

            try:
                supabase.table("news").insert(payload).execute()
                print(f"✅ Successfully inserted: {title[:25]}")
                total_added += 1
            except Exception as e:
                print(f"❌ Supabase Insert Error: {e}")

    print(f"\n==========================================")
    print(f"Execution finished. Total stories added: {total_added}")
    print(f"==========================================")

if __name__ == "__main__":
    run()

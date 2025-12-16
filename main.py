import os
import json
import requests
import feedparser
import datetime
import time
import re
import random
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("DEBUG: Script is starting (Fixed & History Reset Mode)...")

# --- CONFIGURATION ---
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
BLOG_ID = os.environ.get('BLOGGER_ID')
TOKEN_JSON_STR = os.environ.get('BLOGGER_TOKEN_JSON')
HISTORY_FILE = 'posted_history.json' 

# --- TOKEN CLEANER (Auto-Fixes user errors) ---
RAW_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
# Remove brackets, spaces, and 'bot' prefix if present
clean_token = str(RAW_TOKEN).strip().replace('[', '').replace(']', '').replace('(', '').replace(')', '')
if "api.telegram.org" in clean_token:
    parts = clean_token.split('/bot')
    if len(parts) > 1: clean_token = parts[1].split('/')[0]
if clean_token.lower().startswith('bot'):
    clean_token = clean_token[3:]
BOT_TOKEN = clean_token.strip()

# --- WEBSITE LIST ---
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://www.wired.com/feed/category/ai/latest/rss",
    "https://arstechnica.com/tag/ai/feed/",
    "https://www.engadget.com/tag/ai/rss.xml",
    "https://gizmodo.com/tag/artificial-intelligence/rss",
    "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "https://thenextweb.com/topic/artificial-intelligence/feed",
    "https://www.unite.ai/feed/",
    "https://www.marktechpost.com/feed/",
    "https://www.artificialintelligence-news.com/feed/",
    "https://analyticsindiamag.com/feed/",
    "https://www.kdnuggets.com/feed",
    "https://dataconomy.com/feed/",
    "https://insidebigdata.com/feed/",
    "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
    "https://techxplore.com/rss-feed/machine-learning-ai-news/",
    "https://blog.google/technology/ai/rss/",
    "https://blogs.microsoft.com/ai/feed/",
    "https://blogs.nvidia.com/blog/category/deep-learning/feed/",
    "https://aws.amazon.com/blogs/machine-learning/feed/",
    "https://openai.com/blog/rss.xml",
    "https://stackoverflow.blog/tag/ai/feed/",
    "https://www.infoq.com/ai-ml-data-eng/news/feed/",
    "https://readwrite.com/category/artificial-intelligence/feed/",
    "https://searchengineland.com/library/platforms/google/google-bard/feed",
]

# --- HISTORY SYSTEM ---
def save_history(link):
    # Just save to create file, we don't read heavily in reset mode
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump([link], f)
    except:
        pass

# --- GEMINI SETUP ---
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def get_best_model():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name:
                    return m.name
    except:
        pass
    return "models/gemini-1.5-flash"

# --- ANALYSIS FUNCTION ---
def get_analysis_json(title, link, description=""):
    print(f"DEBUG: Analyzing: {title[:30]}...") 
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
        You are an expert Tech Journalist.
        News Title: "{title}"
        Context: {description}
        
        Task: Write a Detailed Summary (approx 5 lines) and a Detailed Impact Analysis (approx 5 lines).
        
        Return strictly valid JSON:
        {{
            "summary": "Write a 5-line detailed paragraph explaining exactly what happened, which companies/models are involved, and the key features released. Do not be vague.",
            "impact": "Write a 5-line detailed paragraph explaining the long-term consequences, how this changes the AI industry, and who benefits the most from this.",
        }}
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "")
        
        return json.loads(text)
            
    except Exception as e:
        print(f"❌ AI Failed ({e}).")
        return None

# --- HTML CARD GENERATOR (Fixed CSS Link) ---
def create_single_card_html(item):
    return f"""
    <link rel="stylesheet" href="[https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0](https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0)" />
    <div style="font-family: 'Inter', sans-serif; max-width: 800px; margin: 0 auto;">
        
        <div style="background: #fff; border: 1px solid #e5e7eb; border-radius: 20px; padding: 30px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.05);">
            
            <h2 style="font-size: 24px; font-weight: 800; color: #111; margin-bottom: 25px; line-height: 1.3;">
                {item['title']}
            </h2>

            <div style="background: #f9fafb; border-left: 4px solid #ef4444; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <span class="material-symbols-outlined" style="color: #ef4444; margin-right: 8px;">psychology</span>
                    <strong style="color: #374151; font-size: 13px; letter-spacing: 1px; text-transform: uppercase;">Detailed Summary</strong>
                </div>
                <p style="margin: 0; color: #374151; font-size: 16px; line-height: 1.7; text-align: justify;">
                    {item['summary']}
                </p>
            </div>

            <div style="background: #f9fafb; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 20px; margin-bottom: 30px;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <span class="material-symbols-outlined" style="color: #3b82f6; margin-right: 8px;">bolt</span>
                    <strong style="color: #374151; font-size: 13px; letter-spacing: 1px; text-transform: uppercase;">Industry Impact</strong>
                </div>
                <p style="margin: 0; color: #374151; font-size: 16px; line-height: 1.7; text-align: justify;">
                    {item['impact']}
                </p>
            </div>

            <div style="text-align: center;">
                <a href="{item['link']}" target="_blank" style="background: #111; color: #fff; text-decoration: none; padding: 14px 28px; border-radius: 50px; font-weight: 600; font-size: 14px; display: inline-flex; align-items: center; transition: transform 0.2s;">
                    Read Original Source
                    <span class="material-symbols-outlined" style="font-size: 18px; margin-left: 8px;">open_in_new</span>
                </a>
            </div>

        </div>
    </div>
    """

# --- MAIN ---
def main():
    # 1. DELETE HISTORY (FORCE RESET)
    if os.path.exists(HISTORY_FILE):
        try:
            os.remove(HISTORY_FILE)
            print("🗑️ History File DELETED (Force Reset Mode).")
        except:
            pass

    print("🎲 Randomizing sources...")
    
    if not BLOG_ID: 
        print("⚠️ WARNING: BLOG_ID is missing!")
        return

    random.shuffle(RSS_FEEDS) # Shuffle websites
    
    final_post = None
    
    # Fake User Agent to prevent blocks
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    # Search for ONE valid news
    for url in RSS_FEEDS:
        print(f"🔍 Checking: {url}")
        try:
            # Try fetching with headers first (better success rate)
            try:
                resp = requests.get(url, headers=HEADERS, timeout=5)
                feed = feedparser.parse(resp.content)
            except:
                feed = feedparser.parse(url)

            if not feed.entries: continue
            
            # Pick the FIRST item (History is deleted, so any item works)
            entry = feed.entries[0]
            print(f"   🎯 Selecting: {entry.title}")
            
            # Generate Summary/Impact only
            desc = entry.get('summary', '') or entry.get('description', '')
            analysis = get_analysis_json(entry.title, entry.link, desc)
            
            if analysis:
                final_post = {
                    'title': entry.title,
                    'link': entry.link,
                    'summary': analysis['summary'],
                    'impact': analysis['impact']
                }
                break # Stop searching after finding one
                
        except Exception as e:
            print(f"⚠️ Feed error: {e}")
            continue

    # --- PUBLISH ---
    if final_post:
        print(f"🚀 Publishing: {final_post['title']}")
        
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            
            # 1. Make HTML Card
            html_content = create_single_card_html(final_post)
            
            # 2. Publish to Blogger
            body = {
                'title': f"⚡ {final_post['title']}", 
                'content': html_content, 
                'labels': ['AI Update']
            }
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Blogger Post: {post['url']}")
            
            # 3. Send Telegram Msg
            print("✈️ Sending to Telegram...")
            tg_msg = f"⚡ *AI Update*\n\n"
            tg_msg += f"🔹 *{final_post['title']}*\n\n"
            tg_msg += f"📝 *Summary:*\n{final_post['summary']}\n\n"
            tg_msg += f"🚀 *Impact:*\n{final_post['impact']}\n\n"
            tg_msg += f"🔗 [Read More]({post['url']})"
            
            if len(tg_msg) > 4000:
                 tg_msg = tg_msg[:4000] + "..."

            # 👇 FIXED URL (Removed Markdown brackets causing errors)
            telegram_url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){BOT_TOKEN}/sendMessage"
            
            response = requests.post(
                telegram_url, 
                data={"chat_id": CHANNEL_ID, "text": tg_msg, "parse_mode": "Markdown"}
            )
            
            if response.status_code == 200:
                print("✅ Telegram Sent Successfully.")
                save_history(final_post['link'])
            else:
                print(f"❌ Telegram Error: {response.text}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("😴 No news found (Check internet or API limits).")

if __name__ == "__main__":
    main()

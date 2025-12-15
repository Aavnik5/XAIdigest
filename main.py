import os
import json
import requests
import feedparser
import datetime
import time
import re
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("DEBUG: Script is starting...")

# --- CONFIGURATION ---
GEMINI_KEY = os.environ.get('GEMINI_API_KEY')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
BLOG_ID = os.environ.get('BLOGGER_ID')
TOKEN_JSON_STR = os.environ.get('BLOGGER_TOKEN_JSON')

RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/"
]

# --- SETUP GEMINI ---
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- DYNAMIC MODEL FINDER ---
def get_best_model():
    """Google se jo model available hai wo utha lo, hardcode mat karo"""
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Prefer 'pro' or 'flash' models if available
                if 'gemini' in m.name:
                    print(f"✅ Auto-Selected Model: {m.name}")
                    return m.name
    except Exception as e:
        print(f"⚠️ Error listing models: {e}")
    return "models/gemini-1.5-flash" # Default fallback

# --- SUMMARY GENERATOR ---
def get_analysis(title, link, description=""):
    print(f"DEBUG: Summarizing: {title[:30]}...") 
    
    # 1. Try AI Generation
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        # Simple Prompt (No strict JSON to avoid errors on experimental models)
        prompt = f"""
        Read this news title: "{title}"
        Link: {link}
        
        Write a summary and impact statement.
        Format exactly like this:
        Summary: [One sentence summary]
        Impact: [One sentence impact]
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Parse text manually
        summary = ""
        impact = ""
        
        if "Summary:" in text and "Impact:" in text:
            parts = text.split("Impact:")
            summary = parts[0].replace("Summary:", "").strip()
            impact = parts[1].strip()
            return summary, impact
            
    except Exception as e:
        print(f"❌ AI Failed ({e}). Switching to Manual Fallback.")

    # 2. Manual Fallback (Agar AI fail hua to ye chalega - Post Khali Nahi Hoga)
    print("⚠️ Using Manual Fallback for content.")
    
    # Use feed description or title as summary
    clean_desc = re.sub('<[^<]+?>', '', description) # Remove HTML tags
    fallback_summary = clean_desc[:150] + "..." if len(clean_desc) > 5 else f"{title} - Click to read full details."
    fallback_impact = "Check the full article to understand the industry impact."
    
    return fallback_summary, fallback_impact

# --- GENERATE HTML ---
def make_html(news_items):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    cards = """<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />"""
    
    for i, item in enumerate(news_items):
        cards += f"""
        <div style="background: #fff; border: 1px solid #eee; border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); font-family: Inter, sans-serif;">
            <h3 style="font-size: 20px; font-weight: 700; color: #1a1a1a; margin-bottom: 20px; line-height: 1.4;">
                {i+1}. {item['title']}
            </h3>
            <div style="background: #fcfcfc; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #f0f0f0;">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span class="material-symbols-outlined" style="color: #ef4444; font-size: 20px; margin-right: 8px;">psychology</span>
                    <strong style="color: #1a1a1a; font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase;">SUMMARY</strong>
                </div>
                <p style="color: #4b5563; font-size: 15px; margin: 0; line-height: 1.6;">{item['summary']}</p>
            </div>
            <div style="background: #fcfcfc; border-radius: 12px; padding: 16px; border: 1px solid #f0f0f0;">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span class="material-symbols-outlined" style="color: #3b82f6; font-size: 20px; margin-right: 8px;">bolt</span>
                    <strong style="color: #1a1a1a; font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase;">IMPACT</strong>
                </div>
                <p style="color: #4b5563; font-size: 15px; margin: 0; line-height: 1.6;">{item['impact']}</p>
            </div>
            <div style="margin-top: 20px; text-align: right;">
                <a href="{item['link']}" style="color: #3b82f6; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-flex; align-items: center;">
                    Read Full Story <span class="material-symbols-outlined" style="font-size: 18px; margin-left: 4px;">arrow_forward</span>
                </a>
            </div>
        </div>
        """
        
    final_html = f"""
    <div style="padding-top: 20px;">
        <div style="display: flex; align-items: center; margin-bottom: 30px;">
            <span style="background: #fee2e2; color: #ef4444; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;">{date_str}</span>
            <span style="color: #9ca3af; font-size: 13px; margin-left: 10px;">Automated Digest</span>
        </div>
        {cards}
    </div>
    """
    return final_html, date_str

# --- MAIN ---
def main():
    print("📰 Collecting News...")
    
    if not BLOG_ID: print("⚠️ WARNING: BLOG_ID is missing!")
    items, seen = [], set()
    
    try:
        for url in RSS_FEEDS:
            print(f"DEBUG: Feed: {url}")
            feed = feedparser.parse(url)
            if not feed.entries: continue
                
            for entry in feed.entries[:2]:
                if entry.link not in seen:
                    # Pass description for fallback usage
                    desc = entry.get('summary', '') or entry.get('description', '')
                    summary, impact = get_analysis(entry.title, entry.link, desc)
                    
                    items.append({'title': entry.title, 'link': entry.link, 'summary': summary, 'impact': impact})
                    seen.add(entry.link)
                    print("⏳ Waiting 3s...")
                    time.sleep(3)
    except Exception as e:
        print(f"❌ Error: {e}")

    if items:
        html, date = make_html(items[:5])
        print("🚀 Publishing to Blogger...")
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            body = {'title': f"⚡ AI Impact Digest | {date}", 'content': html, 'labels': ['AI News']}
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Published: {post['url']}")
            
            print("✈️ Sending Telegram...")
            msg = f"⚡ *AI Impact Digest | {date}*\n\nRead here:\n{post['url']}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown"})
        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("⚠️ No news found.")

if __name__ == "__main__":
    main()

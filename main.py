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

# --- 30+ WEBSITES LIST ---
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

# --- SETUP GEMINI ---
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

# --- DYNAMIC MODEL FINDER ---
def get_best_model():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name:
                    return m.name
    except:
        pass
    return "models/gemini-1.5-flash"

# --- SUMMARY GENERATOR ---
def get_analysis(title, link, description=""):
    print(f"DEBUG: Summarizing: {title[:30]}...") 
    
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
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
        
        summary = ""
        impact = ""
        
        if "Summary:" in text and "Impact:" in text:
            parts = text.split("Impact:")
            summary = parts[0].replace("Summary:", "").strip()
            impact = parts[1].strip()
            return summary, impact
            
    except Exception as e:
        print(f"❌ AI Failed ({e}). Switching to Manual Fallback.")

    print("⚠️ Using Manual Fallback for content.")
    clean_desc = re.sub('<[^<]+?>', '', description)
    fallback_summary = clean_desc[:150] + "..." if len(clean_desc) > 5 else f"{title} - Click to read details."
    fallback_impact = "Check the full article to understand the industry impact."
    
    return fallback_summary, fallback_impact

# --- GENERATE HTML FOR BLOGGER ---
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
    print("📰 Collecting News from 30+ Sources...")
    
    if not BLOG_ID: print("⚠️ WARNING: BLOG_ID is missing!")
    items, seen = [], set()
    
    try:
        # Loop through all feeds
        for url in RSS_FEEDS:
            print(f"DEBUG: Feed: {url}")
            try:
                feed = feedparser.parse(url)
                if not feed.entries: continue
                
                # Limit 1 news per site
                for entry in feed.entries[:1]:
                    if entry.link not in seen:
                        desc = entry.get('summary', '') or entry.get('description', '')
                        summary, impact = get_analysis(entry.title, entry.link, desc)
                        
                        items.append({'title': entry.title, 'link': entry.link, 'summary': summary, 'impact': impact})
                        seen.add(entry.link)
                        
                        # Stop at 10 items max (for Telegram limit safety)
                        if len(items) >= 10:
                            print("✅ Collected 10 top news items. Stopping.")
                            break
                        
                        print("⏳ Waiting 3s...")
                        time.sleep(3)
                        
                if len(items) >= 10: break
                
            except Exception as e:
                print(f"⚠️ Feed error: {e}")
                
    except Exception as e:
        print(f"❌ Global Error: {e}")

    if items:
        # 1. Blogger Post
        html, date = make_html(items)
        print("🚀 Publishing to Blogger...")
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            body = {'title': f"⚡ AI Impact Digest | {date}", 'content': html, 'labels': ['AI News']}
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Published: {post['url']}")
            
            # 2. Telegram Detailed Message
            print("✈️ Sending Detailed Update to Telegram...")
            
            # Create a long message string
            telegram_msg = f"⚡ *AI Impact Digest | {date}*\n\n"
            
            for i, item in enumerate(items):
                # Clean Markdown characters that might break Telegram
                clean_title = item['title'].replace("*", "").replace("_", "").replace("[", "").replace("]", "")
                
                telegram_msg += f"🔹 *{i+1}. {clean_title}*\n\n"
                telegram_msg += f"📝 {item['summary']}\n\n"
                telegram_msg += f"🚀 Impact: {item['impact']}\n\n"
                telegram_msg += f"🔗 [Read Source]({item['link']})\n\n\n"

            telegram_msg += f"-----------------\n📖 *Full Digest on Blog:* {post['url']}"
            
            # Safety Check: Telegram limit is 4096 chars
            if len(telegram_msg) > 4000:
                telegram_msg = telegram_msg[:4000] + "\n\n...(Full list on Blog)"

            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": telegram_msg, "parse_mode": "Markdown"})
            
        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("⚠️ No news found.")

if __name__ == "__main__":
    main()

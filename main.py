import os
import json
import requests
import feedparser
import datetime
import time
import re
import random  # Import random for selecting random website
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
HISTORY_FILE = 'posted_history.json' # File to store used links

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

# --- HISTORY MANAGEMENT ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_history(link):
    history = load_history()
    history.add(link)
    # Keep only last 500 links to save space
    if len(history) > 500:
        history = set(list(history)[-500:])
    with open(HISTORY_FILE, 'w') as f:
        json.dump(list(history), f)

# --- SETUP GEMINI ---
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

# --- CONTENT GENERATOR (FULL BLOG POST) ---
def generate_full_content(title, link, description=""):
    print(f"DEBUG: Generating full post for: {title[:30]}...") 
    
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        # Output strictly in JSON to separate Blog HTML and Telegram Msg
        prompt = f"""
        You are a professional Tech Journalist.
        News Title: "{title}"
        Context: {description}
        Source Link: {link}

        Task: Create a viral, high-quality blog post and a social media caption.
        
        Return ONLY a JSON object with this structure (no markdown formatting):
        {{
            "blog_title": "A catchy, click-worthy title for the blog post",
            "blog_html": "HTML code for a full article. Use <h2>, <p>, <ul>, <li>. Make it engaging, 400+ words. Include an 'Introduction', 'Key Details', 'Why This Matters', and 'Conclusion'. Styling: Use inline CSS for clean look (font-family: Inter, sans-serif).",
            "telegram_msg": "A short, punchy summary for Telegram (max 50 words) with emojis."
        }}
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean potential markdown code blocks if Gemini adds them
        if text.startswith("```json"):
            text = text.replace("```json", "").replace("```", "")
        
        data = json.loads(text)
        return data
            
    except Exception as e:
        print(f"❌ AI Failed ({e}).")
        return None

# --- MAIN ---
def main():
    print("🎲 Randomizing sources to find a trending topic...")
    
    if not BLOG_ID: 
        print("⚠️ WARNING: BLOG_ID is missing!")
        return

    history = load_history()
    
    # Shuffle feeds to pick a random website each time
    random.shuffle(RSS_FEEDS)
    
    target_news = None
    
    # Loop through shuffled feeds to find ONE valid news item
    for url in RSS_FEEDS:
        print(f"🔍 Checking feed: {url}")
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            # Check the top 3 items in this feed (most trending usually on top)
            for entry in feed.entries[:3]:
                if entry.link not in history:
                    # FOUND A NEW TOPIC!
                    print(f"✅ Found fresh topic: {entry.title}")
                    
                    desc = entry.get('summary', '') or entry.get('description', '')
                    content_data = generate_full_content(entry.title, entry.link, desc)
                    
                    if content_data:
                        target_news = {
                            'original_title': entry.title,
                            'original_link': entry.link,
                            'blog_title': content_data['blog_title'],
                            'blog_html': content_data['blog_html'],
                            'telegram_msg': content_data['telegram_msg']
                        }
                        break # Break inner loop (found item)
            
            if target_news:
                break # Break outer loop (found feed)
                
        except Exception as e:
            print(f"⚠️ Feed error: {e}")
            continue

    # --- PUBLISHING PROCESS ---
    if target_news:
        print(f"🚀 Publishing: {target_news['blog_title']}")
        
        # 1. Publish to Blogger
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            
            # Add "Read More" link to the bottom of HTML
            final_html = f"""
            {target_news['blog_html']}
            <hr style="margin: 30px 0; border: 0; border-top: 1px solid #eee;">
            <p style="text-align: center; font-style: italic; color: #666;">
                Source: <a href="{target_news['original_link']}" target="_blank">Read Original Article</a>
            </p>
            """
            
            body = {
                'title': target_news['blog_title'], 
                'content': final_html, 
                'labels': ['AI News', 'Trending']
            }
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Blog Published: {post['url']}")
            
            # 2. Publish to Telegram
            telegram_text = f"🚨 *New AI Update*\n\n"
            telegram_text += f"**{target_news['blog_title']}**\n\n"
            telegram_text += f"{target_news['telegram_msg']}\n\n"
            telegram_text += f"👇 *Read Full Article:* \n{post['url']}"
            
            requests.post(
                f"[https://api.telegram.org/bot](https://api.telegram.org/bot){BOT_TOKEN}/sendMessage", 
                data={"chat_id": CHANNEL_ID, "text": telegram_text, "parse_mode": "Markdown"}
            )
            print("✅ Telegram Sent.")
            
            # 3. Save to History (Critical Step)
            save_history(target_news['original_link'])
            print("💾 Saved to history file.")

        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("😴 No new unposted news found in any feed.")

if __name__ == "__main__":
    main()

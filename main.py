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

# --- SUMMARY GENERATOR (UPDATED FOR 5-5 LINES) ---
def get_analysis(title, link, description=""):
    print(f"DEBUG: Summarizing: {title[:30]}...") 
    
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        
        # Updated Prompt: Asking for 5 lines each
        prompt = f"""
        Read this news title: "{title}"
        Link: {link}
        
        Write a structured analysis.
        
        1. Summary: Write exactly 5 sentences summarizing the key events.
        2. Impact: Write exactly 5 sentences explaining the future impact on the industry.
        
        Format exactly like this:
        Summary: [5 sentences content]
        Impact: [5 sentences content]
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
    fallback_summary = clean_desc[:250] + "..." 
    fallback_impact = "Check the full article for details."
    
    return fallback_summary, fallback_impact

# --- GENERATE HTML FOR BLOGGER ---
def make_html(news_items):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    
    item = news_items[0]
    final_html = f"""
    <div style="font-family: Inter, sans-serif; max-width: 800px; margin: 0 auto;">
        <div style="background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #111; margin-top: 0;">{item['title']}</h2>
            
            <div style="margin-bottom: 20px;">
                <h3 style="color: #ef4444; font-size: 16px; margin-bottom: 8px;">📌 Summary</h3>
                <p style="color: #444; font-size: 16px; line-height: 1.8; margin-top: 0;">
                    {item['summary']}
                </p>
            </div>
            
            <div style="background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 15px; margin: 15px 0;">
                <h3 style="color: #1e3a8a; font-size: 16px; margin-bottom: 8px; margin-top: 0;">🚀 Impact</h3>
                <p style="margin: 0; color: #1e40af; line-height: 1.8;">
                    {item['impact']}
                </p>
            </div>
            
            <p style="margin-top: 20px;">
                <a href="{item['link']}" style="background: #000; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-size: 14px;">Read Full Story →</a>
            </p>
            <p style="color: #888; font-size: 12px; margin-top: 20px;">Source: {item['source']} | Generated by AI</p>
        </div>
    </div>
    """
    return final_html, date_str

# --- MAIN ---
def main():
    print("📰 Selecting ONE Random Source...")
    
    if not BLOG_ID: print("⚠️ WARNING: BLOG_ID is missing!")
    items = []
    
    try:
        # 1. Pick ONE random feed
        random_feed_url = random.choice(RSS_FEEDS)
        print(f"DEBUG: Selected Random Feed: {random_feed_url}")

        try:
            feed = feedparser.parse(random_feed_url)
            
            if feed.entries:
                # Get the very first (latest) entry
                entry = feed.entries[0]
                
                print(f"DEBUG: Found Article: {entry.title}")
                
                desc = entry.get('summary', '') or entry.get('description', '')
                summary, impact = get_analysis(entry.title, entry.link, desc)
                
                # Extract source name from URL for credit
                source_name = random_feed_url.split('/')[2].replace('www.', '')
                
                items.append({
                    'title': entry.title, 
                    'link': entry.link, 
                    'summary': summary, 
                    'impact': impact,
                    'source': source_name
                })
            else:
                print("⚠️ Selected feed was empty, try running again.")
                
        except Exception as e:
            print(f"⚠️ Feed parsing error: {e}")
                
    except Exception as e:
        print(f"❌ Global Error: {e}")

    if items:
        # 1. Blogger Post
        html, date = make_html(items)
        print("🚀 Publishing to Blogger...")
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            body = {'title': f"AI Update: {items[0]['title']}", 'content': html, 'labels': ['AI News', 'Trending']}
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Published: {post['url']}")
            
            # 2. Telegram Message (Detailed 5-5 Lines)
            print("✈️ Sending Update to Telegram...")
            
            item = items[0]
            clean_title = item['title'].replace("*", "").replace("_", "").replace("[", "").replace("]", "")
            
            telegram_msg = f"⚡ *AI Trending Update*\n\n"
            telegram_msg += f"📰 *{clean_title}*\n\n"
            telegram_msg += f"📌 *Summary:*\n{item['summary']}\n\n"
            telegram_msg += f"🚀 *Impact:*\n{item['impact']}\n\n"
            telegram_msg += f"🔗 [Read More]({item['link']})"
            
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": telegram_msg, "parse_mode": "Markdown"})
            
        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("⚠️ No news found.")

if __name__ == "__main__":
    main()

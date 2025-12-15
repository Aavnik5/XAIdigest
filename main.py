import os
import json
import requests
import feedparser
import datetime
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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

# --- GEMINI SUMMARIZATION ---
def get_summary(title, link):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        prompt = f"Summarize this news in 2 short bullet points for a blog post. Focus on facts. News: {title} - {link}"
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        text = response.text.replace("* ", "<li>").replace("\n", "</li>")
        return text if "<li>" in text else f"<li>{text}</li>"
    except:
        return "<li>Click link to read full update.</li>"

# --- GENERATE TAILWIND HTML ---
def make_html(news_items):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    cards = ""
    
    for i, item in enumerate(news_items):
        cards += f"""
        <article class="group relative bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 mb-6">
            <h3 class="text-xl font-bold mb-4 text-gray-900">
                {i+1}. {item['title']}
            </h3>
            <div class="bg-gray-50 p-4 rounded-lg mb-4">
                <strong class="text-blue-600 block mb-2 text-xs uppercase">AI Summary</strong>
                <ul class="list-disc pl-4 text-sm text-gray-700 space-y-2">{item['summary']}</ul>
            </div>
            <a class="text-blue-600 font-bold text-sm hover:underline" href="{item['link']}">Read Full Story →</a>
        </article>
        """
        
    final_html = f"""
    <div style="font-family: sans-serif; max-width: 800px; margin: 0 auto;">
        <p style="color: #666; font-size: 12px; margin-bottom: 20px;">📅 {date_str} • Automated AI Digest</p>
        {cards}
        <div style="margin-top: 40px; padding: 20px; background: #222; color: #fff; border-radius: 12px; text-align: center;">
             <h3 style="margin:0 0 10px 0;">🚀 Boost Your Productivity</h3>
             <p style="color: #aaa; margin-bottom: 15px;">Use AI tools to work faster.</p>
             <a href="#" style="background: #3b82f6; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: bold;">Explore Tools</a>
        </div>
    </div>
    """
    return final_html, date_str

# --- MAIN LOGIC ---
def main():
    print("📰 Collecting News...")
    items = []
    seen = set()
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: # Har feed se top 2 news
                if entry.link not in seen:
                    print(f"Summarizing: {entry.title[:30]}...")
                    summary = get_summary(entry.title, entry.link)
                    items.append({'title': entry.title, 'link': entry.link, 'summary': summary})
                    seen.add(entry.link)
        except Exception as e:
            print(f"Feed Error: {e}")
    
    if items:
        html, date = make_html(items[:5]) # Top 5 only
        
        # Publish to Blogger
        print("🚀 Publishing to Blogger...")
        try:
            creds_dict = json.loads(TOKEN_JSON_STR)
            creds = Credentials.from_authorized_user_info(creds_dict)
            service = build('blogger', 'v3', credentials=creds)
            
            body = {
                'title': f"🤖 AI Updates | {date}",
                'content': html,
                'labels': ['AI News', 'Automated']
            }
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            post_url = post['url']
            print(f"✅ Published: {post_url}")
            
            # Send Telegram Alert
            print("✈️ Sending to Telegram...")
            msg = f"🔥 *New AI Digest Published!*\n\n📅 Date: {date}\n🔗 Read here: {post_url}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown"})
            
        except Exception as e:
            print(f"❌ Error during publishing: {e}")
    else:
        print("No new news found today.")

if __name__ == "__main__":
    main()
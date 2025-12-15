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

# --- GEMINI ANALYSIS (Summary + Impact) ---
def get_analysis(title, link):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        # Prompt ko change kiya taki wo 'Summary' aur 'Impact' dono de
        prompt = f"""
        Analyze this AI news article title: "{title}"
        Link: {link}
        
        Output exactly 2 lines (no bold, no markdown):
        Line 1: A simple 1-sentence summary of what happened.
        Line 2: A simple 1-sentence explanation of the impact/why it matters.
        """
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        lines = response.text.strip().split('\n')
        
        # Fallback agar Gemini format follow na kare
        summary = lines[0] if len(lines) > 0 else "Click to read more."
        impact = lines[1] if len(lines) > 1 else "Significant industry impact expected."
        
        return summary, impact
    except:
        return "Click link to read full update.", "Check article for details."

# --- GENERATE DESIGN MATCH HTML ---
def make_html(news_items):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    
    # Material Icons Link add kiya hai taki Icons dikhein
    cards = """<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />"""
    
    for i, item in enumerate(news_items):
        cards += f"""
        <div style="background: #fff; border: 1px solid #eee; border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.03);">
            
            <h3 style="font-size: 20px; font-weight: 700; color: #1a1a1a; margin-bottom: 20px; line-height: 1.4;">
                {i+1}. {item['title']}
            </h3>
            
            <div style="background: #fcfcfc; border-radius: 12px; padding: 16px; margin-bottom: 12px; border: 1px solid #f0f0f0;">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span class="material-symbols-outlined" style="color: #ef4444; font-size: 20px; margin-right: 8px;">psychology</span>
                    <strong style="color: #1a1a1a; font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase;">GEMINI SUMMARY</strong>
                </div>
                <p style="color: #4b5563; font-size: 15px; margin: 0; line-height: 1.6;">
                    {item['summary']}
                </p>
            </div>

            <div style="background: #fcfcfc; border-radius: 12px; padding: 16px; border: 1px solid #f0f0f0;">
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <span class="material-symbols-outlined" style="color: #3b82f6; font-size: 20px; margin-right: 8px;">bolt</span>
                    <strong style="color: #1a1a1a; font-size: 12px; letter-spacing: 0.5px; text-transform: uppercase;">IMPACT</strong>
                </div>
                <p style="color: #4b5563; font-size: 15px; margin: 0; line-height: 1.6;">
                    {item['impact']}
                </p>
            </div>
            
            <div style="margin-top: 20px; text-align: right;">
                <a href="{item['link']}" style="color: #3b82f6; text-decoration: none; font-weight: 600; font-size: 14px; display: inline-flex; align-items: center;">
                    Read Full Story <span class="material-symbols-outlined" style="font-size: 18px; margin-left: 4px;">arrow_forward</span>
                </a>
            </div>

        </div>
        """
        
    final_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 800px; margin: 0 auto;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
            <span style="background: #fee2e2; color: #ef4444; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;">🔥 Top AI News</span>
            <span style="color: #9ca3af; font-size: 13px;">{date_str}</span>
        </div>
        {cards}
    </div>
    """
    return final_html, date_str

# --- MAIN LOGIC ---
def main():
    print("📰 Collecting News...")
    items = []
    seen = set()
    
    # Error handling ke sath feed fetch
    try:
        for url in RSS_FEEDS:
            feed = feedparser.parse(url)
            for entry in feed.entries[:2]: # Har feed se top 2 news
                if entry.link not in seen:
                    print(f"Analyzing: {entry.title[:30]}...")
                    # Ab Summary aur Impact dono le rahe hain
                    summary, impact = get_analysis(entry.title, entry.link)
                    items.append({
                        'title': entry.title, 
                        'link': entry.link, 
                        'summary': summary,
                        'impact': impact
                    })
                    seen.add(entry.link)
    except Exception as e:
        print(f"Feed parsing error: {e}")

    if items:
        html, date = make_html(items[:5]) # Top 5 only
        
        # Publish to Blogger
        print("🚀 Publishing to Blogger...")
        try:
            creds_dict = json.loads(TOKEN_JSON_STR)
            creds = Credentials.from_authorized_user_info(creds_dict)
            service = build('blogger', 'v3', credentials=creds)
            
            body = {
                'title': f"⚡ AI Impact Digest | {date}",
                'content': html,
                'labels': ['AI News', 'Gemini Analysis']
            }
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            post_url = post['url']
            print(f"✅ Published: {post_url}")
            
            # Send Telegram Alert
            print("✈️ Sending to Telegram...")
            msg = f"⚡ *AI Impact Digest | {date}*\n\nRead the latest analysis:\n{post_url}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown"})
            
        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("No new news found today.")

if __name__ == "__main__":
    main()

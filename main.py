import os
import json
import requests
import feedparser
import datetime
import time
from google import genai
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

# --- GEMINI ANALYSIS (Model Fixed to Stable Version) ---
def get_analysis(title, link):
    print(f"DEBUG: Attempting to summarize: {title[:30]}...") 
    empty_output = ""
    
    try:
        if not GEMINI_KEY:
            print("❌ Error: GEMINI_API_KEY is missing!")
            return empty_output, empty_output

        client = genai.Client(api_key=GEMINI_KEY)
        
        prompt = f"""
        Analyze this AI news article title: "{title}"
        Link: {link}
        
        Provide the output in JSON format only, with keys "summary" and "impact".
        Summary: A concise 1-sentence explanation of the news.
        Impact: A concise 1-sentence explanation of why this news is significant globally/industry-wide.
        """
        
        # 👇 CHANGED MODEL TO 'gemini-1.5-flash-001' (Stable Version ID)
        # Yeh ID 404 error fix karega
        response = client.models.generate_content(
            model='gemini-1.5-flash-001', 
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        
        data = json.loads(response.text)
        
        summary = data.get('summary', empty_output).strip()
        impact = data.get('impact', empty_output).strip()
        
        return summary, impact
        
    except Exception as e:
        print(f"❌ GEMINI API FAILED: {e}")
        return empty_output, empty_output

# --- GENERATE DESIGN MATCH HTML ---
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
    <div style="padding-top: 20px;">
        <div style="display: flex; align-items: center; margin-bottom: 30px;">
            <span style="background: #fee2e2; color: #ef4444; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;">{date_str}</span>
            <span style="color: #9ca3af; font-size: 13px; margin-left: 10px;">Automated Digest</span>
        </div>
        {cards}
    </div>
    """
    return final_html, date_str

# --- MAIN LOGIC ---
def main():
    print("📰 Collecting News...")
    
    if not BLOG_ID:
        print("⚠️ WARNING: BLOG_ID is missing from secrets!")
    
    items = []
    seen = set()
    
    try:
        for url in RSS_FEEDS:
            print(f"DEBUG: Fetching feed: {url}")
            feed = feedparser.parse(url)
            
            if not feed.entries:
                print("DEBUG: No entries found in this feed.")
                continue
                
            for entry in feed.entries[:2]:
                if entry.link not in seen:
                    summary, impact = get_analysis(entry.title, entry.link)
                    
                    # VALIDATION: Agar Gemini fail hua, toh skip karo
                    if not summary or not impact:
                        print("⚠️ Skipping item due to failed Gemini generation.")
                        continue

                    items.append({
                        'title': entry.title, 
                        'link': entry.link, 
                        'summary': summary,
                        'impact': impact
                    })
                    seen.add(entry.link)
                    
                    # DELAY: 5 seconds wait (Flash model fast hai, par safe raho)
                    print("⏳ Waiting 5s...")
                    time.sleep(5)
                    
    except Exception as e:
        print(f"❌ Feed parsing error: {e}")

    if items:
        html, date = make_html(items[:5])
        
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
            
            print("✈️ Sending to Telegram...")
            msg = f"⚡ *AI Impact Digest | {date}*\n\nRead the latest analysis:\n{post_url}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown"})
            
        except Exception as e:
            print(f"❌ Publishing Error: {e}")
    else:
        print("⚠️ No valid generated news found. Post skipped to avoid blank content.")

if __name__ == "__main__":
    main()

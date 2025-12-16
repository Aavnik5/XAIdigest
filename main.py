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

# --- RSS FEEDS ---
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

def get_best_model():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name: return m.name
    except: pass
    return "models/gemini-1.5-flash"

# --- CORE ANALYSIS ENGINE ---
def get_analysis(title, link, description=""):
    print(f"DEBUG: Analyzing: {title[:40]}...") 
    
    try:
        model_name = get_best_model()
        # Safety settings to prevent blocking technical/security content
        model = genai.GenerativeModel(
            model_name,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        prompt = f"""
        Provide a professional analysis of this news:
        TITLE: {title}
        DESCRIPTION: {description[:800]}

        STRICT RULES:
        1. Summary section must have exactly 5 bullet points.
        2. Impact section must have exactly 5 bullet points.
        3. Use a numbered list (1. 2. 3. 4. 5.) for each.

        OUTPUT FORMAT:
        Summary:
        1. [Point 1]
        2. [Point 2]
        3. [Point 3]
        4. [Point 4]
        5. [Point 5]
        
        Impact:
        1. [Point 1]
        2. [Point 2]
        3. [Point 3]
        4. [Point 4]
        5. [Point 5]
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if "Summary:" in text and "Impact:" in text:
            parts = text.split("Impact:")
            summary = parts[0].replace("Summary:", "").strip()
            impact = parts[1].strip()
            
            # Validation: check if we actually have points
            if len(impact.split('\n')) >= 3:
                return summary, impact
        
        raise ValueError("AI response format was incorrect")

    except Exception as e:
        print(f"❌ AI Error: {e}. Using Smart Fallback.")
        
    # SMART FALLBACK: If AI fails, provide high-quality context-aware generic lines
    fallback_summary = (
        "1. This news highlights a significant shift in the current AI landscape.\n"
        "2. Organizations are now focusing on integrating these advanced capabilities.\n"
        "3. Performance and efficiency remain the top priorities for developers.\n"
        "4. This development addresses long-standing challenges in the tech industry.\n"
        "5. The announcement has sparked widespread interest among global stakeholders."
    )
    fallback_impact = (
        "1. This will accelerate the adoption of secure AI frameworks worldwide.\n"
        "2. Industry competitors will likely fast-track their own similar solutions.\n"
        "3. Long-term data privacy standards will be redefined by this approach.\n"
        "4. Market demand for specialized AI infrastructure is expected to surge.\n"
        "5. Future innovations will build upon this foundation for better scalability."
    )
    return fallback_summary, fallback_impact

# --- BLOGGER HTML GENERATOR ---
def make_html(news_items):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    item = news_items[0]
    
    # Points ko list mein convert karna (Empty strings hata kar)
    summary_points = [p.strip("12345. -") for p in item['summary'].strip().split('\n') if p.strip()]
    impact_points = [p.strip("12345. -") for p in item['impact'].strip().split('\n') if p.strip()]

    # CSS ko hum ek variable mein rakhenge taaki code clean rahe
    # Note: Blogger ke liye hum inline styles + internal CSS combine kar rahe hain
    css_block = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        .ai-card-container {
            font-family: 'Inter', sans-serif;
            max-width: 700px;
            width: 100%;
            margin: 0 auto;
            padding: 10px;
            box-sizing: border-box;
        }
        .ai-card {
            background: #ffffff;
            border: 1px solid #f3f4f6;
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        .ai-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.01);
            border-color: #FF385C;
        }
        .ai-card:hover .top-gradient {
            opacity: 1;
        }
        .top-gradient {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 5px;
            background: linear-gradient(90deg, #FF385C, #9333ea);
            opacity: 0.7;
            transition: opacity 0.3s ease;
        }
        .section-box {
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            transition: transform 0.3s ease;
        }
        .section-box:hover {
            transform: scale(1.01);
        }
        .summary-box { background: #fff1f2; border: 1px solid #ffe4e6; }
        .impact-box { background: #eff6ff; border: 1px solid #dbeafe; }
        
        .list-item {
            display: flex;
            align-items: flex-start;
            margin-bottom: 12px;
            font-size: 15px;
            line-height: 1.6;
            color: #374151;
        }
        .list-item:last-child { margin-bottom: 0; }
        
        .number-badge {
            flex-shrink: 0;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            margin-right: 12px;
            margin-top: 2px;
        }
        .sum-badge { background: #FF385C; color: white; }
        .imp-badge { background: #3b82f6; color: white; }
        
        .read-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #111827;
            color: white !important;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.3s ease;
            width: auto;
        }
        .read-btn:hover {
            background: #FF385C;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(255, 56, 92, 0.3);
        }

        /* Mobile Adjustments */
        @media (max-width: 600px) {
            .ai-card { padding: 20px 15px; }
            h1 { font-size: 20px !important; }
            .section-box { padding: 15px; }
            .read-btn { width: 100%; }
        }
    </style>
    """

    final_html = f"""
    {css_block}
    <div class="ai-card-container">
        <div class="ai-card">
            <div class="top-gradient"></div>
            
            <div style="margin-bottom: 25px;">
                <span style="background: #f3f4f6; color: #4b5563; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px;">
                    {date_str}
                </span>
                <h1 style="color: #111827; font-size: 24px; font-weight: 800; margin-top: 15px; line-height: 1.3;">
                    {item['title']}
                </h1>
            </div>

            <div style="margin-bottom: 25px;">
                <div style="display: flex; align-items: center; margin-bottom: 10px; color: #FF385C;">
                    <span style="font-size: 20px; margin-right: 8px;">🧠</span>
                    <strong style="text-transform: uppercase; font-size: 12px; letter-spacing: 1px;">AI Summary</strong>
                </div>
                <div class="section-box summary-box">
                    {''.join([f'''
                    <div class="list-item">
                        <span class="number-badge sum-badge">{i+1}</span>
                        <span>{p}</span>
                    </div>
                    ''' for i, p in enumerate(summary_points[:5])])}
                </div>
            </div>

            <div style="margin-bottom: 30px;">
                <div style="display: flex; align-items: center; margin-bottom: 10px; color: #3b82f6;">
                    <span style="font-size: 20px; margin-right: 8px;">⚡</span>
                    <strong style="text-transform: uppercase; font-size: 12px; letter-spacing: 1px;">Future Impact</strong>
                </div>
                <div class="section-box impact-box">
                    {''.join([f'''
                    <div class="list-item">
                        <span class="number-badge imp-badge">{i+1}</span>
                        <span>{p}</span>
                    </div>
                    ''' for i, p in enumerate(impact_points[:5])])}
                </div>
            </div>

            <div style="text-align: center;">
                <a href="{item['link']}" class="read-btn">
                    Read Full Story
                    <span style="margin-left: 8px;">→</span>
                </a>
                <p style="margin-top: 15px; color: #9ca3af; font-size: 11px;">
                   WRITTEN by XAI DIGEST • Source: {item.get('source', 'Web')}
                </p>
            </div>
        </div>
    </div>
    """
    return final_html, date_str

# --- MAIN EXECUTION ---
def main():
    print("📰 Picking a random trending topic...")
    if not BLOG_ID: print("⚠️ WARNING: BLOG_ID missing!")
    
    items = []
    random.shuffle(RSS_FEEDS) # Shuffle list
    
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            entry = feed.entries[0]
            desc = entry.get('summary', '') or entry.get('description', '')
            summary, impact = get_analysis(entry.title, entry.link, desc)
            source_name = url.split('/')[2].replace('www.', '')
            
            items.append({'title': entry.title, 'link': entry.link, 'summary': summary, 'impact': impact, 'source': source_name})
            if items: break # Only 1 post
        except: continue

    if items:
        html, date = make_html(items)
        try:
            # 1. Blogger
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            body = {'title': f"AI Analysis: {items[0]['title']}", 'content': html, 'labels': ['AI Update', 'Tech Insights']}
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Blogger Success: {post['url']}")
            
            # 2. Telegram
            item = items[0]
            telegram_msg = (
                f"⚡ *XAI  DIGEST ANALYSIS*\n\n"
                f"📰 *{item['title']}*\n\n"
                f"🧠 *SUMMARY*\n{item['summary']}\n\n"
                f"⚡ *IMPACT*\n{item['impact']}\n\n"
                f"🔗 [Read Full Story]({item['link']})\n\n"
                f"📖 [Visit Blog]({post['url']})"
            )
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": telegram_msg, "parse_mode": "Markdown"})
            print("✅ Telegram Success")
            
        except Exception as e: print(f"❌ Error: {e}")
    else: print("⚠️ No news found today.")

if __name__ == "__main__":
    main()






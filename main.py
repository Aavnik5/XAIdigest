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

# --- RSS FEEDS (AI) ---
AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://www.wired.com/feed/category/ai/latest/rss",
    "https://arstechnica.com/tag/ai/feed/",
    "https://www.artificialintelligence-news.com/feed/",
    "https://analyticsindiamag.com/feed/",
    "https://blog.google/technology/ai/rss/",
    "https://openai.com/blog/rss.xml",
]

# --- RSS FEEDS (TRADING & FINANCE) ---
TRADING_FEEDS = [
    "https://finance.yahoo.com/news/rssindex",
    "https://www.investing.com/rss/news.rss",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "https://cointelegraph.com/rss"
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
def get_analysis(title, link, description="", category="AI"):
    print(f"DEBUG: Analyzing ({category}): {title[:40]}...") 
    
    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(
            model_name,
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        context_instruction = ""
        if category == "TRADING":
            context_instruction = "Focus on market sentiment, stock/crypto price impact, and investor strategy."
        else:
            context_instruction = "Focus on technological breakthrough, future capabilities, and industry adoption."

        prompt = f"""
        Analyze this {category} news.
        TITLE: {title}
        DESCRIPTION: {description[:800]}

        CONTEXT: {context_instruction}

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
            
            if len(impact.split('\n')) >= 3:
                return summary, impact
        
        raise ValueError("AI response format was incorrect")

    except Exception as e:
        print(f"❌ AI Error: {e}. Using Smart Fallback.")
        
    fallback_summary = "1. Important update regarding recent market/tech events.\n2. Details are developing rapidly.\n3. Key stakeholders are involved.\n4. Check source link for charts/data.\n5. Global implications expected."
    fallback_impact = "1. Market volatility may increase.\n2. Investors should watch key levels.\n3. Long term trend remains to be seen.\n4. Competitors may react soon.\n5. Regulatory eyes are watching."
    return fallback_summary, fallback_impact

def make_html(news_items, category="AI"):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    item = news_items[0]
    
    # Text cleaning
    summary_points = [p.strip("12345. -") for p in item['summary'].strip().split('\n') if p.strip()]
    impact_points = [p.strip("12345. -") for p in item['impact'].strip().split('\n') if p.strip()]

    # --- THEME COLORS ---
    if category == "TRADING":
        grad_colors = "#10b981, #0ea5e9"
        icon_sum = "trending_up"
        icon_imp = "currency_exchange"
        badge_bg_sum = "#ecfdf5"
        badge_bg_imp = "#f0f9ff"
        pill_sum = "#10b981"
        pill_imp = "#0ea5e9"
    else:
        grad_colors = "#FF385C, #9333ea"
        icon_sum = "psychology"
        icon_imp = "bolt"
        badge_bg_sum = "#fff1f2"
        badge_bg_imp = "#eff6ff"
        pill_sum = "#FF385C"
        pill_imp = "#3b82f6"

    css_block = f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0&display=swap');
        
        .ai-card-container {{ font-family: 'Inter', sans-serif; max-width: 700px; width: 100%; margin: 0 auto; padding: 10px; box-sizing: border-box; }}
        .ai-card {{ background: #ffffff; border: 1px solid #f3f4f6; border-radius: 20px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); position: relative; overflow: hidden; }}
        .top-gradient {{ position: absolute; top: 0; left: 0; width: 100%; height: 5px; background: linear-gradient(90deg, {grad_colors}); }}
        
        .section-box {{ border-radius: 16px; padding: 18px; margin-bottom: 20px; }}
        .summary-box {{ background: {badge_bg_sum}; border: 1px solid {badge_bg_sum}; }}
        .impact-box {{ background: {badge_bg_imp}; border: 1px solid {badge_bg_imp}; }}
        
        .list-item {{ display: flex; align-items: flex-start; margin-bottom: 10px; font-size: 15px; line-height: 1.6; color: #374151; }}
        .number-badge {{ flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; margin-right: 10px; margin-top: 3px; }}
        .sum-badge {{ background: {pill_sum}; color: white; }}
        .imp-badge {{ background: {pill_imp}; color: white; }}
        
        .read-btn {{ display: block; background: #111827; color: white !important; text-decoration: none; padding: 12px; border-radius: 12px; font-weight: 600; font-size: 14px; text-align: center; margin-bottom: 20px; transition: transform 0.2s; }}
        .read-btn:hover {{ transform: translateY(-2px); }}

        .stats-bar {{ display: flex; justify-content: center; align-items: center; border-top: 1px solid #f3f4f6; padding-top: 15px; margin-top: 10px; }}
        .stat-item {{ display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 8px 16px; border-radius: 50px; }}
        
        .share-btn {{ background: #f0fdf4; color: #16a34a; cursor: pointer; border: none; transition: all 0.2s ease; width: 100%; justify-content: center; }}
        .share-btn:hover {{ background: #dcfce7; transform: scale(1.02); }}
        .icon {{ font-size: 18px; font-family: 'Material Symbols Rounded'; }}
    </style>
    """

    # --- JAVASCRIPT LOGIC (ONLY SHARE, NO VIEWS) ---
    script_block = f"""
    <script>
        function sharePost() {{
            const url = window.location.href;
            const text = 'Check this {category} Update: {item['title']}';
            if (navigator.share) {{
                navigator.share({{ title: '{item['title']}', text: text, url: url }});
            }} else {{
                window.open('https://wa.me/?text=' + encodeURIComponent(text + ' ' + url));
            }}
        }}
    </script>
    """

    final_html = f"""
    {css_block}
    <div class="ai-card-container">
        <div class="ai-card">
            <div class="top-gradient"></div>
            
            <div style="margin-bottom: 20px;">
                <span style="background: #f3f4f6; color: #4b5563; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase;">
                    {date_str} • {category}
                </span>
                <h1 style="color: #111827; font-size: 22px; font-weight: 800; margin-top: 12px; line-height: 1.3;">
                    {item['title']}
                </h1>
            </div>

            <div style="margin-bottom: 20px;">
                <div style="display: flex; align-items: center; margin-bottom: 8px; color: {pill_sum};">
                    <span class="material-symbols-rounded" style="margin-right: 6px;">{icon_sum}</span>
                    <strong style="font-size: 12px; letter-spacing: 0.5px;">MARKET SUMMARY</strong>
                </div>
                <div class="section-box summary-box">
                    {''.join([f'<div class="list-item"><span class="number-badge sum-badge">{i+1}</span><span>{p}</span></div>' for i, p in enumerate(summary_points[:5])])}
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <div style="display: flex; align-items: center; margin-bottom: 8px; color: {pill_imp};">
                    <span class="material-symbols-rounded" style="margin-right: 6px;">{icon_imp}</span>
                    <strong style="font-size: 12px; letter-spacing: 0.5px;">FINANCIAL IMPACT</strong>
                </div>
                <div class="section-box impact-box">
                    {''.join([f'<div class="list-item"><span class="number-badge imp-badge">{i+1}</span><span>{p}</span></div>' for i, p in enumerate(impact_points[:5])])}
                </div>
            </div>

            <a href="{item['link']}" class="read-btn" target="_blank">Read Full Source</a>

            <div class="stats-bar">
                <button class="stat-item share-btn" onclick="sharePost()">
                    <span class="icon">share</span>
                    <span>Share This Update</span>
                </button>
            </div>
        </div>
    </div>
    {script_block}
    """
    return final_html, date_str
    
# --- MAIN EXECUTION ---
def main():
    print("📰 Script Started...")
    if not BLOG_ID: print("⚠️ WARNING: BLOG_ID missing!")
    
    # --- RANDOM CATEGORY SELECTION ---
    if random.random() < 0.3:
        category = "TRADING"
        feed_list = TRADING_FEEDS
        label_tag = "Trading News"
        print("📊 Mode: TRADING/FINANCE")
    else:
        category = "AI"
        feed_list = AI_FEEDS
        label_tag = "AI Update"
        print("🤖 Mode: ARTIFICIAL INTELLIGENCE")

    items = []
    random.shuffle(feed_list)
    
    for url in feed_list:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            entry = feed.entries[0]
            desc = entry.get('summary', '') or entry.get('description', '')
            
            summary, impact = get_analysis(entry.title, entry.link, desc, category)
            source_name = url.split('/')[2].replace('www.', '')
            
            items.append({'title': entry.title, 'link': entry.link, 'summary': summary, 'impact': impact, 'source': source_name})
            if items: break
        except: continue

    if items:
        html, date = make_html(items, category)
        try:
            # 1. Blogger
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
            service = build('blogger', 'v3', credentials=creds)
            
            title_prefix = "📈 Market Alert:" if category == "TRADING" else "⚡ AI Update:"
            body = {'title': f"{title_prefix} {items[0]['title']}", 'content': html, 'labels': [label_tag, 'Trending']}
            
            post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print(f"✅ Blogger Success: {post['url']}")
            
            # 2. Telegram
            item = items[0]
            header = "📊 *MARKET & TRADING DIGEST*" if category == "TRADING" else "⚡ *AI & TECH DIGEST*"
            
            telegram_msg = (
                f"{header}\n\n"
                f"📰 *{item['title']}*\n\n"
                f"📝 *SUMMARY*\n{item['summary']}\n\n"
                f"🚀 *IMPACT*\n{item['impact']}\n\n"
                f"🔗 [Read Source]({item['link']})\n\n"
                f"📖 [Read on Blog]({post['url']})"
            )
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          data={"chat_id": CHANNEL_ID, "text": telegram_msg, "parse_mode": "Markdown"})
            print("✅ Telegram Success")
            
        except Exception as e: print(f"❌ Error: {e}")
    else: print("⚠️ No news found.")

if __name__ == "__main__":
    main()

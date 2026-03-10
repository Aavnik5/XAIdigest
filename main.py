import datetime
import html
import json
import os
import random
import re

import feedparser
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("DEBUG: Script is starting...")

# --- CONFIGURATION ---
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3")
LLM_REQUEST_TIMEOUT = int(os.environ.get("LLM_REQUEST_TIMEOUT", "30"))
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
BLOG_ID = os.environ.get("BLOGGER_ID")
TOKEN_JSON_STR = os.environ.get("BLOGGER_TOKEN_JSON")
BLOGGER_DUP_LOOKBACK = int(os.environ.get("BLOGGER_DUP_LOOKBACK", "30"))
FEED_ENTRY_SCAN_LIMIT = int(os.environ.get("FEED_ENTRY_SCAN_LIMIT", "5"))

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
    "https://cointelegraph.com/rss",
]

# --- ARTICLE SCHEMA (prose-based for AdSense compliance) ---
# Each post generates real paragraphs, not just bullet points.
ARTICLE_SCHEMA = {
    "type": "object",
    "properties": {
        "opening": {
            "type": "string",
            "description": "2-3 sentence paragraph: what happened, who did it, and when. Be specific.",
        },
        "context": {
            "type": "string",
            "description": "2-3 sentence paragraph: relevant background — why this is happening now and what led to it.",
        },
        "analysis": {
            "type": "string",
            "description": "3-4 sentence paragraph: what this changes, what it means for the sector, and any nuance worth noting.",
        },
        "impact": {
            "type": "string",
            "description": "2-3 sentence paragraph: who is most affected and what to watch for next.",
        },
        "takeaways": {
            "type": "array",
            "description": "Exactly 3 short bullet points (under 15 words each) for quick scanners.",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "required": ["opening", "context", "analysis", "impact", "takeaways"],
    "additionalProperties": False,
}

# Legacy schema kept only for Telegram fallback formatting
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 5,
            "maxItems": 5,
        },
        "impact": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 5,
            "maxItems": 5,
        },
    },
    "required": ["summary", "impact"],
    "additionalProperties": False,
}


def clean_text(value, max_chars=1200):
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def split_sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def normalize_point(text, max_words=18):
    cleaned = re.sub(r"^\s*[\-\*\d\.\)\(]+", "", text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) > max_words:
        trimmed_words = words[:max_words]
        while trimmed_words and trimmed_words[-1].lower() in {
            "and", "or", "but", "to", "for", "of", "in", "on", "with", "a", "an", "the",
        }:
            trimmed_words.pop()
        cleaned = " ".join(trimmed_words).rstrip(",;:-")
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned[0].upper() + cleaned[1:]


def format_points(points):
    return "\n".join(f"{index + 1}. {point}" for index, point in enumerate(points[:5]))


def build_prose_fallback(title, description, category):
    """Generate minimal prose fallback when LLM is unavailable."""
    clean_desc = description or title
    source_label = "AI" if category == "AI" else "market"

    opening = (
        f"{title}. "
        f"The development was reported today and is drawing attention across the {source_label} sector."
    )
    context = (
        f"This story is part of a broader pattern of activity in the space. "
        f"Readers can find the full details in the source article linked below."
    )
    analysis = (
        f"Based on the available information, this update carries meaningful implications. "
        f"{clean_desc[:200].rstrip('. ')}. "
        f"The full scope of impact will become clearer as more reporting follows."
    )
    impact = (
        f"Stakeholders in the {'AI and developer' if category == 'AI' else 'trading and finance'} space "
        f"should monitor follow-up announcements closely. "
        f"Early signals suggest this could influence decisions in adjacent areas as well."
    )
    takeaways = [
        normalize_point(title),
        "Full context is available in the original source article.",
        "Further updates are expected as the story develops.",
    ]
    return {
        "opening": opening,
        "context": context,
        "analysis": analysis,
        "impact": impact,
        "takeaways": takeaways,
    }


def validate_article(parsed):
    for key in ("opening", "context", "analysis", "impact"):
        val = parsed.get(key, "")
        if not isinstance(val, str) or len(val.strip().split()) < 10:
            raise ValueError(f"Field '{key}' is too short or missing")
    takeaways = parsed.get("takeaways", [])
    if not isinstance(takeaways, list) or len(takeaways) < 3:
        raise ValueError("takeaways must have at least 3 items")
    return parsed


def get_context_instruction(category):
    if category == "TRADING":
        return "Focus on market drivers, tradable implications, sentiment shifts, and business signals."
    return "Focus on what changed, who launched it, product capability, and realistic industry implications."


def build_analysis_messages(title, link, description, category):
    schema_hint = json.dumps(ARTICLE_SCHEMA, separators=(",", ":"))
    system_prompt = (
        "You are a professional tech and business journalist. "
        "Write clear, original, analytical prose. "
        "Return only valid JSON matching the provided schema. "
        "Do not use vague filler phrases."
    )
    user_prompt = f"""
Write a short news analysis article for this {category} story.

TITLE: {title}
DESCRIPTION: {description or "No description provided."}
SOURCE LINK: {link}
CONTEXT: {get_context_instruction(category)}

RULES:
- Write in third-person journalistic style.
- Be specific — mention named companies, products, figures, or market signals when present.
- Do NOT use filler like "details are developing", "global implications expected", or "stakeholders are involved".
- opening: 2-3 sentences explaining what happened.
- context: 2-3 sentences of relevant background.
- analysis: 3-4 sentences of your own analysis of what this means.
- impact: 2-3 sentences on who is affected and what to watch next.
- takeaways: exactly 3 bullet points, each under 15 words.
- Use this JSON schema: {schema_hint}
""".strip()
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_json_content(text):
    content = (text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content.strip())


def extract_openai_style_content(payload):
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError(f"No choices returned: {payload}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        text_parts = [
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        combined = "".join(text_parts).strip()
        if combined:
            return combined
    raise ValueError(f"Model response content was empty: {payload}")


def ollama_headers():
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return headers


def ollama_api_url(path):
    base = OLLAMA_BASE_URL.rstrip("/")
    if base.endswith("/api"):
        return f"{base}{path}"
    return f"{base}/api{path}"


def can_reach_ollama():
    try:
        response = requests.get(
            ollama_api_url("/version"),
            headers=ollama_headers(),
            timeout=2,
        )
        return response.ok
    except requests.RequestException:
        return False


def get_provider_order():
    if LLM_PROVIDER not in {"groq", "ollama", "auto"}:
        raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is missing")
        print("LLM provider order: ['groq']")
        return ["groq"]
    if LLM_PROVIDER == "ollama":
        if not can_reach_ollama():
            raise ValueError(f"Ollama is not reachable at {OLLAMA_BASE_URL}")
        print("LLM provider order: ['ollama']")
        return ["ollama"]
    provider_order = []
    if GROQ_API_KEY:
        provider_order.append("groq")
    if can_reach_ollama():
        provider_order.append("ollama")
    if not provider_order:
        raise ValueError("Neither Groq nor Ollama is configured and reachable")
    print(f"LLM provider order: {provider_order}")
    return provider_order


def request_groq_analysis(messages):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing")
    response = requests.post(
        f"{GROQ_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.5,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "article_analysis",
                    "schema": ARTICLE_SCHEMA,
                    "strict": True,
                },
            },
        },
        timeout=LLM_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return parse_json_content(extract_openai_style_content(response.json()))


def request_ollama_analysis(messages):
    response = requests.post(
        ollama_api_url("/chat"),
        headers=ollama_headers(),
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": ARTICLE_SCHEMA,
            "options": {"temperature": 0.5},
        },
        timeout=LLM_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    message = payload.get("message") or {}
    content = message.get("content", "")
    if not content.strip():
        raise ValueError(f"Ollama response content was empty: {payload}")
    return parse_json_content(content)


def get_blogger_service():
    if not BLOG_ID or not TOKEN_JSON_STR:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON_STR))
    return build("blogger", "v3", credentials=creds)


def normalize_title_key(title):
    cleaned = re.sub(
        r"^(ai update:|market alert:)\s*", "", (title or "").strip(), flags=re.IGNORECASE
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def extract_links_from_html(content):
    return {
        match.strip()
        for match in re.findall(r'href="([^"]+)"', content or "", flags=re.IGNORECASE)
        if match.strip()
    }


def load_recent_post_keys(service, max_results=BLOGGER_DUP_LOOKBACK):
    if service is None:
        return set(), set()
    response = (
        service.posts()
        .list(blogId=BLOG_ID, maxResults=max_results, fetchBodies=True)
        .execute()
    )
    posts = response.get("items", [])
    title_keys = set()
    link_keys = set()
    for post in posts:
        title_key = normalize_title_key(post.get("title", ""))
        if title_key:
            title_keys.add(title_key)
        for link in extract_links_from_html(post.get("content", "")):
            link_keys.add(link)
    print(f"Loaded {len(posts)} recent Blogger posts for duplicate checks.")
    return title_keys, link_keys


def is_duplicate_post(entry, seen_title_keys, seen_links):
    title_key = normalize_title_key(getattr(entry, "title", ""))
    link = getattr(entry, "link", "").strip()
    return title_key in seen_title_keys or link in seen_links


# --- CORE ANALYSIS ENGINE ---
def get_analysis(title, link, description="", category="AI"):
    print(f"DEBUG: Analyzing ({category}): {title[:60]}...")
    cleaned_description = clean_text(description)

    try:
        provider_errors = []
        messages = build_analysis_messages(title, link, cleaned_description, category)

        for provider in get_provider_order():
            try:
                print(f"Using LLM provider: {provider}")
                if provider == "groq":
                    parsed = request_groq_analysis(messages)
                elif provider == "ollama":
                    parsed = request_ollama_analysis(messages)
                else:
                    raise ValueError(f"Unsupported provider: {provider}")

                validated = validate_article(parsed)
                return validated
            except Exception as provider_exc:
                provider_errors.append(f"{provider}: {provider_exc}")

        if provider_errors:
            raise ValueError("; ".join(provider_errors))
        raise ValueError("No configured LLM provider was available")

    except Exception as exc:
        print(f"LLM Error: {exc}. Using prose fallback.")

    return build_prose_fallback(title, cleaned_description, category)


def make_html(news_items, category="AI"):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    item = news_items[0]
    article = item["article"]

    if category == "TRADING":
        accent_color = "#0ea5e9"
        accent_light = "#f0f9ff"
        category_label = "TRADING"
        read_more_label = "View Original Report"
    else:
        accent_color = "#7c3aed"
        accent_light = "#f5f3ff"
        category_label = "AI & TECH"
        read_more_label = "View Original Report"

    # Render takeaway bullets
    takeaways_html = "".join(
        f'<li style="margin-bottom:8px;line-height:1.6;">{html.escape(point.lstrip("-• "))}</li>'
        for point in article["takeaways"][:3]
    )

    source_domain = item["source"]

    final_html = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .xai-wrap {{
        font-family: 'Inter', sans-serif;
        max-width: 720px;
        margin: 0 auto;
        padding: 12px;
        color: #1f2937;
        line-height: 1.7;
        font-size: 16px;
    }}
    .xai-meta {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: {accent_color};
        margin-bottom: 8px;
    }}
    .xai-title {{
        font-size: 26px;
        font-weight: 800;
        line-height: 1.3;
        color: #111827;
        margin: 0 0 20px 0;
    }}
    .xai-divider {{
        border: none;
        border-top: 2px solid {accent_light};
        margin: 24px 0;
    }}
    .xai-section-label {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #9ca3af;
        margin-bottom: 10px;
    }}
    .xai-paragraph {{
        color: #374151;
        margin-bottom: 20px;
        line-height: 1.8;
    }}
    .xai-takeaways {{
        background: {accent_light};
        border-left: 4px solid {accent_color};
        border-radius: 8px;
        padding: 16px 20px;
        margin: 24px 0;
    }}
    .xai-takeaways ul {{
        margin: 0;
        padding-left: 18px;
        color: #374151;
        font-size: 15px;
    }}
    .xai-source {{
        font-size: 13px;
        color: #6b7280;
        padding-top: 20px;
        border-top: 1px solid #f3f4f6;
        margin-top: 24px;
    }}
    .xai-source a {{
        color: {accent_color};
        text-decoration: none;
        font-weight: 600;
    }}
    .xai-source a:hover {{ text-decoration: underline; }}
    .xai-share {{
        display: inline-block;
        margin-top: 16px;
        background: #111827;
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
        cursor: pointer;
        border: none;
    }}
</style>

<script>
    function xaiShare() {{
        const url = window.location.href;
        const text = "Interesting read: {html.escape(item['title'])}";
        if (navigator.share) {{
            navigator.share({{ title: "{html.escape(item['title'])}", text: text, url: url }});
        }} else {{
            window.open('https://wa.me/?text=' + encodeURIComponent(text + ' ' + url));
        }}
    }}
</script>

<div class="xai-wrap">

    <div class="xai-meta">{date_str} &bull; {category_label}</div>
    <h1 class="xai-title">{html.escape(item["title"])}</h1>

    <p class="xai-paragraph">{html.escape(article["opening"])}</p>

    <hr class="xai-divider">

    <div class="xai-section-label">Background</div>
    <p class="xai-paragraph">{html.escape(article["context"])}</p>

    <div class="xai-section-label">Analysis</div>
    <p class="xai-paragraph">{html.escape(article["analysis"])}</p>

    <div class="xai-section-label">What to Watch</div>
    <p class="xai-paragraph">{html.escape(article["impact"])}</p>

    <div class="xai-takeaways">
        <div class="xai-section-label" style="margin-bottom:10px;">Key Takeaways</div>
        <ul>{takeaways_html}</ul>
    </div>

    <div class="xai-source">
        Originally reported by <a href="{html.escape(item['link'], quote=True)}" target="_blank" rel="noopener">{html.escape(source_domain)}</a>
        &mdash; <a href="{html.escape(item['link'], quote=True)}" target="_blank" rel="noopener">{read_more_label} &rarr;</a>
    </div>

    <button class="xai-share" onclick="xaiShare()">&#8679; Share This Story</button>

</div>
"""
    return final_html, date_str


# --- MAIN EXECUTION ---
def main():
    print("Script started...")
    if not BLOG_ID:
        print("WARNING: BLOG_ID missing!")

    try:
        service = get_blogger_service()
        seen_title_keys, seen_links = load_recent_post_keys(service)
    except Exception as exc:
        print(f"Duplicate filter unavailable: {exc}")
        service = None
        seen_title_keys, seen_links = set(), set()

    if random.random() < 0.3:
        category = "TRADING"
        feed_list = TRADING_FEEDS
        label_tag = "Trading News"
        print("Mode: TRADING/FINANCE")
    else:
        category = "AI"
        feed_list = AI_FEEDS
        label_tag = "AI Update"
        print("Mode: ARTIFICIAL INTELLIGENCE")

    items = []
    random.shuffle(feed_list)

    for url in feed_list:
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                continue

            for entry in feed.entries[:FEED_ENTRY_SCAN_LIMIT]:
                if is_duplicate_post(entry, seen_title_keys, seen_links):
                    print(f"Skipping duplicate: {entry.title[:80]}")
                    continue

                desc = entry.get("summary", "") or entry.get("description", "")
                article = get_analysis(entry.title, entry.link, desc, category)
                source_name = url.split("/")[2].replace("www.", "")

                item = {
                    "title": entry.title,
                    "link": entry.link,
                    "article": article,
                    "source": source_name,
                }
                items.append(item)
                seen_title_keys.add(normalize_title_key(entry.title))
                seen_links.add(entry.link.strip())
                break

            if items:
                break
        except Exception as exc:
            print(f"Feed error from {url}: {exc}")

    if not items:
        print("WARNING: No news found.")
        return

    html_body, date = make_html(items, category)

    try:
        if service is None:
            raise ValueError("Blogger service is unavailable")

        title_prefix = "Market Alert:" if category == "TRADING" else "AI Update:"
        body = {
            "title": f"{title_prefix} {items[0]['title']}",
            "content": html_body,
            "labels": [label_tag, "Trending"],
        }
        post = service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"Blogger success: {post['url']}")

        # Telegram still uses the structured bullet format (fine for messaging)
        item = items[0]
        article = item["article"]
        takeaway_bullets = "\n".join(
            f"• {t.lstrip('-• ')}" for t in article["takeaways"][:3]
        )
        header = "*MARKET & TRADING DIGEST*" if category == "TRADING" else "*AI & TECH DIGEST*"
        telegram_msg = (
            f"{header}\n\n"
            f"*{item['title']}*\n\n"
            f"{article['opening']}\n\n"
            f"*Key Points:*\n{takeaway_bullets}\n\n"
            f"[Read on Blog]({post['url']}) | [Original Source]({item['link']})"
        )

        telegram_response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHANNEL_ID,
                "text": telegram_msg,
                "parse_mode": "Markdown",
            },
            timeout=30,
        )
        telegram_response.raise_for_status()
        print("Telegram success")

    except Exception as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()

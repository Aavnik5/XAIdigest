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

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "array",
            "description": "Five concrete takeaways about what happened.",
            "items": {"type": "string"},
            "minItems": 5,
            "maxItems": 5,
        },
        "impact": {
            "type": "array",
            "description": "Five concrete implications about what matters next.",
            "items": {"type": "string"},
            "minItems": 5,
            "maxItems": 5,
        },
    },
    "required": ["summary", "impact"],
    "additionalProperties": False,
}

AI_IMPACT_RULES = [
    (
        r"\bsecurity|cyber|privacy|trust|safety\b",
        "Security and governance reviews may speed up across similar AI deployments.",
    ),
    (
        r"\bopenai|google|meta|microsoft|anthropic|amazon\b",
        "Competing AI platforms may answer with roadmap or pricing moves.",
    ),
    (
        r"\bagent|automation|assistant|copilot\b",
        "Teams evaluating automation may compare this against existing workflow tools.",
    ),
    (
        r"\bresearch|preview|beta|pilot\b",
        "Short-term impact will likely be strongest among developers testing early access.",
    ),
    (
        r"\bopen source|open-source|weights\b",
        "Open model ecosystems could gain adoption if this lowers switching costs.",
    ),
    (
        r"\bregulat|policy|compliance|copyright\b",
        "Compliance and policy scrutiny may rise if rollout expands quickly.",
    ),
    (
        r"\bchip|gpu|inference|compute|datacenter\b",
        "Infrastructure and AI tooling vendors may benefit if demand scales further.",
    ),
]

TRADING_IMPACT_RULES = [
    (
        r"\bbitcoin|btc|crypto|ethereum|eth|token\b",
        "Crypto sentiment and short-term positioning may react quickly to this headline.",
    ),
    (
        r"\bearnings|guidance|revenue|profit|margin\b",
        "Analysts may revise growth and margin assumptions for related names.",
    ),
    (
        r"\bsec|fed|rate|inflation|tariff|policy|regulat\b",
        "Macro and policy-sensitive sectors could see higher volatility.",
    ),
    (
        r"\bmerger|acquisition|deal|partnership\b",
        "Peers in the same segment may reprice on consolidation expectations.",
    ),
    (
        r"\boil|gold|commodity|yield|bond|treasury\b",
        "Cross-asset traders may reassess inflation and rate expectations.",
    ),
    (
        r"\bupgrade|downgrade|target\b",
        "Positioning may shift as brokers and funds update conviction levels.",
    ),
]


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
            "and",
            "or",
            "but",
            "to",
            "for",
            "of",
            "in",
            "on",
            "with",
            "a",
            "an",
            "the",
        }:
            trimmed_words.pop()
        cleaned = " ".join(trimmed_words).rstrip(",;:-")

    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned[0].upper() + cleaned[1:]


def format_points(points):
    return "\n".join(f"{index + 1}. {point}" for index, point in enumerate(points[:5]))


def build_summary_fallback(title, description):
    candidates = [title] + split_sentences(description)
    points = []
    seen = set()

    for candidate in candidates:
        point = normalize_point(candidate)
        if len(point.split()) < 4:
            continue

        key = re.sub(r"[^a-z0-9]+", " ", point.lower()).strip()
        if not key or key in seen:
            continue

        seen.add(key)
        points.append(point)
        if len(points) == 5:
            break

    return points


def build_impact_fallback(title, description, category):
    text = f"{title} {description}".lower()
    focus = re.split(r"[:|-]", title, maxsplit=1)[0].strip() or title.strip()
    focus = normalize_point(focus, max_words=8).rstrip(".")

    rules = TRADING_IMPACT_RULES if category == "TRADING" else AI_IMPACT_RULES
    points = []
    seen = set()

    for pattern, template in rules:
        if re.search(pattern, text):
            key = template.lower()
            if key not in seen:
                seen.add(key)
                points.append(template)
        if len(points) == 5:
            return points

    if category == "TRADING":
        supplements = [
            f"{focus} could influence trading sentiment around related names and sectors.",
            "Position sizing and short-term volatility may stay elevated after this update.",
            "Institutional flows may depend on whether the news changes the fundamental outlook.",
            "Watch peer reactions for confirmation instead of treating the headline alone as trend proof.",
            "The next catalyst will likely decide whether the move extends or fades.",
        ]
    else:
        supplements = [
            f"{focus} could shape near-term competitor decisions in the same space.",
            f"{focus} may influence customer adoption if execution matches the headline.",
            "Teams will likely compare rollout speed against the broader market narrative.",
            "The strongest reaction should come from adjacent products and ecosystem partners.",
            "Follow-up announcements will matter more than the headline if details remain limited.",
        ]

    for supplement in supplements:
        key = supplement.lower()
        if key not in seen:
            seen.add(key)
            points.append(supplement)
        if len(points) == 5:
            break

    return points[:5]


def build_article_fallback(title, description, category):
    summary_points = build_summary_fallback(title, description)
    impact_points = build_impact_fallback(title, description, category)

    if category == "TRADING":
        summary_fillers = [
            "The feed excerpt is short, so the source article should be checked for the full market context.",
            "Key pricing, volume, or guidance details may only be available in the original report.",
            "This headline is likely one part of a broader market story that needs source-level confirmation.",
        ]
    else:
        summary_fillers = [
            "The feed summary is limited, so the source article should be checked for fuller product context.",
            "Launch scope, availability, and technical limits may only be clear in the original post.",
            "This update likely has more implementation detail than the RSS excerpt shows.",
        ]

    filler_index = 0
    while len(summary_points) < 5:
        summary_points.append(normalize_point(summary_fillers[filler_index % len(summary_fillers)]))
        filler_index += 1

    while len(impact_points) < 5:
        impact_points.append(
            normalize_point(
                "More concrete downstream impact should become clearer once follow-up details are published."
            )
        )

    return format_points(summary_points), format_points(impact_points)


def validate_points(points, label):
    if not isinstance(points, list) or len(points) < 5:
        raise ValueError(f"{label} must contain 5 points")

    cleaned = []
    for point in points[:5]:
        normalized = normalize_point(point)
        if len(normalized.split()) < 4:
            raise ValueError(f"{label} point too short: {point}")
        cleaned.append(normalized)
    return cleaned


def get_context_instruction(category):
    if category == "TRADING":
        return "Focus on market drivers, tradable implications, sentiment shifts, and business signals."
    return "Focus on what changed, who launched it, product capability, and realistic industry implications."


def build_analysis_messages(title, link, description, category):
    schema_hint = json.dumps(ANALYSIS_SCHEMA, separators=(",", ":"))
    system_prompt = (
        "You write concise, specific news analysis. "
        "Return only valid JSON matching the provided schema."
    )
    user_prompt = f"""
Analyze this {category} news item using only the provided title and description.

TITLE: {title}
DESCRIPTION: {description or "No description provided."}
SOURCE LINK: {link}
CONTEXT: {get_context_instruction(category)}

RULES:
- Be specific. Mention named companies, products, or market signals when present.
- Do not use vague filler like "details are developing", "stakeholders are involved", or "global implications expected".
- Each point should be a single sentence and under 18 words.
- Return exactly 5 summary points and exactly 5 impact points.
- The summary should describe what happened.
- The impact should explain why it matters next.
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
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
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
            "temperature": 0.4,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "news_analysis",
                    "schema": ANALYSIS_SCHEMA,
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
            "format": ANALYSIS_SCHEMA,
            "options": {"temperature": 0.4},
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
    cleaned = re.sub(r"^(ai update:|market alert:)\s*", "", (title or "").strip(), flags=re.IGNORECASE)
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
    print(f"DEBUG: Analyzing ({category}): {title[:40]}...")
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

                summary_points = validate_points(parsed.get("summary"), "summary")
                impact_points = validate_points(parsed.get("impact"), "impact")
                return format_points(summary_points), format_points(impact_points)
            except Exception as provider_exc:
                provider_errors.append(f"{provider}: {provider_exc}")

        if provider_errors:
            raise ValueError("; ".join(provider_errors))
        raise ValueError("No configured LLM provider was available")

    except Exception as exc:
        print(f"LLM Error: {exc}. Using article-based fallback.")

    return build_article_fallback(title, cleaned_description, category)


def make_html(news_items, category="AI"):
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    item = news_items[0]

    summary_points = [p.strip("12345. -") for p in item["summary"].strip().split("\n") if p.strip()]
    impact_points = [p.strip("12345. -") for p in item["impact"].strip().split("\n") if p.strip()]

    if category == "TRADING":
        grad_colors = "#10b981, #0ea5e9"
        icon_sum = "trending_up"
        icon_imp = "currency_exchange"
        badge_bg_sum = "#ecfdf5"
        badge_bg_imp = "#f0f9ff"
        pill_sum = "#10b981"
        pill_imp = "#0ea5e9"
        summary_label = "MARKET SUMMARY"
        impact_label = "FINANCIAL IMPACT"
    else:
        grad_colors = "#FF385C, #9333ea"
        icon_sum = "psychology"
        icon_imp = "bolt"
        badge_bg_sum = "#fff1f2"
        badge_bg_imp = "#eff6ff"
        pill_sum = "#FF385C"
        pill_imp = "#3b82f6"
        summary_label = "KEY TAKEAWAYS"
        impact_label = "WHY IT MATTERS"

    rendered_summary = "".join(
        f'<div class="list-item"><span class="number-badge sum-badge">{index + 1}</span><span>{html.escape(point)}</span></div>'
        for index, point in enumerate(summary_points[:5])
    )
    rendered_impact = "".join(
        f'<div class="list-item"><span class="number-badge imp-badge">{index + 1}</span><span>{html.escape(point)}</span></div>'
        for index, point in enumerate(impact_points[:5])
    )

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

    share_title = json.dumps(item["title"])
    share_text = json.dumps(f"Check this {category} Update: {item['title']}")

    script_block = f"""
    <script>
        function sharePost() {{
            const url = window.location.href;
            const text = {share_text};
            if (navigator.share) {{
                navigator.share({{ title: {share_title}, text: text, url: url }});
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
                    {date_str} &bull; {html.escape(category)}
                </span>
                <h1 style="color: #111827; font-size: 22px; font-weight: 800; margin-top: 12px; line-height: 1.3;">
                    {html.escape(item["title"])}
                </h1>
            </div>

            <div style="margin-bottom: 20px;">
                <div style="display: flex; align-items: center; margin-bottom: 8px; color: {pill_sum};">
                    <span class="material-symbols-rounded" style="margin-right: 6px;">{icon_sum}</span>
                    <strong style="font-size: 12px; letter-spacing: 0.5px;">{summary_label}</strong>
                </div>
                <div class="section-box summary-box">
                    {rendered_summary}
                </div>
            </div>

            <div style="margin-bottom: 20px;">
                <div style="display: flex; align-items: center; margin-bottom: 8px; color: {pill_imp};">
                    <span class="material-symbols-rounded" style="margin-right: 6px;">{icon_imp}</span>
                    <strong style="font-size: 12px; letter-spacing: 0.5px;">{impact_label}</strong>
                </div>
                <div class="section-box impact-box">
                    {rendered_impact}
                </div>
            </div>

            <a href="{html.escape(item['link'], quote=True)}" class="read-btn" target="_blank">Read Full Source</a>

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

                summary, impact = get_analysis(entry.title, entry.link, desc, category)
                source_name = url.split("/")[2].replace("www.", "")
                item = {
                    "title": entry.title,
                    "link": entry.link,
                    "summary": summary,
                    "impact": impact,
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

        item = items[0]
        header = "*MARKET & TRADING DIGEST*" if category == "TRADING" else "*AI & TECH DIGEST*"

        telegram_msg = (
            f"{header}\n\n"
            f"*{item['title']}*\n\n"
            f"*SUMMARY*\n{item['summary']}\n\n"
            f"*IMPACT*\n{item['impact']}\n\n"
            f"[Read Source]({item['link']})\n\n"
            f"[Read on Blog]({post['url']})"
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

import os
import json
import textwrap
import requests
import datetime
import html
import urllib.parse
import time
import logging
from functools import wraps
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
analyser = SentimentIntensityAnalyzer()

def rate_limit(delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            time.sleep(delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def safe_api_call(func_name, api_call):
    try:
        result = api_call()
        if result:
            logger.info(f"{func_name}: Success")
        else:
            logger.warning(f"{func_name}: No results found")
        return result
    except Exception as e:
        logger.error(f"{func_name}: Error - {e}")
        return None

def classify_reddit_content(title, selftext=""):
    combined = (title + " " + selftext).lower()
    
    success_keywords = [
        "got a job", "landed a job", "hired", "got hired", "career change success",
        "promotion", "promoted", "salary increase", "new position", "job offer"
    ]
    
    pain_keywords = [
        "why is it so hard", "struggling to", "can't find", "difficulty finding",
        "impossible to", "no luck", "rejected", "unemployment", "job search struggles"
    ]
    
    question_keywords = [
        "should i", "is it worth", "how to", "what do you think", "advice needed"
    ]
    
    course_keywords = [
        "just completed", "finished the course", "course review", "thoughts on"
    ]
    
    for keyword in success_keywords:
        if keyword in combined:
            return ("testimonial", 0.9)
    
    for keyword in pain_keywords:
        if keyword in combined:
            return ("pain_point", 0.9)
    
    for keyword in question_keywords:
        if keyword in combined:
            return ("motivation", 0.7)
    
    for keyword in course_keywords:
        if keyword in combined:
            return ("course_rec", 0.6)
    
    if title.endswith("?"):
        return ("motivation", 0.4)
    
    return ("motivation", 0.3)

@rate_limit(delay=2)
def meta_ad():
    def _fetch_meta_ads():
        token = os.environ.get("FB_TOKEN", "").strip()
        if not token:
            logger.error("FB_TOKEN not found")
            return None

        brands = ["New York Times", "Strava", "Peloton", "TED", "MasterClass", "Headspace", "Duolingo"]
        all_candidates = []

        for brand in brands:
            logger.info(f"Searching Meta ads for: {brand}")
            
            for keyword in ["video", "course", "learn", ""]:
                search_term = f"{brand} {keyword}".strip()
                term = urllib.parse.quote(search_term)
                
                url = (
                    f"https://graph.facebook.com/v18.0/ads_archive?"
                    f"search_terms={term}&"
                    "ad_reached_countries=US&"
                    "ad_active_status=ACTIVE&"
                    "fields=ad_creative_body,ad_snapshot_url,impressions_lower_bound&"
                    "limit=20&"
                    f"access_token={token}"
                )
                
                try:
                    resp = requests.get(url, timeout=15)
                    if resp.status_code != 200:
                        continue
                    
                    data = resp.json()
                    if "error" in data:
                        logger.error(f"Meta API error: {data['error']}")
                        continue
                    
                    ads = data.get("data", [])
                    logger.info(f"Found {len(ads)} ads for {search_term}")
                    
                    for ad in ads:
                        ad['source_brand'] = brand
                        ad['search_term'] = search_term
                        all_candidates.append(ad)
                        
                except Exception as e:
                    logger.warning(f"Error fetching {search_term}: {e}")
                    continue

        logger.info(f"Total Meta ad candidates found: {len(all_candidates)}")

        if not all_candidates:
            return None

        video_like_ads = []
        for ad in all_candidates:
            body_text = ad.get("ad_creative_body", "").lower()
            engagement_indicators = ["video", "watch", "learn", "course", "join", "start", "discover"]
            
            if any(indicator in body_text for indicator in engagement_indicators) or len(body_text) > 50:
                video_like_ads.append(ad)

        target_ads = video_like_ads if video_like_ads else all_candidates
        
        if not target_ads:
            return None

        try:
            top = max(target_ads, key=lambda r: int(r.get("impressions_lower_bound", 0)))
        except:
            top = target_ads[0]
        
        creative_body = html.unescape(top.get("ad_creative_body", "")[:150])
        snapshot = top.get("ad_snapshot_url", "")
        impressions = top.get("impressions_lower_bound", "N/A")
        brand = top.get("source_brand", "Unknown")
        search_term = top.get("search_term", "")

        return (
            f"*🎯 Premium Brand Inspiration ({brand})*\n"
            f"• **Search term:** {search_term}\n"
            f"• **Impressions:** {impressions} (lower bound)\n"
            f"• **Hook:** {creative_body}...\n"
            f"• [Watch Ad Preview]({snapshot})"
        )

    return safe_api_call("meta_ad", _fetch_meta_ads)

@rate_limit(delay=1.5)
def reddit_insight():
    def _fetch_reddit_insights():
        client_id = os.environ.get("REDDIT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_SECRET", "").strip()
        if not (client_id and client_secret):
            return None

        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        data = {"grant_type": "client_credentials"}
        
        token_resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers={"User-Agent": "swipebot"},
            timeout=10
        ).json()

        token = token_resp.get("access_token")
        if not token:
            return None

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}

        searches = [
            {
                "subreddit": "Coursera",
                "query": "got%20hired|landed%20job|career%20success",
                "type": "testimonial",
                "min_ups": 3,
                "min_sentiment": 0.3
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "coursera%20got%20hired|google%20certificate%20hired",
                "type": "testimonial", 
                "min_ups": 5,
                "min_sentiment": 0.2
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "can't%20find%20job|struggling%20entry%20level",
                "type": "pain_point",
                "min_ups": 20,
                "min_sentiment": -0.3
            },
            {
                "subreddit": "learnprogramming",
                "query": "completed%20coursera|finished%20andrew%20ng",
                "type": "course_rec",
                "min_ups": 15,
                "min_sentiment": 0.3
            }
        ]

        best_candidate = None
        best_score = 0

        for search in searches:
            url = (
                f"https://oauth.reddit.com/r/{search['subreddit']}/search?"
                f"q={search['query']}&restrict_sr=on&sort=top&t=month&limit=20"
            )
            
            try:
                response = requests.get(url, headers=headers, timeout=10).json()
                posts = response.get("data", {}).get("children", [])
                
                for post in posts:
                    data = post.get("data", {})
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")
                    ups = data.get("ups", 0)
                    
                    actual_type, confidence = classify_reddit_content(title, selftext)
                    
                    if actual_type != search["type"] and confidence > 0.6:
                        continue
                    
                    if ups < search["min_ups"]:
                        continue
                        
                    combined = title + " " + selftext
                    sentiment = analyser.polarity_scores(combined).get("compound", 0)
                    
                    if sentiment < search["min_sentiment"]:
                        continue
                    
                    score = ups * confidence
                    
                    if search["type"] == "testimonial":
                        score *= 5
                    elif search["type"] == "pain_point":
                        score *= 3
                    elif search["type"] == "course_rec":
                        score *= 2
                    
                    if score > best_score:
                        best_score = score
                        best_candidate = {
                            "data": data,
                            "type": actual_type,
                            "subreddit": search["subreddit"],
                            "sentiment": sentiment,
                            "upvotes": ups,
                            "score": score,
                            "confidence": confidence
                        }

            except Exception as e:
                continue

        if best_candidate:
            data = best_candidate["data"]
            title = data.get("title", "")
            permalink = data.get("permalink", "")
            
            type_labels = {
                "testimonial": "✅ Success Story",
                "pain_point": "❗ Pain Point",
                "motivation": "💡 User Question", 
                "course_rec": "📚 Course Experience"
            }
            
            type_label = type_labels.get(best_candidate["type"], "Insight")
            headline = textwrap.shorten(title, 90)
            
            return (
                f"*{type_label} from r/{best_candidate['subreddit']}*\n"
                f"• **{headline}**\n"
                f"• {best_candidate['upvotes']} upvotes | "
                f"Sentiment: {best_candidate['sentiment']:.2f}\n"
                f"• [Read more](https://reddit.com{permalink})"
            )

        return None

    return safe_api_call("reddit_insight", _fetch_reddit_insights)

@rate_limit(delay=1)
def reddit_story():
    def _fetch_reddit_story():
        client_id = os.environ.get("REDDIT_ID", "")
        client_secret = os.environ.get("REDDIT_SECRET", "")
        if not client_id or not client_secret:
            return None

        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        data = {"grant_type": "client_credentials"}
        token_response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers={"User-Agent": "swipebot"},
            timeout=10
        ).json()

        token = token_response.get("access_token")
        if not token:
            return None

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}
        
        query = "coursera%20completed|coursera%20finished|earned%20certificate"
        
        query_url = (
            f"https://oauth.reddit.com/r/coursera+learnprogramming+getStudying/search"
            f"?q={query}&sort=top&restrict_sr=on&t=month&limit=30"
        )
        
        posts_response = requests.get(query_url, headers=headers, timeout=10).json()
        children = posts_response.get("data", {}).get("children", [])

        best_post = None
        best_score = 0
        
        for post in children:
            data = post.get("data", {})
            title = data.get("title", "")
            selftext = data.get("selftext", "")
            ups = data.get("ups", 0)

            content_type, confidence = classify_reddit_content(title, selftext)
            
            if content_type not in ["course_rec", "testimonial"] or confidence < 0.5:
                continue

            combined_text = title + " " + selftext
            sentiment = analyser.polarity_scores(combined_text).get("compound", 0)

            if ups >= 5 and sentiment > 0.2:
                score = ups * sentiment * confidence
                
                completion_words = ["completed", "finished", "earned", "graduated", "success"]
                if any(word in combined_text.lower() for word in completion_words):
                    score *= 2
                
                if score > best_score:
                    best_score = score
                    best_post = data

        if best_post:
            title = best_post.get("title", "")
            permalink = best_post.get("permalink", "")
            ups = best_post.get("ups", 0)
            headline = textwrap.shorten(title, 90)
            
            return (
                f"*📈 Course Completion Story*\n"
                f"• **{headline}**\n"
                f"• {ups} upvotes\n"
                f"• [Reddit link](https://reddit.com{permalink})"
            )

        return None

    return safe_api_call("reddit_story", _fetch_reddit_story)

def format_digest(blocks):
    valid_blocks = [section for section in blocks if section]
    
    if not valid_blocks:
        return None
        
    formatted_blocks = []
    for i, block in enumerate(valid_blocks):
        if i > 0:
            formatted_blocks.append("─" * 35)
        formatted_blocks.append(block)
    
    return "\n\n".join(formatted_blocks)

def send_slack(msg):
    hook = os.getenv("SLACK_WEBHOOK", "").strip()
    if hook:
        try:
            response = requests.post(
                hook, 
                data=json.dumps({"text": msg}), 
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False
    return False

def send_email(msg):
    user = os.getenv("EMAIL_FROM", "").strip()
    pwd = os.getenv("EMAIL_PW", "").strip()
    to = os.getenv("EMAIL_TO", "").strip()

    if not (user and pwd and to):
        return False

    try:
        import email.message
        import smtplib

        email_msg = email.message.EmailMessage()
        email_msg["Subject"] = f"Swipe-File Digest - {datetime.date.today()}"
        email_msg["From"] = user
        email_msg["To"] = to
        email_msg.set_content(msg)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(user, pwd)
            smtp.send_message(email_msg)
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False

def main():
    logger.info("Starting Swipe-File Scout...")
    
    blocks = [
        meta_ad(),
        reddit_insight(),
        reddit_story()
    ]

    successful_blocks = [b for b in blocks if b is not None]
    logger.info(f"Successfully fetched {len(successful_blocks)}/3 content blocks")

    digest = format_digest(blocks)
    
    if not digest:
        digest = (
            "*🔄 Fallback Insight*\n"
            "• **Check API credentials and try again**\n"
            "• **Focus on testimonial-driven video ads**"
        )

    if digest:
        timestamp = datetime.date.today().strftime("%Y-%m-%d")
        full_msg = f"▶️ Swipe-file digest ({timestamp})\n\n" + digest

        if send_slack(full_msg):
            logger.info("Digest sent via Slack")
        elif send_email(full_msg):
            logger.info("Digest sent via email")
        else:
            logger.error("Failed to send digest")

if __name__ == "__main__":
    main()
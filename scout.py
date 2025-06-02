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
    """Enhanced classification that actually reads the content"""
    combined = (title + " " + selftext).lower()
    
    # EXPLICIT success indicators - must mention coursera AND success
    coursera_success_keywords = [
        "coursera got a job", "coursera landed job", "coursera helped me get",
        "google certificate got hired", "google it support hired", 
        "coursera career change success", "coursera promotion"
    ]
    
    # General success but check if coursera-related
    general_success_keywords = [
        "got a job", "landed a job", "hired", "job offer", "promotion"
    ]
    
    # Clear pain points
    pain_keywords = [
        "why is it so hard", "struggling to", "can't find", "difficulty finding",
        "impossible to", "no luck", "rejected", "unemployment", "job search struggles",
        "been applying for months", "getting discouraged", "feeling stuck"
    ]
    
    # Questions/advice seeking (high confidence)
    question_keywords = [
        "can i get", "should i", "is it worth", "how do i", "what do you think", 
        "advice needed", "help me", "recommendations", "which course", 
        "best way to", "how to start", "career switch at", "entry-level job by learning"
    ]
    
    # ACTUAL course completions (not questions about them)
    completion_keywords = [
        "just completed coursera", "finished coursera course", "earned my certificate",
        "graduated from coursera", "coursera specialization complete", 
        "completed andrew ng", "finished my coursera"
    ]
    
    # Check for explicit Coursera success stories first
    for keyword in coursera_success_keywords:
        if keyword in combined:
            return ("testimonial", 0.95)
    
    # Check for general success but only if coursera mentioned
    if "coursera" in combined or "google certificate" in combined:
        for keyword in general_success_keywords:
            if keyword in combined:
                return ("testimonial", 0.8)
    
    # Check for clear pain points
    for keyword in pain_keywords:
        if keyword in combined:
            return ("pain_point", 0.9)
    
    # Check for questions/advice seeking (these are NOT success stories)
    for keyword in question_keywords:
        if keyword in combined:
            return ("motivation", 0.9)  # High confidence this is a question
    
    # Check for actual completions
    for keyword in completion_keywords:
        if keyword in combined:
            return ("course_rec", 0.8)
    
    # Fallback: Questions end with ?
    if title.strip().endswith("?"):
        return ("motivation", 0.8)  # Questions are NOT completion stories
    
    # If contains coursera + completed/finished but wasn't caught above
    if "coursera" in combined and any(word in combined for word in ["completed", "finished", "done with"]):
        return ("course_rec", 0.6)
    
    return ("motivation", 0.3)

@rate_limit(delay=2)
def meta_ad():
    """Enhanced Meta Ad search with detailed debugging"""
    def _fetch_meta_ads():
        token = os.environ.get("FB_TOKEN", "").strip()
        if not token:
            logger.error("FB_TOKEN not found in environment variables")
            return (
                "❌ META AD LIBRARY ACCESS PENDING\n"
                "   → FB_TOKEN found but requires approval\n"
                "   → Status: developers.facebook.com/tools/explorer\n"
                "   → Typical approval: 1-3 business days\n"
            )

        # Test the token first
        test_url = f"https://graph.facebook.com/v18.0/me?access_token={token}"
        try:
            test_resp = requests.get(test_url, timeout=10)
            if test_resp.status_code != 200:
                logger.error(f"FB_TOKEN test failed: {test_resp.status_code}")
                return (
                    "❌ META AD LIBRARY TOKEN ISSUE\n"
                    f"   → Authentication failed (HTTP {test_resp.status_code})\n"
                    "   → Action: Regenerate token at developers.facebook.com\n"
                    "   → Required: ads_read permission + account approval\n"
                )
        except Exception as e:
            logger.error(f"FB_TOKEN test error: {e}")
            return None

        brands = ["New York Times", "Strava", "Peloton", "TED", "MasterClass"]
        all_candidates = []

        for brand in brands:
            logger.info(f"Searching Meta ads for: {brand}")
            
            # Try just the brand name first (broader search)
            term = urllib.parse.quote(brand)
            
            url = (
                f"https://graph.facebook.com/v18.0/ads_archive?"
                f"search_terms={term}&"
                "ad_reached_countries=US&"
                "ad_active_status=ACTIVE&"
                "fields=ad_creative_body,ad_snapshot_url,impressions_lower_bound&"
                "limit=50&"  # Increased limit
                f"access_token={token}"
            )
            
            try:
                logger.info(f"Requesting Meta API for: {brand}")
                resp = requests.get(url, timeout=15)
                logger.info(f"Meta API response status: {resp.status_code}")
                
                if resp.status_code != 200:
                    logger.warning(f"Meta API returned {resp.status_code} for {brand}")
                    continue
                
                data = resp.json()
                
                if "error" in data:
                    logger.error(f"Meta API error for {brand}: {data['error']}")
                    continue
                
                ads = data.get("data", [])
                logger.info(f"Found {len(ads)} ads for {brand}")
                
                # Log first few ad snippets for debugging
                for i, ad in enumerate(ads[:3]):
                    body = ad.get("ad_creative_body", "")[:100]
                    logger.info(f"  Ad {i+1}: {body}...")
                
                for ad in ads:
                    ad['source_brand'] = brand
                    all_candidates.append(ad)
                    
            except Exception as e:
                logger.error(f"Error fetching ads for {brand}: {e}")
                continue

        logger.info(f"Total Meta ad candidates found: {len(all_candidates)}")

        if not all_candidates:
            return (
                "❌ META AD LIBRARY NO RESULTS\n"
                "   → No active ads found for target brands\n"
                "   → Possible: Geographic restrictions or approval pending\n"
                "   → Alternative: Manual ad library search at facebook.com/ads/library\n"
            )

        # Less aggressive filtering
        target_ads = []
        for ad in all_candidates:
            body_text = ad.get("ad_creative_body", "")
            impressions = int(ad.get("impressions_lower_bound", 0))
            
            # Keep ads with substantial content OR high impressions
            if len(body_text) > 30 or impressions > 1000:
                target_ads.append(ad)
        
        if not target_ads:
            target_ads = all_candidates  # Fallback to all

        logger.info(f"Filtered to {len(target_ads)} relevant ads")

        # Pick highest performing ad
        try:
            top = max(target_ads, key=lambda r: int(r.get("impressions_lower_bound", 0)))
        except:
            top = target_ads[0]
        
        creative_body = html.unescape(top.get("ad_creative_body", "No body text")[:200])
        snapshot = top.get("ad_snapshot_url", "")
        impressions = top.get("impressions_lower_bound", "N/A")
        brand = top.get("source_brand", "Unknown")

        logger.info(f"Selected ad from {brand} with {impressions} impressions")

        return (
            f"🎯 PREMIUM BRAND INSPIRATION ({brand.upper()})\n"
            f"   → Impressions: {impressions:,} (lower bound)\n"
            f"   → Hook: \"{creative_body}\"\n"
            f"   → Preview: {snapshot}\n"
        )

    return safe_api_call("meta_ad", _fetch_meta_ads)

@rate_limit(delay=1.5)
def reddit_insight():
    """Enhanced Reddit search with better classification"""
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

        # More specific searches for actual Coursera success stories
        searches = [
            {
                "subreddit": "Coursera",
                "query": "got%20hired%20after|landed%20job%20coursera|career%20success%20coursera",
                "type": "testimonial",
                "min_ups": 3,
                "min_sentiment": 0.3
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "google%20certificate%20hired|coursera%20got%20job",
                "type": "testimonial", 
                "min_ups": 5,
                "min_sentiment": 0.2
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "can't%20find%20job|struggling%20entry%20level|hard%20to%20find%20work",
                "type": "pain_point",
                "min_ups": 50,  # Higher threshold for generic pain points
                "min_sentiment": -0.2
            }
        ]

        best_candidate = None
        best_score = 0

        for search in searches:
            url = (
                f"https://oauth.reddit.com/r/{search['subreddit']}/search?"
                f"q={search['query']}&restrict_sr=on&sort=top&t=month&limit=25"
            )
            
            try:
                response = requests.get(url, headers=headers, timeout=10).json()
                posts = response.get("data", {}).get("children", [])
                
                logger.info(f"Found {len(posts)} posts in r/{search['subreddit']} for {search['type']}")
                
                for post in posts:
                    data = post.get("data", {})
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")
                    ups = data.get("ups", 0)
                    
                    # Use our enhanced classification
                    actual_type, confidence = classify_reddit_content(title, selftext)
                    
                    logger.debug(f"Post '{title[:50]}...' classified as {actual_type} (confidence: {confidence})")
                    
                    # STRICT matching - only accept if classification matches AND high confidence
                    if actual_type != search["type"] or confidence < 0.7:
                        continue
                    
                    if ups < search["min_ups"]:
                        continue
                        
                    combined = title + " " + selftext
                    sentiment = analyser.polarity_scores(combined).get("compound", 0)
                    
                    if sentiment < search["min_sentiment"]:
                        continue
                    
                    # For testimonials, check if coursera is actually mentioned
                    if search["type"] == "testimonial":
                        if not any(word in combined.lower() for word in ["coursera", "google certificate", "google it"]):
                            logger.debug(f"Skipping testimonial - no Coursera mention: {title[:50]}...")
                            continue
                    
                    score = ups * confidence
                    
                    if search["type"] == "testimonial":
                        score *= 10  # Much higher weight for actual success stories
                    elif search["type"] == "pain_point":
                        score *= 3
                    
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
                "testimonial": "✅ Coursera Success Story",
                "pain_point": "❗ Career Pain Point",
                "motivation": "💡 User Question", 
                "course_rec": "📚 Course Experience"
            }
            
            type_label = type_labels.get(best_candidate["type"], "Insight")
            headline = textwrap.shorten(title, 85)
            
            logger.info(f"Selected {best_candidate['type']} from r/{best_candidate['subreddit']} with score {best_candidate['score']}")
            
            return (
                f"✅ COURSERA SUCCESS STORY (r/{best_candidate['subreddit']})\n"
                f"   → {headline}\n"
                f"   → {best_candidate['upvotes']} upvotes | Sentiment: {best_candidate['sentiment']:.2f}\n"
                f"   → Link: https://reddit.com{permalink}\n"
            )

        return None

    return safe_api_call("reddit_insight", _fetch_reddit_insights)

@rate_limit(delay=1)
def reddit_story():
    """Find ACTUAL completion stories, not questions about learning"""
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
        
        # VERY specific queries for actual completions
        queries = [
            "coursera%20completed%20specialization",
            "finished%20coursera%20course",
            "earned%20coursera%20certificate", 
            "graduated%20coursera%20program"
        ]
        
        best_post = None
        best_score = 0
        
        for query in queries:
            query_url = (
                f"https://oauth.reddit.com/r/coursera+getStudying/search"
                f"?q={query}&sort=top&restrict_sr=on&t=month&limit=20"
            )
            
            posts_response = requests.get(query_url, headers=headers, timeout=10).json()
            children = posts_response.get("data", {}).get("children", [])

            for post in children:
                data = post.get("data", {})
                title = data.get("title", "")
                selftext = data.get("selftext", "")
                ups = data.get("ups", 0)

                # Use our enhanced classification
                content_type, confidence = classify_reddit_content(title, selftext)
                
                logger.debug(f"Story candidate: '{title[:50]}...' -> {content_type} (confidence: {confidence})")
                
                # STRICT: Only accept actual course completions, not questions
                if content_type not in ["course_rec", "testimonial"] or confidence < 0.6:
                    continue
                
                # REJECT if it's clearly a question
                if title.strip().endswith("?") or any(word in title.lower() for word in ["can i", "should i", "how do", "advice"]):
                    logger.debug(f"Rejecting question: {title[:50]}...")
                    continue

                combined_text = title + " " + selftext
                sentiment = analyser.polarity_scores(combined_text).get("compound", 0)

                if ups >= 3 and sentiment > 0.1:  # Lower thresholds since we're being strict
                    score = ups * sentiment * confidence
                    
                    # Big bonus for completion words
                    completion_words = ["completed", "finished", "earned", "graduated"]
                    if any(word in combined_text.lower() for word in completion_words):
                        score *= 3
                    
                    if score > best_score:
                        best_score = score
                        best_post = data

        if best_post:
            title = best_post.get("title", "")
            permalink = best_post.get("permalink", "")
            ups = best_post.get("ups", 0)
            headline = textwrap.shorten(title, 85)
            
            return (
                f"📈 COURSE COMPLETION STORY\n"
                f"   → {headline}\n"
                f"   → {ups} upvotes | Quality Score: {best_score:.0f}\n"
                f"   → Link: https://reddit.com{permalink}\n"
            )

        return None

    return safe_api_call("reddit_story", _fetch_reddit_story)

def format_digest(blocks):
    """Format digest to look professional in both email and Slack"""
    valid_blocks = [section for section in blocks if section]
    
    if not valid_blocks:
        return None
    
    # Clean, professional formatting
    formatted_blocks = []
    for i, block in enumerate(valid_blocks):
        if i > 0:
            formatted_blocks.append("\n" + "="*60 + "\n")  # Clean separator
        formatted_blocks.append(block)
    
    return "\n".join(formatted_blocks)

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
        # Professional header
        header = f"COURSERA AD INSPIRATION DIGEST | {datetime.date.today().strftime('%B %d, %Y')}"
        separator = "="*len(header)
        
        full_msg = f"{separator}\n{header}\n{separator}\n\n{digest}\n\n{separator}\nGenerated by Swipe-File Scout"

        if send_slack(full_msg):
            logger.info("Digest sent via Slack")
        elif send_email(full_msg):
            logger.info("Digest sent via email")
        else:
            logger.error("Failed to send digest")

if __name__ == "__main__":
    main()
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

analyser = SentimentIntensityAnalyzer()

# ---------- utilities ----------
def rate_limit(delay=1):
    """Rate limiting decorator to avoid API abuse"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            time.sleep(delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def safe_api_call(func_name, api_call):
    """Wrapper for safe API calls with comprehensive error handling"""
    try:
        result = api_call()
        if result:
            logger.info(f"{func_name}: Success")
        else:
            logger.warning(f"{func_name}: No results found")
        return result
    except requests.exceptions.Timeout:
        logger.warning(f"{func_name}: API timeout")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"{func_name}: Request failed - {e}")
        return None
    except KeyError as e:
        logger.warning(f"{func_name}: Missing expected data - {e}")
        return None
    except Exception as e:
        logger.error(f"{func_name}: Unexpected error - {e}")
        return None

def classify_reddit_content(title, selftext=""):
    """
    Better classification logic for Reddit content.
    Returns tuple: (type, confidence_score)
    """
    combined = (title + " " + selftext).lower()
    
    # Clear success indicators (high confidence)
    success_keywords = [
        "got a job", "landed a job", "hired", "got hired", "career change success",
        "promotion", "promoted", "salary increase", "new position", "job offer",
        "career transition success", "breakthrough", "achievement", "accomplished",
        "completed and got", "finished and landed", "certificate helped me get"
    ]
    
    # Clear pain point indicators (high confidence)  
    pain_keywords = [
        "why is it so hard", "struggling to", "can't find", "difficulty finding",
        "impossible to", "no luck", "rejected", "unemployment", "job search struggles",
        "been applying for months", "getting discouraged", "feeling stuck",
        "can't afford", "student debt", "financial struggle"
    ]
    
    # Question/seeking advice indicators
    question_keywords = [
        "should i", "is it worth", "how to", "what do you think", "advice needed",
        "recommendations", "which course", "best way to", "help me choose"
    ]
    
    # Course discussion indicators
    course_keywords = [
        "just completed", "finished the course", "course review", "thoughts on",
        "recommend this course", "course experience", "learning from"
    ]
    
    # Check for clear success stories first
    for keyword in success_keywords:
        if keyword in combined:
            return ("testimonial", 0.9)
    
    # Check for clear pain points
    for keyword in pain_keywords:
        if keyword in combined:
            return ("pain_point", 0.9)
    
    # Check for questions/advice seeking
    for keyword in question_keywords:
        if keyword in combined:
            return ("motivation", 0.7)
    
    # Check for course discussions
    for keyword in course_keywords:
        if keyword in combined:
            return ("course_rec", 0.6)
    
    # Fallback: use title structure
    if title.endswith("?"):
        return ("motivation", 0.4)  # Likely a question
    
    if "coursera" in combined and any(word in combined for word in ["completed", "finished", "done"]):
        return ("course_rec", 0.5)
    
    return ("motivation", 0.3)  # Default fallback

# ---------- helpers ----------
@rate_limit(delay=2)
def meta_ad():
    """
    Enhanced Meta Ad search with better debugging and fallback strategies.
    """
    def _fetch_meta_ads():
        token = os.environ.get("FB_TOKEN", "").strip()
        if not token:
            logger.error("FB_TOKEN not found in environment")
            return None

        # Simplified brand list for better results
        brands = [
            "New York Times",
            "Strava", 
            "Peloton",
            "TED",
            "MasterClass",
            "Headspace",
            "Duolingo"
        ]

        all_candidates = []

        # Search each brand with multiple strategies
        for brand in brands:
            logger.info(f"Searching Meta ads for: {brand}")
            
            # Strategy 1: Brand + video
            for keyword in ["video", "course", "learn", ""]:  # Include empty for just brand name
                search_term = f"{brand} {keyword}".strip()
                term = urllib.parse.quote(search_term)
                
                url = (
                    f"https://graph.facebook.com/v18.0/ads_archive?"
                    f"search_terms={term}&"
                    "ad_reached_countries=US&"
                    "ad_active_status=ACTIVE&"
                    "fields=ad_creative_body,ad_snapshot_url,impressions_lower_bound,ad_creation_time&"
                    "limit=20&"
                    f"access_token={token}"
                )
                
                try:
                    logger.info(f"Requesting: {search_term}")
                    resp = requests.get(url, timeout=15)
                    
                    if resp.status_code != 200:
                        logger.warning(f"Meta API returned status {resp.status_code} for {search_term}")
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
            logger.warning("No Meta ads found - check FB_TOKEN and API access")
            return None

        # Less aggressive filtering - keep more candidates
        video_like_ads = []
        for ad in all_candidates:
            body_text = ad.get("ad_creative_body", "").lower()
            snapshot_url = ad.get("ad_snapshot_url", "")
            
            # Broader video/engagement indicators
            engagement_indicators = [
                "video", "watch", "stream", "play", "episode", "series", 
                "learn", "course", "lesson", "training", "tutorial",
                "join", "start", "begin", "discover", "unlock"
            ]
            
            if (any(indicator in body_text for indicator in engagement_indicators) or 
                "/video/" in snapshot_url or
                len(body_text) > 50):  # Any substantial ad copy
                video_like_ads.append(ad)

        target_ads = video_like_ads if video_like_ads else all_candidates
        
        logger.info(f"Filtered to {len(target_ads)} relevant ads")

        if not target_ads:
            return None

        # Pick highest performing ad
        try:
            top = max(target_ads, key=lambda r: int(r.get("impressions_lower_bound", 0)))
        except:
            top = target_ads[0]  # Fallback to first ad
        
        creative_body = html.unescape(top.get("ad_creative_body", "")[:150])
        snapshot = top.get("ad_snapshot_url", "")
        impressions = top.get("impressions_lower_bound", "N/A")
        brand = top.get("source_brand", "Unknown")
        search_term = top.get("search_term", "")

        logger.info(f"Selected ad from {brand} with {impressions} impressions")

        return (
            f"*🎯 Premium Brand Inspiration ({brand})*\n"
            f"• **Search term:** {search_term}\n"
            f"• **Impressions:** {impressions} (lower bound)\n"
            f"• **Hook:** {creative_body}{'...' if len(creative_body) == 150 else ''}\n"
            f"• [Watch Ad Preview]({snapshot})"
        )

    return safe_api_call("meta_ad", _fetch_meta_ads)

@rate_limit(delay=1.5)
def reddit_insight():
    """
    Enhanced Reddit search with better classification and debugging.
    """
    def _fetch_reddit_insights():
        client_id = os.environ.get("REDDIT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_SECRET", "").strip()
        if not (client_id and client_secret):
            logger.error("Reddit credentials not found")
            return None

        # OAuth token
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
            logger.error("Failed to get Reddit token")
            return None

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}

        # More targeted searches with explicit success story queries
        searches = [
            # Explicit success stories
            {
                "subreddit": "Coursera",
                "query": "got%20hired|landed%20job|career%20success|job%20offer|promotion%20after",
                "type": "testimonial",
                "min_ups": 3,
                "min_sentiment": 0.3
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "coursera%20got%20hired|coursera%20landed%20job|google%20certificate%20hired",
                "type": "testimonial", 
                "min_ups": 5,
                "min_sentiment": 0.2
            },
            {
                "subreddit": "cscareerquestions",
                "query": "coursera%20helped%20get%20job|coursera%20career%20success",
                "type": "testimonial",
                "min_ups": 8,
                "min_sentiment": 0.25
            },
            # Clear pain points
            {
                "subreddit": "ITCareerQuestions",
                "query": "can't%20find%20job|struggling%20entry%20level|hard%20to%20find",
                "type": "pain_point",
                "min_ups": 20,  # Higher threshold for pain points
                "min_sentiment": -0.3
            },
            # Course completions and positive experiences
            {
                "subreddit": "learnprogramming",
                "query": "completed%20coursera|finished%20andrew%20ng|coursera%20experience",
                "type": "course_rec",
                "min_ups": 15,
                "min_sentiment": 0.3
            }
        ]

        best_candidate = None
        best_score = 0

        # Search each target
        for search in searches:
            url = (
                f"https://oauth.reddit.com/r/{search['subreddit']}/search?"
                f"q={search['query']}&restrict_sr=on&sort=top&t=month&limit=20"
            )
            
            logger.info(f"Searching r/{search['subreddit']} for {search['type']}")
            
            try:
                response = requests.get(url, headers=headers, timeout=10).json()
                posts = response.get("data", {}).get("children", [])
                
                logger.info(f"Found {len(posts)} posts in r/{search['subreddit']}")
                
                for post in posts:
                    data = post.get("data", {})
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")
                    ups = data.get("ups", 0)
                    
                    # Use our better classification
                    actual_type, confidence = classify_reddit_content(title, selftext)
                    
                    # Skip if classification doesn't match what we're looking for
                    if actual_type != search["type"] and confidence > 0.6:
                        logger.debug(f"Skipping '{title[:50]}...' - classified as {actual_type}, looking for {search['type']}")
                        continue
                    
                    # Check minimums
                    if ups < search["min_ups"]:
                        continue
                        
                    combined = title + " " + selftext
                    sentiment = analyser.polarity_scores(combined).get("compound", 0)
                    
                    if sentiment < search["min_sentiment"]:
                        continue
                    
                    # Enhanced scoring
                    score = ups * confidence  # Weight by classification confidence
                    
                    # Type multipliers
                    if search["type"] == "testimonial":
                        score *= 5  # Highest value for actual success stories
                    elif search["type"] == "pain_point":
                        score *= 3  # High value for positioning insights
                    elif search["type"] == "course_rec":
                        score *= 2  # Good for social proof
                    
                    if score > best_score:
                        best_score = score
                        best_candidate = {
                            "data": data,
                            "type": actual_type,  # Use actual classification
                            "subreddit": search["subreddit"],
                            "sentiment": sentiment,
                            "upvotes": ups,
                            "score": score,
                            "confidence": confidence
                        }
# Format the best result
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
            
            logger.info(f"Selected {best_candidate['type']} from r/{best_candidate['subreddit']} with score {best_candidate['score']}")
            
            return (
                f"*{type_label} from r/{best_candidate['subreddit']}*\n"
                f"• **{headline}**\n"
                f"• {best_candidate['upvotes']} upvotes | "
                f"Sentiment: {best_candidate['sentiment']:.2f} | "
                f"Confidence: {best_candidate['confidence']:.1f}\n"
                f"• [Read more](https://reddit.com{permalink})"
            )

        logger.warning("No suitable Reddit content found")
        return None

    return safe_api_call("reddit_insight", _fetch_reddit_insights)

@rate_limit(delay=1)
def reddit_story():
    """
    Simplified story finder focused on actual completion stories.
    """
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
        
        # Focus on clear completion/success keywords
        query = "coursera%20completed|coursera%20finished|coursera%20graduated|earned%20certificate"
        
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

            # Use our classification to ensure it's actually a positive completion story
            content_type, confidence = classify_reddit_content(title, selftext)
            
            # Only consider if it's actually a course completion or testimonial
            if content_type not in ["course_rec", "testimonial"] or confidence < 0.5:
                continue

            combined_text = title + " " + selftext
            sentiment = analyser.polarity_scores(combined_text).get("compound", 0)

            if ups >= 5 and sentiment > 0.2:
                score = ups * sentiment * confidence
                
                # Bonus for completion words
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
                f"• {ups} upvotes | Score: {best_score:.0f}\n"
                f"• [Reddit link](https://reddit.com{permalink})"
            )

        return None

    return safe_api_call("reddit_story", _fetch_reddit_story)

def fallback_content():
    """Provide backup content when APIs fail"""
    return (
        "*🔄 Fallback Insight*\n"
        "• **Meta Ad Library may be unavailable - check FB_TOKEN**\n"
        "• **Focus on testimonial-driven video ads**\n"
        "• **Current trend: Career transformation messaging resonates strongly**"
    )

def format_digest(blocks):
    """Enhanced formatting with better structure"""
    valid_blocks = [section for section in blocks if section]
    
    if not valid_blocks:
        return None
        
    # Add section separators
    formatted_blocks = []
    for i, block in enumerate(valid_blocks):
        if i > 0:
            formatted_blocks.append("─" * 35)
        formatted_blocks.append(block)
    
    return "\n\n".join(formatted_blocks)

def send_slack(msg: str) -> bool:
    """Send message to Slack"""
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

def send_email(msg: str) -> bool:
    """Send message via email"""
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

# ---------- assemble & post ----------
def main():
    """Main execution function with better logging"""
    logger.info("Starting Swipe-File Scout...")
    
    # Gather insights
    blocks = [
        meta_ad(),
        reddit_insight(),
        reddit_story()
    ]

    # Count successful fetches
    successful_blocks = [b for b in blocks if b is not None]
    logger.info(f"Successfully fetched {len(successful_blocks)}/3 content blocks")

    # Create digest
    digest = format_digest(blocks)
    
    # Add fallback if everything failed
    if not digest:
        digest = fallback_content()
        logger.warning("Using fallback content - all APIs failed")

    # Send digest
    if digest:
        timestamp = datetime.date.today().strftime("%Y-%m-%d")
        full_msg = f"▶️ Swipe-file digest ({timestamp})\n\n" + digest

        # Try Slack first; if that fails, fall back to email
        if send_slack(full_msg):
            logger.info("Digest sent via Slack")
        elif send_email(full_msg):
            logger.info("Digest sent via email")
        else:
            logger.error("Failed to send digest via both Slack and email")
    else:
        logger.warning("No digest content generated")

# Run the main function
if __name__ == "__main__":
    main()

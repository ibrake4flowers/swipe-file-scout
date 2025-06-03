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

@rate_limit(delay=2)
def meta_ad():
    """Meta ad search - simplified"""
    def _fetch_meta_ads():
        token = os.environ.get("FB_TOKEN", "").strip()
        if not token:
            return "🔴 META ADS: FB_TOKEN missing"

        # Test token
        test_url = f"https://graph.facebook.com/v18.0/me?access_token={token}"
        try:
            test_resp = requests.get(test_url, timeout=10)
            if test_resp.status_code != 200:
                return f"🔴 META ADS: Token invalid (HTTP {test_resp.status_code})"
        except:
            return "🔴 META ADS: Connection failed"

        # Simple brand search
        brands = ["Strava", "Peloton", "MasterClass"]
        for brand in brands:
            term = urllib.parse.quote(brand)
            url = (
                f"https://graph.facebook.com/v18.0/ads_archive?"
                f"search_terms={term}&ad_reached_countries=US&ad_active_status=ACTIVE&"
                "fields=ad_creative_body,ad_snapshot_url,impressions_lower_bound&"
                f"limit=10&access_token={token}"
            )
            
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    ads = data.get("data", [])
                    if ads:
                        ad = ads[0]  # Just take the first one
                        body = html.unescape(ad.get("ad_creative_body", "")[:100])
                        impressions = ad.get("impressions_lower_bound", "Unknown")
                        return (
                            f"🎯 META AD INSPIRATION\n"
                            f"Brand: {brand}\n"
                            f"Impressions: {impressions}\n"
                            f"Hook: {body}..."
                        )
            except:
                continue
        
        return "🔴 META ADS: Pending FB approval (normal for new accounts)"

    return safe_api_call("meta_ad", _fetch_meta_ads)

@rate_limit(delay=1.5)
def reddit_audience_insights():
    """Find audience pain points, motivations, and language for ad empathy"""
    def _fetch_reddit():
        client_id = os.environ.get("REDDIT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_SECRET", "").strip()
        if not (client_id and client_secret):
            return "🔴 REDDIT: Credentials missing"

        # Get token
        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        data = {"grant_type": "client_credentials"}
        
        try:
            token_resp = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                headers={"User-Agent": "swipebot"},
                timeout=10
            ).json()
            token = token_resp.get("access_token")
            if not token:
                return "🔴 REDDIT: Token failed"
        except:
            return "🔴 REDDIT: Connection failed"

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}

        # AUDIENCE EMPATHY SUBREDDITS - where people share real struggles and wins
        target_subreddits = [
            "careerchange", "careeradvice", "ITCareerQuestions", "cscareerquestions",
            "getStudying", "selfimprovement", "digitalnomad", "marketing",
            "DataScience", "learnprogramming", "AskCareerAdvice"
        ]

        # AUDIENCE INSIGHT PATTERNS - what we want to understand about our audience
        insight_patterns = {
            "PAIN_POINTS": {
                "triggers": ["feeling stuck", "dead end", "hate my job", "burned out", "unfulfilled", 
                           "career change", "switch careers", "need advice", "lost motivation"],
                "emoji": "😤",
                "min_ups": 15
            },
            "SUCCESS_STORIES": {
                "triggers": ["landed", "got hired", "career change success", "finally did it", 
                           "best decision", "changed my life", "so grateful", "dream job"],
                "emoji": "🎉",
                "min_ups": 10
            },
            "LEARNING_MOTIVATION": {
                "triggers": ["want to learn", "should i study", "worth learning", "how to start",
                           "beginner advice", "roadmap", "skill development", "upskilling"],
                "emoji": "🧠",
                "min_ups": 8
            }
        }

        found_insights = []

        # Search each subreddit for general career/learning discussions (not just Coursera)
        for subreddit in target_subreddits:
            logger.info(f"Searching r/{subreddit} for audience insights...")
            
            # Broader search for career/learning discussions
            search_queries = [
                "career%20change%20OR%20switch%20careers%20OR%20new%20career",
                "feeling%20stuck%20OR%20dead%20end%20OR%20unfulfilled",
                "learn%20new%20skills%20OR%20upskilling%20OR%20reskilling"
            ]
            
            for query in search_queries:
                search_url = (
                    f"https://oauth.reddit.com/r/{subreddit}/search?"
                    f"q={query}&sort=hot&restrict_sr=on&t=week&limit=15"
                )
                
                try:
                    resp = requests.get(search_url, headers=headers, timeout=10).json()
                    posts = resp.get("data", {}).get("children", [])
                    
                    for post in posts:
                        data = post.get("data", {})
                        title = data.get("title", "")
                        selftext = data.get("selftext", "")
                        ups = data.get("ups", 0)
                        created = data.get("created_utc", 0)
                        
                        # Combine title and text for analysis
                        full_text = (title + " " + selftext).lower()
                        
                        # Check against each insight pattern
                        for insight_type, pattern in insight_patterns.items():
                            if ups < pattern["min_ups"]:
                                continue
                                
                            # Check if any triggers match
                            trigger_match = any(trigger in full_text for trigger in pattern["triggers"])
                            
                            if trigger_match:
                                # Extract meaningful quote from the post
                                quote = ""
                                if selftext and len(selftext) > 50:
                                    # Get first meaningful sentence
                                    sentences = selftext.split('.')
                                    for sentence in sentences[:3]:
                                        if len(sentence.strip()) > 30:
                                            quote = sentence.strip()[:200] + "..."
                                            break
                                
                                # Classify based on content analysis
                                actual_type = "LEARNING_MOTIVATION"  # Default
                                
                                # Pain point detection
                                pain_words = ["stuck", "hate", "unfulfilled", "burned out", "dead end", "miserable"]
                                if any(word in full_text for word in pain_words):
                                    actual_type = "PAIN_POINTS"
                                
                                # Success story detection  
                                success_words = ["landed", "hired", "got the job", "success", "finally", "dream job", "best decision"]
                                if any(word in full_text for word in success_words):
                                    actual_type = "SUCCESS_STORIES"
                                
                                found_insights.append({
                                    "type": actual_type,
                                    "emoji": insight_patterns[actual_type]["emoji"],
                                    "title": title,
                                    "quote": quote if quote else title,
                                    "url": "https://reddit.com" + data.get("permalink", ""),
                                    "upvotes": ups,
                                    "subreddit": subreddit,
                                    "score": ups * (3 if actual_type == "PAIN_POINTS" else 2 if actual_type == "SUCCESS_STORIES" else 1),
                                    "age_hours": (time.time() - created) / 3600
                                })
                                break  # Found a match for this post
                                
                except Exception as e:
                    logger.warning(f"Error searching r/{subreddit}: {e}")
                    continue

        # Sort by relevance and recency
        found_insights.sort(key=lambda x: x["score"] - (x["age_hours"] / 48), reverse=True)
        
        # Get diverse insights - one of each type
        final_insights = []
        used_types = set()
        
        for insight in found_insights:
            if insight["type"] not in used_types and len(final_insights) < 3:
                final_insights.append(insight)
                used_types.add(insight["type"])
        
        # Format results with quotes for ad inspiration
        if final_insights:
            formatted = []
            for insight in final_insights:
                age_str = f"{insight['age_hours']:.0f}h ago" if insight['age_hours'] < 48 else f"{insight['age_hours']/24:.0f}d ago"
                
                type_labels = {
                    "PAIN_POINTS": "AUDIENCE PAIN POINT",
                    "SUCCESS_STORIES": "SUCCESS STORY", 
                    "LEARNING_MOTIVATION": "LEARNING MOTIVATION"
                }
                
                formatted.append(
                    f"{insight['emoji']} {type_labels[insight['type']]} - r/{insight['subreddit']}\n"
                    f"   Title: {insight['title'][:70]}{'...' if len(insight['title']) > 70 else ''}\n"
                    f"   Quote: \"{insight['quote'][:150]}{'...' if len(insight['quote']) > 150 else ''}\"\n"
                    f"   {insight['upvotes']} upvotes | Posted {age_str}\n"
                    f"   {insight['url']}"
                )
            
            return "\n\n".join(formatted)
        
        logger.info(f"Searched {len(target_subreddits)} subreddits for audience insights")
        return "🔴 REDDIT: No audience insights found in target subreddits this week"

    return safe_api_call("reddit_audience_insights", _fetch_reddit)

def send_slack(msg):
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

def send_email(msg):
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
        email_msg["Subject"] = f"Coursera Ad Digest - {datetime.date.today()}"
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
    
    # Get content
    meta_content = meta_ad()
    reddit_content = reddit_audience_insights()  # Updated function name
    
    # Build digest
    sections = []
    if meta_content:
        sections.append(meta_content)
    if reddit_content:
        sections.append(reddit_content)
    
    if not sections:
        sections.append("🔴 ALL APIS FAILED - Check credentials")
    
    # Simple, clean formatting for Slack
    digest = "\n\n" + "="*50 + "\n\n".join([""] + sections) + "\n\n" + "="*50
    
    # Send
    timestamp = datetime.date.today().strftime('%B %d, %Y')
    full_msg = f"COURSERA AD DIGEST | {timestamp}" + digest
    
    # Try Slack first, then email
    if send_slack(full_msg):
        logger.info("Digest sent via Slack")
    elif send_email(full_msg):
        logger.info("Digest sent via email")
    else:
        logger.error("Failed to send digest")
    
    # Also print to console for debugging
    print(full_msg)

if __name__ == "__main__":
    main()
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
def reddit_insights():
    """Smart Reddit search across top subreddits for different story types"""
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

        # TOP SUBREDDITS for our core domains: business, tech, data, creative, AI/ML, high-income skills
        target_subreddits = [
            # Core Coursera community
            "Coursera",
            
            # Technology & Career Development
            "ITCareerQuestions", 
            "cscareerquestions",
            "learnprogramming",
            "webdev",
            
            # Data Science & Analytics
            "DataScience",
            "analytics", 
            "MachineLearning",
            
            # Business & Professional Skills
            "careeradvice",
            "careerchange", 
            "digitalnomad",
            "marketing",
            
            # Creative & Design
            "graphic_design",
            "userexperience",
            
            # Learning & Skill Development
            "getStudying",
            "selfimprovement",
            "AskCareerAdvice"
        ]

        # STORY TYPES we're looking for with their patterns
        story_patterns = {
            "SUCCESS_STORY": {
                "keywords": ["got job", "got hired", "landed job", "career success", "promotion", "job offer"],
                "emoji": "✅",
                "min_ups": 10
            },
            "PAIN_POINT": {
                "keywords": ["why is it so hard", "can't find", "struggling to", "no luck", "rejected", "difficult to get"],
                "emoji": "❗",
                "min_ups": 25
            },
            "COURSE_COMPLETION": {
                "keywords": ["completed coursera", "finished coursera", "earned certificate", "graduated from"],
                "emoji": "📚",
                "min_ups": 5
            },
            "ADVICE_SEEKING": {
                "keywords": ["should i take", "is coursera worth", "which course", "recommendations"],
                "emoji": "💡",
                "min_ups": 8
            }
        }

        found_stories = []

        # Search each subreddit
        for subreddit in target_subreddits:
            logger.info(f"Searching r/{subreddit}...")
            
            # Search for coursera mentions in the last week
            search_url = (
                f"https://oauth.reddit.com/r/{subreddit}/search?"
                "q=coursera&sort=new&restrict_sr=on&t=week&limit=25"
            )
            
            try:
                resp = requests.get(search_url, headers=headers, timeout=10).json()
                posts = resp.get("data", {}).get("children", [])
                
                logger.info(f"  Found {len(posts)} coursera posts")
                
                for post in posts:
                    data = post.get("data", {})
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")
                    ups = data.get("ups", 0)
                    created = data.get("created_utc", 0)
                    
                    # Combine title and text for analysis
                    full_text = (title + " " + selftext).lower()
                    
                    # Check against each story pattern
                    for story_type, pattern in story_patterns.items():
                        # Must have minimum upvotes
                        if ups < pattern["min_ups"]:
                            continue
                            
                        # Check if any keywords match
                        keyword_match = any(keyword in full_text for keyword in pattern["keywords"])
                        
                        if keyword_match:
                            # Additional logic for different story types
                            if story_type == "SUCCESS_STORY":
                                # Must mention coursera AND success
                                if "coursera" in full_text and any(term in full_text for term in ["job", "hired", "career", "promotion"]):
                                    found_stories.append({
                                        "type": f"{pattern['emoji']} {story_type.replace('_', ' ')}",
                                        "title": title,
                                        "url": "https://reddit.com" + data.get("permalink", ""),
                                        "upvotes": ups,
                                        "subreddit": subreddit,
                                        "score": ups * 3,  # Higher weight for success stories
                                        "age_hours": (time.time() - created) / 3600
                                    })
                            
                            elif story_type == "PAIN_POINT":
                                # Must be a question or complaint
                                if title.endswith("?") or any(word in full_text for word in ["why", "how", "struggling"]):
                                    found_stories.append({
                                        "type": f"{pattern['emoji']} {story_type.replace('_', ' ')}",
                                        "title": title,
                                        "url": "https://reddit.com" + data.get("permalink", ""),
                                        "upvotes": ups,
                                        "subreddit": subreddit,
                                        "score": ups * 2,  # Good for understanding pain points
                                        "age_hours": (time.time() - created) / 3600
                                    })
                            
                            elif story_type == "COURSE_COMPLETION":
                                # Must NOT be a question, must show completion
                                if not title.endswith("?") and any(word in full_text for word in ["completed", "finished", "done"]):
                                    found_stories.append({
                                        "type": f"{pattern['emoji']} {story_type.replace('_', ' ')}",
                                        "title": title,
                                        "url": "https://reddit.com" + data.get("permalink", ""),
                                        "upvotes": ups,
                                        "subreddit": subreddit,
                                        "score": ups * 1.5,  # Social proof value
                                        "age_hours": (time.time() - created) / 3600
                                    })
                            
                            elif story_type == "ADVICE_SEEKING":
                                # Must be a question
                                if title.endswith("?"):
                                    found_stories.append({
                                        "type": f"{pattern['emoji']} {story_type.replace('_', ' ')}",
                                        "title": title,
                                        "url": "https://reddit.com" + data.get("permalink", ""),
                                        "upvotes": ups,
                                        "subreddit": subreddit,
                                        "score": ups * 1,  # Lower priority
                                        "age_hours": (time.time() - created) / 3600
                                    })
                            
                            break  # Found a match, don't double-count
                            
            except Exception as e:
                logger.warning(f"Error searching r/{subreddit}: {e}")
                continue

        # Sort by score (upvotes * type multiplier) and recency
        found_stories.sort(key=lambda x: x["score"] - (x["age_hours"] / 24), reverse=True)
        
        # Take top 3 different types
        final_stories = []
        used_types = set()
        
        for story in found_stories:
            story_type = story["type"].split()[1]  # Get type without emoji
            if story_type not in used_types and len(final_stories) < 3:
                final_stories.append(story)
                used_types.add(story_type)
        
        # Format results
        if final_stories:
            formatted = []
            for story in final_stories:
                age_str = f"{story['age_hours']:.0f}h ago" if story['age_hours'] < 48 else f"{story['age_hours']/24:.0f}d ago"
                formatted.append(
                    f"{story['type']} - r/{story['subreddit']}\n"
                    f"   {story['title'][:80]}{'...' if len(story['title']) > 80 else ''}\n"
                    f"   {story['upvotes']} upvotes | Posted {age_str}\n"
                    f"   {story['url']}"
                )
            
            return "\n\n".join(formatted)
        
        logger.info(f"Searched {len(target_subreddits)} subreddits, found {len(found_stories)} total stories")
        return "🔴 REDDIT: No relevant Coursera discussions found in target subreddits this week"

    return safe_api_call("reddit_insights", _fetch_reddit)

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
    reddit_content = reddit_insights()
    
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
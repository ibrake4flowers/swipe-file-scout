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
        return api_call()
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

def validate_env_vars():
    """Check required environment variables"""
    required_vars = {
        'FB_TOKEN': 'Meta Ad Library access',
        'REDDIT_ID': 'Reddit API access', 
        'REDDIT_SECRET': 'Reddit API access'
    }
    
    missing = []
    for var, purpose in required_vars.items():
        if not os.getenv(var):
            missing.append(f"{var} ({purpose})")
    
    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
        return False
    return True

# ---------- helpers ----------
@rate_limit(delay=2)
def meta_ad():
    """
    Fetch a top‐performing video promo from premium brands that require investment
    but unlock transformation (knowledge, health, skills, etc.). Focus on best-in-class
    examples rather than direct education competitors.
    """
    # Premium brands that require investment but unlock transformation
    # These represent best-in-class marketing for "investment → transformation"
    brands = [
        "New York Times",      # Knowledge/awareness investment
        "Strava",             # Health/fitness progress investment  
        "Peloton",            # Health transformation investment
        "TED",                # Learning/inspiration investment
        "MasterClass",        # Skill/expertise investment (but premium positioning)
        "Headspace",          # Mental wellness investment
        "Duolingo",           # Language learning investment
        "Adobe Creative",     # Creative skills investment
        "Spotify Premium",    # Enhanced experience investment
        "Netflix",            # Entertainment/content investment
        "Apple Fitness",      # Health ecosystem investment
        "LinkedIn Premium"    # Career advancement investment
    ]

    def _fetch_meta_ads():
        token = os.environ.get("FB_TOKEN", "").strip()
        if not token:
            return None

        all_candidates = []

        # Search each brand + "video" for video-first campaigns
        for brand in brands:
            term = urllib.parse.quote(f"{brand} video")
            url = (
                f"https://graph.facebook.com/v18.0/ads_archive?"
                f"search_terms={term}"
                "&ad_reached_countries=US&"
                "ad_active_status=ACTIVE&"
                "fields=ad_creative_body,ad_snapshot_url,impressions_lower_bound,ad_creation_time"
                f"&access_token={token}"
            )
            
            resp = requests.get(url, timeout=10).json()
            data = resp.get("data", [])
            
            for ad in data:
                ad['source_brand'] = brand  # Track which brand this came from
                all_candidates.append(ad)

        if not all_candidates:
            return None

        # Filter for video-like content
        video_like_ads = []
        for ad in all_candidates:
            body_text = ad.get("ad_creative_body", "").lower()
            snapshot_url = ad.get("ad_snapshot_url", "")
            
            # Enhanced video detection
            video_indicators = ["video", "watch", "stream", "play", "episode", "series"]
            if any(indicator in body_text for indicator in video_indicators) or "/video/" in snapshot_url:
                video_like_ads.append(ad)

        target_ads = video_like_ads if video_like_ads else all_candidates
        
        if not target_ads:
            return None

        # Pick highest performing ad
        top = max(target_ads, key=lambda r: int(r.get("impressions_lower_bound", 0)))
        
        creative_body = html.unescape(top.get("ad_creative_body", "")[:120])
        snapshot = top.get("ad_snapshot_url", "")
        impressions = top.get("impressions_lower_bound", "N/A")
        brand = top.get("source_brand", "Unknown")

        return (
            f"*🎯 Premium Brand Inspiration ({brand})*\n"
            f"• **Impressions (lower bound):** {impressions:,}\n"
            f"• **Hook (first 120 chars):** {creative_body}…\n"
            f"• [Watch Ad Preview]({snapshot})"
        )

    return safe_api_call("meta_ad", _fetch_meta_ads)

@rate_limit(delay=1.5)
def reddit_insight():
    """
    Enhanced Reddit search for Coursera ad inspiration across multiple subreddits.
    Finds testimonials, pain points, and motivations with smart scoring.
    """
    def _fetch_reddit_insights():
        client_id = os.environ.get("REDDIT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_SECRET", "").strip()
        if not (client_id and client_secret):
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
            return None

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}

        # Define targeted searches across key subreddits
        searches = [
            # High-value testimonials
            {
                "subreddit": "Coursera",
                "query": "got%20a%20job|landed%20a%20job|career%20change%20success|hired%20after|promotion",
                "type": "testimonial",
                "min_ups": 3,
                "min_sentiment": 0.3
            },
            {
                "subreddit": "ITCareerQuestions",
                "query": "coursera%20google%20it|coursera%20certificate%20job|google%20it%20support|coursera%20hired",
                "type": "testimonial", 
                "min_ups": 5,
                "min_sentiment": 0.2
            },
            {
                "subreddit": "cscareerquestions",
                "query": "coursera%20helped|coursera%20certificate%20hired|coursera%20career",
                "type": "testimonial",
                "min_ups": 8,
                "min_sentiment": 0.25
            },
            # Pain points & motivations
            {
                "subreddit": "careerchange",
                "query": "coursera%20worth|online%20learning%20career|need%20new%20skills|career%20transition",
                "type": "motivation",
                "min_ups": 6,
                "min_sentiment": 0.1
            },
            {
                "subreddit": "StudentLoans", 
                "query": "coursera%20alternative|can't%20afford%20college|online%20degree|cheaper%20education",
                "type": "pain_point",
                "min_ups": 5,
                "min_sentiment": -0.5  # Pain points can be negative
            },
            {
                "subreddit": "jobs",
                "query": "coursera%20certification|upskill%20career|need%20skills|online%20course",
                "type": "motivation",
                "min_ups": 10,
                "min_sentiment": 0.0
            },
            # Course discussions
            {
                "subreddit": "learnprogramming",
                "query": "coursera%20machine%20learning|andrew%20ng|coursera%20programming|coursera%20python",
                "type": "course_rec",
                "min_ups": 12,
                "min_sentiment": 0.2
            },
            {
                "subreddit": "DataScience",
                "query": "coursera%20data%20science|coursera%20specialization|best%20coursera",
                "type": "course_rec",
                "min_ups": 15,
                "min_sentiment": 0.15
            },
            {
                "subreddit": "getStudying",
                "query": "learning%20how%20to%20learn|coursera%20study|productivity%20course",
                "type": "course_rec",
                "min_ups": 8,
                "min_sentiment": 0.2
            }
        ]

        best_candidate = None
        best_score = 0

        # Search each target
        for search in searches:
            url = (
                f"https://oauth.reddit.com/r/{search['subreddit']}/search?"
                f"q={search['query']}&restrict_sr=on&sort=top&t=month&limit=15"
            )
            
            response = requests.get(url, headers=headers, timeout=10).json()
            posts = response.get("data", {}).get("children", [])
            
            for post in posts:
                data = post.get("data", {})
                title = data.get("title", "")
                selftext = data.get("selftext", "")
                ups = data.get("ups", 0)
                
                # Check minimums
                if ups < search["min_ups"]:
                    continue
                    
                combined = title + " " + selftext
                sentiment = analyser.polarity_scores(combined).get("compound", 0)
                
                if sentiment < search["min_sentiment"]:
                    continue
                
                # Enhanced scoring algorithm
                score = ups
                
                # Type multipliers
                if search["type"] == "testimonial":
                    score *= 3  # Highest value for success stories
                elif search["type"] == "pain_point":
                    score *= 2.5  # High value for positioning insights
                elif search["type"] == "motivation":
                    score *= 2  # Good for understanding user intent
                
                # Sentiment bonuses
                if sentiment > 0.5:  # Very positive
                    score *= 1.8
                elif sentiment > 0.3:  # Positive
                    score *= 1.4
                    
                # Content depth bonus
                if len(combined) > 500:  # Very detailed posts
                    score *= 1.5
                elif len(combined) > 200:  # Decent detail
                    score *= 1.2
                
                # Recency bonus (fresher insights)
                created_utc = data.get("created_utc", 0)
                days_old = (time.time() - created_utc) / 86400
                if days_old < 7:  # Less than a week old
                    score *= 1.3
                elif days_old < 30:  # Less than a month old
                    score *= 1.1
                
                if score > best_score:
                    best_score = score
                    best_candidate = {
                        "data": data,
                        "type": search["type"],
                        "subreddit": search["subreddit"],
                        "sentiment": sentiment,
                        "upvotes": ups,
                        "score": score
                    }

        # Format the best result
        if best_candidate:
            data = best_candidate["data"]
            title = data.get("title", "")
            permalink = data.get("permalink", "")
            
            type_labels = {
                "testimonial": "✅ Success Story",
                "pain_point": "❗ Pain Point",
                "motivation": "💡 Motivation", 
                "course_rec": "📚 Course Discussion"
            }
            
            type_label = type_labels.get(best_candidate["type"], "Insight")
            headline = textwrap.shorten(title, 95)
            
            return (
                f"*{type_label} from r/{best_candidate['subreddit']}*\n"
                f"• **{headline}**\n"
                f"• {best_candidate['upvotes']} upvotes | "
                f"Sentiment: {best_candidate['sentiment']:.2f} | "
                f"Score: {best_candidate['score']:.0f}\n"
                f"• [Read more](https://reddit.com{permalink})"
            )

        return None

    return safe_api_call("reddit_insight", _fetch_reddit_insights)

@rate_limit(delay=1)
def reddit_story():
    """
    Fetch a highly upvoted, positive Coursera 'completed' post from Reddit.
    Enhanced to find the most compelling completion stories.
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
        
        # Enhanced search queries for completion stories
        queries = [
            "coursera%20completed%20OR%20finished%20OR%20graduated",
            "coursera%20certificate%20earned%20OR%20received",
            "coursera%20specialization%20done%20OR%20completed"
        ]
        
        best_post = None
        best_score = 0
        
        for query in queries:
            query_url = (
                f"https://oauth.reddit.com/r/coursera+learnprogramming+getStudying/search"
                f"?q={query}&sort=top&restrict_sr=on&t=month&limit=25"
            )
            posts_response = requests.get(query_url, headers=headers, timeout=10).json()
            children = posts_response.get("data", {}).get("children", [])

            for post in children:
                data = post.get("data", {})
                title = data.get("title", "")
                selftext = data.get("selftext", "")
                ups = data.get("ups", 0)

                combined_text = title + " " + selftext
                sentiment = analyser.polarity_scores(combined_text).get("compound", 0)

                # Enhanced scoring for completion stories
                if ups >= 8 and sentiment > 0.3:
                    score = ups * sentiment
                    
                    # Bonus for detailed stories
                    if len(combined_text) > 300:
                        score *= 1.5
                    
                    # Bonus for transformation keywords
                    transformation_words = ["job", "career", "hired", "promotion", "learned", "changed"]
                    if any(word in combined_text.lower() for word in transformation_words):
                        score *= 1.8
                    
                    if score > best_score:
                        best_score = score
                        best_post = data

        if best_post:
            title = best_post.get("title", "")
            permalink = best_post.get("permalink", "")
            ups = best_post.get("ups", 0)
            headline = textwrap.shorten(title, 95)
            
            return (
                f"*📈 Learner Success Story*\n"
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
        "• **Trending: Coursera Plus annual discount discussions**\n"
        "• Focus on ROI messaging and career transformation stories\n"
        "• Consider testimonial-based video ads featuring real student outcomes"
    )

def deduplicate_content(digest):
    """Remove similar content to avoid repetitive insights"""
    if not digest:
        return digest
        
    lines = digest.split('\n')
    unique_lines = []
    seen_headlines = set()
    
    for line in lines:
        if '**' in line and line.count('**') >= 2:  # Headline
            # Extract text between ** markers
            start = line.find('**') + 2
            end = line.find('**', start)
            if end > start:
                headline_clean = line[start:end].lower().strip()
                if headline_clean not in seen_headlines:
                    seen_headlines.add(headline_clean)
                    unique_lines.append(line)
                else:
                    continue  # Skip duplicate headline
            else:
                unique_lines.append(line)
        else:
            unique_lines.append(line)
    
    return '\n'.join(unique_lines)

def format_digest(blocks):
    """Enhanced formatting with better structure"""
    valid_blocks = [section for section in blocks if section]
    
    if not valid_blocks:
        return None
        
    # Add section separators
    formatted_blocks = []
    for i, block in enumerate(valid_blocks):
        if i > 0:
            formatted_blocks.append("─" * 35)  # Separator line
        formatted_blocks.append(block)
    
    return "\n\n".join(formatted_blocks)

# ---------- assemble & post ----------
def main():
    """Main execution function"""
    # Validate environment
    if not validate_env_vars():
        logger.error("Critical environment variables missing")
    
    # Gather insights
    blocks = [
        meta_ad(),
        reddit_insight(),
        reddit_story()
    ]

    # Create digest
    digest = format_digest(blocks)
    
    # Add fallback if everything failed
    if not digest:
        digest = fallback_content()
    else:
        digest = deduplicate_content(digest)

    # Send digest
    if digest:
        timestamp = datetime.date.today().strftime("%Y-%m-%d")
        full_msg = f"▶️ Swipe-file digest ({timestamp})\n\n" + digest

        # Try Slack first; if that fails, fall back to email
        if not send_slack(full_msg):
            send_email(full_msg)
            
        logger.info("Digest sent successfully")
    else:
        logger.warning("No digest content generated")

# ---------- helpers to send ----------
def send_slack(msg: str) -> bool:
    """
    Attempt to send the message to Slack via the SLACK_WEBHOOK URL.
    Returns True if SLACK_WEBHOOK is set and the POST is attempted.
    """
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
    """
    Send the message via Gmail SMTP using EMAIL_FROM, EMAIL_PW, EMAIL_TO.
    Returns True if all three environment variables are set and send succeeds.
    """
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

# Run the main function
if __name__ == "__main__":
    main()
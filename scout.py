import os
import json
import textwrap
import requests
import datetime
import html
import urllib.parse
import time
import logging
import hashlib
from functools import wraps
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
analyser = SentimentIntensityAnalyzer()

# File to store previously shared post IDs
SHARED_POSTS_FILE = "shared_posts.json"

def load_shared_posts():
    """Load previously shared post IDs from file"""
    try:
        if os.path.exists(SHARED_POSTS_FILE):
            with open(SHARED_POSTS_FILE, 'r') as f:
                data = json.load(f)
                # Clean up old entries (older than 30 days)
                cutoff_time = time.time() - (30 * 24 * 60 * 60)
                cleaned_data = {k: v for k, v in data.items() if v > cutoff_time}
                return cleaned_data
        return {}
    except Exception as e:
        logger.warning(f"Could not load shared posts file: {e}")
        return {}

def save_shared_posts(shared_posts):
    """Save shared post IDs to file"""
    try:
        with open(SHARED_POSTS_FILE, 'w') as f:
            json.dump(shared_posts, f)
    except Exception as e:
        logger.error(f"Could not save shared posts file: {e}")

def create_post_id(post_data):
    """Create a unique ID for a post based on Reddit ID and URL"""
    reddit_id = post_data.get("id", "")
    permalink = post_data.get("permalink", "")
    
    # Always use Reddit ID as primary identifier
    if reddit_id:
        return f"reddit_{reddit_id}"
    elif permalink:
        # Extract ID from permalink as fallback
        permalink_parts = permalink.split('/')
        if len(permalink_parts) > 4:
            return f"reddit_{permalink_parts[4]}"
    
    # Last resort: hash title + created time
    title = post_data.get("title", "")
    created = post_data.get("created_utc", 0)
    content = f"{title}_{created}"
    return f"hash_{hashlib.md5(content.encode()).hexdigest()[:12]}"

def is_post_already_shared(post_id, shared_posts):
    """Check if a post has been shared before"""
    return post_id in shared_posts

def mark_post_as_shared(post_id, shared_posts):
    """Mark a post as shared with current timestamp"""
    shared_posts[post_id] = time.time()

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

@rate_limit(delay=1)
def reddit_coursera_insights():
    """Find Coursera-specific audience insights: pain points, successes, and motivations"""
    def _fetch_reddit():
        # Load previously shared posts
        shared_posts = load_shared_posts()
        logger.info(f"Loaded {len(shared_posts)} previously shared posts")
        
        client_id = os.environ.get("REDDIT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_SECRET", "").strip()
        if not (client_id and client_secret):
            return "🔴 *REDDIT*: Credentials missing"

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
                return "🔴 *REDDIT*: Token failed"
        except:
            return "🔴 *REDDIT*: Connection failed"

        headers = {"Authorization": f"bearer {token}", "User-Agent": "swipebot"}

        # STREAMLINED SUBREDDITS - focus on the best ones only
        target_subreddits = [
            "Coursera", "ITCareerQuestions", "careerchange", 
            "learnprogramming", "DataScience"
        ]

        # COURSERA-SPECIFIC INSIGHT PATTERNS - HIGHER UPVOTE THRESHOLDS
        insight_patterns = {
            "COURSERA_PROGRESS": {
                "coursera_terms": ["coursera", "google certificate", "google it support", "ibm certificate", "andrew ng"],
                "progress_terms": ["started", "taking", "enrolled in", "working on", "just began", "signed up", "trying out"],
                "emoji": "📈",
                "min_ups": 15
            },
            "COURSERA_DOUBTS": {
                "coursera_terms": ["coursera", "online course", "certificate", "mooc"],
                "doubt_terms": ["worth it", "waste of time", "legitimate", "employers recognize", "actually help", "does it count"],
                "emoji": "🤔",
                "min_ups": 20
            },
            "COURSERA_STRUGGLES": {
                "coursera_terms": ["coursera", "online learning", "certificate program"],
                "struggle_terms": ["struggling with", "hard to", "difficult", "overwhelmed", "stuck", "motivation", "pissed off", "frustrated"],
                "emoji": "😰",
                "min_ups": 25  # Higher for struggles since they get more engagement
            },
            "COURSERA_RECOMMENDATIONS": {
                "coursera_terms": ["coursera", "course recommendation", "which course", "best course"],
                "rec_terms": ["recommend", "suggest", "best for", "should i take", "worth taking", "good learning platforms"],
                "emoji": "💡",
                "min_ups": 20
            }
        }

        found_insights = []
        new_posts_found = 0
        duplicate_posts_skipped = 0

        # Search each subreddit specifically for Coursera discussions
        for subreddit in target_subreddits:
            logger.info(f"Searching r/{subreddit} for Coursera insights...")
            
            # Search for Coursera mentions - SMART search with OR queries but optimized
            search_url = (
                f"https://oauth.reddit.com/r/{subreddit}/search?"
                "q=coursera%20OR%20%22google%20certificate%22%20OR%20%22online%20course%22&"
                "sort=hot&restrict_sr=on&t=week&limit=15"
            )
            
            try:
                resp = requests.get(search_url, headers=headers, timeout=5).json()
                posts = resp.get("data", {}).get("children", [])
                
                logger.info(f"  Found {len(posts)} posts (processing up to 10)")
                
                # Process only first 10 posts for speed
                posts = posts[:10]
                
                for post in posts:
                    data = post.get("data", {})
                    
                    # Check if we've already shared this post
                    post_id = create_post_id(data)
                    if is_post_already_shared(post_id, shared_posts):
                        duplicate_posts_skipped += 1
                        logger.info(f"  Skipping duplicate post ID {post_id}: {data.get('title', '')[:50]}...")
                        continue
                    
                    title = data.get("title", "")
                    selftext = data.get("selftext", "")
                    ups = data.get("ups", 0)
                    created = data.get("created_utc", 0)
                    
                    # Combine title and text for analysis
                    full_text = (title + " " + selftext).lower()
                    
                    # Must mention Coursera or related terms (faster check)
                    mentions_coursera = any(term in full_text for term in [
                        "coursera", "google certificate", "google it", "online course"
                    ])
                    
                    if not mentions_coursera:
                        continue
                    
                    # Better classification based on actual content
                    title_lower = title.lower()
                    full_text_lower = full_text.lower()
                    
                    # EXPLICIT pain point detection first
                    pain_indicators = [
                        "depressed", "burned out", "burnout", "feeling stuck", "done with", 
                        "hate my job", "miserable", "trapped", "dead end", "fucked up"
                    ]
                    
                    # EXPLICIT progress indicators
                    progress_indicators = [
                        "just started", "enrolled in", "signed up for", "taking coursera",
                        "working through", "half way through", "making progress on"
                    ]
                    
                    # EXPLICIT doubt indicators  
                    doubt_indicators = [
                        "worth it", "waste of time", "do employers", "actually help",
                        "legitimate", "recognized", "does it count"
                    ]
                    
                    # Classify based on actual content, not pattern matching
                    actual_type = None
                    
                    # Check for pain points first (strongest signal)
                    if any(indicator in full_text_lower for indicator in pain_indicators):
                        actual_type = "COURSERA_STRUGGLES"
                    
                    # Check for explicit progress
                    elif any(indicator in full_text_lower for indicator in progress_indicators):
                        actual_type = "COURSERA_PROGRESS"
                    
                    # Check for doubts/questions
                    elif any(indicator in full_text_lower for indicator in doubt_indicators):
                        actual_type = "COURSERA_DOUBTS"
                    
                    # Check for seeking recommendations
                    elif title.endswith("?") and any(word in title_lower for word in ["which", "best", "recommend", "should i"]):
                        actual_type = "COURSERA_RECOMMENDATIONS"
                    
                    # Skip if we can't classify properly
                    if not actual_type:
                        continue
                    
                    # Must also meet the pattern requirements
                    pattern = insight_patterns[actual_type]
                    if ups < pattern["min_ups"]:
                        logger.info(f"  Skipping '{title[:50]}...' - only {ups} upvotes (need {pattern['min_ups']})")
                        continue
                    
                    # Must mention both Coursera terms AND have pattern terms
                    has_coursera_term = any(term in full_text for term in pattern["coursera_terms"])
                    has_pattern_term = any(term in full_text for term in pattern.get("progress_terms", []) + 
                                                                            pattern.get("doubt_terms", []) + 
                                                                            pattern.get("struggle_terms", []) + 
                                                                            pattern.get("rec_terms", []))
                    
                    # REQUIRE Coursera mention for relevance
                    if not has_coursera_term:
                        logger.info(f"  Skipping '{title[:50]}...' - no Coursera mention")
                        continue
                    
                    # Extract meaningful quote (faster processing)
                    quote = ""
                    if selftext and len(selftext) > 100:
                        # Quick quote extraction - just first good sentence
                        sentences = selftext.split('.')[:3]
                        for sentence in sentences:
                            if len(sentence.strip()) > 50:
                                quote = sentence.strip()[:250]
                                break
                    
                    # Use title if no good quote found
                    if not quote:
                        quote = title[:150]
                    
                    # This is a new post that meets our criteria - mark it as shared
                    mark_post_as_shared(post_id, shared_posts)
                    new_posts_found += 1
                    logger.info(f"  ✅ Added new post ID {post_id}: {title[:50]}... ({ups} upvotes)")
                    
                    found_insights.append({
                        "type": actual_type,  # Use our better classification
                        "emoji": insight_patterns[actual_type]["emoji"],
                        "title": title,
                        "quote": quote,
                        "url": "https://reddit.com" + data.get("permalink", ""),
                        "upvotes": ups,
                        "subreddit": subreddit,
                        "score": ups * (3 if "STRUGGLES" in actual_type else 2 if "DOUBTS" in actual_type else 1),
                        "age_days": (time.time() - created) / 86400,
                        "post_id": post_id
                    })
                    break  # Found a match, move to next post
                            
            except Exception as e:
                logger.warning(f"Error searching r/{subreddit}: {e}")
                continue

        # Save updated shared posts file
        save_shared_posts(shared_posts)
        
        logger.info(f"Found {new_posts_found} new posts, skipped {duplicate_posts_skipped} duplicates")

        # Sort by relevance (score) and recency
        found_insights.sort(key=lambda x: x["score"] - (x["age_days"] / 7), reverse=True)
        
        # Take top 5 different types for better variety, but ensure high quality
        final_insights = []
        used_types = set()
        
        for insight in found_insights:
            # Only include posts with significant engagement
            if insight["upvotes"] >= 15 and len(final_insights) < 5:
                if insight["type"] not in used_types or len(final_insights) < 3:
                    final_insights.append(insight)
                    used_types.add(insight["type"])
        
        # Format results with Coursera context
        if final_insights:
            formatted = []
            for insight in final_insights:
                age_str = f"{insight['age_days']:.0f}d ago" if insight['age_days'] >= 1 else "today"
                
                type_labels = {
                    "COURSERA_PROGRESS": "MAKING PROGRESS",
                    "COURSERA_DOUBTS": "COURSERA SKEPTICISM", 
                    "COURSERA_STRUGGLES": "LEARNING CHALLENGES",
                    "COURSERA_RECOMMENDATIONS": "COURSE SEEKING"
                }
                
                formatted.append(
                    f"{insight['emoji']} *{type_labels[insight['type']]}* • r/{insight['subreddit']}\n"
                    f"*{insight['title'][:70]}{'...' if len(insight['title']) > 70 else ''}*\n"
                    f"_{insight['quote'][:180]}{'...' if len(insight['quote']) > 180 else ''}_\n"
                    f"👍 {insight['upvotes']} upvotes • {age_str}\n"
                    f"🔗 {insight['url']}\n"
                )
            
            # Add stats about new vs duplicate posts
            stats_msg = f"\n📊 *Stats:* {new_posts_found} new posts found, {duplicate_posts_skipped} duplicates skipped"
            return "\n\n".join(formatted) + stats_msg
        
        logger.info(f"Searched {len(target_subreddits)} subreddits for Coursera insights")
        if new_posts_found == 0 and duplicate_posts_skipped > 0:
            return f"🔴 *REDDIT*: No new Coursera posts found ({duplicate_posts_skipped} duplicates skipped)"
        else:
            return "🔴 *REDDIT*: No Coursera-specific discussions found in target subreddits"

    return safe_api_call("reddit_coursera_insights", _fetch_reddit)

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
    
    # Get content - SIMPLIFIED to avoid function name issues
    reddit_content = reddit_coursera_insights()
    
    # Build digest - focus on Reddit insights only for now
    if reddit_content:
        digest = reddit_content
    else:
        digest = "🔴 *NO INSIGHTS FOUND* - Check Reddit credentials"
    
    # Send
    timestamp = datetime.date.today().strftime('%B %d, %Y')
    header = f"📊 *COURSERA AD DIGEST* | {timestamp}"
    footer = "─" * 30 + "\n_Generated by Swipe-File Scout_"
    
    full_msg = f"{header}\n\n{digest}\n\n{footer}"
    
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
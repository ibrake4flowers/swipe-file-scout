import os
import json
import textwrap
import requests
import datetime
import html
import urllib.parse
import time
import logging
import random
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

@rate_limit(delay=1)
def alternative_ad_inspiration():
    """Find inspiring ads from alternative sources while waiting for Meta approval"""
    def _fetch_alternative_ads():
        
        # Curated list of inspiring ad concepts (fallback)
        inspiring_concepts = [
            {
                "concept": "Transformation Storytelling",
                "description": "Before/after narratives showing career transformation",
                "example": "Person stuck in dead-end job → thriving in new career after online learning",
                "why": "Mirrors your Reddit insights about people feeling stuck"
            },
            {
                "concept": "Expert Social Proof", 
                "description": "Featuring recognizable instructors and university partnerships",
                "example": "Learn from Stanford professors and Google engineers",
                "why": "Leverages Coursera's unique partnerships vs competitors"
            },
            {
                "concept": "Micro-Learning Moments",
                "description": "Show bite-sized learning fitting into busy lives", 
                "example": "15 minutes during lunch break = new skill building",
                "why": "Addresses time constraints barrier from your Reddit research"
            },
            {
                "concept": "Peer Success Stories",
                "description": "Real student testimonials in authentic settings",
                "example": "Recent graduate explaining career change in their new office",
                "why": "Builds on the success stories you're finding in Reddit"
            },
            {
                "concept": "Skills Gap Messaging",
                "description": "Address the disconnect between current skills and dream job",
                "example": "Bridge the gap between where you are and where you want to be",
                "why": "Speaks to career transition anxiety found in Reddit discussions"
            }
        ]
        
        # Return a random inspiring concept
        concept = random.choice(inspiring_concepts)
        
        return (
            f"💡 *AD CONCEPT INSPIRATION*\n"
            f"*{concept['concept']}*\n"
            f"_{concept['description']}_\n"
            f"*Example:* {concept['example']}\n"
            f"*Why it works:* {concept['why']}\n"
        )

    return safe_api_call("alternative_ad_inspiration", _fetch_alternative_ads)

@rate_limit(delay=1)
def reddit_coursera_insights():
    """Find Coursera-specific audience insights: pain points, successes, and motivations"""
    def _fetch_reddit():
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

        # COURSERA-SPECIFIC INSIGHT PATTERNS
        insight_patterns = {
            "COURSERA_PROGRESS": {
                "coursera_terms": ["coursera", "google certificate", "google it support", "ibm certificate", "andrew ng"],
                "progress_terms": ["started", "taking", "enrolled in", "working on", "just began", "signed up", "trying out"],
                "emoji": "📈",
                "min_ups": 5
            },
            "COURSERA_DOUBTS": {
                "coursera_terms": ["coursera", "online course", "certificate", "mooc"],
                "doubt_terms": ["worth it", "waste of time", "legitimate", "employers recognize", "actually help", "does it count"],
                "emoji": "🤔",
                "min_ups": 8
            },
            "COURSERA_STRUGGLES": {
                "coursera_terms": ["coursera", "online learning", "certificate program"],
                "struggle_terms": ["struggling with", "hard to", "difficult", "overwhelmed", "stuck", "motivation", "pissed off", "frustrated"],
                "emoji": "😰",
                "min_ups": 5
            },
            "COURSERA_RECOMMENDATIONS": {
                "coursera_terms": ["coursera", "course recommendation", "which course", "best course"],
                "rec_terms": ["recommend", "suggest", "best for", "should i take", "worth taking", "good learning platforms"],
                "emoji": "💡",
                "min_ups": 8
            }
        }

        found_insights = []

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
                    
                    # Check against each insight pattern
                    for insight_type, pattern in insight_patterns.items():
                        if ups < pattern["min_ups"]:
                            continue
                        
                        # Must mention both Coursera terms AND the specific pattern terms
                        has_coursera_term = any(term in full_text for term in pattern["coursera_terms"])
                        has_pattern_term = any(term in full_text for term in pattern.get("progress_terms", []) + 
                                                                                pattern.get("doubt_terms", []) + 
                                                                                pattern.get("struggle_terms", []) + 
                                                                                pattern.get("rec_terms", []))
                        
                        if has_coursera_term and has_pattern_term:
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
                            
                            found_insights.append({
                                "type": insight_type,
                                "emoji": pattern["emoji"],
                                "title": title,
                                "quote": quote,
                                "url": "https://reddit.com" + data.get("permalink", ""),
                                "upvotes": ups,
                                "subreddit": subreddit,
                                "score": ups * (2 if "DOUBTS" in insight_type else 2 if "STRUGGLES" in insight_type else 1),
                                "age_days": (time.time() - created) / 86400
                            })
                            break
                            
            except Exception as e:
                logger.warning(f"Error searching r/{subreddit}: {e}")
                continue

        # Sort by relevance (score) and recency
        found_insights.sort(key=lambda x: x["score"] - (x["age_days"] / 7), reverse=True)
        
        # Take top 2 different types (faster processing)
        final_insights = []
        used_types = set()
        
        for insight in found_insights:
            if insight["type"] not in used_types and len(final_insights) < 2:
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
            
            return "\n\n".join(formatted)
        
        logger.info(f"Searched {len(target_subreddits)} subreddits for Coursera insights")
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
    
    # Get content
    alt_ad_content = alternative_ad_inspiration()
    reddit_content = reddit_coursera_insights()
    
    # Build digest
    sections = []
    if alt_ad_content:
        sections.append(alt_ad_content)
    if reddit_content:
        sections.append(reddit_content)
    
    # Clean, Slack-optimized formatting
    digest = "\n\n".join(sections) if sections else "🔴 *ALL APIS FAILED* - Check credentials"
    
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
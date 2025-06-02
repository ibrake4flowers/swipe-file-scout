import os
import json
import textwrap
import requests
import datetime
import html
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyser = SentimentIntensityAnalyzer()

# ---------- helpers ----------
def meta_ad():
    """
    Fetch the top ad from the Meta Ad Library using ads_read permissions.
    Returns a string like:
    "*Promo Play*
     • **Hook:** ... … 
     • [View Ad](ad_snapshot_url)"
    Or returns None if no ads are found.
    """
    url = (
        "https://graph.facebook.com/v18.0/ads_archive?"
        "search_terms=off%20save%20ends&ad_reached_countries=US"
        "&fields=ad_creative_body,ad_creative_link_caption,ad_snapshot_url,"
        "impressions_lower_bound,ad_creation_time"
        "&access_token=" + os.environ.get("FB_TOKEN", "")
    )
    response = requests.get(url).json()
    ad_list = response.get("data", [])
    if not ad_list:
        return None

    try:
        top_ad = max(ad_list, key=lambda r: int(r.get("impressions_lower_bound", 0)))
    except (ValueError, TypeError):
        return None

    body = html.unescape(top_ad.get("ad_creative_body", "")[:80])
    snapshot_url = top_ad.get("ad_snapshot_url", "")
    return f"*Promo Play*\n• **Hook:** {body}…\n• [View Ad]({snapshot_url})"


def reddit_story():
    """
    Fetch a highly upvoted, positive Coursera 'completed' post from Reddit.
    Returns a string like:
    "*Learner Story*
     • **Post Title**
     • [Reddit link](permalink)"
    Or returns None if no suitable post is found.
    """
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
    query_url = (
        "https://oauth.reddit.com/r/coursera+learnprogramming/search"
        "?q=coursera%20completed%20OR%20finished&sort=new&restrict_sr=on&limit=50"
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

        if ups >= 10 and sentiment > 0.4:
            permalink = data.get("permalink", "")
            headline = textwrap.shorten(title, 100)
            return f"*Learner Story*\n• **{headline}**\n• [Reddit link](https://reddit.com{permalink})"

    return None


# ---------- assemble & post ----------
blocks = [
    meta_ad(),
    reddit_story()
]

# Create 'digest' by joining only non-None blocks with two newlines
digest = "\n\n".join([section for section in blocks if section])


# ---------- helpers to send ----------
def send_slack(msg: str) -> bool:
    """
    Attempt to send the message to Slack via the SLACK_WEBHOOK URL.
    Returns True if SLACK_WEBHOOK is set and the POST is attempted.
    """
    hook = os.getenv("SLACK_WEBHOOK", "").strip()
    if hook:
        try:
            requests.post(hook, data=json.dumps({"text": msg}), timeout=10)
            return True
        except Exception:
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
        email_msg["Subject"] = "Swipe-File Digest"
        email_msg["From"] = user
        email_msg["To"] = to
        email_msg.set_content(msg)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(user, pwd)
            smtp.send_message(email_msg)
        return True
    except Exception:
        return False


# ---------- send the digest ----------
if digest:
    full_msg = f"▶️ Swipe-file digest ({datetime.date.today()})\n\n" + digest

    # Try Slack first; if that fails or SLACK_WEBHOOK is not set, fall back to email
    if not send_slack(full_msg):
        send_email(full_msg)

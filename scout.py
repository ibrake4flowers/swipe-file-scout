import os, json, textwrap, requests, datetime, html
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
analyser = SentimentIntensityAnalyzer()

# ---------- helpers ----------
def meta_ad():
    url = ("https://graph.facebook.com/v18.0/ads_archive?"
           "search_terms=off%20save%20ends&ad_reached_countries=US"
           "&fields=ad_creative_body,ad_creative_link_caption,ad_snapshot_url,"
           "impressions_lower_bound,ad_creation_time&access_token="+os.environ["FB_TOKEN"])
    res = requests.get(url).json().get("data", [])
    top = max(res, key=lambda r: int(r["impressions_lower_bound"])) if res else None
    if not top: return None
    return f"*Promo Play*\n• **Hook:** {html.unescape(top['ad_creative_body'][:80])}…\n• [View Ad]({top['ad_snapshot_url']})"

def reddit_story():
    auth = requests.auth.HTTPBasicAuth(os.environ["REDDIT_ID"], os.environ["REDDIT_SECRET"])
    data = {"grant_type":"client_credentials"}
    token = requests.post("https://www.reddit.com/api/v1/access_token", auth=auth,
                          data=data, headers={"User-Agent":"swipebot"}).json()["access_token"]
    hdrs = {"Authorization": f"bearer {token}", "User-Agent":"swipebot"}
    q = ("https://oauth.reddit.com/r/coursera+learnprogramming/search"
         "?q=coursera%20completed%20OR%20finished&sort=new&restrict_sr=on&limit=50")
    posts = requests.get(q, headers=hdrs).json()["data"]["children"]
    for p in posts:
        t = p["data"]["title"]+" "+p["data"].get("selftext","")
        if p["data"]["ups"]>=10 and analyser.polarity_scores(t)["compound"]>0.4:
            url = "https://reddit.com"+p["data"]["permalink"]
            headline = textwrap.shorten(p["data"]["title"], 100)
            return f"*Learner Story*\n• **{headline}**\n• [Reddit link]({url})"
    return None
def catalog_pulse():
    """Return a markdown bullet list of new + top-enrolled courses."""
    base = "https://www.coursera.org/api/onDemandCourses.v1"
    # ---- 1. newest titles --------------------------------------------------
    new_url = f"{base}?q=search&query=&sortField=recentlyLaunched&limit=3"
    new_titles = [c["name"] for c in requests.get(new_url).json()["elements"]]
    # ---- 2. top enrolled last 30 days --------------------------------------
    pop_url = f"{base}?q=search&query=&sortField=popular&limit=3"
    pop_titles = [c["name"] for c in requests.get(pop_url).json()["elements"]]
    # Build markdown
    bullets  = "📊 *Catalog Pulse*\n"
    bullets += "• **New this week:** " + ", ".join(new_titles) + "\n"
    bullets += "• **Top-enrolled 30 d:** " + ", ".join(pop_titles)
    return bullets

def fetch_json(url):
    # Coursera blocks some non-browser user-agents; spoof one & handle errors
    hdrs = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=hdrs, timeout=10)
    if r.status_code != 200:
        return {}
    return r.json()

def fresh_spin():
    """Return a launch or milestone pulled from the catalog; skip gracefully if none."""
    base = "https://www.coursera.org/api/onDemandCourses.v1"
    new_url = f"{base}?q=search&sortField=recentlyLaunched&limit=10"
    newest = fetch_json(new_url).get("elements", [])

    # 1. Newest launch in the last 14 days
    new_url = f"{base}?q=search&sortField=recentlyLaunched&limit=10"
    newest = requests.get(new_url).json()["elements"]

    # filter to last 14 days
    two_weeks = datetime.datetime.utcnow() - datetime.timedelta(days=14)
    fresh = [
        c for c in newest
        if datetime.datetime.fromtimestamp(c["createdAt"]/1000) > two_weeks
    ]

    if fresh:                                 # prefer true “brand new”
        pick = random.choice(fresh)
        return (f"✨ *Fresh Spin*\n"
                f"• **New course:** {pick['name']}\n"
                f"• Why care: launched {pick['partners'][0]['name']} just this month\n"
                f"• URL: https://www.coursera.org/learn/{pick['slug']}")
    # 2. Otherwise--pick a course celebrating a round-number anniversary (1 yr, 2 yr…)
    pop_url = f"{base}?q=search&sortField=popular&limit=50"
    popular = requests.get(pop_url).json()["elements"]
    today   = datetime.datetime.utcnow().date()

    for c in popular:
        launch = datetime.datetime.fromtimestamp(c["createdAt"]/1000).date()
        age = (today - launch).days // 365
        if age in {1,2,3,5}:                  # milestone birthdays you care about
            return (f"✨ *Fresh Spin*\n"
                    f"• **{c['name']}** turns {age} years old this week!\n"
                    f"• {c['enrollments']} learners so far.\n"
                    f"• URL: https://www.coursera.org/learn/{c['slug']}")

    return None      # if neither condition hits, nothing gets added

# ---------- assemble & post ----------
blocks = [meta_ad(), reddit_story()
digest  = "\n\n".join([b for b in blocks if b])

# ---------- helpers to send ----------
def send_slack(msg: str) -> bool:
    hook = os.getenv("SLACK_WEBHOOK")
    if hook:
        requests.post(hook, data=json.dumps({"text": msg}))
        return True
    return False

def send_email(msg: str) -> bool:
    user = os.getenv("EMAIL_FROM")
    pwd  = os.getenv("EMAIL_PW")
    to   = os.getenv("EMAIL_TO")
    if not (user and pwd and to):
        return False
    import email.message, smtplib
    m = email.message.EmailMessage()
    m["Subject"] = "Swipe-File Digest"
    m["From"], m["To"] = user, to
    m.set_content_

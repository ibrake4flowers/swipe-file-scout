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

def fresh_spin():
    feed = "https://blog.coursera.org/feed/"
    xml = requests.get(feed).text.split("<item>")
    latest = xml[1] if len(xml)>1 else ""
    title = latest.split("<title>")[1].split("</title>")[0]
    link  = latest.split("<link>")[1].split("</link>")[0]
    pub   = latest.split("<pubDate>")[1].split("</pubDate>")[0]
    return f"*Fresh Spin*\n• **{title}**\n• Published {pub}\n• [Read more]({link})"

# ---------- assemble & post ----------
blocks = [meta_ad(), reddit_story(), fresh_spin()]
digest  = "\n\n".join([b for b in blocks if b])

if digest:
    payload = {"text": f"▶️ Swipe-file digest ({datetime.date.today()})\n\n"+digest}
    requests.post(os.environ["SLACK_WEBHOOK"], data=json.dumps(payload))

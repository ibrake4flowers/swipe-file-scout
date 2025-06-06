# Swipe-File Scout  🕵️‍♀️✨  
A weekly GitHub Actions workflow that drops three high-performing ad ideas
(Promo Play, Learner Story, Fresh Spin), top upvoted Reddit threads, and Linkedin Cert shares into a Slack channel.  
Uses the Meta Ad Library, Reddit API, and Google alerts—completely free tier.

## Quick start
1. **Fork → Settings → Secrets**  
   - `FB_TOKEN` – system-user token with `ads_read`  
   - `REDDIT_ID` / `REDDIT_SECRET` – from your Reddit “script” app  
   - `SLACK_WEBHOOK` – incoming-webhook URL of the Slack channel
2. **Run the workflow** (Actions ▸ Swipe-File-Scout ▸ *Run workflow*).  
   A digest appears in Slack within ~60 s.
3. Automatic schedule: every even-numbered Monday at 08:30 PT.

## Customising  
| What | How |
|------|-----|
| Change the run day/time | Edit `cron:` in `.github/workflows/scout.yml`. |
| Switch focus programme | Tweak copy lines at the bottom of `scout.py`. |
| Turn weekly instead of bi-weekly | Delete the “Skip odd weeks” shell block. |
| Use Claude for copywriting | Replace the Python formatter with an MCP call. |

## Data & privacy
The script *reads* public ad creatives and Reddit posts only.  
No personal user data is stored; secrets are injected at runtime via
GitHub Actions and never committed to the repo.

## License
[MIT](LICENSE) 

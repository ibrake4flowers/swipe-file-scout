import os
import json
import requests
import datetime
import time
import logging
import hashlib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import imaplib
import email
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleAlertsSuccessMonitor:
    """
    Monitor Google Alerts emails for LinkedIn success stories
    """
    
    def __init__(self):
        # Email credentials for reading Google Alerts (reuse existing email setup)
        self.gmail_user = os.getenv("GMAIL_USER", "") or os.getenv("EMAIL_FROM", "")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD", "") or os.getenv("EMAIL_PW", "")
        
        # Slack webhook for notifications
        self.slack_webhook = os.getenv("SLACK_WEBHOOK", "")
        
        # Data storage
        self.stories_file = "linkedin_success_stories.json"
        
        # Story scoring criteria
        self.high_value_keywords = {
            "career_transformation": ["career change", "switched careers", "new career", "transitioned to", "career pivot"],
            "job_success": ["landed a job", "got hired", "new position", "job offer", "started working"],
            "promotion": ["promoted to", "got promoted", "promotion", "new role as"],
            "salary_impact": ["salary increase", "raise", "doubled my income", "better pay", "higher salary"],
            "gratitude": ["grateful for", "thankful", "changed my life", "couldn't have done it without"],
            "coursera_specific": ["coursera certificate", "google certificate", "coursera course", "andrew ng"]
        }
        
    def setup_gmail_alerts(self):
        """
        Instructions for setting up Google Alerts
        This is a one-time manual setup that the user needs to do
        """
        alert_setup_instructions = """
🚀 **GOOGLE ALERTS SETUP INSTRUCTIONS**

1. **Go to Google Alerts**: https://www.google.com/alerts

2. **Create These 5 Alerts** (one at a time):

   Alert #1: linkedin.com "coursera certificate" completed
   Alert #2: linkedin.com "google certificate" career change  
   Alert #3: linkedin.com "coursera helped me" job
   Alert #4: linkedin.com coursera "landed" OR "hired" OR "promoted"
   Alert #5: linkedin.com "coursera course" "grateful" OR "thankful"

3. **Settings for Each Alert**:
   - How often: As-it-happens
   - Sources: Automatic  
   - Language: English
   - Region: Any region (or United States)
   - How many: Only the best results
   - Deliver to: [Your Gmail address]

4. **Email Setup**:
   - The alerts will come from googlealerts-noreply@google.com
   - Subject line: "Google Alert - [your search terms]"

5. **Gmail App Password** (for this script):
   - Go to Google Account settings
   - Security > 2-Step Verification > App passwords
   - Generate password for "Mail"
   - Use this password in GMAIL_APP_PASSWORD environment variable

6. **Test**: You should start getting emails within a few hours!

**Pro Tip**: Start with fewer alerts and add more once you see what quality you're getting.
        """
        
        return alert_setup_instructions
    
    def load_existing_stories(self):
        """Load previously found stories"""
        try:
            if os.path.exists(self.stories_file):
                with open(self.stories_file, 'r') as f:
                    return json.load(f)
            return {"stories": [], "last_processed": None}
        except Exception as e:
            logger.warning(f"Could not load existing stories: {e}")
            return {"stories": [], "last_processed": None}
    
    def save_stories(self, stories_data):
        """Save stories to file"""
        try:
            with open(self.stories_file, 'w') as f:
                json.dump(stories_data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save stories: {e}")
    
    def connect_to_gmail(self):
        """Connect to Gmail using IMAP"""
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(self.gmail_user, self.gmail_password)
            mail.select('inbox')
            return mail
        except Exception as e:
            logger.error(f"Failed to connect to Gmail: {e}")
            return None
    
    def fetch_google_alerts_emails(self, days_back=7):
        """Fetch Google Alerts emails from the last few days"""
        mail = self.connect_to_gmail()
        if not mail:
            return []
        
        try:
            # Search for Google Alerts emails from the last week
            since_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime("%d-%b-%Y")
            search_criteria = f'(FROM "googlealerts-noreply@google.com" SINCE {since_date})'
            
            result, message_ids = mail.search(None, search_criteria)
            if result != 'OK':
                logger.error("Failed to search Gmail")
                return []
            
            email_data = []
            message_ids = message_ids[0].split()
            
            logger.info(f"Found {len(message_ids)} Google Alerts emails")
            
            # Process each email
            for msg_id in message_ids[-50:]:  # Limit to last 50 emails
                try:
                    result, msg_data = mail.fetch(msg_id, '(RFC822)')
                    if result != 'OK':
                        continue
                    
                    email_message = email.message_from_bytes(msg_data[0][1])
                    
                    # Extract email content
                    email_info = {
                        'subject': email_message['Subject'],
                        'date': email_message['Date'],
                        'message_id': email_message['Message-ID'],
                        'links': []
                    }
                    
                    # Extract HTML content and links
                    for part in email_message.walk():
                        if part.get_content_type() == "text/html":
                            html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            links = self.extract_linkedin_links(html_content)
                            email_info['links'] = links
                            break
                    
                    if email_info['links']:
                        email_data.append(email_info)
                
                except Exception as e:
                    logger.warning(f"Error processing email {msg_id}: {e}")
                    continue
            
            mail.close()
            mail.logout()
            
            return email_data
            
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []
    
    def extract_linkedin_links(self, html_content):
        """Extract LinkedIn links from Google Alerts email HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        linkedin_links = []
        
        # Find all links in the email
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Google Alerts URLs are often wrapped in redirects
            if 'linkedin.com' in href or 'linkedin.com' in link.get_text():
                # Clean up Google redirect URLs
                if 'url?q=' in href:
                    try:
                        actual_url = href.split('url?q=')[1].split('&')[0]
                        actual_url = unquote(actual_url)
                    except:
                        actual_url = href
                else:
                    actual_url = href
                
                # Only include LinkedIn post/profile URLs
                if 'linkedin.com' in actual_url and any(path in actual_url for path in ['/posts/', '/feed/', '/pulse/']):
                    linkedin_links.append({
                        'url': actual_url,
                        'text': link.get_text().strip(),
                        'found_in_alert': True
                    })
        
        return linkedin_links
    
    def analyze_story_potential(self, link_data):
        """Analyze a LinkedIn link for success story potential"""
        text = link_data.get('text', '').lower()
        url = link_data.get('url', '')
        
        story_score = 0
        found_signals = []
        
        # Score based on text content
        for category, keywords in self.high_value_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    if category == "career_transformation":
                        story_score += 20
                        found_signals.append(f"CAREER_CHANGE: {keyword}")
                    elif category == "job_success":
                        story_score += 15
                        found_signals.append(f"JOB_SUCCESS: {keyword}")
                    elif category == "promotion":
                        story_score += 15
                        found_signals.append(f"PROMOTION: {keyword}")
                    elif category == "salary_impact":
                        story_score += 12
                        found_signals.append(f"SALARY: {keyword}")
                    elif category == "gratitude":
                        story_score += 10
                        found_signals.append(f"GRATITUDE: {keyword}")
                    elif category == "coursera_specific":
                        story_score += 8
                        found_signals.append(f"COURSERA: {keyword}")
                    break  # Only count each category once
        
        # Bonus for LinkedIn posts (vs profiles)
        if '/posts/' in url or '/feed/' in url:
            story_score += 5
            found_signals.append("LINKEDIN_POST")
        
        return story_score, found_signals
    
    def create_story_id(self, link_data):
        """Create unique ID for a story"""
        url = link_data.get('url', '')
        text = link_data.get('text', '')
        content = f"{url}_{text}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def process_new_stories(self):
        """Process new Google Alerts emails and find success stories"""
        logger.info("Processing new Google Alerts emails...")
        
        # Load existing data
        stories_data = self.load_existing_stories()
        existing_stories = {story['id']: story for story in stories_data['stories']}
        
        # Fetch new emails
        emails = self.fetch_google_alerts_emails(days_back=3)  # Check last 3 days
        
        new_stories = []
        processed_links = 0
        
        for email_info in emails:
            for link in email_info['links']:
                processed_links += 1
                
                # Create story ID
                story_id = self.create_story_id(link)
                
                # Skip if already processed
                if story_id in existing_stories:
                    continue
                
                # Analyze story potential
                story_score, signals = self.analyze_story_potential(link)
                
                # Only keep high-potential stories
                if story_score >= 15:
                    story = {
                        'id': story_id,
                        'url': link['url'],
                        'text': link['text'],
                        'story_score': story_score,
                        'signals': signals,
                        'found_date': datetime.datetime.now().isoformat(),
                        'alert_subject': email_info['subject'],
                        'alert_date': email_info['date'],
                        'outreach_status': 'pending'
                    }
                    
                    new_stories.append(story)
                    existing_stories[story_id] = story
                    logger.info(f"Found high-value story (score: {story_score}): {link['text'][:50]}...")
        
        # Update stories data
        stories_data['stories'] = list(existing_stories.values())
        stories_data['last_processed'] = datetime.datetime.now().isoformat()
        stories_data['total_links_processed'] = processed_links
        
        # Save updated data
        self.save_stories(stories_data)
        
        logger.info(f"Processed {processed_links} links, found {len(new_stories)} new high-value stories")
        
        return new_stories, stories_data
    
    def generate_outreach_report(self, stories_data):
        """Generate formatted report for team review"""
        
        all_stories = stories_data.get('stories', [])
        high_value_stories = [s for s in all_stories if s.get('story_score', 0) >= 20]
        medium_value_stories = [s for s in all_stories if 15 <= s.get('story_score', 0) < 20]
        
        # Sort by score
        high_value_stories.sort(key=lambda x: x.get('story_score', 0), reverse=True)
        
        report_lines = [
            f"🎯 **LINKEDIN SUCCESS STORY DIGEST** | {datetime.date.today().strftime('%B %d, %Y')}",
            f"",
            f"📊 **Summary from Google Alerts:**",
            f"• Total stories found: {len(all_stories)}",
            f"• High-value outreach candidates (20+ score): {len(high_value_stories)}",
            f"• Medium-value stories (15-19 score): {len(medium_value_stories)}",
            f"• Last processed: {stories_data.get('last_processed', 'Unknown')[:16]}",
            f"• Links processed: {stories_data.get('total_links_processed', 'Unknown')}",
            f"",
            f"🌟 **TOP OUTREACH CANDIDATES:**",
            f""
        ]
        
        # Add top 5 high-value stories
        for i, story in enumerate(high_value_stories[:5]):
            found_date = story.get('found_date', '')[:10] if story.get('found_date') else 'Unknown'
            
            report_lines.extend([
                f"**#{i+1} - Score: {story.get('story_score', 0)}**",
                f"📅 Found: {found_date}",
                f"🔗 URL: {story.get('url', 'No URL')}",
                f"📝 Preview: {story.get('text', 'No preview')[:150]}...",
                f"🎯 Signals: {', '.join(story.get('signals', []))[:100]}...",
                f"📧 From Alert: {story.get('alert_subject', 'Unknown')[:50]}...",
                f"",
                f"**Outreach Strategy:**",
                f"• Visit LinkedIn post directly",
                f"• Engage with post (like/comment) first",
                f"• Send personalized connection request",
                f"• Mention specific achievement from their post",
                f"• Offer to feature their success story",
                f"",
                f"---",
                f""
            ])
        
        if not high_value_stories:
            report_lines.extend([
                f"No high-value stories found yet.",
                f"• Check that Google Alerts are set up correctly",
                f"• Verify Gmail credentials are working",
                f"• Consider adjusting scoring criteria",
                f""
            ])
        
        report_lines.extend([
            f"📈 **Next Steps:**",
            f"1. Review top candidates above",
            f"2. Visit LinkedIn posts to verify quality",
            f"3. Craft personalized outreach messages",
            f"4. Track response rates in stories file",
            f"",
            f"💡 **Google Alerts Setup:**",
            f"Make sure you have these 5 alerts running:",
            f"• linkedin.com \"coursera certificate\" completed",
            f"• linkedin.com \"google certificate\" career change",  
            f"• linkedin.com \"coursera helped me\" job",
            f"• linkedin.com coursera \"landed\" OR \"hired\" OR \"promoted\"",
            f"• linkedin.com \"coursera course\" \"grateful\" OR \"thankful\"",
            f"",
            f"_Generated by Google Alerts Success Story Monitor_"
        ])
        
        return "\n".join(report_lines)
    
    def send_slack_notification(self, message):
        """Send notification to Slack"""
        if not self.slack_webhook:
            return False
        
        try:
            response = requests.post(
                self.slack_webhook,
                json={"text": message},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    def run_story_scan(self):
        """Run complete story scanning process"""
        logger.info("Starting Google Alerts success story scan...")
        
        # Check Gmail credentials
        if not (self.gmail_user and self.gmail_password):
            setup_instructions = self.setup_gmail_alerts()
            print(setup_instructions)
            return {
                'status': 'setup_required',
                'message': 'Gmail credentials not configured. See setup instructions above.'
            }
        
        try:
            # Process new stories
            new_stories, stories_data = self.process_new_stories()
            
            # Generate report
            report = self.generate_outreach_report(stories_data)
            
            # Send to Slack or print
            if self.send_slack_notification(report):
                logger.info("Report sent to Slack")
            else:
                logger.info("Slack not configured, printing report:")
                print(report)
            
            return {
                'status': 'success',
                'new_stories_found': len(new_stories),
                'total_stories': len(stories_data.get('stories', [])),
                'report': report
            }
            
        except Exception as e:
            logger.error(f"Error during story scan: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

def main():
    monitor = GoogleAlertsSuccessMonitor()
    results = monitor.run_story_scan()
    
    if results['status'] == 'setup_required':
        print("\n" + "="*60)
        print("SETUP REQUIRED")
        print("="*60)
        print(results['message'])
    elif results['status'] == 'success':
        print(f"\n✅ Scan complete!")
        print(f"📊 Found {results['new_stories_found']} new high-value stories")
        print(f"📈 Total stories in database: {results['total_stories']}")
    else:
        print(f"\n❌ Scan failed: {results['message']}")

if __name__ == "__main__":
    main()

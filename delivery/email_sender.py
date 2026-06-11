import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Dict, Optional
from config.settings import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT

logger = logging.getLogger(__name__)

class EmailSender:
    """Sends HTML email reports with inline analytical chart attachments via SMTP"""

    def __init__(self):
        self.sender = EMAIL_SENDER
        self.password = EMAIL_PASSWORD
        self.receiver = EMAIL_RECEIVER
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT

    def send_report(
        self,
        html_content: str,
        charts: Dict[str, str], # Maps e.g. 'chart_price' to base64 string
        subject: str = "서울 주요 7개구 부동산 실거래 동향 일일 보고서"
    ) -> bool:
        """
        Send the HTML email report with inline chart attachments.
        If email configuration is incomplete (e.g. during testing), it logs a warning
        but allows the program to continue, preventing failures.
        """
        # 1. Validate credentials
        if not self.sender or not self.password:
            logger.warning(
                "⚠️ EMAIL_SENDER or EMAIL_PASSWORD not configured in .env. "
                "Email delivery skipped. (You can view the saved HTML report in data/history/)"
            )
            return False

        try:
            logger.info(f"Preparing to send email to {self.receiver} via {self.smtp_server}:{self.smtp_port}...")
            
            # 2. Create the outer message (multipart/related for inline images)
            msg = MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = self.receiver

            # 3. Add the HTML text part
            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)
            
            msg_html = MIMEText(html_content, 'html', 'utf-8')
            msg_alternative.attach(msg_html)

            # 4. Attach inline images
            for cid, b64_str in charts.items():
                if not b64_str:
                    continue
                try:
                    img_data = base64.b64decode(b64_str)
                    img = MIMEImage(img_data, 'png')
                    img.add_header('Content-ID', f'<{cid}>')
                    img.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
                    msg.attach(img)
                    logger.info(f"Attached inline image: cid=<{cid}>")
                except Exception as img_err:
                    logger.error(f"Failed to attach image {cid}: {img_err}")

            # 5. Connect and send
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.set_debuglevel(0)
            server.starttls() # Secure connection
            
            server.login(self.sender, self.password)
            server.sendmail(self.sender, [self.receiver], msg.as_string())
            server.quit()
            
            logger.info(f"✅ Daily report email successfully sent to {self.receiver}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send real estate report email: {e}")
            return False

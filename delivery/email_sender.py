import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Dict, Optional
from config.settings import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT

logger = logging.getLogger(__name__)

class EmailSender:
    """Sends HTML email reports with inline analytical chart attachments and optional file attachments via SMTP"""

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
        subject: str = "서울 주요 7개구 부동산 실거래 동향 일일 보고서",
        attachment_path: Optional[str] = None
    ) -> bool:
        """
        Send the HTML email report with inline chart attachments and optional file attachments.
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
            
            # 2. Create the outer message (multipart/mixed to support both inline elements and attachments)
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = self.receiver

            # 3. Create a multipart/related container for the body + inline images
            msg_related = MIMEMultipart('related')
            msg.attach(msg_related)

            # 4. Add the HTML text part to the related container
            msg_alternative = MIMEMultipart('alternative')
            msg_related.attach(msg_alternative)
            
            msg_html = MIMEText(html_content, 'html', 'utf-8')
            msg_alternative.attach(msg_html)

            # 5. Attach inline images to the related container
            for cid, b64_str in charts.items():
                if not b64_str:
                    continue
                try:
                    img_data = base64.b64decode(b64_str)
                    img = MIMEImage(img_data, 'png')
                    img.add_header('Content-ID', f'<{cid}>')
                    img.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
                    msg_related.attach(img)
                    logger.info(f"Attached inline image: cid=<{cid}>")
                except Exception as img_err:
                    logger.error(f"Failed to attach image {cid}: {img_err}")

            # 6. Add file attachment if provided
            if attachment_path and Path(attachment_path).exists():
                try:
                    path = Path(attachment_path)
                    part = MIMEBase('application', 'octet-stream')
                    with open(path, 'rb') as file:
                        part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{path.name}"'
                    )
                    msg.attach(part)
                    logger.info(f"Attached file: {path.name}")
                except Exception as attach_err:
                    logger.error(f"Failed to add attachment: {attach_err}")

            # 7. Connect and send
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

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("SMTP_FROM")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send email via SMTP.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email content
    
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email

        msg.attach(MIMEText(html_content, "html"))

        # Use SMTP_SSL for port 465, SMTP with starttls for port 587
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(FROM_EMAIL, to_email, msg.as_string())

        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {str(e)}")
        return False


def render_template(template_content: str, context: dict) -> str:
    """
    Render Jinja2 template with context variables.
    
    Args:
        template_content: Template HTML string
        context: Dictionary of variables to render
    
    Returns:
        Rendered HTML string
    """
    template = Template(template_content)
    return template.render(**context)


def send_new_user_email(user_email: str, user_name: str, uid: str, token: str) -> bool:
    """
    Send new user registration email with activation link.
    
    Args:
        user_email: User's email address
        user_name: User's display name
        uid: User ID encoded in base64
        token: Activation token
    
    Returns:
        True if email sent successfully
    """
    template_path = "src/users/templates/new_user_email.html"
    try:
        with open(template_path, "r") as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"Template not found: {template_path}")
        return False

    context = {
        "user_title": user_name or user_email.split("@")[0],
        "domain": BACKEND_API_URL,
        "uid": uid,
        "token": token,
        "year": datetime.now().year,
    }

    html_content = render_template(template_content, context)
    return send_email(user_email, "Complete Your Registration", html_content)


def send_forgot_password_email(user_email: str, user_name: str, uid: str, token: str) -> bool:
    """
    Send password reset email with reset link.
    
    Args:
        user_email: User's email address
        user_name: User's display name
        uid: User ID encoded in base64
        token: Password reset token
    
    Returns:
        True if email sent successfully
    """
    template_path = "src/users/templates/forgot_password_email.html"
    try:
        with open(template_path, "r") as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"Template not found: {template_path}")
        return False

    context = {
        "user": user_name or user_email.split("@")[0],
        "domain": BACKEND_API_URL,
        "uid": uid,
        "token": token,
        "year": datetime.now().year,
    }

    html_content = render_template(template_content, context)
    return send_email(user_email, "Reset Your Password", html_content)

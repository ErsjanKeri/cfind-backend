"""
Email service using SMTP (ZeptoMail).

Handles all transactional emails:
- Email verification
- Password reset
- Password changed confirmation
- Agent rejection notification
- Buyer demand claimed notification
"""

import asyncio
import html
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Get current year dynamically
CURRENT_YEAR = datetime.now().year


# ============================================================================
# SMTP EMAIL SENDING (ZeptoMail, Gmail, etc.)
# ============================================================================

async def send_email_smtp(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> bool:
    """
    Send email via SMTP (e.g., ZeptoMail, Gmail).

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML email body
        text_content: Plain text fallback (optional)

    Returns:
        True if email sent successfully, False otherwise
    """
    if not settings.SMTP_PASSWORD:
        # Development mode: Log email instead of sending
        logger.info(f"[DEV MODE] Email would be sent to {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content: {html_content[:200]}...")
        return True

    def _send_sync():
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
        msg['To'] = to_email

        if text_content:
            msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))

        if settings.SMTP_PORT == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context) as server:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
        elif settings.SMTP_PORT == 587:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            raise ValueError(f"Unsupported SMTP port: {settings.SMTP_PORT}")

    try:
        await asyncio.to_thread(_send_sync)
        logger.info(f"SMTP email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Error sending SMTP email to {to_email}: {str(e)}")
        return False


# ============================================================================
# MAIN EMAIL SENDING FUNCTION (SMTP only)
# ============================================================================

async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> bool:
    """
    Send email via SMTP (ZeptoMail).

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML email body
        text_content: Plain text fallback (optional)

    Returns:
        True if email sent successfully, False otherwise

    Example:
        success = await send_email(
            to_email="user@example.com",
            subject="Welcome to CompanyFinder",
            html_content="<h1>Welcome!</h1>"
        )
    """
    return await send_email_smtp(to_email, subject, html_content, text_content)


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

async def send_verification_email(
    to_email: str,
    user_name: str,
    verification_token: str
) -> bool:
    """
    Send email verification link to user.

    Args:
        to_email: User's email address
        user_name: User's name
        verification_token: Verification token (valid for 24 hours)

    Returns:
        True if email sent successfully, False otherwise
    """
    safe_name = html.escape(user_name)
    verification_url = f"{settings.APP_URL}/verify-email?token={verification_token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #355781; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background-color: #355781; color: white !important; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to CompanyFinder Albania!</h1>
            </div>
            <div class="content">
                <p>Hello {safe_name},</p>

                <p>Thank you for registering with CompanyFinder Albania, the premier marketplace for buying and selling businesses in Albania.</p>

                <p>To complete your registration, please verify your email address by clicking the button below:</p>

                <p style="text-align: center;">
                    <a href="{verification_url}" class="button">Verify Email Address</a>
                </p>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: white; padding: 10px; border-radius: 4px;">{verification_url}</p>

                <p><strong>This link will expire in 24 hours.</strong></p>

                <p>If you didn't create an account with CompanyFinder Albania, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; {CURRENT_YEAR} CompanyFinder Albania. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Welcome to CompanyFinder Albania!

    Hello {user_name},

    Thank you for registering. Please verify your email address by visiting:
    {verification_url}

    This link will expire in 24 hours.

    If you didn't create an account, you can safely ignore this email.
    """

    return await send_email(
        to_email=to_email,
        subject="Verify your email address - CompanyFinder Albania",
        html_content=html_content,
        text_content=text_content
    )


# ============================================================================
# PASSWORD RESET
# ============================================================================

async def send_password_reset_email(
    to_email: str,
    user_name: str,
    reset_token: str
) -> bool:
    """
    Send password reset link to user.

    Args:
        to_email: User's email address
        user_name: User's name
        reset_token: Reset token (valid for 1 hour, single-use)

    Returns:
        True if email sent successfully, False otherwise
    """
    safe_name = html.escape(user_name)
    reset_url = f"{settings.APP_URL}/reset-password?token={reset_token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #dc2626; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background-color: #dc2626; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .warning {{ background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Password Reset Request</h1>
            </div>
            <div class="content">
                <p>Hello {safe_name},</p>

                <p>We received a request to reset your password for your CompanyFinder Albania account.</p>

                <p>Click the button below to reset your password:</p>

                <p style="text-align: center;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </p>

                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: white; padding: 10px; border-radius: 4px;">{reset_url}</p>

                <div class="warning">
                    <p><strong>⚠️ Important:</strong></p>
                    <ul>
                        <li>This link will expire in <strong>1 hour</strong></li>
                        <li>This link can only be used <strong>once</strong></li>
                        <li>If you didn't request this reset, please ignore this email</li>
                    </ul>
                </div>

                <p>For security, your password won't be changed until you complete the reset process.</p>
            </div>
            <div class="footer">
                <p>&copy; {CURRENT_YEAR} CompanyFinder Albania. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Password Reset Request

    Hello {user_name},

    We received a request to reset your password. Click the link below to reset it:
    {reset_url}

    This link will expire in 1 hour and can only be used once.

    If you didn't request this reset, please ignore this email.
    """

    return await send_email(
        to_email=to_email,
        subject="Reset your password - CompanyFinder Albania",
        html_content=html_content,
        text_content=text_content
    )


# ============================================================================
# PASSWORD CHANGED CONFIRMATION
# ============================================================================

async def send_password_changed_email(
    to_email: str,
    user_name: str
) -> bool:
    """
    Send confirmation email after successful password change.

    Args:
        to_email: User's email address
        user_name: User's name

    Returns:
        True if email sent successfully, False otherwise
    """
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #16a34a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .success {{ background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 15px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✓ Password Changed Successfully</h1>
            </div>
            <div class="content">
                <p>Hello {html.escape(user_name)},</p>

                <div class="success">
                    <p><strong>Your password has been successfully changed.</strong></p>
                </div>

                <p>Your CompanyFinder Albania account password was recently updated. All your active sessions have been logged out for security.</p>

                <p>You can now log in with your new password.</p>

                <p><strong>If you didn't make this change:</strong></p>
                <ul>
                    <li>Your account may be compromised</li>
                    <li>Please contact our support team immediately</li>
                    <li>Consider enabling additional security measures</li>
                </ul>
            </div>
            <div class="footer">
                <p>&copy; {CURRENT_YEAR} CompanyFinder Albania. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Password Changed Successfully

    Hello {user_name},

    Your CompanyFinder Albania account password was successfully changed.

    If you didn't make this change, please contact support immediately.
    """

    return await send_email(
        to_email=to_email,
        subject="Password changed - CompanyFinder Albania",
        html_content=html_content,
        text_content=text_content
    )


# ============================================================================
# AGENT REJECTION NOTIFICATION
# ============================================================================

async def send_agent_rejection_email(
    to_email: str,
    agent_name: str,
    rejection_reason: str
) -> bool:
    """
    Send notification email when agent verification is rejected.

    Args:
        to_email: Agent's email address
        agent_name: Agent's name
        rejection_reason: Reason for rejection (from admin)

    Returns:
        True if email sent successfully, False otherwise
    """
    safe_name = html.escape(agent_name)
    safe_reason = html.escape(rejection_reason)
    settings_url = f"{settings.APP_URL}/settings"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #dc2626; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .reason-box {{ background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0; }}
            .button {{ display: inline-block; background-color: #355781; color: white !important; padding: 12px 30px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Agent Verification Update</h1>
            </div>
            <div class="content">
                <p>Hello {safe_name},</p>

                <p>Thank you for your interest in joining CompanyFinder Albania as a verified agent.</p>

                <p>After reviewing your application, we regret to inform you that your verification request has been declined for the following reason:</p>

                <div class="reason-box">
                    <p><strong>Reason for decline:</strong></p>
                    <p>{safe_reason}</p>
                </div>

                <p><strong>What you can do next:</strong></p>
                <ul>
                    <li>Review the reason for decline carefully</li>
                    <li>Update your profile and documents accordingly</li>
                    <li>Resubmit your verification request</li>
                </ul>

                <p style="text-align: center;">
                    <a href="{settings_url}" class="button">Update Profile & Resubmit</a>
                </p>

                <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
            </div>
            <div class="footer">
                <p>&copy; {CURRENT_YEAR} CompanyFinder Albania. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Agent Verification Update

    Hello {agent_name},

    Your agent verification request has been declined.

    Reason: {rejection_reason}

    Please update your profile and documents at {settings_url} and resubmit.

    If you have questions, please contact support.
    """

    return await send_email(
        to_email=to_email,
        subject="Agent Verification Update - CompanyFinder Albania",
        html_content=html_content,
        text_content=text_content
    )


# ============================================================================
# BUYER DEMAND CLAIMED NOTIFICATION
# ============================================================================

async def send_demand_claimed_email(
    to_email: str,
    buyer_name: str,
    agent_name: str,
    agent_email: str,
    agent_phone: Optional[str],
    agent_whatsapp: Optional[str],
    demand_description: str
) -> bool:
    """
    Send notification email when agent claims a buyer's demand.

    Args:
        to_email: Buyer's email address
        buyer_name: Buyer's name
        agent_name: Agent's name
        agent_email: Agent's email address
        agent_phone: Agent's phone number (optional)
        agent_whatsapp: Agent's WhatsApp number (optional)
        demand_description: Description of the demand

    Returns:
        True if email sent successfully, False otherwise
    """
    safe_buyer = html.escape(buyer_name)
    safe_agent = html.escape(agent_name)
    safe_agent_email = html.escape(agent_email)
    safe_phone = html.escape(agent_phone) if agent_phone else None
    safe_whatsapp = html.escape(agent_whatsapp) if agent_whatsapp else None
    safe_desc = html.escape(demand_description)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #16a34a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 8px 8px; }}
            .agent-card {{ background-color: white; border: 2px solid #16a34a; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .contact-info {{ background-color: #f0fdf4; padding: 15px; border-radius: 6px; margin: 15px 0; }}
            .footer {{ text-align: center; margin-top: 30px; color: #6b7280; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 Good News! An Agent is Interested</h1>
            </div>
            <div class="content">
                <p>Hello {safe_buyer},</p>

                <p>Great news! A verified agent has shown interest in your business demand and would like to help you.</p>

                <div class="agent-card">
                    <h2 style="margin-top: 0; color: #16a34a;">Agent Details</h2>
                    <p><strong>Name:</strong> {safe_agent}</p>

                    <div class="contact-info">
                        <p><strong>Contact Information:</strong></p>
                        <p>📧 Email: <a href="mailto:{safe_agent_email}">{safe_agent_email}</a></p>
                        {"<p>📱 Phone: " + safe_phone + "</p>" if safe_phone else ""}
                        {"<p>💬 WhatsApp: " + safe_whatsapp + "</p>" if safe_whatsapp else ""}
                    </div>
                </div>

                <p><strong>Your demand:</strong></p>
                <p style="background: white; padding: 15px; border-left: 4px solid #355781; border-radius: 4px;">{safe_desc}</p>

                <p><strong>Next steps:</strong></p>
                <ul>
                    <li>The agent will reach out to you soon</li>
                    <li>You can also contact them directly using the details above</li>
                    <li>Discuss your requirements and explore opportunities</li>
                </ul>

                <p>We wish you the best in your business endeavors!</p>
            </div>
            <div class="footer">
                <p>&copy; {CURRENT_YEAR} CompanyFinder Albania. All rights reserved.</p>
                <p>This is an automated message, please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
    Good News! An Agent is Interested

    Hello {buyer_name},

    A verified agent has shown interest in your business demand.

    Agent: {agent_name}
    Email: {agent_email}
    {"Phone: " + agent_phone if agent_phone else ""}
    {"WhatsApp: " + agent_whatsapp if agent_whatsapp else ""}

    Your demand: {demand_description}

    The agent will reach out to you soon, or you can contact them directly.
    """

    return await send_email(
        to_email=to_email,
        subject="An Agent is Interested in Your Business Demand - CompanyFinder Albania",
        html_content=html_content,
        text_content=text_content
    )

from flask import current_app, render_template
from flask_mail import Message
from app import mail
from threading import Thread

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Failed to send email: {e}")

def send_email(subject, sender, recipients, text_body, html_body):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    
    # Send email asynchronously
    Thread(target=send_async_email,
           args=(current_app._get_current_object(), msg)).start()

def send_templated_email(template_name, recipient_email, context_data):
    """Fetch an EmailTemplate from DB, render it with Jinja2, and send it."""
    from app.models.email import EmailTemplate
    from jinja2 import Template
    
    template = EmailTemplate.query.filter_by(name=template_name).first()
    if not template:
        current_app.logger.warning(f"Email template '{template_name}' not found. Cannot send email.")
        return
        
    try:
        # Render Jinja syntax within the DB template
        jinja_subject = Template(template.subject)
        jinja_body = Template(template.body)
        
        subject = jinja_subject.render(**context_data)
        text_body = jinja_body.render(**context_data)
        
        # Simple HTML conversion (newlines to <br>)
        html_body = text_body.replace('\n', '<br>')
        
        sender = current_app.config.get('MAIL_USERNAME') or 'noreply@shrinehomestay.com'
        
        send_email(
            subject=subject,
            sender=sender,
            recipients=[recipient_email],
            text_body=text_body,
            html_body=html_body
        )
    except Exception as e:
        current_app.logger.error(f"Error rendering/sending email template '{template_name}': {e}")

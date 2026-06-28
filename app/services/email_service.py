from app.utils.mail import send_templated_email

class EmailService:
    @staticmethod
    def send_enquiry_received_emails(enquiry, admin_email):
        # To Admin
        send_templated_email(
            template_name="new_enquiry",
            recipient_email=admin_email,
            context_data={"enquiry": enquiry}
        )
        # To Guest
        send_templated_email(
            template_name="enquiry_received_guest",
            recipient_email=enquiry.email,
            context_data={"enquiry": enquiry}
        )
        
    @staticmethod
    def send_booking_rejected_email(enquiry):
        send_templated_email(
            template_name="booking_rejected",
            recipient_email=enquiry.email,
            context_data={"enquiry": enquiry}
        )
        
    @staticmethod
    def send_booking_cancelled_email(booking):
        send_templated_email(
            template_name="booking_cancelled",
            recipient_email=booking.email,
            context_data={"booking": booking}
        )

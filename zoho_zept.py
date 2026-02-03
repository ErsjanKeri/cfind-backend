import smtplib, ssl
from email.message import EmailMessage
port = 587
smtp_server = "smtp.zeptomail.eu"
username="emailapikey"
password = "yA6KbHtf7FqklDpWEhQ61cCO9N4wpas9iny/4HjmKZAhfoPjjKFt0EVrdtfsLjWM2IeE4KpXPdNHI4vtvNlZfZc9MdUDfZTGTuv4P2uV48xh8ciEYNYhjJqrArkYF65OeRoiAiw0QfcnWA=="
message = "Test email sent successfully."
msg = EmailMessage()
msg['Subject'] = "Test Email"
msg['From'] = "noreply@cfind.ai"
msg['To'] = "ersjankeri@gmail.com"
msg.set_content(message)
try:
    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(username, password)
            server.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
    else:
        print ("use 465 / 587 as port value")
        exit()
    print ("successfully sent")
except Exception as e:
    print (e)
import os

# Read from Environment Variables (Render will set these)
TWILIO_SID = os.environ.get('TWILIO_SID', '')  # Auto read from Render
TWILIO_TOKEN = os.environ.get('TWILIO_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')
WHATSAPP_TO = os.environ.get('WHATSAPP_TO', '')
SYMBOL = os.environ.get('SYMBOL', 'BTCUSDT')
BLOCK_MINUTES = int(os.environ.get('BLOCK_MINUTES', '5'))
import os
from dotenv import load_dotenv

load_dotenv()

# RD Station
RD_CLIENT_ID = os.getenv("RD_CLIENT_ID")
RD_CLIENT_SECRET = os.getenv("RD_CLIENT_SECRET")
RD_REFRESH_TOKEN = os.getenv("RD_REFRESH_TOKEN")
RD_PRIVATE_TOKEN = os.getenv("RD_PRIVATE_TOKEN")
RD_CRM_TOKEN = os.getenv("RD_CRM_TOKEN")

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID")

# Meta Ads
META_APP_ID = os.getenv("META_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")

# Google Sheets
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_FILE = "credentials/google_service_account.json"

# Microsoft Clarity
# Token JWT gerado em clarity.microsoft.com → Settings → Data Export → Generate new API token
# Limites: 10 requests/dia, dados dos últimos 1-3 dias (precisa acumular diariamente em planilha)
CLARITY_API_TOKEN = os.getenv("CLARITY_API_TOKEN")

# Supabase (autenticação e armazenamento seguro dos dados)
SUPABASE_URL         = os.getenv("SUPABASE_URL")          # ex: https://xxxx.supabase.co
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service_role key (NUNCA expor no front)

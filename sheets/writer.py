import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_client():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def write_sheet(sheet_name, data, spreadsheet_id=None):
    if not data:
        print(f"  Sem dados para gravar na aba '{sheet_name}'.")
        return

    gc = get_client()
    sid = spreadsheet_id or config.GOOGLE_SHEET_ID
    spreadsheet = gc.open_by_key(sid)

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=10000, cols=50)

    df = pd.DataFrame(data)
    df = df.fillna("")

    headers = df.columns.tolist()
    values = df.values.tolist()

    worksheet.clear()
    worksheet.update([headers] + values)

    print(f"  Aba '{sheet_name}' atualizada: {len(values)} linhas gravadas.")

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


def merge_sheet(sheet_name, new_data, dedup_keys, spreadsheet_id=None):
    """
    Mescla `new_data` à aba `sheet_name`, deduplicando por `dedup_keys`.

    Comportamento:
      - Se a aba não existe, cria com `new_data`.
      - Se existe, lê o conteúdo atual, remove linhas que batem com `new_data`
        nas chaves `dedup_keys`, anexa as novas linhas, e regrava tudo.
      - Mantém o histórico de dias anteriores intacto.

    Usado para dados de fontes com janela limitada (ex.: Clarity entrega apenas
    últimos 1-3 dias — precisamos acumular dia a dia em planilha).
    """
    if not new_data:
        print(f"  Sem dados novos para mesclar na aba '{sheet_name}'.")
        return

    gc = get_client()
    sid = spreadsheet_id or config.GOOGLE_SHEET_ID
    spreadsheet = gc.open_by_key(sid)

    new_df = pd.DataFrame(new_data).fillna("")

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        existing = worksheet.get_all_records() or []
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=20000, cols=50)
        existing = []

    if existing:
        old_df = pd.DataFrame(existing).fillna("")
        # Alinha colunas (se a estrutura mudou, junção tolerante)
        all_cols = list(dict.fromkeys(list(old_df.columns) + list(new_df.columns)))
        old_df = old_df.reindex(columns=all_cols, fill_value="")
        new_df = new_df.reindex(columns=all_cols, fill_value="")

        # Remove de old_df linhas com mesma chave que existem em new_df
        if all(k in old_df.columns for k in dedup_keys):
            new_keys = set(map(tuple, new_df[dedup_keys].astype(str).values.tolist()))
            mask = old_df[dedup_keys].astype(str).apply(tuple, axis=1).isin(new_keys)
            old_df = old_df[~mask]

        merged = pd.concat([old_df, new_df], ignore_index=True)
    else:
        merged = new_df

    headers = merged.columns.tolist()
    values  = merged.astype(str).where(merged.notna(), "").values.tolist()

    worksheet.clear()
    worksheet.update([headers] + values)
    print(f"  Aba '{sheet_name}' mesclada: {len(values)} linhas totais (+{len(new_df)} novas).")

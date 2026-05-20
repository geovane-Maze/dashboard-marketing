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


def merge_sheet(sheet_name, new_data, dedup_keys, spreadsheet_id=None,
                date_col=None, retention_days=None):
    """
    Mescla `new_data` à aba `sheet_name`, deduplicando por `dedup_keys`.

    Comportamento:
      - Se a aba não existe, cria com `new_data` (tamanho mínimo necessário).
      - Se existe, lê o conteúdo atual, remove linhas que batem com `new_data`
        nas chaves `dedup_keys`, anexa as novas linhas, e regrava tudo.
      - Se `date_col` e `retention_days` forem informados, descarta linhas
        com data anterior ao período de retenção (evita estourar limite de
        10 milhões de células do Google Sheets).

    Usado para dados de fontes com janela retroativa limitada — acumular dia a dia
    em planilha sem perder histórico.
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
        # Tamanho conservador — sheet expande automaticamente quando precisa.
        n_cols = max(len(new_df.columns) + 5, 20)
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=2000, cols=n_cols)
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

    # Retenção: descarta dados muito antigos para não estourar limite de células
    if date_col and retention_days and date_col in merged.columns:
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(days=retention_days)).isoformat()
        before = len(merged)
        merged = merged[merged[date_col].astype(str) >= cutoff].reset_index(drop=True)
        dropped = before - len(merged)
        if dropped > 0:
            print(f"  Retenção {retention_days}d: {dropped} linhas antigas descartadas.")

    headers = merged.columns.tolist()
    values  = merged.astype(str).where(merged.notna(), "").values.tolist()

    worksheet.clear()
    worksheet.update([headers] + values)
    print(f"  Aba '{sheet_name}' mesclada: {len(values)} linhas totais (+{len(new_df)} novas).")

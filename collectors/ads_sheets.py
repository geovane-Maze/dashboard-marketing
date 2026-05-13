import gspread
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ADS_SHEET_ID = "1GC9-gtQM--sgpEejMGh2_pfibIt9w_511cJ7Ct3ACYA"
ADS_TAB_NAME = "[CDC -B2B Franquadora] Criativos Facebook/Google"

# Planilha Google Ads com dados diários (inclui campanhas Performance Max)
GOOGLE_ADS_SHEET_ID = "1828k1fV55SSRuB8QJXFAnqIgAjECbwm4aZz-9FPySkI"
GOOGLE_ADS_TAB_NAME = "Atualizado 13.05"


def _get_client():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def _parse_number(value):
    if not value:
        return None
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except Exception:
        return None


def get_ads_data():
    print("Coletando dados de Meta Ads e Google Ads da planilha...")
    gc = _get_client()
    spreadsheet = gc.open_by_key(ADS_SHEET_ID)
    ws = spreadsheet.worksheet(ADS_TAB_NAME)
    rows = ws.get_all_values()

    meta_ads = []
    google_ads = []

    for row in rows[1:]:
        # Garante que a linha tem colunas suficientes
        while len(row) < 36:
            row.append("")

        # --- META ADS (colunas 0-16) ---
        if row[0] and row[0] != "Day":
            meta_ads.append({
                "data": row[0],
                "campanha": row[1],
                "conjunto": row[2],
                "anuncio": row[3],
                "data_criacao": row[4],
                "gasto": _parse_number(row[5]),
                "cliques_link": _parse_number(row[6]),
                "engajamento": _parse_number(row[7]),
                "permalink": row[8],
                "alcance": _parse_number(row[9]),
                "frequencia": _parse_number(row[10]),
                "impressoes": _parse_number(row[11]),
                "resultados": _parse_number(row[12]),
                "leads": _parse_number(row[13]),
                "leads_facebook": _parse_number(row[14]),
                "thumbnail": row[15],
                "leads_prospecta": _parse_number(row[16]),
            })

        # --- GOOGLE ADS (colunas 19-35) ---
        if row[19] and row[19] != "Day":
            google_ads.append({
                "data": row[19],
                "mes": row[20],
                "campanha": row[21],
                "grupo_anuncio": row[22],
                "anuncio": row[23],
                "gasto": _parse_number(row[24]),
                "cliques": _parse_number(row[25]),
                "impressoes": _parse_number(row[26]),
                "conversoes": _parse_number(row[27]),
                "total_cliques": _parse_number(row[35]),
            })

    print(f"  Meta Ads: {len(meta_ads)} linhas")
    print(f"  Google Ads: {len(google_ads)} linhas")
    return meta_ads, google_ads


def get_google_ads_sheet_data():
    """
    Lê dados do Google Ads da planilha exportada diariamente pelo Google Ads.
    Inclui campanhas Performance Max (invisíveis em ad_group queries da API).
    Cabeçalhos na linha 3, dados a partir da linha 4.
    Colunas: [0] Dia, [2] Campanha, [12] Conversões, [14] Custo, [19] Cliques, [21] Impr.
    """
    print("Coletando Google Ads da planilha diária (inclui PMax)...")
    gc = _get_client()
    spreadsheet = gc.open_by_key(GOOGLE_ADS_SHEET_ID)
    ws = spreadsheet.worksheet(GOOGLE_ADS_TAB_NAME)
    rows = ws.get_all_values()

    google_ads = []
    # Cabeçalhos na linha 3 (índice 2), dados a partir da linha 4 (índice 3)
    for row in rows[3:]:
        while len(row) < 22:
            row.append("")

        dia = row[0].strip()
        campanha = row[2].strip()
        if not dia or not campanha or dia.lower() in ("dia", "total") or campanha == "--":
            continue

        gasto = _parse_number(row[14])
        if not gasto:
            continue

        google_ads.append({
            "data": dia,
            "campanha": campanha,
            "gasto": gasto,
            "cliques": _parse_number(row[19]) or 0,
            "impressoes": _parse_number(row[21]) or 0,
            "conversoes": _parse_number(row[12]) or 0,
        })

    print(f"  Google Ads (planilha diária): {len(google_ads)} linhas")
    return google_ads

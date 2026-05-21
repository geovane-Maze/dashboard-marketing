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
GOOGLE_ADS_SHEET_ID = "1TJ5HhoAjmezkXz_lxxVpym04rCG1Qb12BrelmpiL9lg"
GOOGLE_ADS_TAB_NAME = "Atualizado -"

# Planilha Google Ads no nível de ANÚNCIO (criativos) — texto + métricas
GOOGLE_ADS_CREATIVES_SHEET_ID = "1V6_cP63qmYoqfT5k7MNjDFfhQFnaKkqYY0Fr-hSsuIs"


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
    Lê dados do Google Ads da planilha exportada pelo Google Ads.
    Suporta dois formatos:
      - Formato DIÁRIO: [0]=Dia [2]=Campanha [12]=Conversões [14]=Custo [19]=Cliques [21]=Impr.
      - Formato AGREGADO: [0]=Status [1]=Campanha [11]=Conversões [13]=Custo [18]=Cliques [20]=Impr.
    """
    from datetime import date as _date
    print("Coletando Google Ads da planilha (inclui PMax)...")
    gc = _get_client()
    spreadsheet = gc.open_by_key(GOOGLE_ADS_SHEET_ID)

    # O nome da aba muda a cada atualização (ex.: "Google ads - 19.05").
    # Tenta o nome configurado; se não achar, usa a primeira aba da planilha.
    try:
        ws = spreadsheet.worksheet(GOOGLE_ADS_TAB_NAME)
    except Exception:
        ws = spreadsheet.worksheets()[0]
        print(f"  [aba '{GOOGLE_ADS_TAB_NAME}' não encontrada — usando '{ws.title}']")
    rows = ws.get_all_values()

    if len(rows) < 4:
        print("  Google Ads: planilha vazia ou sem dados suficientes.")
        return []

    # Detecta o formato pela linha de cabeçalho (linha 3, índice 2)
    header = [h.strip().lower() for h in rows[2]]
    is_daily = any("dia" in h or "day" in h for h in header[:3])
    is_aggregate = any("status" in h or "campanha" in h for h in header[:3]) and not is_daily

    google_ads = []

    if is_daily:
        # Formato antigo: dados diários com coluna Dia
        for row in rows[3:]:
            while len(row) < 22:
                row.append("")
            dia = row[0].strip()
            campanha = row[2].strip()
            if not dia or not campanha or dia.lower() in ("dia", "total", "day") or campanha == "--":
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
        print(f"  Google Ads (diário): {len(google_ads)} linhas")

    elif is_aggregate:
        # Formato agregado: totais por campanha sem breakdown diário.
        # NÃO sobrescrevemos o histórico diário (para não corromper os gráficos mensais).
        # Os dados históricos existentes na aba google_ads são mantidos.
        print(f"  AVISO: planilha no formato agregado (sem coluna de data por dia).")
        print(f"  Os dados históricos existentes serão mantidos. Para atualização completa,")
        print(f"  forneça uma planilha com breakdown diário (coluna 'Dia').")
        # Retorna vazio para que o writer NÃO sobrescreva a aba histórica
        return []

    else:
        print("  Google Ads: formato de planilha não reconhecido.")

    return google_ads


def get_google_ads_creatives_sheet_data():
    """
    Lê dados de CRIATIVOS do Google Ads (nível de anúncio, não de campanha).
    Planilha tem 1 linha por (dia, anúncio) com textos + métricas.

    Estrutura esperada:
      Linha 1: título "Relatório de anúncios"
      Linha 2: período "1 de janeiro de 2026 - 20 de maio de 2026"
      Linha 3: header com 96 colunas
      Linha 4+: dados

    Retorna lista de dicts (1 por linha de dia x anúncio):
      data, anuncio, campanha, grupo, tipo, status, url_final, qualidade,
      headlines (lista até 15), descriptions (lista até 5), cta,
      custo, conversoes, custo_por_conversao
    """
    print("Coletando criativos Google Ads (textos por anúncio)...")
    gc = _get_client()
    spreadsheet = gc.open_by_key(GOOGLE_ADS_CREATIVES_SHEET_ID)
    # Pega a primeira aba (nome muda a cada export)
    ws = spreadsheet.worksheets()[0]
    print(f"  Aba: {ws.title}")
    rows = ws.get_all_values()

    if len(rows) < 4:
        print("  Sem dados suficientes.")
        return []

    header = rows[2]
    def col(name):
        try:
            return header.index(name)
        except ValueError:
            return None

    I = {
        'dia':       col('Dia'),
        'status_ad': col('Status do anúncio'),
        'url':       col('URL final'),
        'nome_ad':   col('Nome do anúncio'),
        'campanha':  col('Campanha'),
        'grupo':     col('Grupo de anúncios'),
        'tipo':      col('Tipo de anúncio'),
        'qualidade': col('Qualidade do anúncio'),
        'cta':       col('Texto de call-to-action'),
        'custo':     col('Custo'),
        'conv':      col('Conversões'),
        'cpc':       col('Custo / conv.'),
    }

    # Indices dos 15 títulos e 5 descrições
    title_idx = [col(f'Título {i}') for i in range(1, 16)]
    desc_idx  = [col(f'Descrição {i}') for i in range(1, 6)]

    def _clean(v):
        v = (v or '').strip()
        return '' if v in ('--', '') else v

    out = []
    skipped = 0
    for r in rows[3:]:
        # Garante tamanho
        while len(r) < 96:
            r.append('')

        dia = _clean(r[I['dia']] if I['dia'] is not None else '')
        nome = _clean(r[I['nome_ad']] if I['nome_ad'] is not None else '')

        # Filtros básicos: ignora linhas sem data ou sem nome
        if not dia or dia.lower() in ('dia', 'total', 'day'):
            skipped += 1
            continue
        # Sem nome de anúncio (search dinâmicos) — não dá pra rankear individualmente
        if not nome:
            skipped += 1
            continue

        headlines = [_clean(r[i]) for i in title_idx if i is not None]
        headlines = [h for h in headlines if h]
        descriptions = [_clean(r[i]) for i in desc_idx if i is not None]
        descriptions = [d for d in descriptions if d]

        out.append({
            'data':        dia,
            'anuncio':     nome,
            'campanha':    _clean(r[I['campanha']] if I['campanha'] is not None else ''),
            'grupo':       _clean(r[I['grupo']] if I['grupo'] is not None else ''),
            'tipo':        _clean(r[I['tipo']] if I['tipo'] is not None else ''),
            'status':      _clean(r[I['status_ad']] if I['status_ad'] is not None else ''),
            'url_final':   _clean(r[I['url']] if I['url'] is not None else ''),
            'qualidade':   _clean(r[I['qualidade']] if I['qualidade'] is not None else ''),
            'cta':         _clean(r[I['cta']] if I['cta'] is not None else ''),
            'headlines':   ' | '.join(headlines[:5]),  # top 5 unidos em string
            'descriptions':' | '.join(descriptions[:2]),
            'custo':       _parse_number(r[I['custo']]) or 0,
            'conversoes':  _parse_number(r[I['conv']]) or 0,
            'custo_por_conversao': _parse_number(r[I['cpc']]) or 0,
        })

    print(f"  Criativos Google: {len(out)} linhas (puladas: {skipped})")
    return out

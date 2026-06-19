import os
import json
import time

import gspread
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ADS_SHEET_ID = "1GC9-gtQM--sgpEejMGh2_pfibIt9w_511cJ7Ct3ACYA"
ADS_TAB_NAME = "[CDC -B2B Franquadora] Criativos Facebook/Google"

# Snapshot dos thumbnails de criativo — rede de segurança contra falhas
# transitórias (503/429) ao ler a planilha antiga (39k linhas). Se o read ao
# vivo falhar, usamos o último snapshot bom para NUNCA deixar os criativos sem
# imagem. Atualizado a cada read bem-sucedido.
THUMBS_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "creative_thumbs.json"
)

# Planilha Google Ads com dados diários (inclui campanhas Performance Max)
# DEPRECATED: substituído pela Cronograma (export automático via Adveronix).
# Mantido aqui só para compatibilidade caso alguém queira voltar ao fluxo manual.
GOOGLE_ADS_SHEET_ID = "159NJH6tuiBQhg9PsnTuy7MNx3msEGqUh7f8TNXAEt54"
GOOGLE_ADS_TAB_NAME = "Atualizado -"

# Planilha Google Ads no nível de ANÚNCIO (criativos) — texto + métricas
GOOGLE_ADS_CREATIVES_SHEET_ID = "1dbK3qov09Q1vO43U4JThuIp_YVyaTAXTkiuAcE3XL8I"

# Planilha "Cronograma - Clínica da Cidade" — export automático via Adveronix.
# Substituiu o fluxo manual de copiar/colar planilha do Google Ads.
CRONOGRAMA_SHEET_ID = "19rDFjMX7y7L1_-1BMSBUNlyKOsduX8S3RY5C5BqVxKI"
CRONOGRAMA_GOOGLE_TAB = "B2B - Google Banco de Dados"
CRONOGRAMA_META_TAB = "B2B - Facebook Banco de Dados"


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
    Coleta dados do Google Ads da planilha "Cronograma - Clínica da Cidade",
    aba "B2B - Google Banco de Dados" — alimentada automaticamente pelo Adveronix.

    Estrutura da planilha origem:
      Col 0: Day            (data ex: '2026-06-09')
      Col 1: Month          (1º do mês, não usado)
      Col 2: Campaign Name
      Col 3: Ad Name        (não usado — agregamos por campanha+data)
      Col 4: Cost (Spend)   (formato pt-BR com vírgula)
      Col 5: Clicks
      Col 6: Impressions
      Col 7: Conversions

    Como cada (data, campanha) pode ter várias linhas (1 por anúncio), agregamos
    somando todas as métricas por (data, campanha) pra manter compatibilidade
    com o formato da aba google_ads do nosso banco.
    """
    from collections import defaultdict
    print(f"Coletando Google Ads da Cronograma (Adveronix)...")
    gc = _get_client()
    spreadsheet = gc.open_by_key(CRONOGRAMA_SHEET_ID)

    try:
        ws = spreadsheet.worksheet(CRONOGRAMA_GOOGLE_TAB)
    except Exception:
        print(f"  ERRO: aba '{CRONOGRAMA_GOOGLE_TAB}' não encontrada na planilha Cronograma.")
        return []

    rows = ws.get_all_values()
    if len(rows) < 2:
        print("  Cronograma Google Ads: planilha vazia.")
        return []

    # Header check — confirma que estamos lendo a aba certa
    header = [h.strip().lower() for h in rows[0]]
    if not (header and header[0] == "day" and "campaign name" in header):
        print(f"  AVISO: header inesperado. Encontrado: {rows[0][:8]}")
        return []

    # Agrega por (data, campanha) — uma campanha pode ter várias ads no mesmo dia
    agg = defaultdict(lambda: {"gasto": 0.0, "cliques": 0, "impressoes": 0, "conversoes": 0.0})
    for row in rows[1:]:
        if len(row) < 8:
            continue
        day      = row[0].strip()
        campanha = row[2].strip()
        if not day or not campanha:
            continue
        # Pula totais/footers
        if day.lower() in ("day", "total"):
            continue

        gasto      = _parse_number(row[4]) or 0
        cliques    = _parse_number(row[5]) or 0
        impressoes = _parse_number(row[6]) or 0
        conversoes = _parse_number(row[7]) or 0

        key = (day, campanha)
        agg[key]["gasto"]      += gasto
        agg[key]["cliques"]    += cliques
        agg[key]["impressoes"] += impressoes
        agg[key]["conversoes"] += conversoes

    # Converte pra lista no formato esperado pelo nosso writer
    google_ads = []
    for (data, campanha), m in agg.items():
        google_ads.append({
            "data":       data,
            "campanha":   campanha,
            "gasto":      round(m["gasto"], 2),
            "cliques":    int(m["cliques"]),
            "impressoes": int(m["impressoes"]),
            "conversoes": round(m["conversoes"], 2),
        })

    # Ordena por data crescente
    google_ads.sort(key=lambda r: r["data"])
    if google_ads:
        print(f"  Google Ads (Cronograma): {len(google_ads)} linhas | "
              f"de {google_ads[0]['data']} até {google_ads[-1]['data']}")
    else:
        print("  Google Ads (Cronograma): sem dados.")
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


def _get_creative_thumbnails():
    """
    Mapa {ad_name: thumbnail_url} a partir da planilha antiga (ADS_SHEET),
    coluna "Creative Thumbnail" — URLs do CDN de anúncios (scontent.xx.fbcdn.net),
    que renderizam direto em <img> (diferente do permalink do Instagram, que é
    bloqueado por referer no navegador).

    O Adveronix (aba Cronograma) NÃO exporta a imagem do criativo, só o permalink.
    Por isso buscamos o thumbnail aqui e cruzamos por "Ad Name" (match exato 1:1).
    As URLs expiram (param oe=), mas a planilha é atualizada continuamente e a
    coleta roda 3x/dia, então o link fica sempre fresco — igual ao fluxo antigo.

    ROBUSTEZ: a planilha tem ~39k linhas e o Google às vezes devolve 503/429 no
    read pesado. Fazemos retry com backoff e, se ainda assim falhar, caímos no
    snapshot salvo (THUMBS_SNAPSHOT_FILE) — assim os criativos NUNCA ficam sem
    imagem por uma falha transitória. Todo read bem-sucedido atualiza o snapshot.
    """
    rows = None
    last_err = None
    for attempt in range(4):
        try:
            gc = _get_client()
            rows = gc.open_by_key(ADS_SHEET_ID).worksheet(ADS_TAB_NAME).get_all_values()
            break
        except Exception as e:
            last_err = e
            wait = 3 * (attempt + 1)
            print(f"  AVISO: read de thumbnails falhou (tentativa {attempt+1}/4): {e}. Retry em {wait}s.")
            time.sleep(wait)

    if rows is None:
        snap = _load_thumbs_snapshot()
        print(f"  FALLBACK: usando snapshot de thumbnails ({len(snap)} anúncios). Último erro: {last_err}")
        return snap

    if len(rows) < 2:
        return _load_thumbs_snapshot()

    header = [h.strip().lower() for h in rows[0]]
    try:
        iAd = header.index("ad name")
        iTh = header.index("creative thumbnail")
    except ValueError:
        print("  AVISO: colunas 'Ad Name'/'Creative Thumbnail' não encontradas. Usando snapshot.")
        return _load_thumbs_snapshot()

    thumbs = {}
    for r in rows[1:]:
        if len(r) <= max(iAd, iTh):
            continue
        ad = r[iAd].strip()
        th = r[iTh].strip()
        if ad and th.startswith("http"):
            thumbs[ad] = th  # linhas em ordem cronológica → última (mais recente) vence

    if thumbs:
        _save_thumbs_snapshot(thumbs)
        print(f"  Thumbnails de criativo (planilha antiga): {len(thumbs)} anúncios.")
        return thumbs

    # leu mas veio vazio (planilha sem coluna preenchida?) → não regride, usa snapshot
    print("  AVISO: planilha antiga sem thumbnails preenchidos. Usando snapshot.")
    return _load_thumbs_snapshot()


def _load_thumbs_snapshot():
    try:
        with open(THUMBS_SNAPSHOT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"  AVISO: não consegui ler snapshot de thumbnails: {e}")
        return {}


def _save_thumbs_snapshot(thumbs):
    try:
        os.makedirs(os.path.dirname(THUMBS_SNAPSHOT_FILE), exist_ok=True)
        with open(THUMBS_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump(thumbs, f, ensure_ascii=False)
    except Exception as e:
        print(f"  AVISO: não consegui salvar snapshot de thumbnails: {e}")


def get_meta_ads_sheet_data():
    """
    Coleta Meta Ads (nível de ANÚNCIO) da planilha "Cronograma - Clínica da Cidade",
    aba "B2B - Facebook Banco de Dados" — alimentada automaticamente pelo Adveronix.

    Substitui o fluxo antigo (API quebrada + export manual incompleto). Cobre TODOS
    os criativos ativos por campanha/conjunto/anúncio.

    Estrutura origem:
      Day, Campaign Name, Ad Set Name, Ad Name, Date Created, Amount Spent,
      Link Clicks, Post Engagement, Creative Instagram Permalink, Reach,
      Frequency, Impressions, Purchases, Results, Cost per Result, ...

    Agrega por (Day, Campaign, Ad Set, Ad) e devolve no formato que o ETL
    (aggregate_meta_ads) espera: data, campanha, conjunto, anuncio, gasto,
    cliques_link, impressoes, leads, permalink.

    Obs: "leads" usa a coluna Results do Meta (resultado de otimização). O lead
    REAL de franquia é cruzado depois no ETL via CRM (leads_rd por utm_content).
    """
    from collections import defaultdict
    print("Coletando Meta Ads da Cronograma (Adveronix - Facebook)...")
    gc = _get_client()
    ss = gc.open_by_key(CRONOGRAMA_SHEET_ID)
    try:
        ws = ss.worksheet(CRONOGRAMA_META_TAB)
    except Exception:
        print(f"  ERRO: aba '{CRONOGRAMA_META_TAB}' não encontrada.")
        return []

    rows = ws.get_all_values()
    if len(rows) < 2:
        print("  Cronograma Meta: planilha vazia.")
        return []

    header = [h.strip().lower() for h in rows[0]]
    def col(name):
        try:
            return header.index(name)
        except ValueError:
            return None
    iDay  = col("day")
    iCamp = col("campaign name")
    iSet  = col("ad set name")
    iAd   = col("ad name")
    iSpent = col("amount spent")
    iClk  = col("link clicks")
    iImp  = col("impressions")
    iRes  = col("results")
    iLink = col("creative instagram permalink")
    if iDay is None or iCamp is None or iAd is None:
        print(f"  AVISO: header inesperado. Encontrado: {rows[0][:6]}")
        return []

    agg = defaultdict(lambda: {"gasto": 0.0, "cliques_link": 0.0, "impressoes": 0.0, "leads": 0.0, "permalink": ""})
    for r in rows[1:]:
        if len(r) <= iAd:
            continue
        day = r[iDay].strip()
        camp = r[iCamp].strip()
        anuncio = r[iAd].strip()
        if not day or day.lower() in ("day", "total") or not anuncio:
            continue
        conj = r[iSet].strip() if iSet is not None and len(r) > iSet else ""
        key = (day, camp, conj, anuncio)
        a = agg[key]
        a["gasto"]        += _parse_number(r[iSpent]) or 0 if iSpent is not None else 0
        a["cliques_link"] += _parse_number(r[iClk]) or 0 if iClk is not None else 0
        a["impressoes"]   += _parse_number(r[iImp]) or 0 if iImp is not None else 0
        a["leads"]        += _parse_number(r[iRes]) or 0 if iRes is not None else 0
        if iLink is not None and len(r) > iLink and r[iLink].strip():
            a["permalink"] = r[iLink].strip()

    thumbs = _get_creative_thumbnails()  # {ad_name: thumbnail_url} da planilha antiga

    out = []
    for (day, camp, conj, anuncio), m in agg.items():
        out.append({
            "data": day, "campanha": camp, "conjunto": conj, "anuncio": anuncio,
            "gasto": round(m["gasto"], 2), "cliques_link": int(m["cliques_link"]),
            "impressoes": int(m["impressoes"]), "leads": round(m["leads"], 2),
            "permalink": m["permalink"], "thumbnail": thumbs.get(anuncio, ""),
        })
    out.sort(key=lambda r: r["data"])
    if out:
        print(f"  Meta Ads (Cronograma): {len(out)} linhas | de {out[0]['data']} até {out[-1]['data']}")
    return out

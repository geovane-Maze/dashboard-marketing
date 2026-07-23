#!/usr/bin/env python3
"""
Generate aggregated JSON data for the marketing dashboard.
Run after main.py. Reads from Google Sheets and writes to dashboard/data/summary.json.
"""

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REPASSE_KEYWORDS = ["taguatinga", "maringá", "maringa", "praia grande"]

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "data"
)


def get_client():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def read_sheet(gc, sheet_name):
    spreadsheet = gc.open_by_key(config.GOOGLE_SHEET_ID)
    ws = spreadsheet.worksheet(sheet_name)
    rows = ws.get_all_values()
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(cell.strip() for cell in row)]


# ════════════════════════════════════════════════════════════════════
# BACKFILL de leads importados (2 bases de outro CRM importadas no RD)
# ════════════════════════════════════════════════════════════════════
# As bases entraram no RD em maio/2026 SEM utm_source e com a data de
# IMPORTAÇÃO (não a original). Resultado: ~926 leads pagos viravam "orgânico"
# e todos caíam em maio/2026. O arquivo data/imports_backfill.json
# (gerado a partir do export das planilhas, cruzado por e-mail → id do lead)
# devolve a fonte real (utm_source canônico) e a data original (criado_em).
# Para desfazer: basta remover/zerar esse arquivo — o ETL volta ao normal.
IMPORTS_BACKFILL_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "imports_backfill.json"
)


def load_imports_backfill():
    """Lê {lead_id: {criado_em?, utm_source?}}. Silencioso se o arquivo não existir."""
    try:
        with open(IMPORTS_BACKFILL_FILE, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  Backfill de importados: {len(data)} leads ({IMPORTS_BACKFILL_FILE}).")
        return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"  AVISO: não consegui ler o backfill de importados: {e}")
        return {}


def apply_imports_backfill(leads, backfill):
    """
    Corrige in-place os leads importados: data original (criado_em) e fonte
    (utm_source) quando ausente. Só toca nos ids presentes no backfill.
    """
    if not backfill:
        return leads
    n_data = n_src = 0
    for lead in leads:
        entry = backfill.get(str(lead.get("id", "")).strip())
        if not entry:
            continue
        if entry.get("criado_em"):
            lead["criado_em"] = entry["criado_em"]
            n_data += 1
        # só preenche fonte se o lead não tiver uma utm_source válida
        if entry.get("utm_source") and not (lead.get("utm_source") or "").strip():
            lead["utm_source"] = entry["utm_source"]
            n_src += 1
    print(f"  Backfill aplicado: data corrigida em {n_data} leads, fonte em {n_src}.")
    return leads


# ════════════════════════════════════════════════════════════════════
# MATCHING utm_content (CRM) ↔ anuncio (Meta Ads)
# ════════════════════════════════════════════════════════════════════
_TOKEN_STOP = {
    'anuncio', 'ad', 'ads', 'v1', 'v2', 'v3', 'v4', 'v5',
    'de', 'da', 'do', 'a', 'o', 'e', 'com', 'para', 'no', 'na', 'os', 'as',
    'estatico', 'animado', 'video', 'vídeo',
}

def _tokens(s):
    """Normaliza string em conjunto de tokens significativos (sem acento, lowercase, sem stop words)."""
    if not s:
        return set()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower()
    parts = re.split(r'[^a-z0-9]+', s)
    return {p for p in parts if p and p not in _TOKEN_STOP and len(p) >= 3}

def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def attach_google_campaign_leads(google_agg, leads):
    """
    Leads CRM por CAMPANHA Google via utm_campaign DIRETO (grava `leads` no
    google_ads.campaign_daily). Antes a coluna "Leads CRM" da tabela de campanhas
    vinha só do matching utm_content ↔ nome de anúncio — campanhas cujos anúncios
    não casam por nome (ex.: DG.Grupo.Por.Cidade, utm_content genérico) mostravam
    0 leads mesmo com leads reais no CRM. utm_campaign → nome da campanha por
    containment de tokens (mesma régua do infer_utm_source_quebrada); sem match
    inequívoco, não atribui (decomposição nunca excede o KPI por fonte).
    """
    names = google_agg.get("campaign_names") or []
    pools = [(n, _tokens(n)) for n in names]
    cache = {}

    def resolve(c):
        if c not in cache:
            tc = _tokens(c)
            best, bn = 0.0, None
            for n, ts in pools:
                if ts and tc:
                    cov = len(tc & ts) / len(tc)
                    if cov > best:
                        best, bn = cov, n
            cache[c] = bn if best >= 0.6 else None
        return cache[c]

    per = defaultdict(int)
    for l in leads:
        if (l.get("utm_source") or "").strip() != "googlecpc":
            continue
        c = (l.get("utm_campaign") or "").strip()
        dia = parse_date_to_day(l.get("criado_em"))
        if not c or not dia:
            continue
        camp = resolve(c)
        if camp:
            per[(camp, dia)] += 1

    rows = google_agg.get("campaign_daily") or []
    idx = {(r["campanha"], r["data"]): r for r in rows}
    for (camp, dia), n in per.items():
        r = idx.get((camp, dia))
        if r is None:
            r = {"campanha": camp, "data": dia, "gasto": 0, "conversoes": 0,
                 "impressoes": 0, "cliques": 0}
            rows.append(r)
            idx[(camp, dia)] = r
        r["leads"] = n
    google_agg["campaign_daily"] = rows
    total = sum(per.values())
    if total:
        print(f"    Leads CRM por campanha Google (utm_campaign direto): {total} leads atribuídos")
    return google_agg


def attach_google_group_leads(gc_agg, google_agg, leads, gc_rows):
    """
    Leads CRM por GRUPO Google via utm_term (estado/UF), para leads SEM rastreio
    por anúncio. Caso DG.Grupo.Por.Cidade: o utm_content é genérico e não casa com
    nenhum nome de anúncio — a campanha mostrava 13 leads e TODOS os grupos/anúncios
    mostravam 0 (e a régua recomendava "Pausar" com base no 0 falso). Mas o utm_term
    traz o estado ('Cidade.Sao.Paulo') e os grupos são '[ESTADO - SP] ...': dá pra
    atribuir ao GRUPO com evidência real. Regras:
      - só leads googlecpc cujo utm_content NÃO casa com anúncio (evita dupla contagem
        com o matching por nome, mesma régua Jaccard >= 0.4);
      - utm_campaign resolve a campanha (containment >= 0.6, como nas outras);
      - o UF do utm_term precisa bater com EXATAMENTE um grupo da campanha.
    O nível ANÚNCIO fica sem esses leads mesmo (não há evidência) — o front marca
    "dados insuf." em vez de "Ruim/Pausar".
    """
    ad_pool = [_tokens(r.get("anuncio") or "") for r in (gc_rows or [])]
    ad_pool = [t for t in ad_pool if t]

    def casa_com_anuncio(utm_content):
        tc = _tokens(utm_content)
        return bool(tc) and any(_jaccard(tc, ta) >= 0.4 for ta in ad_pool)

    grupos_por_camp = defaultdict(dict)   # campanha -> {grupo: set(UFs no nome)}
    for r in (gc_rows or []):
        c = (r.get("campanha") or "").strip()
        g = (r.get("grupo") or "").strip()
        if c and g and g not in grupos_por_camp[c]:
            grupos_por_camp[c][g] = set(re.findall(r"\b[A-Z]{2}\b", g))

    ESTADO_UF = {"sao paulo": "SP", "rio de janeiro": "RJ", "minas gerais": "MG",
                 "minas": "MG", "parana": "PR", "santa catarina": "SC",
                 "rio grande do sul": "RS", "bahia": "BA", "goias": "GO",
                 "espirito santo": "ES", "distrito federal": "DF"}

    def uf_do_term(t):
        t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
        t = re.sub(r"[^a-z]+", " ", t).strip()
        for nome, uf in ESTADO_UF.items():
            if nome in t:
                return uf
        m = re.search(r"\b(sp|rj|mg|pr|sc|rs|ba|go|es|df)\b", t)
        return m.group(1).upper() if m else None

    names = google_agg.get("campaign_names") or []
    pools = [(n, _tokens(n)) for n in names]
    cache = {}

    def resolve(c):
        if c not in cache:
            tc = _tokens(c)
            best, bn = 0.0, None
            for n, ts in pools:
                if ts and tc:
                    cov = len(tc & ts) / len(tc)
                    if cov > best:
                        best, bn = cov, n
            cache[c] = bn if best >= 0.6 else None
        return cache[c]

    per = defaultdict(int)
    for l in leads:
        if (l.get("utm_source") or "").strip() != "googlecpc":
            continue
        c = (l.get("utm_campaign") or "").strip()
        dia = parse_date_to_day(l.get("criado_em"))
        if not c or not dia:
            continue
        if casa_com_anuncio(l.get("utm_content") or ""):
            continue   # já entra via matching por anúncio (group_daily normal)
        camp = resolve(c)
        if not camp:
            continue
        uf = uf_do_term(l.get("utm_term") or "")
        if not uf:
            continue
        candidatos = [g for g, ufs in grupos_por_camp.get(camp, {}).items() if uf in ufs]
        if len(candidatos) != 1:
            continue
        per[(camp, candidatos[0], dia)] += 1

    rows = gc_agg.get("group_daily") or []
    idx = {(r["campanha"], r["grupo"], r["data"]): r for r in rows}
    for (camp, grupo, dia), n in per.items():
        r = idx.get((camp, grupo, dia))
        if r is None:
            r = {"data": dia, "campanha": camp, "grupo": grupo,
                 "gasto": 0, "conversoes": 0, "leads": 0}
            rows.append(r)
            idx[(camp, grupo, dia)] = r
        r["leads"] = round((r.get("leads") or 0) + n, 2)
    gc_agg["group_daily"] = rows

    # Nível ANÚNCIO: sem rastreio individual (utm_content genérico), o melhor possível
    # é uma ESTIMATIVA por rateio proporcional ao gasto dos anúncios do grupo no dia
    # (mesmo mecanismo do rateio Meta). Vai num campo SEPARADO `leads_est` — o front
    # exibe com "≈" pra nunca confundir estimativa com rastreio real.
    cad_rows = gc_agg.get("creative_group_daily") or []
    cad_idx = defaultdict(list)
    for r in cad_rows:
        cad_idx[(r["campanha"], r["grupo"], r["data"])].append(r)
    est_total = 0.0
    for (camp, grupo, dia), n in per.items():
        ads_dia = cad_idx.get((camp, grupo, dia)) or []
        tot_g = sum(r.get("gasto") or 0 for r in ads_dia)
        if tot_g <= 0:
            continue
        for r in ads_dia:
            frac = n * ((r.get("gasto") or 0) / tot_g)
            if frac:
                r["leads_est"] = round((r.get("leads_est") or 0) + frac, 2)
                est_total += frac

    tot = sum(per.values())
    if tot:
        print(f"    Leads CRM por grupo Google (utm_term/UF): {tot} leads atribuídos "
              f"({est_total:.1f} rateados como estimativa p/ anúncios)")
    return gc_agg


def infer_utm_source_quebrada(leads, meta_rows, google_rows):
    """
    Recupera a utm_source de leads cujo LINK da campanha veio QUEBRADO:
    '?%20utm_source=googlecpc&utm_medium=...' — o '%20' (espaço) corrompe o NOME do
    1º parâmetro, então o RD grava utm_source VAZIA mas utm_medium/campaign/term/
    content chegam preenchidos (descoberto pelo Geovane em 17/07/2026; ex.: campanha
    DG.Grupo.Por.Cidade, 16 leads, todos Google/gclid). Sem isso, lead PAGO cai
    como "orgânico" e some da atribuição por campanha.

    Preenche a fonte SÓ com evidência inequívoca, nesta ordem:
      1) votos: outros leads da MESMA utm_campaign com fonte paga conhecida (unânime);
      2) fallback: containment de tokens da utm_campaign nos NOMES de campanha das
         plataformas (google_ads/meta_ads) — ex.: 'DG.Grupo.Por.Cidade' cobre 100%
         dos tokens de '[DG] - [GRUPO POR CIDADE] - [SP]...' (Google).
    Links já foram corrigidos na origem; isto conserta o HISTÓRICO e cobre recaídas.
    """
    votos = defaultdict(Counter)
    for l in leads:
        s = (l.get("utm_source") or "").strip()
        c = (l.get("utm_campaign") or "").strip()
        if c and s in ("googlecpc", "metaads"):
            votos[c][s] += 1

    g_pool = [_tokens(r.get("campanha") or "") for r in (google_rows or [])]
    m_pool = [_tokens(r.get("campanha") or "") for r in (meta_rows or [])]

    def cobertura(tc, pool):
        best = 0.0
        for ts in pool:
            if ts:
                best = max(best, len(tc & ts) / len(tc))
        return best

    n, por_fonte, cache = 0, Counter(), {}
    for l in leads:
        if (l.get("utm_source") or "").strip():
            continue
        c = (l.get("utm_campaign") or "").strip()
        if not c:
            continue   # sem campanha não há evidência — fica como está (orgânico)
        if c not in cache:
            fonte = None
            v = votos.get(c)
            if v and len(v) == 1:
                fonte = next(iter(v))
            else:
                tc = _tokens(c)
                if tc:
                    gs, ms = cobertura(tc, g_pool), cobertura(tc, m_pool)
                    if gs >= 0.6 and gs > ms:
                        fonte = "googlecpc"
                    elif ms >= 0.6 and ms > gs:
                        fonte = "metaads"
            cache[c] = fonte
        if cache[c]:
            l["utm_source"] = cache[c]
            n += 1
            por_fonte[cache[c]] += 1
    if n:
        print(f"  UTM quebrada recuperada pela campanha: {n} leads -> {dict(por_fonte)}")
    return leads


def match_rd_leads_daily(meta_rows, google_creatives_rows, leads, threshold=0.4):
    """
    Faz matching token-based (Jaccard) entre utm_content de leads do RD Station
    e nomes de anúncios (Meta + Google). Retorna dicts diários.

    Como funciona:
      • Constroi pools separados de anúncios Meta e Google
      • Para cada lead com utm_content, decide o pool baseado em utm_source
      • Encontra melhor anúncio por Jaccard >= threshold
      • Atribui +1 ao (anúncio, data_de_criacao_do_lead)

    Returns:
      meta_daily:   {anuncio: {data: count}}
      google_daily: {anuncio: {data: count}}
      stats: {"meta_matched": N, "google_matched": N, "unmatched": N}
    """
    meta_pool = {(r.get("anuncio") or "").strip() for r in meta_rows}
    meta_pool.discard("")
    google_pool = {(r.get("anuncio") or "").strip() for r in google_creatives_rows}
    google_pool.discard("")

    meta_tokens   = [(a, _tokens(a)) for a in meta_pool]
    google_tokens = [(a, _tokens(a)) for a in google_pool]

    meta_daily   = defaultdict(lambda: defaultdict(int))
    google_daily = defaultdict(lambda: defaultdict(int))
    stats = {"meta_matched": 0, "google_matched": 0, "unmatched": 0}

    for lead in leads:
        utm_c = (lead.get("utm_content") or "").strip()
        if not utm_c:
            continue
        tc = _tokens(utm_c)
        if not tc:
            stats["unmatched"] += 1
            continue

        src = (lead.get("utm_source") or "").strip()
        day = parse_date_to_day(lead.get("criado_em"))
        if not day:
            continue

        if src == "metaads":
            pool, daily, key = meta_tokens, meta_daily, "meta_matched"
        elif src == "googlecpc":
            pool, daily, key = google_tokens, google_daily, "google_matched"
        else:
            continue

        best, best_score = None, 0.0
        for anuncio, ta in pool:
            s = _jaccard(tc, ta)
            if s > best_score:
                best_score, best = s, anuncio

        if best_score >= threshold and best:
            daily[best][day] += 1
            stats[key] += 1
        else:
            stats["unmatched"] += 1

    print(f"  [Match RD/Ads] Meta={stats['meta_matched']}  Google={stats['google_matched']}  sem_match={stats['unmatched']}")
    return dict(meta_daily), dict(google_daily), stats


def compute_creative_funnel_quality(meta_rows, google_creatives_rows, leads, deals, threshold=0.4):
    """
    Para cada criativo (Meta + Google), calcula:
      - Total de leads atribuídos
      - Quantos chegaram a etapas QUALIFICADAS (Reunião PDF, Apresentação BP, Envio COF, Workshop)
      - Taxa de qualidade = qualificados / leads_total
      - CPL geral e CPL por lead qualificado

    Usa matching Jaccard de utm_content + lookup de email no CRM.

    Returns: list ordenada por leads qualificados (decrescente).
    """
    PIPELINE = [
        'entrada de lead', 'tentativa de contato', 'qualificação',
        'qualificado não agendada', '1ª reunião agendada', '1ª reunião realizada',
        'reunião de bp agendada', 'reunião de bp realizada', 'envio de cof',
        'visita / reunião com jamil', 'análise financeira/jurídica', 'comitê final',
    ]
    QUALIFIED_FROM = 4  # '1ª reunião agendada' em diante = qualificado

    def stage_idx(etapa):
        el = (etapa or '').lower().strip()
        for i, s in enumerate(PIPELINE):
            if el == s or el in s or s in el: return i
        return -1

    # ── 1. Pools de anúncios (Meta + Google) ─────────────────────────────
    meta_pool = {(r.get("anuncio") or "").strip() for r in meta_rows}
    meta_pool.discard("")
    google_pool = {(r.get("anuncio") or "").strip() for r in google_creatives_rows}
    google_pool.discard("")
    meta_tokens   = [(a, _tokens(a)) for a in meta_pool]
    google_tokens = [(a, _tokens(a)) for a in google_pool]

    # ── 2. Email → etapa atual do CRM ───────────────────────────────────
    email_to_stage = {}
    for d in deals:
        email = (d.get("contato_email") or "").strip().lower()
        etapa = normalize_etapa(d.get("etapa") or "")
        if email:
            email_to_stage[email] = etapa

    # ── 3. Pra cada lead, match → criativo + lookup etapa ────────────────
    creative_funnel = defaultdict(lambda: {
        "source": None,
        "campanha": "",
        "thumbnail": "",
        "permalink": "",
        "leads_total": 0,
        "stages": defaultdict(int),
    })

    # Metadados de campanha/thumb (vem dos creatives agregados Meta e Google)
    meta_meta_by_ad = {}
    for r in meta_rows:
        a = (r.get("anuncio") or "").strip()
        if not a or a in meta_meta_by_ad: continue
        meta_meta_by_ad[a] = {
            "campanha": r.get("campanha", ""),
            "thumbnail": r.get("thumbnail", ""),
            "permalink": r.get("permalink", ""),
        }

    google_meta_by_ad = {}
    for r in google_creatives_rows:
        a = (r.get("anuncio") or "").strip()
        if not a or a in google_meta_by_ad: continue
        google_meta_by_ad[a] = {
            "campanha": r.get("campanha", ""),
        }

    for lead in leads:
        utm_c = (lead.get("utm_content") or "").strip()
        if not utm_c: continue
        tc = _tokens(utm_c)
        if not tc: continue

        src = (lead.get("utm_source") or "").strip()
        if src == "metaads":
            pool = meta_tokens; src_label = "meta"
        elif src == "googlecpc":
            pool = google_tokens; src_label = "google"
        else:
            continue

        best, best_score = None, 0.0
        for anuncio, ta in pool:
            s = _jaccard(tc, ta)
            if s > best_score:
                best_score, best = s, anuncio

        if best_score < threshold or not best:
            continue

        # Etapa atual do lead (via email → CRM)
        lead_email = (lead.get("email") or "").strip().lower()
        etapa = email_to_stage.get(lead_email, "Entrada de Lead")

        # Acumula
        cf = creative_funnel[best]
        cf["source"] = src_label
        if not cf["campanha"]:
            metadata = meta_meta_by_ad.get(best) if src_label == "meta" else google_meta_by_ad.get(best)
            if metadata:
                cf["campanha"]  = metadata.get("campanha", "")
                cf["thumbnail"] = metadata.get("thumbnail", "")
                cf["permalink"] = metadata.get("permalink", "")
        cf["leads_total"] += 1
        cf["stages"][etapa] += 1

    # ── 4. Soma gasto por anúncio (Meta + Google) ───────────────────────
    meta_gasto = defaultdict(float)
    for r in meta_rows:
        a = (r.get("anuncio") or "").strip()
        if a:
            try: meta_gasto[a] += float(str(r.get("gasto", 0) or 0).replace(",", "."))
            except: pass

    google_gasto = defaultdict(float)
    for r in google_creatives_rows:
        a = (r.get("anuncio") or "").strip()
        if a:
            try: google_gasto[a] += parse_num(r.get("custo"))
            except: pass

    # ── 5. Constrói resultado ────────────────────────────────────────────
    results = []
    for anuncio, info in creative_funnel.items():
        leads_total = info["leads_total"]
        stages = dict(info["stages"])
        qualif = sum(c for stage, c in stages.items() if stage_idx(stage) >= QUALIFIED_FROM)
        gasto = meta_gasto[anuncio] if info["source"] == "meta" else google_gasto[anuncio]
        results.append({
            "anuncio":        anuncio,
            "source":         info["source"],
            "campanha":       info["campanha"],
            "thumbnail":      info["thumbnail"],
            "permalink":      info["permalink"],
            "leads_total":    leads_total,
            "qualificados":   qualif,
            "quality_rate":   round(qualif / leads_total * 100, 1) if leads_total else 0,
            "gasto":          round(gasto, 2),
            "cpl":            round(gasto / leads_total, 2) if leads_total else 0,
            "cpl_qualificado": round(gasto / qualif, 2) if qualif else 0,
            "stages":         stages,
        })

    # Ordena por qualificados DESC, depois por quality_rate
    results.sort(key=lambda x: (-x["qualificados"], -x["quality_rate"]))
    return results


def attach_rd_leads_to_creatives(creatives_list, meta_rows, leads, threshold=0.4):
    """Conta leads do CRM por criativo via matching token-based de utm_content ↔ anuncio.

    Estratégia:
      1. Constrói pool com TODOS os anúncios da aba meta_ads (não só os top 50)
      2. Para cada lead com utm_source=metaads e utm_content, encontra anuncio
         com maior Jaccard >= threshold
      3. Acumula contagem por anuncio
      4. Anexa leads_rd e cpl_rd em cada item de creatives_list
    """
    # 1. Pool de TODOS os anúncios (do meta_ads raw)
    all_anuncios = set()
    for r in meta_rows:
        a = (r.get("anuncio") or "").strip()
        if a:
            all_anuncios.add(a)
    # Garante que os top creatives também estão no pool
    for c in creatives_list:
        all_anuncios.add(c["anuncio"])
    anuncio_tokens = [(a, _tokens(a)) for a in all_anuncios]

    # 2. Para cada lead metaads, achar melhor anuncio
    leads_per_anuncio = defaultdict(int)
    unmatched = 0
    for lead in leads:
        if (lead.get("utm_source") or "").strip() != "metaads":
            continue
        utm_c = lead.get("utm_content") or ""
        if not utm_c:
            continue
        tc = _tokens(utm_c)
        if not tc:
            unmatched += 1
            continue
        best, best_score = None, 0.0
        for anuncio, ta in anuncio_tokens:
            s = _jaccard(tc, ta)
            if s > best_score:
                best_score, best = s, anuncio
        if best_score >= threshold and best:
            leads_per_anuncio[best] += 1
        else:
            unmatched += 1

    # 3. Anexa em creatives_list
    for c in creatives_list:
        leads_rd = leads_per_anuncio.get(c["anuncio"], 0)
        c["leads_rd"] = leads_rd
        c["cpl_rd"] = round(c["gasto"] / leads_rd, 2) if leads_rd > 0 else 0

    total_matched = sum(leads_per_anuncio.values())
    print(f"  [Match RD/Meta] leads matched: {total_matched}, sem match: {unmatched}")
    return creatives_list


# ════════════════════════════════════════════════════════════════════
# CRIPTOGRAFIA AES-256-GCM (proteção por senha)
# ════════════════════════════════════════════════════════════════════
def upload_to_supabase(file_path: str) -> bool:
    """
    Faz upload do summary.json para o bucket privado 'dashboard-data' no Supabase Storage.
    Usa a service_role key (nunca exposta no front-end).
    Retorna True em caso de sucesso.
    """
    supabase_url = config.SUPABASE_URL
    service_key  = config.SUPABASE_SERVICE_KEY

    if not supabase_url or not service_key:
        print("  AVISO: SUPABASE_URL ou SUPABASE_SERVICE_KEY não definidos — upload ignorado.")
        return False

    try:
        from supabase import create_client, Client
        sb: Client = create_client(supabase_url, service_key)

        with open(file_path, "rb") as f:
            content = f.read()

        # upsert=True substitui o arquivo existente
        sb.storage.from_("dashboard-data").upload(
            path="summary.json",
            file=content,
            file_options={"content-type": "application/json", "upsert": "true"},
        )
        print(f"  >>> summary.json enviado ao Supabase Storage com sucesso!")
        return True

    except Exception as exc:
        print(f"  ERRO ao fazer upload para o Supabase: {exc}")
        return False


def dedupe_by_id(records, source_name=""):
    """Defensive dedup: remove registros com mesmo 'id' (mantém primeira ocorrência)."""
    if not records:
        return records
    seen = set()
    result = []
    dup_count = 0
    for r in records:
        rid = (r.get("id") or "").strip()
        if not rid:
            result.append(r)  # sem id: mantém (não é duplicação detectável)
            continue
        if rid in seen:
            dup_count += 1
            continue
        seen.add(rid)
        result.append(r)
    if dup_count > 0:
        print(f"  [Dedupe] {source_name}: {dup_count} duplicatas removidas ({len(result)} únicos).")
    return result


def parse_num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", ".").replace(" ", "").replace("R$", "").strip())
    except Exception:
        return 0.0


def _parse_dt(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            pass
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"]:
        try:
            return datetime.strptime(date_str[:10], fmt)
        except ValueError:
            pass
    return None


def parse_date_to_month(date_str):
    dt = _parse_dt(date_str)
    return dt.strftime("%Y-%m") if dt else None


def parse_date_to_day(date_str):
    dt = _parse_dt(date_str)
    return dt.strftime("%Y-%m-%d") if dt else None


STAGE_NORMALIZE = {
    # ── Funil atual do RD (12 etapas) ─────────────────────────────────────────
    'entrada de lead':                     'Entrada de Lead',
    'tentativa de contato':                'Tentativa de Contato',
    'qualificação':                        'Qualificação',
    'qualificacao':                        'Qualificação',
    'qualificado não agendada':            'Qualificado Não agendada',
    'qualificado nao agendada':            'Qualificado Não agendada',
    'reunião de bp agendada':              'Reunião de BP Agendada',
    'reuniao de bp agendada':              'Reunião de BP Agendada',
    'reunião de bp realizada':             'Reunião de BP Realizada',
    'reuniao de bp realizada':             'Reunião de BP Realizada',
    'visita / reunião com jamil':          'Visita / Reunião com Jamil',
    'visita / reuniao com jamil':          'Visita / Reunião com Jamil',
    # ── Legados/planejados (dados históricos) ─────────────────────────────────
    'tentativa de conexão':                'Tentativa de Conexão',
    'tentativa de conexao':                'Tentativa de Conexão',
    'lead respondente':                    'Lead Respondente',
    'prospect':                            'Prospect',
    '1ª reunião agendada':                 '1ª Reunião Agendada',
    '1a reunião agendada':                 '1ª Reunião Agendada',
    '1ª reuniao agendada':                 '1ª Reunião Agendada',
    '1a reuniao agendada':                 '1ª Reunião Agendada',
    '1ª reunião realizada':                '1ª Reunião Realizada',
    '1a reunião realizada':                '1ª Reunião Realizada',
    '1ª reuniao realizada':                '1ª Reunião Realizada',
    '1a reuniao realizada':                '1ª Reunião Realizada',
    'apresentação do business plan':       'Apresentação do Business Plan',
    'apresentacao do business plan':       'Apresentação do Business Plan',
    'envio de cof':                        'Envio de COF',
    'workshop':                            'Workshop',
    'análise financeira/jurídica':         'Análise Financeira/Jurídica',
    'analise financeira/juridica':         'Análise Financeira/Jurídica',
    'análise financeira / jurídica':       'Análise Financeira/Jurídica',
    'analise financeira / juridica':       'Análise Financeira/Jurídica',
    'comitê final':                        'Comitê Final',
    'comite final':                        'Comitê Final',
    # ── Etapas RENOMEADAS no CRM — legados mesclados nos nomes novos ──────────
    'pré-qualificado':                     'Prospect',
    'pre-qualificado':                     'Prospect',
    'pré qualificado':                     'Prospect',
    'pre qualificado':                     'Prospect',
    'reunião pdf':                         '1ª Reunião Agendada',
    'reuniao pdf':                         '1ª Reunião Agendada',
    'reunião de pdf':                      '1ª Reunião Agendada',
    # ── Etapas legadas antigas (dados históricos) ────────────────────────────
    'aprovação final':                     'Aprovação Final',
    'aprovacao final':                     'Aprovação Final',
    'contato inicial':                     'Contato Inicial',
    'nutrição 1':                          'Nutrição 1',
    'nutricao 1':                          'Nutrição 1',
    'nutrição 2':                          'Nutrição 2',
    'nutricao 2':                          'Nutrição 2',
    # ── Sistema ──────────────────────────────────────────────────────────────
    'etapa descarte':                      'Etapa Descarte',
}


def normalize_etapa(etapa):
    if not etapa:
        return 'sem etapa'
    return STAGE_NORMALIZE.get(etapa.strip().lower(), etapa.strip())


def is_repasse(campaign_name):
    if not campaign_name:
        return False
    name_lower = campaign_name.lower()
    return any(kw in name_lower for kw in REPASSE_KEYWORDS)


def aggregate_leads(leads):
    monthly = defaultdict(lambda: {
        "total": 0, "qualificados": 0,
        "pago": 0, "organico": 0, "googlecpc": 0, "metaads": 0,
    })
    daily = defaultdict(lambda: {"total": 0, "qualificados": 0})
    by_source = defaultdict(int)
    by_canal = defaultdict(int)
    by_lifecycle = defaultdict(int)
    by_capital = defaultdict(int)
    by_prazo = defaultdict(int)
    prazo_daily = defaultdict(lambda: defaultdict(int))     # dia → prazo → count
    capital_daily = defaultdict(lambda: defaultdict(int))   # dia → capital → count (filtro de período no front)
    canal_monthly = defaultdict(lambda: defaultdict(int))
    canal_daily = defaultdict(lambda: defaultdict(int))

    for lead in leads:
        criado = lead.get("criado_em")
        mes = parse_date_to_month(criado)
        dia = parse_date_to_day(criado)
        lc = str(lead.get("lifecycle_stage") or "").lower()
        qualif = "qualif" in lc or "mql" in lc

        src_norm = (lead.get("utm_source") or "").strip()
        if mes:
            monthly[mes]["total"] += 1
            if qualif:
                monthly[mes]["qualificados"] += 1
            # Split pago/orgânico por mês (mesma regra do dashboard: pago = googlecpc/metaads).
            # Reflete o backfill dos leads importados (fonte real recuperada do export).
            if src_norm == "googlecpc":
                monthly[mes]["googlecpc"] += 1
                monthly[mes]["pago"] += 1
            elif src_norm == "metaads":
                monthly[mes]["metaads"] += 1
                monthly[mes]["pago"] += 1
            else:
                monthly[mes]["organico"] += 1
        if dia:
            daily[dia]["total"] += 1
            if qualif:
                daily[dia]["qualificados"] += 1

        src = lead.get("utm_source") or lead.get("canal") or "direto"
        by_source[src] += 1

        canal = lead.get("canal") or "sem canal"
        by_canal[canal] += 1

        if mes:
            canal_monthly[mes][canal] += 1
        if dia:
            canal_daily[dia][canal] += 1

        lc2 = lead.get("lifecycle_stage") or "sem estágio"
        by_lifecycle[lc2] += 1

        capital = lead.get("capital_disponivel") or "não informado"
        by_capital[capital] += 1
        if dia:
            capital_daily[dia][capital] += 1

        prazo = lead.get("prazo_abertura") or "não informado"
        by_prazo[prazo] += 1
        if dia:
            prazo_daily[dia][prazo] += 1

    pagos = sum(v for k, v in by_canal.items() if any(kw in k.lower() for kw in ["busca paga", "paid", "cpc", " paga"]))
    organicos = len(leads) - pagos

    return {
        "total": len(leads),
        "pagos": pagos,
        "organicos": organicos,
        "monthly": [{"mes": k, **v} for k, v in sorted(monthly.items())],
        "daily": [{"data": k, **v} for k, v in sorted(daily.items())],
        "by_source": [
            {"source": k, "total": v}
            for k, v in sorted(by_source.items(), key=lambda x: -x[1])[:15]
        ],
        "by_canal": [
            {"canal": k, "total": v}
            for k, v in sorted(by_canal.items(), key=lambda x: -x[1])
        ],
        "by_lifecycle": [
            {"stage": k, "total": v}
            for k, v in sorted(by_lifecycle.items(), key=lambda x: -x[1])
        ],
        "by_capital": [
            {"capital": k, "total": v}
            for k, v in sorted(by_capital.items(), key=lambda x: -x[1])
            if k != "não informado"
        ],
        "by_prazo": [
            {"prazo": k, "total": v}
            for k, v in sorted(by_prazo.items(), key=lambda x: -x[1])
            if k != "não informado"
        ],
        "prazo_daily": [
            {"data": dia, "prazo": p, "total": count}
            for dia, prazos in sorted(prazo_daily.items())
            for p, count in prazos.items()
        ],
        "capital_daily": [
            {"data": dia, "capital": c, "total": count}
            for dia, capitais in sorted(capital_daily.items())
            for c, count in capitais.items()
        ],
        "canal_monthly": [
            {"mes": mes, "canal": c, "total": count}
            for mes, canals in sorted(canal_monthly.items())
            for c, count in canals.items()
        ],
        "canal_daily": [
            {"data": dia, "canal": c, "total": count}
            for dia, canals in sorted(canal_daily.items())
            for c, count in canals.items()
        ],
    }


def clean_loss_reason(m):
    """
    Limpa o motivo de perda para exibição: remove o prefixo de CATEGORIA
    (tudo antes do primeiro '/' ou ' - ') e mantém só o motivo em si.
    Normaliza separadores internos (',' e '/') para ' / '.

    Ex.: 'DESENGAJAMENTO DURANTE FUNIL/ Não responde'            -> 'Não responde'
         'LEADS INACESSÍVEIS/ Fornecedor,Consumidor/Oferta...'   -> 'Fornecedor / Consumidor / Oferta...'
         'DESENGAJAMENTO - Parou de se corresponder'             -> 'Parou de se corresponder'
         'Cliente optou por não realizar o projeto'              -> (sem separador, mantém igual)
    """
    if not m:
        return m
    s = str(m).strip()
    idx_slash = s.find('/')
    idx_dash = s.find(' - ')
    cands = [i for i in (idx_slash, idx_dash) if i != -1]
    if cands:
        i = min(cands)
        s = s[i + 1:] if i == idx_slash else s[i + 3:]
    s = re.sub(r'\s*[,/]\s*', ' / ', s).strip()
    return s


def aggregate_crm(deals, leads=None):
    by_stage = defaultdict(lambda: {"total": 0, "valor": 0.0, "ganhos": 0})
    active_stage = defaultdict(lambda: {"total": 0, "valor": 0.0})  # apenas ativos
    by_loss_reason = defaultdict(int)
    by_loss_reason_stage = defaultdict(lambda: defaultdict(int))  # motivo → etapa → count
    by_loss_stage = defaultdict(int)          # perdas por etapa do funil
    by_loss_utm_source = defaultdict(int)     # perdas por utm_source
    by_loss_utm_campaign = defaultdict(int)   # perdas por utm_campaign
    by_loss_utm_content = defaultdict(int)    # perdas por utm_content (anúncio)
    losses_daily = []                         # 1 linha por deal perdido (filtrável por data)
    by_responsavel = defaultdict(lambda: {"total": 0, "ganhos": 0, "valor": 0.0})
    monthly_won = defaultdict(lambda: {"total": 0, "valor": 0.0})
    monthly_stages = defaultdict(lambda: {
        "reuniao_pdf": 0, "apresentacao_bp": 0, "perdidos": 0,
        "reuniao_agendada": 0, "reuniao_realizada": 0,
    })

    # Índice de leads por e-mail para cruzar UTMs com os deals perdidos
    lead_by_email = {}
    if leads:
        for lead in leads:
            email = (lead.get("email") or "").strip().lower()
            if email:
                lead_by_email[email] = lead

    total_won = 0
    total_lost = 0
    total_value = 0.0

    def is_deal_importado(deal):
        # 164 deals entraram no RD em 04-05/05/2026 via importação em massa
        # (bases dos CRMs antigos) com deal_source "Formulário de CRM" e a data
        # de IMPORTAÇÃO no criado_em — distorciam qualquer visão por período.
        fonte_ascii = unicodedata.normalize("NFKD", str(deal.get("fonte") or ""))
        fonte_ascii = fonte_ascii.encode("ascii", "ignore").decode().strip().lower()
        return fonte_ascii.startswith("formulario de crm")

    def criado_efetivo_do(deal, lead):
        # Deals importados: a data real de origem é a do LEAD que os originou
        # (a aba leads já passa pelo imports_backfill, que devolve a data
        # original dos CRMs antigos). Sem lead casado, mantém a data de
        # importação — o front declara isso na conciliação.
        criado = deal.get("criado_em")
        if is_deal_importado(deal) and lead:
            lead_criado = lead.get("criado_em")
            if lead_criado and str(lead_criado)[:10] < str(criado or "9999")[:10]:
                return lead_criado
        return criado

    for deal in deals:
        etapa_raw = deal.get("etapa") or "sem etapa"
        etapa = normalize_etapa(etapa_raw)          # nome normalizado
        ganho_raw = str(deal.get("ganho") or "").lower()
        ganho = ganho_raw in ("true", "1", "sim", "yes")
        # win=False conta como PERDA mesmo SEM motivo registrado. Antes "perdido" vinha
        # só do motivo_perda, então 6 deals fechados-perdidos sem motivo eram contados
        # como ABERTOS e poluíam o funil ativo. A verdade é o flag ganho/win do RD.
        perdeu_flag = ganho_raw in ("false", "0", "nao", "não", "no")
        perdido = bool(deal.get("motivo_perda")) or perdeu_flag
        valor = parse_num(deal.get("valor_total"))
        deal_email = (deal.get("contato_email") or "").strip().lower()
        deal_lead = lead_by_email.get(deal_email)
        criado_efetivo = criado_efetivo_do(deal, deal_lead)

        by_stage[etapa]["total"] += 1
        by_stage[etapa]["valor"] += valor
        if ganho:
            by_stage[etapa]["ganhos"] += 1

        # Funil de ativos: exclui ganhos, perdidos e etapas de descarte
        EXCLUIR_ATIVO = {'etapa descarte', 'sem etapa'}
        if not ganho and not perdido and etapa.lower() not in EXCLUIR_ATIVO:
            active_stage[etapa]["total"] += 1
            active_stage[etapa]["valor"] += valor

        if ganho:
            total_won += 1
            total_value += valor
            mes = parse_date_to_month(deal.get("data_fechamento") or deal.get("criado_em"))
            if mes:
                monthly_won[mes]["total"] += 1
                monthly_won[mes]["valor"] += valor

        motivo = clean_loss_reason(deal.get("motivo_perda"))
        if perdido:
            motivo_lbl = motivo or "não informado"   # ghosts win=False sem motivo
            by_loss_reason[motivo_lbl] += 1
            by_loss_reason_stage[motivo_lbl][etapa] += 1
            by_loss_stage[etapa] += 1
            total_lost += 1

            # Cruzar UTMs via e-mail do contato
            lead = deal_lead
            if lead:
                src  = lead.get("utm_source")   or "não identificado"
                camp = lead.get("utm_campaign") or "não identificado"
                cont = lead.get("utm_content")  or "não identificado"
                by_loss_utm_source[src] += 1
                by_loss_utm_campaign[camp] += 1
                by_loss_utm_content[cont] += 1
            else:
                src = camp = cont = "não identificado"

            # Aggregação DIÁRIA para filtro por período no front-end.
            # "data"   = data de fechamento (quando a perda foi marcada).
            # "criado" = data de criação do negócio — usada para filtrar as perdas
            #            no MESMO eixo dos leads (perda = subconjunto dos leads
            #            que entraram no período, evitando perdas > leads).
            #            Deals importados usam a data ORIGINAL do lead (backfill).
            dia_perda = parse_date_to_day(deal.get("data_fechamento") or deal.get("criado_em"))
            dia_criado = parse_date_to_day(criado_efetivo)
            if dia_perda:
                loss_row = {
                    "data": dia_perda,
                    "criado": dia_criado,
                    "motivo": motivo_lbl,
                    "etapa": etapa,
                    "utm_source": src,
                    "utm_campaign": camp,
                    "utm_content": cont,
                }
                if is_deal_importado(deal):
                    loss_row["imp"] = 1
                losses_daily.append(loss_row)

        mes_criado = parse_date_to_month(criado_efetivo)
        if mes_criado:
            etapa_lower = etapa.lower()
            # reuniao_pdf = renomeada para "1ª Reunião Agendada" (mantém legado)
            if ("1ª reunião agendada" in etapa_lower or "1a reunião agendada" in etapa_lower
                    or "reunião pdf" in etapa_lower or "reuniao pdf" in etapa_lower):
                monthly_stages[mes_criado]["reuniao_pdf"] += 1
            if ("reunião de bp agendada" in etapa_lower or "reuniao de bp agendada" in etapa_lower
                    or "apresentação do business plan" in etapa_lower or "apresentacao do business plan" in etapa_lower):
                monthly_stages[mes_criado]["apresentacao_bp"] += 1
            if "reunião agendada" in etapa_lower or "reuniao agendada" in etapa_lower:
                monthly_stages[mes_criado]["reuniao_agendada"] += 1
            if "reunião realizada" in etapa_lower or "reuniao realizada" in etapa_lower:
                monthly_stages[mes_criado]["reuniao_realizada"] += 1
            if perdido:
                monthly_stages[mes_criado]["perdidos"] += 1

        resp = deal.get("responsavel") or "sem responsável"
        by_responsavel[resp]["total"] += 1
        if ganho:
            by_responsavel[resp]["ganhos"] += 1
            by_responsavel[resp]["valor"] += valor

    total_open = len(deals) - total_won - total_lost

    funnel = sorted(by_stage.items(), key=lambda x: -x[1]["total"])

    # Funil de ativos na ordem correta do pipeline
    PIPELINE_ORDER = [
        # Funil atual do RD (12 etapas) — ordem oficial
        'entrada de lead', 'tentativa de contato', 'qualificação', 'qualificacao',
        'qualificado não agendada', 'qualificado nao agendada',
        '1ª reunião agendada', '1ª reunião realizada',
        'reunião de bp agendada', 'reuniao de bp agendada',
        'reunião de bp realizada', 'reuniao de bp realizada',
        'envio de cof', 'visita / reunião com jamil', 'visita / reuniao com jamil',
        'análise financeira/jurídica', 'comitê final',
        # Etapas legadas/planejadas (dados históricos — ficam ao final)
        'tentativa de conexão', 'lead respondente', 'prospect',
        'apresentação do business plan', 'workshop',
        'aprovação final', 'contato inicial', 'nutrição 1', 'nutrição 2',
    ]
    def stage_sort_key(name):
        nl = name.lower()
        for i, s in enumerate(PIPELINE_ORDER):
            if nl == s or nl in s or s in nl:
                return i
        return 999

    active_funnel_sorted = sorted(active_stage.items(), key=lambda x: stage_sort_key(x[0]))

    # ── Lista minimal de deals para "Funil de Conversão do Período" no frontend ──
    # Permite filtro por data e cálculo de passed-through por etapa.
    # Mantém leve: só campos necessários (etapa normalizada + criado_em).
    deals_minimal = []
    for deal in deals:
        etapa = normalize_etapa(deal.get("etapa") or "sem etapa")
        # Fonte do lead (cruza por e-mail). Pago = googlecpc/metaads; resto = orgânico.
        email = (deal.get("contato_email") or "").strip().lower()
        lead = lead_by_email.get(email)
        # Deals IMPORTADOS (04-05/05/2026, fonte "Formulário de CRM") entram com a
        # data ORIGINAL do lead — sem isso, 174 negócios de jan-abr empilhavam em
        # maio e distorciam qualquer funil por período. Flag "imp" permite ao front
        # declarar a régua na tela.
        criado = parse_date_to_day(criado_efetivo_do(deal, lead))
        if not criado:
            continue
        src = (lead.get("utm_source") if lead else "") or ""
        fonte = "googlecpc" if src == "googlecpc" else ("metaads" if src == "metaads" else "organico")
        # Data de criação do LEAD que originou o negócio (quando casou por e-mail).
        # Permite ao front conciliar "leads do período" × "negócios do período":
        # negócio de julho pode vir de lead de junho (ex.: represa da Leadster) e
        # lead de julho pode ainda não ter negócio — os totais NÃO são o mesmo recorte.
        lead_criado = parse_date_to_day(lead.get("criado_em")) if lead else None
        # Status do negócio (mesma regra do C3: win=false conta como perda mesmo sem
        # motivo). Permite ao front montar "Negócios por Etapa" (abertos) RESPEITANDO
        # o filtro de período — antes usava o active_funnel global, que ignorava o filtro.
        g = str(deal.get("ganho") or "").lower()
        if g in ("true", "1", "sim", "yes"):
            st = "ganho"
        elif bool(deal.get("motivo_perda")) or g in ("false", "0", "nao", "não", "no"):
            st = "perdido"
        else:
            st = "aberto"
        row = {"etapa": etapa, "criado_em": criado, "fonte": fonte,
               "lead_criado": lead_criado, "st": st}
        if is_deal_importado(deal):
            row["imp"] = 1
        deals_minimal.append(row)

    # ── Perdas: separação pago vs orgânico ───────────────────────────────────
    # Considera-se "pago" qualquer lead cuja utm_source seja googlecpc ou metaads.
    # Os demais (direto, organico, e-mail, "não identificado", etc.) entram em
    # orgânico para que a soma feche com total_lost.
    PAID_SRCS = {"googlecpc", "metaads"}
    total_lost_pago     = sum(v for k, v in by_loss_utm_source.items() if k in PAID_SRCS)
    total_lost_organico = total_lost - total_lost_pago

    return {
        "total_deals": len(deals),
        "total_won": total_won,
        "total_lost": total_lost,
        "total_lost_pago": total_lost_pago,
        "total_lost_organico": total_lost_organico,
        "total_open": total_open,
        "total_active": sum(v["total"] for v in active_stage.values()),
        "total_value_won": round(total_value, 2),
        "taxa_fechamento": round(total_won / len(deals) * 100, 1) if deals else 0,
        "deals_minimal": deals_minimal,   # para Funil de Conversão do Período
        "funnel": [
            {"etapa": k, "total": v["total"], "valor": round(v["valor"], 2), "ganhos": v["ganhos"]}
            for k, v in funnel
        ],
        "active_funnel": [
            {"etapa": k, "total": v["total"], "valor": round(v["valor"], 2)}
            for k, v in active_funnel_sorted
        ],
        "losses": [
            {"motivo": k, "total": v}
            for k, v in sorted(by_loss_reason.items(), key=lambda x: -x[1])
        ],
        "losses_by_reason_stage": {
            motivo: [{"etapa": etapa, "total": cnt}
                     for etapa, cnt in sorted(stages.items(), key=lambda x: -x[1])]
            for motivo, stages in by_loss_reason_stage.items()
        },
        "losses_by_stage": [
            {"etapa": k, "total": v}
            for k, v in sorted(by_loss_stage.items(), key=lambda x: -x[1])
        ],
        "losses_by_utm_source": [
            {"utm": k, "total": v}
            for k, v in sorted(by_loss_utm_source.items(), key=lambda x: -x[1])
        ],
        "losses_by_utm_campaign": [
            {"utm": k, "total": v}
            for k, v in sorted(by_loss_utm_campaign.items(), key=lambda x: -x[1])
        ],
        "losses_by_utm_content": [
            {"utm": k, "total": v}
            for k, v in sorted(by_loss_utm_content.items(), key=lambda x: -x[1])
        ],
        # 1 linha por deal perdido, com data + dimensões — usado pelos filtros
        # da página "Gargalos & Perdas" no front-end.
        "losses_daily": losses_daily,
        "by_responsavel": [
            {"responsavel": k, "total": v["total"], "ganhos": v["ganhos"], "valor": round(v["valor"], 2)}
            for k, v in sorted(by_responsavel.items(), key=lambda x: -x[1]["total"])
        ],
        "monthly_won": [
            {"mes": k, "total": v["total"], "valor": round(v["valor"], 2)}
            for k, v in sorted(monthly_won.items())
        ],
        "monthly_stages": [
            {
                "mes": k,
                "reuniao_pdf": v["reuniao_pdf"],
                "apresentacao_bp": v["apresentacao_bp"],
                "perdidos": v["perdidos"],
                "reuniao_agendada": v["reuniao_agendada"],
                "reuniao_realizada": v["reuniao_realizada"],
            }
            for k, v in sorted(monthly_stages.items())
        ],
    }


def aggregate_meta_ads(rows, leads_daily_map=None):
    monthly = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
        "expansao_gasto": 0.0, "repasse_gasto": 0.0,
        "expansao_leads": 0.0, "repasse_leads": 0.0,
    })
    daily = defaultdict(lambda: {"gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0})
    campaigns = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0, "tipo": "Expansão"
    })
    camp_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))
    creatives = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
        "thumbnail": "", "campanha": "", "conjunto": "", "permalink": "",
    })
    # Diário por criativo — permite filtro de data no front-end (Top 5 do período)
    creatives_daily = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))
    # Diário por CAMPANHA — atribuição correta (cada linha bruta tem sua campanha),
    # permite a tabela de campanhas respeitar o filtro de DIA sem o problema do
    # creatives_daily (que agrega por nome de anúncio reusado entre campanhas).
    camp_daily = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads_plat": 0.0, "impressoes": 0.0, "cliques": 0.0, "leads_crm": 0.0,
    }))
    ad_camp_day = {}  # (anuncio, dia) -> campanha (p/ atribuir leads CRM à campanha certa)
    # Diário por CONJUNTO (atribuição correta: cada linha bruta tem seu conjunto+campanha
    # reais). Resolve a inflação da tabela "Qualidade dos públicos", que antes somava por
    # NOME de anúncio (creatives_daily) e despejava TODO o gasto de um anúncio multi-conjunto
    # num único conjunto (FEIRA aparecia R$3.461 sendo que a campanha-mãe gastou R$477).
    adset_daily = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads_plat": 0.0, "impressoes": 0.0, "cliques": 0.0, "leads_crm": 0.0,
    }))
    ad_conj_spend = defaultdict(lambda: defaultdict(float))  # (anuncio,dia) -> {(camp,conj): gasto}
    # Diário por (ANÚNCIO, campanha, conjunto): a tabela "Qualidade dos anúncios" quebra por
    # conjunto real — um criativo que roda em N conjuntos vira N linhas com o gasto certo de
    # cada, em vez de 1 linha com o total dele rotulado num conjunto só (Vídeo Institucional
    # aparecia R$3.283 sob FEIRA, sendo que só R$300 foram da FEIRA).
    creative_adset_daily = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads_plat": 0.0, "leads_crm": 0.0,
    }))

    for row in rows:
        mes = parse_date_to_month(row.get("data"))
        dia = parse_date_to_day(row.get("data"))
        if not mes:
            continue

        gasto = parse_num(row.get("gasto"))
        leads = parse_num(row.get("leads"))
        impressoes = parse_num(row.get("impressoes"))
        cliques = parse_num(row.get("cliques_link"))
        campanha = row.get("campanha") or ""
        tipo = "Repasse" if is_repasse(campanha) else "Expansão"

        monthly[mes]["gasto"] += gasto
        monthly[mes]["leads"] += leads
        monthly[mes]["impressoes"] += impressoes
        monthly[mes]["cliques"] += cliques

        if dia:
            daily[dia]["gasto"] += gasto
            daily[dia]["leads"] += leads
            daily[dia]["impressoes"] += impressoes
            daily[dia]["cliques"] += cliques

        if tipo == "Repasse":
            monthly[mes]["repasse_gasto"] += gasto
            monthly[mes]["repasse_leads"] += leads
        else:
            monthly[mes]["expansao_gasto"] += gasto
            monthly[mes]["expansao_leads"] += leads

        if campanha:
            campaigns[campanha]["gasto"] += gasto
            campaigns[campanha]["leads"] += leads
            campaigns[campanha]["impressoes"] += impressoes
            campaigns[campanha]["cliques"] += cliques
            campaigns[campanha]["tipo"] = tipo

            camp_monthly[campanha][mes]["gasto"] += gasto
            camp_monthly[campanha][mes]["leads"] += leads
            camp_monthly[campanha][mes]["impressoes"] += impressoes
            camp_monthly[campanha][mes]["cliques"] += cliques

            if dia:
                cd = camp_daily[campanha][dia]
                cd["gasto"] += gasto; cd["leads_plat"] += leads
                cd["impressoes"] += impressoes; cd["cliques"] += cliques

        anuncio = row.get("anuncio") or ""
        if anuncio:
            creatives[anuncio]["gasto"] += gasto
            creatives[anuncio]["leads"] += leads
            creatives[anuncio]["impressoes"] += impressoes
            creatives[anuncio]["cliques"] += cliques
            if row.get("thumbnail"):
                creatives[anuncio]["thumbnail"] = row.get("thumbnail")
            if row.get("permalink"):
                creatives[anuncio]["permalink"] = row.get("permalink")
            if row.get("conjunto"):
                creatives[anuncio]["conjunto"] = row.get("conjunto")
            if campanha:  # sempre atualiza para o nome mais recente da campanha
                creatives[anuncio]["campanha"] = campanha

            # Diário por criativo (para filtro de data no Top 5 da página Criativos)
            if dia:
                creatives_daily[anuncio][dia]["gasto"] += gasto
                creatives_daily[anuncio][dia]["leads"] += leads
                creatives_daily[anuncio][dia]["impressoes"] += impressoes
                creatives_daily[anuncio][dia]["cliques"] += cliques
                ad_camp_day[(anuncio, dia)] = campanha   # campanha real do anúncio nesse dia

                conjunto = row.get("conjunto") or ""
                if conjunto:
                    ak = (campanha, conjunto)
                    ad_s = adset_daily[ak][dia]
                    ad_s["gasto"] += gasto;      ad_s["leads_plat"] += leads
                    ad_s["impressoes"] += impressoes; ad_s["cliques"] += cliques
                    ad_conj_spend[(anuncio, dia)][ak] += gasto
                    cad = creative_adset_daily[(anuncio, campanha, conjunto)][dia]
                    cad["gasto"] += gasto; cad["leads_plat"] += leads

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        # CPL sem leads = null (não 0): meses históricos com gasto e 0 leads
        # coletados desenhavam CPL R$0 no gráfico — parecia ótimo, era buraco.
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else None
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        monthly_list.append({
            "mes": mes,
            "gasto": round(d["gasto"], 2),
            "leads": int(round(d["leads"])),
            "cpl": cpl,
            "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])),
            "ctr": ctr,
            "expansao_gasto": round(d["expansao_gasto"], 2),
            "repasse_gasto": round(d["repasse_gasto"], 2),
            "expansao_leads": int(round(d["expansao_leads"])),
            "repasse_leads": int(round(d["repasse_leads"])),
        })

    campaigns_list = []
    for nome, d in sorted(campaigns.items(), key=lambda x: -x[1]["gasto"])[:30]:
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        campaigns_list.append({
            "campanha": nome, "tipo": d["tipo"],
            "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    creatives_list = []
    # Inclui todos os criativos (não só top 50) — a página Criativos filtra por período.
    for nome, d in sorted(creatives.items(), key=lambda x: -x[1]["gasto"])[:300]:
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        creatives_list.append({
            "anuncio": nome, "campanha": d["campanha"],
            "conjunto": d.get("conjunto", ""),
            "thumbnail": d["thumbnail"],
            "permalink": d.get("permalink", ""),
            "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    campaign_monthly_list = []
    for camp, months in sorted(camp_monthly.items()):
        tipo = "Repasse" if is_repasse(camp) else "Expansão"
        for mes, d in sorted(months.items()):
            campaign_monthly_list.append({
                "campanha": camp, "mes": mes, "tipo": tipo,
                "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
                "impressoes": int(round(d["impressoes"])), "cliques": int(round(d["cliques"])),
            })

    total_gasto = sum(d["gasto"] for d in monthly.values())
    total_leads = sum(d["leads"] for d in monthly.values())

    daily_list = [
        {"data": d, "gasto": round(v["gasto"], 2), "leads": int(round(v["leads"])),
         "impressoes": int(round(v["impressoes"])), "cliques": int(round(v["cliques"]))}
        for d, v in sorted(daily.items())
    ]

    # Lista flat (anuncio x data). Campo `leads` = LEADS DO CRM (via matching
    # utm_content ↔ anuncio), NÃO os "leads" da plataforma Meta (que são imprecisos).
    # Sem thumbnail/permalink (otimização de tamanho — front faz lookup no `creatives`).
    creatives_daily_list = []
    leads_daily_map = leads_daily_map or {}
    for nome, dias in creatives_daily.items():
        ad_leads_map = leads_daily_map.get(nome, {})
        for dia, v in sorted(dias.items()):
            leads_crm = ad_leads_map.get(dia, 0)
            if v["gasto"] == 0 and leads_crm == 0:
                continue
            creatives_daily_list.append({
                "data":    dia,
                "anuncio": nome,
                "gasto":   round(v["gasto"], 2),
                "leads":   leads_crm,           # <-- CRM (matching utm), não plataforma!
                "leads_plat": int(round(v["leads"])),  # leads reportados pela plataforma Meta
                "impressoes": int(v["impressoes"]),
                "cliques":    int(v["cliques"]),
            })

    # Diário por CAMPANHA: atribui os leads CRM (matching) à campanha real do anúncio
    # naquele dia (ad_camp_day) e monta a lista. Atribuição correta + filtro de dia.
    for nome, dias in leads_daily_map.items():
        for dia, n in dias.items():
            cp = ad_camp_day.get((nome, dia))
            if cp:
                camp_daily[cp][dia]["leads_crm"] += n
    campaign_daily_list = []
    for camp, dias in camp_daily.items():
        for dia, v in sorted(dias.items()):
            if v["gasto"] == 0 and v["leads_crm"] == 0 and v["leads_plat"] == 0:
                continue
            campaign_daily_list.append({
                "data": dia, "campanha": camp,
                "gasto": round(v["gasto"], 2),
                "leads": int(round(v["leads_crm"])),       # CRM (matching)
                "leads_plat": int(round(v["leads_plat"])),  # plataforma
                "impressoes": int(v["impressoes"]),
                "cliques": int(v["cliques"]),
            })

    # Diário por CONJUNTO: atribui os leads CRM (matching, por nome de anúncio) ao(s)
    # conjunto(s) reais onde o anúncio rodou naquele dia, PROPORCIONAL ao gasto (um anúncio
    # multi-conjunto divide seus leads entre os conjuntos onde gastou). Gasto/impr/cliques
    # já são exatos (cada linha bruta tem seu conjunto). Resolve o bug FEIRA.
    for nome, dias in leads_daily_map.items():
        for dia, n in dias.items():
            spends = ad_conj_spend.get((nome, dia))
            if not spends:
                continue
            tot = sum(spends.values())
            if tot <= 0:
                continue
            for ak, sp in spends.items():
                frac = n * (sp / tot)
                adset_daily[ak][dia]["leads_crm"] += frac
                creative_adset_daily[(nome, ak[0], ak[1])][dia]["leads_crm"] += frac
    adset_daily_list = []
    for (campanha, conjunto), dias in adset_daily.items():
        for dia, v in sorted(dias.items()):
            if v["gasto"] == 0 and v["leads_crm"] == 0 and v["leads_plat"] == 0:
                continue
            adset_daily_list.append({
                "data": dia, "campanha": campanha, "conjunto": conjunto,
                "gasto": round(v["gasto"], 2),
                "leads": round(v["leads_crm"], 2),          # CRM proporcional ao gasto
                "leads_plat": int(round(v["leads_plat"])),  # plataforma
                "impressoes": int(v["impressoes"]),
                "cliques": int(v["cliques"]),
            })
    creative_adset_daily_list = []
    for (anuncio, campanha, conjunto), dias in creative_adset_daily.items():
        for dia, v in sorted(dias.items()):
            if v["gasto"] == 0 and v["leads_crm"] == 0 and v["leads_plat"] == 0:
                continue
            creative_adset_daily_list.append({
                "data": dia, "anuncio": anuncio, "campanha": campanha, "conjunto": conjunto,
                "gasto": round(v["gasto"], 2),
                "leads": round(v["leads_crm"], 2),          # CRM proporcional ao gasto
                "leads_plat": int(round(v["leads_plat"])),
            })

    return {
        "total_gasto": round(total_gasto, 2),
        "total_leads": int(round(total_leads)),
        "cpl_geral": round(total_gasto / total_leads, 2) if total_leads > 0 else 0,
        "monthly": monthly_list,
        "daily": daily_list,
        "campaigns": campaigns_list,
        "campaign_monthly": campaign_monthly_list,
        "campaign_daily": campaign_daily_list,
        "adset_daily": adset_daily_list,
        "creative_adset_daily": creative_adset_daily_list,
        "campaign_names": sorted(camp_monthly.keys()),
        "creatives": creatives_list,
        "creatives_daily": creatives_daily_list,
    }


def aggregate_google_ads(rows):
    monthly = defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0
    })
    daily = defaultdict(lambda: {"gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0})
    campaigns = defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0
    })
    camp_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))
    camp_daily = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))

    for row in rows:
        mes = parse_date_to_month(row.get("data"))
        dia = parse_date_to_day(row.get("data"))
        if not mes:
            continue

        gasto = parse_num(row.get("gasto"))
        conversoes = parse_num(row.get("conversoes"))
        impressoes = parse_num(row.get("impressoes"))
        cliques = parse_num(row.get("cliques"))
        campanha = row.get("campanha") or ""

        monthly[mes]["gasto"] += gasto
        monthly[mes]["conversoes"] += conversoes
        monthly[mes]["impressoes"] += impressoes
        monthly[mes]["cliques"] += cliques

        if dia:
            daily[dia]["gasto"] += gasto
            daily[dia]["conversoes"] += conversoes
            daily[dia]["impressoes"] += impressoes
            daily[dia]["cliques"] += cliques

        if campanha:
            campaigns[campanha]["gasto"] += gasto
            campaigns[campanha]["conversoes"] += conversoes
            campaigns[campanha]["impressoes"] += impressoes
            campaigns[campanha]["cliques"] += cliques

            camp_monthly[campanha][mes]["gasto"] += gasto
            camp_monthly[campanha][mes]["conversoes"] += conversoes
            camp_monthly[campanha][mes]["impressoes"] += impressoes
            camp_monthly[campanha][mes]["cliques"] += cliques

            if dia:
                camp_daily[campanha][dia]["gasto"] += gasto
                camp_daily[campanha][dia]["conversoes"] += conversoes
                camp_daily[campanha][dia]["impressoes"] += impressoes
                camp_daily[campanha][dia]["cliques"] += cliques

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        # CPL sem conversões = null (não 0) — mesmo racional do Meta: gasto sem
        # lead coletado não é CPL zero, é ausência de dado.
        cpl = round(d["gasto"] / d["conversoes"], 2) if d["conversoes"] > 0 else None
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        monthly_list.append({
            "mes": mes,
            "gasto": round(d["gasto"], 2),
            "conversoes": int(round(d["conversoes"])),
            "cpl": cpl,
            "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])),
            "ctr": ctr,
        })

    campaigns_list = []
    for nome, d in sorted(campaigns.items(), key=lambda x: -x[1]["gasto"])[:30]:
        cpl = round(d["gasto"] / d["conversoes"], 2) if d["conversoes"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        campaigns_list.append({
            "campanha": nome,
            "gasto": round(d["gasto"], 2), "conversoes": int(round(d["conversoes"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    campaign_monthly_list = []
    for camp, months in sorted(camp_monthly.items()):
        for mes, d in sorted(months.items()):
            campaign_monthly_list.append({
                "campanha": camp, "mes": mes,
                "gasto": round(d["gasto"], 2), "conversoes": int(round(d["conversoes"])),
                "impressoes": int(round(d["impressoes"])), "cliques": int(round(d["cliques"])),
            })

    # Diário por CAMPANHA (cada linha bruta já tem sua campanha → atribuição correta).
    # A tabela de campanhas do front usa ele p/ respeitar o filtro de DIA, em vez de
    # somar o mês inteiro (corrige o "gasto fantasma", igual ao Meta/campaign_daily).
    campaign_daily_list = []
    for camp, dias in camp_daily.items():
        for dia, d in sorted(dias.items()):
            if d["gasto"] == 0 and d["conversoes"] == 0:
                continue
            campaign_daily_list.append({
                "campanha": camp, "data": dia,
                "gasto": round(d["gasto"], 2), "conversoes": int(round(d["conversoes"])),
                "impressoes": int(round(d["impressoes"])), "cliques": int(round(d["cliques"])),
            })

    total_gasto = sum(d["gasto"] for d in monthly.values())
    total_conversoes = sum(d["conversoes"] for d in monthly.values())

    daily_list = [
        {"data": d, "gasto": round(v["gasto"], 2), "conversoes": int(round(v["conversoes"])),
         "impressoes": int(round(v["impressoes"])), "cliques": int(round(v["cliques"]))}
        for d, v in sorted(daily.items())
    ]

    return {
        "total_gasto": round(total_gasto, 2),
        "total_conversoes": int(round(total_conversoes)),
        "cpl_geral": round(total_gasto / total_conversoes, 2) if total_conversoes > 0 else 0,
        "monthly": monthly_list,
        "daily": daily_list,
        "campaigns": campaigns_list,
        "campaign_monthly": campaign_monthly_list,
        "campaign_daily": campaign_daily_list,
        "campaign_names": sorted(camp_monthly.keys()),
    }


def aggregate_ga4(rows):
    monthly = defaultdict(lambda: {
        "sessions": 0, "users": 0, "new_users": 0, "conversions": 0,
        "bounce_weighted": 0.0, "duration_weighted": 0.0,
    })
    channels = defaultdict(lambda: {"sessions": 0, "users": 0, "conversions": 0})
    devices = defaultdict(int)
    pages = defaultdict(int)
    sources = defaultdict(int)

    # Detecta linhas com flag _kind (coleta nova). Ignora 'demo' pra não duplicar.
    has_kind_flag = any("_kind" in r for r in (rows or []))

    # Último dia coletado — o front usa pra avisar quando a coleta GA4 estiver
    # parada (já ficou 44 dias congelada em silêncio, jun-jul/26).
    last_day = ""

    for row in rows:
        dia_row = parse_date_to_day(row.get("date"))
        if dia_row and dia_row > last_day:
            last_day = dia_row

        if has_kind_flag and row.get("_kind") == "demo":
            continue  # demografia: já foi agregada pelo aggregate_ga4_lps

        mes = parse_date_to_month(row.get("date"))
        if not mes:
            continue

        sessions = int(parse_num(row.get("sessions")))
        users = int(parse_num(row.get("totalUsers")))
        new_users = int(parse_num(row.get("newUsers")))
        conversions = int(parse_num(row.get("conversions")))
        bounce = parse_num(row.get("bounceRate"))
        duration = parse_num(row.get("averageSessionDuration"))

        monthly[mes]["sessions"] += sessions
        monthly[mes]["users"] += users
        monthly[mes]["new_users"] += new_users
        monthly[mes]["conversions"] += conversions
        monthly[mes]["bounce_weighted"] += bounce * sessions
        monthly[mes]["duration_weighted"] += duration * sessions

        channel = row.get("sessionDefaultChannelGroup") or "outros"
        channels[channel]["sessions"] += sessions
        channels[channel]["users"] += users
        channels[channel]["conversions"] += conversions

        device = row.get("deviceCategory") or "outros"
        devices[device] += sessions

        page = row.get("pagePath") or "/"
        pages[page] += int(parse_num(row.get("screenPageViews")))

        source = row.get("sessionSource") or "direto"
        sources[source] += sessions

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        s = d["sessions"]
        avg_bounce = round(d["bounce_weighted"] / s * 100, 1) if s > 0 else 0
        avg_duration = round(d["duration_weighted"] / s, 1) if s > 0 else 0
        monthly_list.append({
            "mes": mes,
            "sessions": s,
            "users": d["users"],
            "new_users": d["new_users"],
            "conversions": d["conversions"],
            "bounce_rate": avg_bounce,
            "avg_duration": avg_duration,
        })

    return {
        "total_sessions": sum(d["sessions"] for d in monthly.values()),
        "total_users": sum(d["users"] for d in monthly.values()),
        "last_date": last_day or None,   # último dia coletado (aviso de defasagem)
        "monthly": monthly_list,
        "channels": [
            {"channel": k, "sessions": v["sessions"], "users": v["users"], "conversions": v["conversions"]}
            for k, v in sorted(channels.items(), key=lambda x: -x[1]["sessions"])
        ],
        "devices": [
            {"device": k, "sessions": v}
            for k, v in sorted(devices.items(), key=lambda x: -x[1])
        ],
        "top_pages": [
            {"page": k, "views": v}
            for k, v in sorted(pages.items(), key=lambda x: -x[1])[:20]
        ],
        "sources": [
            {"source": k, "sessions": v}
            for k, v in sorted(sources.items(), key=lambda x: -x[1])[:15]
        ],
    }


LP_EXPANSAO = {
    "franqueado": {
        "label": "Franqueado",
        "url":   "https://franquiaclinicadacidade.com.br/Franqueado",
        # Aceita variações: case + com/sem barra final (GA4 preserva o case original)
        "paths": ["/Franqueado", "/Franqueado/", "/franqueado", "/franqueado/"],
    },
    "home": {
        "label": "Home",
        "url":   "https://franquiaclinicadacidade.com.br/",
        "paths": ["/"],
    },
    "pablo": {
        "label": "Pablo Spyer",
        "url":   "https://franquiaclinicadacidade.com.br/pablo-spyer/",
        "paths": ["/pablo-spyer", "/pablo-spyer/", "/Pablo-Spyer", "/Pablo-Spyer/", "/pablo.spyer/", "/pablo.spyer"],
    },
}
# Lookup reverso: path → key da LP
LP_PATH_LOOKUP = {p: k for k, v in LP_EXPANSAO.items() for p in v["paths"]}


def aggregate_ga4_lps(rows):
    """
    Agrega o GA4 raw pelas 3 LPs de expansão (Franqueado, Home, Pablo Spyer).
    Para cada LP gera: totais (sessions, users, conversions, bounce, duration),
    breakdowns por cidade, fonte, canal, dispositivo, e evolução mensal.

    Estrutura: {by_lp: {key: {meta, totals, top_cities, top_sources, channels,
                              devices, monthly}}, has_demographics: bool}
    """
    # Estrutura: por LP, agrega POR MÊS com breakdowns
    # Permite filtragem mensal no front
    by_lp = {}
    def _new_month():
        return {
            "sessions": 0, "users": 0, "new_users": 0, "pageviews": 0,
            "conversions": 0, "bounce_w": 0.0, "duration_w": 0.0,
            "cities": defaultdict(int), "sources": defaultdict(int),
            "channels": defaultdict(int), "devices": defaultdict(int),
            "ages": defaultdict(int), "genders": defaultdict(int),
        }
    for k, meta in LP_EXPANSAO.items():
        by_lp[k] = {
            "meta": {"label": meta["label"], "url": meta["url"], "key": k},
            "monthly": defaultdict(_new_month),
        }

    has_age = has_gender = False

    # Detecta se a coleta nova (com _kind) está sendo usada — se sim, filtra:
    # principais → métricas + breakdowns; demo → SÓ idade/sexo (evita duplicação).
    has_kind_flag = any("_kind" in r for r in (rows or []))

    for row in (rows or []):
        page = (row.get("pagePath") or "").strip()
        k = LP_PATH_LOOKUP.get(page)
        if not k:
            continue
        b = by_lp[k]
        kind = row.get("_kind")  # "main", "demo" ou None (coleta antiga)

        sessions = int(parse_num(row.get("sessions")))
        if not sessions:
            continue

        mes = parse_date_to_month(row.get("date"))
        if not mes:
            continue
        m = b["monthly"][mes]

        # ── Demografia (vem de request DEMO ou MAIN antigo) ────────────────────
        age = row.get("userAgeBracket")
        gen = row.get("userGender")
        if age and age.lower() not in ("", "unknown", "(not set)", "not set"):
            has_age = True
            m["ages"][age] += sessions
        if gen and gen.lower() not in ("", "unknown", "(not set)", "not set"):
            has_gender = True
            m["genders"][gen] += sessions

        # Se a linha é do request DEMO, não conta métricas/breakdowns (evita duplicação)
        if has_kind_flag and kind == "demo":
            continue

        # ── Linhas MAIN (ou coleta antiga) — métricas + breakdowns por mês ────
        users       = int(parse_num(row.get("totalUsers")))
        new_users   = int(parse_num(row.get("newUsers")))
        pageviews   = int(parse_num(row.get("screenPageViews")))
        conversions = int(parse_num(row.get("conversions")))
        bounce      = parse_num(row.get("bounceRate"))
        duration    = parse_num(row.get("averageSessionDuration"))

        m["sessions"]    += sessions
        m["users"]       += users
        m["new_users"]   += new_users
        m["pageviews"]   += pageviews
        m["conversions"] += conversions
        m["bounce_w"]    += bounce * sessions
        m["duration_w"]  += duration * sessions

        # breakdowns POR MÊS
        city = (row.get("city") or "(não definido)").strip() or "(não definido)"
        if city.lower() not in ("(not set)", "not set"):
            m["cities"][city] += sessions
        src = (row.get("sessionSource") or "direto").strip()
        m["sources"][src] += sessions
        ch  = (row.get("sessionDefaultChannelGroup") or "Outros").strip()
        m["channels"][ch] += sessions
        dev = (row.get("deviceCategory") or "outros").strip()
        m["devices"][dev] += sessions

    # Serialização final: por LP, lista de meses com totais + breakdowns
    # Front filtra os meses dentro do período selecionado e agrega no cliente.
    result = {"by_lp": {}, "has_demographics": has_age or has_gender,
              "has_age": has_age, "has_gender": has_gender}
    for k, b in by_lp.items():
        monthly_data = []
        for mes, m in sorted(b["monthly"].items()):
            monthly_data.append({
                "mes": mes,
                "sessions":    m["sessions"],
                "users":       m["users"],
                "new_users":   m["new_users"],
                "pageviews":   m["pageviews"],
                "conversions": m["conversions"],
                "bounce_w":    round(m["bounce_w"], 2),
                "duration_w":  round(m["duration_w"], 2),
                "cities":   dict(m["cities"]),
                "sources":  dict(m["sources"]),
                "channels": dict(m["channels"]),
                "devices":  dict(m["devices"]),
                "ages":     dict(m["ages"]),
                "genders":  dict(m["genders"]),
            })
        result["by_lp"][k] = {
            "meta": b["meta"],
            "monthly_data": monthly_data,
        }
    return result


def aggregate_utm(leads):
    sources = defaultdict(int)
    mediums = defaultdict(int)
    campaigns_utm = defaultdict(int)
    contents_utm = defaultdict(int)                         # utm_content → total leads
    campaigns_src = defaultdict(lambda: defaultdict(int))   # campaign -> source -> count
    sources_monthly = defaultdict(lambda: defaultdict(int))
    mediums_monthly = defaultdict(lambda: defaultdict(int))
    campaigns_monthly = defaultdict(lambda: defaultdict(int))
    sources_daily = defaultdict(lambda: defaultdict(int))
    mediums_daily = defaultdict(lambda: defaultdict(int))
    campaigns_daily = defaultdict(lambda: defaultdict(int))
    campaigns_src_daily = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for lead in leads:
        src = lead.get("utm_source") or "direto"
        med = lead.get("utm_medium") or "nenhum"
        camp = lead.get("utm_campaign")
        cont = lead.get("utm_content")
        if cont:
            contents_utm[cont] += 1

        sources[src] += 1
        mediums[med] += 1
        if camp:
            campaigns_utm[camp] += 1
            campaigns_src[camp][src] += 1

        mes = parse_date_to_month(lead.get("criado_em"))
        dia = parse_date_to_day(lead.get("criado_em"))

        if mes:
            sources_monthly[mes][src] += 1
            mediums_monthly[mes][med] += 1
            if camp:
                campaigns_monthly[mes][camp] += 1
        if dia:
            sources_daily[dia][src] += 1
            mediums_daily[dia][med] += 1
            if camp:
                campaigns_daily[dia][camp] += 1
                campaigns_src_daily[dia][camp][src] += 1

    def dominant_source(src_dict):
        return max(src_dict, key=src_dict.get) if src_dict else "direto"

    return {
        "sources": [
            {"source": k, "total": v}
            for k, v in sorted(sources.items(), key=lambda x: -x[1])
        ],
        "mediums": [
            {"medium": k, "total": v}
            for k, v in sorted(mediums.items(), key=lambda x: -x[1])
        ],
        "campaigns": [
            {"campaign": k, "total": v, "source": dominant_source(campaigns_src[k])}
            for k, v in sorted(campaigns_utm.items(), key=lambda x: -x[1])[:20]
        ],
        "contents": [
            {"content": k, "total": v}
            for k, v in sorted(contents_utm.items(), key=lambda x: -x[1])[:30]
        ],
        "sources_monthly": [
            {"mes": mes, "source": src, "total": count}
            for mes, srcs in sorted(sources_monthly.items())
            for src, count in srcs.items()
        ],
        "mediums_monthly": [
            {"mes": mes, "medium": m, "total": count}
            for mes, meds in sorted(mediums_monthly.items())
            for m, count in meds.items()
        ],
        "campaigns_monthly": [
            {"mes": mes, "campaign": c, "total": count}
            for mes, camps in sorted(campaigns_monthly.items())
            for c, count in camps.items()
        ],
        "sources_daily": [
            {"data": dia, "source": src, "total": count}
            for dia, srcs in sorted(sources_daily.items())
            for src, count in srcs.items()
        ],
        "mediums_daily": [
            {"data": dia, "medium": m, "total": count}
            for dia, meds in sorted(mediums_daily.items())
            for m, count in meds.items()
        ],
        "campaigns_daily": [
            {
                "data": dia, "campaign": c, "total": count,
                "source": dominant_source(campaigns_src_daily[dia][c]),
            }
            for dia, camps in sorted(campaigns_daily.items())
            for c, count in camps.items()
        ],
    }



def aggregate_google_ads_creatives(rows, leads_daily_map=None):
    """
    Agrega criativos do Google Ads (sheet 'google_ads_creatives').

    Cada linha de entrada = (data, anúncio). Para o dashboard:
      - daily: lista flat (data x anuncio) com leads do CRM (matching utm_content)
      - creatives: agregado por anúncio com leads_crm/cpl_crm

    Importante: As "conversões" da planilha Google são da plataforma — imprecisas.
    `leads_crm` é a fonte de verdade (vem do RD Station via Jaccard match).
    """
    if not rows:
        return {"daily": [], "creatives": [], "group_daily": [], "creative_group_daily": []}

    daily_list = []
    by_ad = defaultdict(lambda: {
        "gasto": 0.0, "conversoes_plataforma": 0.0,
        "campanha": "", "grupo": "", "tipo": "",
        "url_final": "", "cta": "", "qualidade": "",
        "headlines": "", "descriptions": "", "thumbnail": "",
        "primeira_data": "", "ultima_data": "",
    })
    # Diário por GRUPO e por ANÚNCIO×grupo (dimensão REAL, via API). Resolve a inflação por
    # nome (o grupo antes recebia todo o gasto de um anúncio reusado, via byAd[nome].grupo) e
    # o truncamento da planilha Adveronix. group_daily soma TUDO (inclui anúncios sem nome —
    # Search RSA); creative_group_daily só os com nome.
    group_daily = defaultdict(lambda: defaultdict(lambda: {"gasto": 0.0, "conv": 0.0, "leads_crm": 0.0}))
    creative_group_daily = defaultdict(lambda: defaultdict(lambda: {"gasto": 0.0, "leads_crm": 0.0}))
    ad_grp_spend = defaultdict(lambda: defaultdict(float))  # (anuncio,dia) -> {(camp,grupo): gasto}
    daily_raw = []                        # linhas cruas p/ o daily_list (leads rateados depois)
    spend_ad_day = defaultdict(float)     # (anuncio,dia) -> gasto total (base do rateio)
    rows_ad_day = defaultdict(int)        # (anuncio,dia) -> nº de linhas (rateio igual se gasto=0)

    leads_daily_map = leads_daily_map or {}

    for r in rows:
        data = (r.get("data") or "").strip()
        if not data:
            continue
        nome = (r.get("anuncio") or "").strip()
        campanha_r = (r.get("campanha") or "").strip()
        grupo_r = (r.get("grupo") or "").strip()
        gasto = parse_num(r.get("custo"))
        conv  = parse_num(r.get("conversoes"))

        # GRUPO daily — inclui anúncios SEM nome (o grupo soma tudo que gastou nele)
        if grupo_r:
            gd = group_daily[(campanha_r, grupo_r)][data]
            gd["gasto"] += gasto; gd["conv"] += conv

        if not nome:
            continue   # resto (nível anúncio/creative) só p/ anúncios com nome
        if grupo_r:
            creative_group_daily[(nome, campanha_r, grupo_r)][data]["gasto"] += gasto
            ad_grp_spend[(nome, data)][(campanha_r, grupo_r)] += gasto

        # Linha flat (data, anuncio) — leads são RATEADOS depois do loop. Com a fonte na API,
        # o mesmo anúncio aparece em N linhas no mesmo dia (uma por campanha/grupo); atribuir
        # o total de leads do dia a CADA linha DUPLICAVA (2 campanhas com o mesmo anúncio
        # somavam 14 leads sendo 7 reais). O rateio é proporcional ao gasto de cada linha.
        daily_raw.append({
            "data":     data,
            "anuncio":  nome,
            "campanha": r.get("campanha") or "",
            "tipo":     r.get("tipo") or "",
            "gasto":    gasto,
        })
        spend_ad_day[(nome, data)] += gasto
        rows_ad_day[(nome, data)] += 1

        # Agregado por anuncio
        d = by_ad[nome]
        d["gasto"]                 += gasto
        d["conversoes_plataforma"] += conv
        for f in ("campanha", "grupo", "tipo", "url_final", "cta", "qualidade",
                  "headlines", "descriptions", "thumbnail"):
            v = (r.get(f) or "").strip()
            if v:
                d[f] = v
        if not d["primeira_data"] or data < d["primeira_data"]:
            d["primeira_data"] = data
        if data > d["ultima_data"]:
            d["ultima_data"] = data

    # Monta o daily_list com leads RATEADOS por (anuncio, dia): proporcional ao gasto de
    # cada linha; se o gasto do dia for 0, divide igualmente entre as linhas. Garante que
    # a soma das linhas = leads reais do dia (sem duplicar por campanha/grupo).
    for rr in daily_raw:
        key = (rr["anuncio"], rr["data"])
        leads_day = leads_daily_map.get(rr["anuncio"], {}).get(rr["data"], 0)
        if leads_day:
            tot = spend_ad_day[key]
            frac = leads_day * (rr["gasto"] / tot) if tot > 0 else leads_day / rows_ad_day[key]
        else:
            frac = 0
        if rr["gasto"] == 0 and frac == 0:
            continue
        daily_list.append({
            "data":     rr["data"],
            "anuncio":  rr["anuncio"],
            "campanha": rr["campanha"],
            "tipo":     rr["tipo"],
            "gasto":    round(rr["gasto"], 2),
            "leads":    round(frac, 2),   # <-- CRM rateado (soma das linhas = leads do dia)
        })

    # Soma de leads_crm por anúncio (todos os dias)
    leads_crm_total = {nome: sum(dias.values()) for nome, dias in leads_daily_map.items()}

    creatives_list = []
    for nome, d in sorted(by_ad.items(), key=lambda x: -x[1]["gasto"]):
        leads_crm = leads_crm_total.get(nome, 0)
        cpl_crm   = round(d["gasto"] / leads_crm, 2) if leads_crm > 0 else 0
        creatives_list.append({
            "anuncio":      nome,
            "campanha":     d["campanha"],
            "grupo":        d["grupo"],
            "tipo":         d["tipo"],
            "url_final":    d["url_final"],
            "cta":          d["cta"],
            "qualidade":    d["qualidade"],
            "headlines":    d["headlines"],
            "descriptions": d["descriptions"],
            "thumbnail":    d["thumbnail"],
            "gasto":        round(d["gasto"], 2),
            "leads_crm":    leads_crm,                                    # <-- VERDADE
            "cpl_crm":      cpl_crm,                                      # <-- VERDADE
            "conversoes_plataforma": int(round(d["conversoes_plataforma"])),  # ref
            "primeira_data": d["primeira_data"],
            "ultima_data":   d["ultima_data"],
        })

    # Distribui os leads CRM (por nome de anúncio) ao(s) grupo(s) reais onde o anúncio rodou,
    # PROPORCIONAL ao gasto — mesma lógica do Meta (adset_daily). Gasto já é exato por grupo.
    for nome, dias in leads_daily_map.items():
        for dia, n in dias.items():
            spends = ad_grp_spend.get((nome, dia))
            if not spends:
                continue
            tot = sum(spends.values())
            if tot <= 0:
                continue
            for (camp, grupo), sp in spends.items():
                frac = n * (sp / tot)
                group_daily[(camp, grupo)][dia]["leads_crm"] += frac
                creative_group_daily[(nome, camp, grupo)][dia]["leads_crm"] += frac

    group_daily_list = []
    for (campanha, grupo), dias in group_daily.items():
        for dia, v in sorted(dias.items()):
            if v["gasto"] == 0 and v["leads_crm"] == 0:
                continue
            group_daily_list.append({
                "data": dia, "campanha": campanha, "grupo": grupo,
                "gasto": round(v["gasto"], 2), "conversoes": round(v["conv"], 2),
                "leads": round(v["leads_crm"], 2),
            })
    creative_group_daily_list = []
    for (anuncio, campanha, grupo), dias in creative_group_daily.items():
        for dia, v in sorted(dias.items()):
            if v["gasto"] == 0 and v["leads_crm"] == 0:
                continue
            creative_group_daily_list.append({
                "data": dia, "anuncio": anuncio, "campanha": campanha, "grupo": grupo,
                "gasto": round(v["gasto"], 2), "leads": round(v["leads_crm"], 2),
            })

    return {
        "daily":     daily_list,
        "creatives": creatives_list,
        "group_daily": group_daily_list,
        "creative_group_daily": creative_group_daily_list,
    }


def build_relatorio(leads, crm, meta_agg, google_agg, utm_agg, meta_rows=None, meetings_agg=None):
    """
    Pré-calcula as métricas do Relatório Resumido para o mês atual.
    Retorna um dict pronto para ser renderizado no dashboard sem lógica extra no front.
    """
    # Tradução manual dos meses para evitar dependência do locale pt_BR do sistema
    MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    def _label_mes(dt):
        return f"{MESES_PT[dt.month]}/{dt.year}"

    agora = datetime.now()
    mes_atual = agora.strftime("%Y-%m")
    mes_label = _label_mes(agora)

    # ── Leads do mês por source ───────────────────────────────────────────────
    mes_src = {}
    for r in utm_agg.get("sources_monthly", []):
        if r["mes"] == mes_atual:
            mes_src[r["source"]] = r["total"]

    google_leads_mes  = mes_src.get("googlecpc", 0)
    meta_leads_mes    = mes_src.get("metaads", 0)
    direto_leads_mes  = mes_src.get("direto", 0)
    pago_leads_mes    = google_leads_mes + meta_leads_mes
    total_leads_mes   = sum(mes_src.values())
    organico_leads_mes = total_leads_mes - pago_leads_mes

    # ── Gasto e CPL do mês ───────────────────────────────────────────────────
    meta_gasto_mes   = sum(r.get("gasto", 0) for r in meta_agg.get("daily", [])
                           if (r.get("data") or "").startswith(mes_atual))
    google_gasto_mes = sum(r.get("gasto", 0) for r in google_agg.get("daily", [])
                           if (r.get("data") or "").startswith(mes_atual))
    total_gasto_mes  = meta_gasto_mes + google_gasto_mes

    cpl_meta   = round(meta_gasto_mes / meta_leads_mes, 2)   if meta_leads_mes   else None
    cpl_google = round(google_gasto_mes / google_leads_mes, 2) if google_leads_mes else None
    cpl_pago   = round(total_gasto_mes / pago_leads_mes, 2)   if pago_leads_mes   else None

    # ── Funil CRM ─────────────────────────────────────────────────────────────
    total_deals    = crm.get("total_deals", 0)
    total_won      = crm.get("total_won", 0)
    total_lost     = crm.get("total_lost", 0)
    total_active   = crm.get("total_active", 0)

    # "Reunião PDF" foi renomeada para "1ª Reunião Agendada" no CRM.
    def _is_1a_agendada(nm):
        nl = nm.lower()
        return ("reuni" in nl and "agendada" in nl) or ("reuni" in nl and "pdf" in nl)
    reuniao_pdf_total  = next((e["total"] for e in crm.get("funnel", [])
                               if _is_1a_agendada(e["etapa"])), 0)
    reuniao_pdf_ativo  = next((e["total"] for e in crm.get("active_funnel", [])
                               if _is_1a_agendada(e["etapa"])), 0)

    taxa_reuniao_total = round(reuniao_pdf_total / total_deals * 100, 1) if total_deals else 0
    taxa_reuniao_ativo = round(reuniao_pdf_ativo / total_active * 100, 1) if total_active else 0

    # Reunião PDF do MÊS ATUAL (deals criados no mês cuja etapa atual é Reunião PDF)
    reuniao_pdf_mes = next((r.get("reuniao_pdf", 0) for r in crm.get("monthly_stages", [])
                            if r["mes"] == mes_atual), 0)
    # Taxa do mês: % de leads do mês que chegaram em Reunião PDF
    taxa_reuniao_mes = round(reuniao_pdf_mes / total_leads_mes * 100, 1) if total_leads_mes else None

    # ── Perdas do mês ─────────────────────────────────────────────────────────
    perdas_mes = next((r["perdidos"] for r in crm.get("monthly_stages", [])
                       if r["mes"] == mes_atual), 0)

    top_motivos = [
        {"motivo": r["motivo"], "total": r["total"]}
        for r in crm.get("losses", [])[:5]
    ]

    # ── Leads históricos por canal ─────────────────────────────────────────────
    src_map = {r["source"]: r["total"] for r in utm_agg.get("sources", [])}

    # ── Funil ativo detalhado ──────────────────────────────────────────────────
    funil_ativo = [
        {"etapa": e["etapa"], "total": e["total"]}
        for e in crm.get("active_funnel", [])
    ]

    # ── Comparativo mês anterior ──────────────────────────────────────────────
    from datetime import datetime as _dt, timedelta
    primeiro_dia_mes = _dt.now().replace(day=1)
    mes_ant_dt  = primeiro_dia_mes - timedelta(days=1)
    mes_anterior = mes_ant_dt.strftime("%Y-%m")
    mes_ant_label = _label_mes(mes_ant_dt)

    ant_src = {}
    for r in utm_agg.get("sources_monthly", []):
        if r["mes"] == mes_anterior:
            ant_src[r["source"]] = r["total"]
    ant_google = ant_src.get("googlecpc", 0)
    ant_meta   = ant_src.get("metaads", 0)
    ant_pago   = ant_google + ant_meta
    ant_total  = sum(ant_src.values())

    ant_meta_gasto   = sum(r.get("gasto", 0) for r in meta_agg.get("daily", [])
                           if (r.get("data") or "").startswith(mes_anterior))
    ant_google_gasto = sum(r.get("gasto", 0) for r in google_agg.get("daily", [])
                           if (r.get("data") or "").startswith(mes_anterior))
    ant_cpl_meta   = round(ant_meta_gasto / ant_meta, 2)     if ant_meta   else None
    ant_cpl_google = round(ant_google_gasto / ant_google, 2) if ant_google else None
    ant_cpl_pago   = round((ant_meta_gasto + ant_google_gasto) / ant_pago, 2) if ant_pago else None

    ant_reuniao = next((r.get("reuniao_pdf", 0) for r in crm.get("monthly_stages", [])
                        if r["mes"] == mes_anterior), 0)

    # ── Reuniões REAIS (campos 1ª/2ª Reunião do CRM) — agregadas por mês ──────
    # Fonte: meetings_agg["detail"]. 1 linha = 1 negócio com reunião registrada.
    # Conta TODAS as agendadas (1ª + 2ª) = compareceu + no-show no mês de referência.
    def _classe(v):
        s = str(v or "").strip().lower()
        if s == "sim": return "compareceu"
        if s in ("não", "nao"): return "noshow"
        return None

    def _meet_mes(mes_alvo):
        agend = noshow = 0
        for r in ((meetings_agg or {}).get("detail") or []):
            data = r.get("data") or ""
            if data[:7] != mes_alvo:
                continue
            for f in ("r1", "r2"):
                cls = _classe(r.get(f))
                if cls == "compareceu":
                    agend += 1
                elif cls == "noshow":
                    agend += 1
                    noshow += 1
        return agend, noshow

    reun_agendadas_mes, no_show_mes = _meet_mes(mes_atual)
    ant_reun_agendadas, ant_no_show = _meet_mes(mes_anterior)
    taxa_no_show_mes = round(no_show_mes / reun_agendadas_mes * 100, 1) if reun_agendadas_mes else None

    def variacao(atual, anterior):
        # Se qualquer um dos lados for None ou 0, não há base de comparação confiável
        if atual is None or anterior is None or not anterior:
            return None
        return round((atual - anterior) / anterior * 100, 1)

    comparativo = {
        "mes_anterior": mes_anterior,
        "mes_ant_label": mes_ant_label,
        "leads_total":  {"atual": total_leads_mes,   "anterior": ant_total,   "delta": variacao(total_leads_mes,   ant_total)},
        "leads_pago":   {"atual": pago_leads_mes,    "anterior": ant_pago,    "delta": variacao(pago_leads_mes,    ant_pago)},
        "leads_google": {"atual": google_leads_mes,  "anterior": ant_google,  "delta": variacao(google_leads_mes,  ant_google)},
        "leads_meta":   {"atual": meta_leads_mes,    "anterior": ant_meta,    "delta": variacao(meta_leads_mes,    ant_meta)},
        "cpl_meta":     {"atual": cpl_meta,          "anterior": ant_cpl_meta,   "delta": variacao(cpl_meta,   ant_cpl_meta)},
        "cpl_google":   {"atual": cpl_google,        "anterior": ant_cpl_google, "delta": variacao(cpl_google, ant_cpl_google)},
        "cpl_pago":     {"atual": cpl_pago,          "anterior": ant_cpl_pago,   "delta": variacao(cpl_pago,   ant_cpl_pago)},
        # Reunião PDF: comparação MENSAL (deals criados no mês cuja etapa virou Reunião PDF) — mantido por compat.
        "reuniao_pdf":  {"atual": reuniao_pdf_mes,   "anterior": ant_reuniao,    "delta": variacao(reuniao_pdf_mes, ant_reuniao)},
        # Reuniões Agendadas: dado real do CRM (1ª + 2ª Reunião marcadas no mês)
        "reunioes_agendadas": {"atual": reun_agendadas_mes, "anterior": ant_reun_agendadas, "delta": variacao(reun_agendadas_mes, ant_reun_agendadas)},
    }

    # ── Semáforo de saúde ─────────────────────────────────────────────────────
    def semaforo_cpl_meta(v):
        if v is None: return "gray"
        return "green" if v < 200 else ("yellow" if v <= 350 else "red")
    def semaforo_cpl_google(v):
        if v is None: return "gray"
        return "green" if v < 150 else ("yellow" if v <= 250 else "red")
    def semaforo_cpl_pago(v):
        if v is None: return "gray"
        return "green" if v < 200 else ("yellow" if v <= 300 else "red")
    def semaforo_no_show(v):
        # Taxa de No-Show: QUANTO MENOR, MELHOR (< 20% OK, 20-35% atenção, > 35% alerta)
        if v is None: return "gray"
        return "green" if v < 20 else ("yellow" if v <= 35 else "red")

    semaforo = [
        {"label": "CPL Meta Ads",    "valor": cpl_meta,    "status": semaforo_cpl_meta(cpl_meta),
         "ref": "< R$200 🟢  R$200-350 🟡  > R$350 🔴"},
        {"label": "CPL Google Ads",  "valor": cpl_google,  "status": semaforo_cpl_google(cpl_google),
         "ref": "< R$150 🟢  R$150-250 🟡  > R$250 🔴"},
        {"label": "CPL Médio Pago",  "valor": cpl_pago,    "status": semaforo_cpl_pago(cpl_pago),
         "ref": "< R$200 🟢  R$200-300 🟡  > R$300 🔴"},
        # Taxa de No-Show do mês: campo "1ª Reunião = Não" / total agendadas
        {"label": "Taxa de No-Show (mês)", "valor": taxa_no_show_mes, "status": semaforo_no_show(taxa_no_show_mes),
         "ref": "< 20% 🟢  20-35% 🟡  > 35% 🔴", "tipo": "pct"},
    ]

    # ── Top criativos do mês ──────────────────────────────────────────────────
    top_criativos = []
    if meta_rows:
        criat_mes = defaultdict(lambda: {
            "gasto": 0.0, "leads": 0.0, "thumbnail": "", "permalink": "", "campanha": "", "conjunto": ""
        })
        for row in meta_rows:
            # Usa parse_date_to_month (mesma lógica do resto do script) para
            # tolerar formatos de data diferentes na planilha (ex.: dd/mm/yyyy)
            if parse_date_to_month(row.get("data")) != mes_atual:
                continue
            nome = (row.get("anuncio") or "").strip()
            if not nome:
                continue
            criat_mes[nome]["gasto"]  += parse_num(row.get("gasto"))
            criat_mes[nome]["leads"]  += parse_num(row.get("leads"))
            if row.get("thumbnail") and not criat_mes[nome]["thumbnail"]:
                criat_mes[nome]["thumbnail"] = row.get("thumbnail")
            if row.get("permalink") and not criat_mes[nome]["permalink"]:
                criat_mes[nome]["permalink"] = row.get("permalink")
            if row.get("campanha") and not criat_mes[nome]["campanha"]:
                criat_mes[nome]["campanha"] = row.get("campanha")
            if row.get("conjunto") and not criat_mes[nome]["conjunto"]:
                criat_mes[nome]["conjunto"] = row.get("conjunto")

        for nome, d in sorted(criat_mes.items(), key=lambda x: -x[1]["leads"])[:5]:
            cpl_c = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else None
            top_criativos.append({
                "anuncio":   nome,
                "campanha":  d["campanha"],
                "conjunto":  d["conjunto"],
                "thumbnail": d["thumbnail"],
                "permalink": d["permalink"],
                "gasto":     round(d["gasto"], 2),
                "leads":     int(round(d["leads"])),
                "cpl":       cpl_c,
            })

    return {
        "mes":             mes_atual,
        "mes_label":       mes_label,
        # Leads do mês
        "leads_mes": {
            "total":    total_leads_mes,
            "pago":     pago_leads_mes,
            "organico": organico_leads_mes,
            "googlecpc": google_leads_mes,
            "metaads":   meta_leads_mes,
            "direto":    direto_leads_mes,
        },
        # Custos e CPL
        "custos_mes": {
            "meta_gasto":   round(meta_gasto_mes, 2),
            "google_gasto": round(google_gasto_mes, 2),
            "total_gasto":  round(total_gasto_mes, 2),
            "cpl_meta":     cpl_meta,
            "cpl_google":   cpl_google,
            "cpl_pago":     cpl_pago,
        },
        # CRM geral
        "crm_resumo": {
            "total_deals":          total_deals,
            "total_won":            total_won,
            "total_lost":           total_lost,
            "total_active":         total_active,
            "reuniao_pdf_total":    reuniao_pdf_total,        # snapshot histórico: deals atualmente na etapa
            "reuniao_pdf_pct":      taxa_reuniao_total,        # snapshot / total_deals
            "reuniao_pdf_ativo":    reuniao_pdf_ativo,         # ativos atualmente na etapa
            "reuniao_pdf_ativo_pct": taxa_reuniao_ativo,
            "reuniao_pdf_mes":      reuniao_pdf_mes,           # deals criados NESTE mês com etapa = Reunião PDF
            "reuniao_pdf_mes_pct":  taxa_reuniao_mes,          # % do mês: reuniao_pdf_mes / total_leads_mes
            "perdas_mes":           perdas_mes,
        },
        # Top motivos de perda
        "top_motivos_perda": top_motivos,
        # Funil ativo por etapa
        "funil_ativo": funil_ativo,
        # Leads históricos por canal
        "leads_historico": {
            "googlecpc": src_map.get("googlecpc", 0),
            "metaads":   src_map.get("metaads", 0),
            "direto":    src_map.get("direto", 0),
        },
        # Perdas por canal (histórico)
        "perdas_por_canal": crm.get("losses_by_utm_source", []),
        # Comparativo mês anterior
        "comparativo": comparativo,
        # Semáforo de saúde
        "semaforo": semaforo,
        # Top 5 criativos do mês (Meta Ads)
        "top_criativos_mes": top_criativos,
    }


def _classify_reuniao(v):
    """'Sim' → compareceu · 'Não' → noshow · resto → None."""
    s = str(v or "").strip().lower()
    if s in ("sim", "compareceu", "yes", "true", "1"):
        return "compareceu"
    if s in ("não", "nao", "no-show", "noshow", "no", "false", "0"):
        return "noshow"
    return None


def aggregate_meetings(deals):
    """
    Reuniões a partir dos CAMPOS PERSONALIZADOS do negócio no RD CRM:
      - reuniao_1 / reuniao_2: 'Sim' = compareceu, 'Não' = No-Show

    Gera detalhe (1 linha por negócio com pelo menos uma reunião registrada)
    para o front filtrar por período. Usa criado_em como data de referência
    (o RD não guarda a data da reunião nesses campos — é a melhor aproximação).
    Inclui também contagem de FPQ (Sim/Não).
    """
    fpq = {"sim": 0, "nao": 0}
    detail = []

    for d in (deals or []):
        c1 = _classify_reuniao(d.get("reuniao_1"))
        c2 = _classify_reuniao(d.get("reuniao_2"))

        fv = str(d.get("fpq") or "").strip().lower()
        if fv in ("sim", "yes", "true", "1"):
            fpq["sim"] += 1
        elif fv in ("não", "nao", "no", "false", "0"):
            fpq["nao"] += 1

        if not c1 and not c2:
            continue

        detail.append({
            "data": parse_date_to_day(d.get("criado_em")),
            "deal_nome": d.get("nome") or "—",
            "responsavel": d.get("responsavel") or "sem responsável",
            "r1": d.get("reuniao_1") or "",
            "r2": d.get("reuniao_2") or "",
            "justificativa": d.get("justificativa_no_show") or "",
        })

    # Totais all-time (o front recalcula filtrado a partir de `detail`)
    def tot(field):
        comp = sum(1 for x in detail if _classify_reuniao(x[field]) == "compareceu")
        ns   = sum(1 for x in detail if _classify_reuniao(x[field]) == "noshow")
        base = comp + ns
        return {"compareceu": comp, "noshow": ns, "total": base,
                "taxa_noshow": round(ns / base * 100, 1) if base else 0}

    return {
        "r1": tot("r1"),
        "r2": tot("r2"),
        "fpq": fpq,
        "detail": sorted(detail, key=lambda x: x["data"] or ""),
    }


# ════════════════════════════════════════════════════════════════════
# LEADS SCORING CLOSER — leads em etapas avançadas (de "Reunião de BP
# Realizada" em diante), com score de prioridade para o closer.
# ════════════════════════════════════════════════════════════════════
SCORING_FROM_STAGE = 'reunião de bp realizada'   # filtro: desta etapa em diante

# Pontos por etapa (mais avançado = mais perto do fechamento)
_STAGE_PTS = [
    ('reunião de bp realizada', 150),
    ('envio de cof',            200),
    ('visita / reunião com jamil', 220),
    ('análise financeira',      240),
    ('comitê final',            250),
]


def _capital_to_num(s):
    """Extrai o valor em R$ de strings tipo 'R$ 770.000,00 (Setecentos...)'."""
    if not s:
        return None
    m = re.search(r'(\d[\d\.]*,?\d*)', str(s).replace(' ', ''))
    if not m:
        return None
    try:
        return float(m.group(1).replace('.', '').replace(',', '.'))
    except ValueError:
        return None


def _pts_etapa(etapa):
    el = (etapa or '').lower().strip()
    pts = 150
    for name, p in _STAGE_PTS:
        if name in el or el in name:
            pts = p
    return pts


def _pts_capital(cap):
    if cap is None:
        return 0
    if cap >= 760000:
        return 200
    if cap >= 500000:
        return 150
    if cap >= 300000:
        return 100
    return 60


def _pts_prazo(prazo):
    p = (prazo or '').lower()
    if not p:
        return 40
    if 'imediat' in p or '0 a 3' in p or 'até 3' in p or 'ate 3' in p:
        return 150
    if '3 a 6' in p:
        return 120
    if '6 a 12' in p:
        return 90
    if 'acima' in p or 'mais de' in p or '12 a' in p:
        return 60
    return 70


def _pts_engajamento(interacoes, r1, r2, fpq):
    try:
        n = int(float(interacoes or 0))
    except (ValueError, TypeError):
        n = 0
    pts = min(n * 6, 90)
    if (r1 or '').strip():
        pts += 20
    if (r2 or '').strip():
        pts += 20
    if 'sim' in (fpq or '').lower():
        pts += 20
    return min(pts, 150)


def _pts_recencia(dias):
    if dias is None:
        return 30
    if dias <= 7:
        return 100
    if dias <= 15:
        return 80
    if dias <= 30:
        return 55
    if dias <= 60:
        return 30
    return 15


def _classificacao(total):
    if total >= 800:
        return ('Excelente', 5)
    if total >= 650:
        return ('Bom', 4)
    if total >= 500:
        return ('Regular', 3)
    return ('Frio', 2)


# Qualificação manual do deal no RD CRM (campo `rating`, 1–5 = temperatura).
# Confirmado: rating=1 = "Muito frio" (cruzado com a interface). None = sem qualificação.
QUALIFICACAO_CRM = {1: "Muito frio", 2: "Frio", 3: "Morno", 4: "Quente", 5: "Venda certa!"}


def _qualificacao_crm(rating):
    try:
        return QUALIFICACAO_CRM.get(int(rating), "")
    except (TypeError, ValueError):
        return ""


def build_leads_scoring_closer(crm_deals, leads, tarefas, atividades):
    """
    Lista de leads em etapas avançadas (de SCORING_FROM_STAGE em diante) com
    score de prioridade para o closer. Cruza com `leads` (cidade/capital/prazo),
    `crm_tarefas` (próxima tarefa) e `crm_atividades` (último contato).
    """
    order_idx = {name: i for i, name in enumerate([
        'entrada de lead', 'tentativa de contato', 'qualificação',
        'qualificado não agendada', '1ª reunião agendada', '1ª reunião realizada',
        'reunião de bp agendada', 'reunião de bp realizada', 'envio de cof',
        'visita / reunião com jamil', 'análise financeira/jurídica', 'comitê final',
    ])}

    def stage_pos(etapa):
        el = (etapa or '').lower().strip()
        for name, i in order_idx.items():
            if el == name or el in name or name in el:
                return i
        return -1

    from_pos = order_idx[SCORING_FROM_STAGE]
    leads_by_email = {(l.get('email') or '').strip().lower(): l for l in leads}

    # Índices de tarefas/atividades por deal
    tar_by_deal = defaultdict(list)
    for t in (tarefas or []):
        if t.get('deal_id'):
            tar_by_deal[t['deal_id']].append(t)
    ativ_by_deal = defaultdict(list)
    for a in (atividades or []):
        if a.get('deal_id'):
            ativ_by_deal[a['deal_id']].append(a)

    now = datetime.now()
    out = []
    for d in crm_deals:
        if stage_pos(d.get('etapa')) < from_pos:
            continue
        # Pula deals JÁ FECHADOS (ganhos ou perdidos). Antes o filtro era só por etapa,
        # então deals PERDIDOS (que permanecem na etapa onde morreram) entravam na lista
        # de "prioridade do closer" — 8 de 15 estavam perdidos, incl. o rank #1. A lista
        # do closer só pode ter deals VIVOS (em aberto).
        _ganho = str(d.get('ganho') or '').lower()
        if _ganho in ('true', '1', 'sim', 'yes') or bool(d.get('motivo_perda')) \
                or _ganho in ('false', '0', 'nao', 'não', 'no'):
            continue
        email = (d.get('contato_email') or '').strip().lower()
        lead = leads_by_email.get(email, {})
        cap_raw = lead.get('capital_disponivel') or ''
        cap_num = _capital_to_num(cap_raw)
        prazo = lead.get('prazo_abertura') or ''
        cidade = lead.get('cidade') or ''
        estado = lead.get('estado') or ''

        # Próxima tarefa (aberta, mais próxima)
        abertas = [t for t in tar_by_deal.get(d['id'], []) if (t.get('status') or '').lower() == 'open']
        abertas.sort(key=lambda t: t.get('data') or '9999')
        prox = abertas[0] if abertas else None
        proxima_tarefa = None
        if prox:
            proxima_tarefa = {
                "assunto": prox.get('assunto') or 'Tarefa',
                "data": (prox.get('data') or '')[:10],
                "responsavel": prox.get('responsavel') or '',
            }

        # Último contato (data mais recente entre atividades e tarefas concluídas)
        datas = [a.get('data') for a in ativ_by_deal.get(d['id'], []) if a.get('data')]
        datas += [t.get('data_conclusao') for t in tar_by_deal.get(d['id'], []) if t.get('data_conclusao')]
        ultimo = max(datas) if datas else (d.get('atualizado_em') or '')
        dias_ult = None
        ult_dt = _parse_dt(ultimo)
        if ult_dt:
            dias_ult = (now - ult_dt).days

        pts = {
            "etapa":       _pts_etapa(d.get('etapa')),
            "capital":     _pts_capital(cap_num),
            "prazo":       _pts_prazo(prazo),
            "engajamento": _pts_engajamento(d.get('interacoes'), d.get('reuniao_1'), d.get('reuniao_2'), d.get('fpq')),
            "recencia":    _pts_recencia(dias_ult),
            "dados":       _pts_dados([d.get('contato_telefone'), email, cidade, cap_raw, prazo, d.get('fonte')]),
        }
        total = sum(pts.values())
        classif, estrelas = _classificacao(total)

        out.append({
            "id": d.get('id'),
            "nome": d.get('nome') or d.get('contato_nome') or 'Sem nome',
            "etapa": normalize_etapa(d.get('etapa')),
            "cidade": cidade,
            "estado": estado,
            "capital": cap_raw,
            "prazo": prazo,
            "reuniao_1": d.get('reuniao_1') or '',
            "business_plan": d.get('reuniao_2') or '',
            "fpq": d.get('fpq') or '',
            "proxima_tarefa": proxima_tarefa,
            "ultimo_contato": (ultimo or '')[:10],
            "interacoes": d.get('interacoes') or '0',
            "pts": pts,
            "score_total": total,
            "classificacao": classif,
            "estrelas": estrelas,
            "fonte": d.get('fonte') or '',
            "campanha": d.get('campanha') or '',
            "telefone": d.get('contato_telefone') or '',
            "email": d.get('contato_email') or '',
            "responsavel": d.get('responsavel') or '',
            "qualificacao_crm": _qualificacao_crm(d.get('rating')),  # temperatura manual do time no RD
        })

    out.sort(key=lambda x: -x['score_total'])
    for i, item in enumerate(out):
        item['ranking'] = i + 1
    print(f"  Leads Scoring Closer: {len(out)} leads (de '{SCORING_FROM_STAGE}' em diante).")
    return out


def _pts_dados(campos):
    filled = sum(1 for c in campos if (c or '').strip())
    return min(filled * 25, 150)


def main():
    print("Gerando dados do dashboard...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    gc = get_client()

    print("  Lendo leads...")
    leads = read_sheet(gc, "leads")
    leads = dedupe_by_id(leads, "leads")
    leads = apply_imports_backfill(leads, load_imports_backfill())

    print("  Lendo CRM deals...")
    crm_deals = read_sheet(gc, "crm_deals")
    crm_deals = dedupe_by_id(crm_deals, "crm_deals")

    print("  Lendo CRM tarefas/atividades (scoring closer)...")
    try:
        crm_tarefas = read_sheet(gc, "crm_tarefas")
    except Exception as e:
        print(f"  AVISO: crm_tarefas indisponível: {e}"); crm_tarefas = []
    try:
        crm_atividades = read_sheet(gc, "crm_atividades")
    except Exception as e:
        print(f"  AVISO: crm_atividades indisponível: {e}"); crm_atividades = []


    print("  Lendo Meta Ads (API — substitui o Adveronix)...")
    meta_ads = None
    try:
        from collectors import meta_ads_api
        meta_ads = meta_ads_api.get_ad_insights_daily(since="2025-01-01")
        if meta_ads:
            print(f"    Meta Ads via API: {len(meta_ads)} linhas (anúncio/dia)")
        else:
            meta_ads = None
    except Exception as e:
        print(f"    AVISO: Meta API falhou ({e}) — caindo na planilha Adveronix.")
        meta_ads = None
    if not meta_ads:
        meta_ads = read_sheet(gc, "meta_ads")  # fallback: planilha Adveronix
        print(f"    (fallback Adveronix: {len(meta_ads)} linhas)")

    print("  Lendo Google Ads...")
    google_ads = read_sheet(gc, "google_ads")

    # Recupera utm_source de leads com link quebrado ('%20utm_source') — ver docstring.
    # Roda APÓS o backfill (que só preenche quem não tem fonte) e ANTES de todas as
    # agregações/matching, então o lead recuperado conta como pago E entra na
    # atribuição por campanha/anúncio (tem utm_campaign/content).
    leads = infer_utm_source_quebrada(leads, meta_ads, google_ads)

    print("  Lendo GA4...")
    ga4 = read_sheet(gc, "ga4_sessions")

    # Série diária da aba "Metas e Conversão" (site de expansão via hostName +
    # evento lead_prospecta). A aba pode não existir até o coletor novo rodar —
    # nesse caso o front mantém os cartões em "Aguardando conexão do GA4".
    print("  Lendo GA4 Metas (hostName + lead_prospecta)...")
    metas_ga4_daily = []
    try:
        for row in read_sheet(gc, "ga4_metas_daily"):
            dia = parse_date_to_day(row.get("date"))
            if not dia:
                continue
            metas_ga4_daily.append({
                "data": dia,
                "sessoes": int(parse_num(row.get("sessions"))),
                "lead_prospecta": int(parse_num(row.get("lead_prospecta"))),
            })
        print(f"    ga4_metas_daily: {len(metas_ga4_daily)} dias")
    except Exception as e:
        print(f"    ga4_metas_daily indisponível ({e}) — cartões da aba Metas ficam reservados")

    # Eventos de movimentação de etapa (crm_stage_events) → série diária do
    # "Volume comercial" da aba Metas. Aba pode não existir até o coletor rodar.
    print("  Lendo eventos de etapa do CRM (aba Metas)...")
    metas_eventos_daily = []
    try:
        TIPO_POR_ETAPA = {
            "Qualificação": "qualificacoes",
            "Qualificado Não agendada": "qual_nao_agendada",
            "1ª Reunião Agendada": "reunioes_agendadas",
            "1ª Reunião Realizada": "reunioes_realizadas",
        }
        ev_por_dia = defaultdict(lambda: {
            "qualificacoes": 0, "qual_nao_agendada": 0,
            "reunioes_agendadas": 0, "reunioes_realizadas": 0,
        })
        for row in read_sheet(gc, "crm_stage_events"):
            tipo = TIPO_POR_ETAPA.get(normalize_etapa(row.get("etapa") or ""))
            dia = parse_date_to_day(row.get("data"))
            if tipo and dia:
                ev_por_dia[dia][tipo] += 1
        metas_eventos_daily = [{"data": d, **v} for d, v in sorted(ev_por_dia.items())]
        tot_ev = sum(sum(v.values()) for v in ev_por_dia.values())
        print(f"    crm_stage_events: {tot_ev} eventos em {len(metas_eventos_daily)} dias")
    except Exception as e:
        print(f"    crm_stage_events indisponível ({e}) — Volume comercial fica reservado")

    print("  Lendo Previsibilidade 2026 (espelho planilha — legado/produção)...")
    previsibilidade_data = None
    try:
        from collectors import previsibilidade
        previsibilidade_data = previsibilidade.get_previsibilidade_data()
        if previsibilidade_data:
            blocks = []
            if previsibilidade_data.get("previsibilidade"):
                blocks.append(f"PREVISIBILIDADE ({len(previsibilidade_data['previsibilidade']['rows'])} linhas)")
            if previsibilidade_data.get("atingimento"):
                blocks.append(f"ATINGIMENTO ({len(previsibilidade_data['atingimento']['rows'])} linhas)")
            print(f"    {' + '.join(blocks)}")
    except Exception as e:
        print(f"    AVISO: não consegui ler planilha de Previsibilidade: {e}")
        previsibilidade_data = None

    # Previsibilidade NATIVA (modelo novo) é montada mais abaixo — precisa do
    # investimento mensal já agregado (meta_agg/google_agg).

    print("  Lendo Google Ads Criativos (API — substitui a planilha Adveronix travada)...")
    google_ads_creatives_rows = []
    try:
        from collectors import google_ads as google_ads_collector
        google_ads_creatives_rows = google_ads_collector.get_ad_daily(days_back=120)
        if google_ads_creatives_rows:
            print(f"    Google criativos via API: {len(google_ads_creatives_rows)} linhas (anúncio/dia)")
    except Exception as e:
        print(f"    AVISO get_ad_daily falhou ({e}) — caindo na planilha Adveronix.")
        google_ads_creatives_rows = []
    if not google_ads_creatives_rows:
        try:
            google_ads_creatives_rows = read_sheet(gc, "google_ads_creatives")
            print(f"    (fallback planilha Adveronix: {len(google_ads_creatives_rows)} linhas)")
        except Exception:
            print(f"    (sem aba google_ads_creatives ainda)")

    print("  Agregando dados...")

    # Faz o matching utm_content ↔ anuncio UMA VEZ para Meta e Google (com data)
    print("  Matching RD Station leads <-> criativos (Meta + Google)...")
    meta_leads_daily, google_leads_daily, _match_stats = match_rd_leads_daily(
        meta_ads, google_ads_creatives_rows, leads
    )

    meta_aggregated = aggregate_meta_ads(meta_ads, leads_daily_map=meta_leads_daily)

    # Status REAL das campanhas Meta (effective_status via API) — a planilha do
    # Adveronix não traz status, então o dashboard antes "adivinhava" pelo gasto
    # recente, marcando campanhas pausadas como Ativas. Vai em meta_ads.campaign_status.
    try:
        from collectors import meta_ads_api
        meta_status = meta_ads_api.get_campaign_status()
        if meta_status:
            meta_aggregated["campaign_status"] = meta_status
            n_act = sum(1 for v in meta_status.values() if v == "ACTIVE")
            print(f"    Status Meta (API): {len(meta_status)} campanhas · {n_act} ativas")
        else:
            # NÃO falha em silêncio: token inválido/ausente => campaign_status vazio =>
            # o front mostraria status errado. Anota erro VISÍVEL no GitHub Actions
            # (sem abortar o ETL — o front cai no "—" honesto). Ver get_campaign_status.
            print("::error::Status Meta (API) VAZIO — META_ACCESS_TOKEN invalido/ausente ou sem "
                  "permissao ads_read. campaign_status NAO foi gravado; o dashboard vai mostrar "
                  "'-' (status indisponivel) em vez de Ativo/Pausado. Confira o secret META_ACCESS_TOKEN.")
    except Exception as e:
        print(f"::error::Status Meta (API) FALHOU: {e}")

    # Mantém agregação total no creatives (já existente — para legacy compatibility)
    attach_rd_leads_to_creatives(meta_aggregated["creatives"], meta_ads, leads)

    # Qualidade de cada criativo: quantos leads avançaram para etapas qualificadas
    print("  Calculando qualidade dos criativos (etapa do lead no funil)...")
    creative_quality = compute_creative_funnel_quality(
        meta_ads, google_ads_creatives_rows, leads, crm_deals
    )
    print(f"    {len(creative_quality)} criativos com qualidade atribuída")

    crm_agg     = aggregate_crm(crm_deals, leads)
    meetings_agg = aggregate_meetings(crm_deals)
    meta_agg    = meta_aggregated
    google_agg  = aggregate_google_ads(google_ads)

    # Status REAL das campanhas Google (campaign.status via API) — mesma correção do
    # Meta: o dashboard antes "adivinhava" o status pelo gasto recente, marcando
    # campanhas pausadas como Ativas. Vai em google_ads.campaign_status.
    try:
        from collectors import google_ads as google_ads_collector
        google_status = google_ads_collector.get_campaign_status()
        if google_status:
            google_agg["campaign_status"] = google_status
            n_act = sum(1 for v in google_status.values() if v == "ENABLED")
            print(f"    Status Google (API): {len(google_status)} campanhas · {n_act} ativas")
        else:
            print("::error::Status Google (API) VAZIO — credenciais Google Ads invalidas/ausentes. "
                  "campaign_status NAO foi gravado; o dashboard vai mostrar '-' (status indisponivel) "
                  "em vez de Ativo/Pausado.")
    except Exception as e:
        print(f"::error::Status Google (API) FALHOU: {e}")

    # Leads CRM por campanha Google via utm_campaign (grava `leads` no campaign_daily)
    attach_google_campaign_leads(google_agg, leads)

    # Criativos Google agregados + leads por GRUPO via utm_term/UF (leads sem
    # rastreio por anúncio — ex.: DG.Grupo.Por.Cidade)
    gc_agg = aggregate_google_ads_creatives(google_ads_creatives_rows, leads_daily_map=google_leads_daily)
    attach_google_group_leads(gc_agg, google_agg, leads, google_ads_creatives_rows)

    utm_agg     = aggregate_utm(leads)
    leads_agg   = aggregate_leads(leads)

    # Previsibilidade NATIVA (Jan-Abr meta planilha + Mai-Jun real do CRM + Jul-Dez projeção).
    # Vai numa chave SEPARADA (`previsibilidade_nativa`) p/ não quebrar a produção,
    # que ainda renderiza o espelho legado em `previsibilidade`. Usa o investimento
    # mensal real (meta+google) p/ o CPL de Mai/Jun.
    print("  Montando Previsibilidade 2026 (nativa v2: real Jan-Jun + projeção CPL)...")
    previsibilidade_nativa_data = None
    try:
        from collectors import previsibilidade_nativa
        previsibilidade_nativa_data = previsibilidade_nativa.get_previsibilidade_data(
            meta_monthly=meta_agg.get("monthly"),
            google_monthly=google_agg.get("monthly"),
        )
        if previsibilidade_nativa_data:
            mai = previsibilidade_nativa_data["mensal"][4]   # Maio
            print(f"    OK [{previsibilidade_nativa_data['modelo']}]: "
                  f"{len(previsibilidade_nativa_data['mensal'])} meses · "
                  f"Maio real {mai['leads']} leads · "
                  f"H2 base R$ {previsibilidade_nativa_data['cenarios']['base']['receita']:,.0f}")
    except Exception as e:
        import traceback
        print(f"    AVISO: não consegui montar Previsibilidade nativa: {e}")
        traceback.print_exc()
        previsibilidade_nativa_data = None

    summary = {
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "totals": {
            "leads": len(leads),
            "crm_deals": len(crm_deals),
            "meta_rows": len(meta_ads),
            "google_rows": len(google_ads),
            "ga4_rows": len(ga4),
        },
        "leads": leads_agg,
        "crm": crm_agg,
        "meetings": meetings_agg,
        "meta_ads": meta_agg,
        "google_ads": google_agg,
        "ga4": aggregate_ga4(ga4),
        "ga4_lps": aggregate_ga4_lps(ga4),
        "metas": {"ga4_daily": metas_ga4_daily,
                  "eventos_daily": metas_eventos_daily},   # aba Metas e Conversão
        "utm": utm_agg,
        "google_ads_creatives": gc_agg,
        "creative_quality": creative_quality,
        "previsibilidade": previsibilidade_data,
        "previsibilidade_nativa": previsibilidade_nativa_data,
        "relatorio": build_relatorio(leads, crm_agg, meta_agg, google_agg, utm_agg, meta_rows=meta_ads, meetings_agg=meetings_agg),
        "scoring_closer": build_leads_scoring_closer(crm_deals, leads, crm_tarefas, crm_atividades),
    }

    output_file = os.path.join(OUTPUT_DIR, "summary.json")

    # Grava o arquivo local (usado apenas como artefato temporário no CI;
    # o arquivo NÃO é commitado no git — os dados vão para o Supabase Storage)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(output_file) / 1024
    print(f"  Arquivo local gerado: {output_file} ({size_kb:.1f} KB)")

    # Envia para o Supabase Storage (bucket privado 'dashboard-data')
    upload_to_supabase(output_file)

    print("Dashboard data gerado com sucesso!")


if __name__ == "__main__":
    main()

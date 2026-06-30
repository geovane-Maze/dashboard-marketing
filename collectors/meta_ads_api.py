# -*- coding: utf-8 -*-
"""
Meta Ads — API (Graph). Hoje usado só para o STATUS REAL das campanhas
(effective_status: ACTIVE / PAUSED / ...), que a planilha do Adveronix não traz.

O gasto/impressões/leads continuam vindo da planilha (estão corretos). Este módulo
só resolve o bug de "Ativo/Pausado" — o dashboard antes adivinhava o status pelo
gasto recente, marcando campanhas pausadas como ativas.

Requer no ambiente (.env local / GitHub Secrets):
  META_ACCESS_TOKEN   — token de acesso da Meta (Graph API)
  META_AD_ACCOUNT_ID  — id da conta de anúncios (sem o prefixo act_)
"""
import os
import requests

GRAPH = "https://graph.facebook.com/v21.0"


def _cfg():
    tok = os.environ.get("META_ACCESS_TOKEN")
    acct = os.environ.get("META_AD_ACCOUNT_ID")
    return tok, acct


def get_campaign_status():
    """
    Retorna {nome_da_campanha: 'ACTIVE'|'PAUSED'|...} para todas as campanhas da conta.
    Em caso de falta de token/erro, retorna {} (o front cai no fallback heurístico).
    """
    tok, acct = _cfg()
    if not tok or not acct:
        print("    Meta API: META_ACCESS_TOKEN/META_AD_ACCOUNT_ID ausentes — status pulado.")
        return {}
    out = {}
    url = f"{GRAPH}/act_{acct}/campaigns"
    params = {"fields": "name,effective_status", "limit": 200, "access_token": tok}
    try:
        while url:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code != 200:
                print(f"    Meta API: HTTP {r.status_code} — status pulado. {r.text[:160]}")
                return out
            j = r.json()
            for c in j.get("data", []):
                nome = (c.get("name") or "").strip()
                status = c.get("effective_status") or "UNKNOWN"
                if not nome:
                    continue
                # Campanhas com nome repetido: marca ACTIVE se QUALQUER uma estiver ativa
                # (o dashboard agrupa por nome, então o status é o "melhor" do grupo).
                if status == "ACTIVE" or nome not in out:
                    out[nome] = status
            url = j.get("paging", {}).get("next")
            params = None  # a URL do `next` já vem com tudo
        return out
    except Exception as e:
        print(f"    Meta API: erro ao buscar status: {e}")
        return out


def _paginated(url, params):
    """GET paginado da Graph API. Retorna a lista `data` concatenada."""
    out = []
    while url:
        r = requests.get(url, params=params, timeout=90)
        if r.status_code != 200:
            print(f"    Meta API: HTTP {r.status_code} em {url.split('?')[0]} — {r.text[:160]}")
            break
        j = r.json()
        out += j.get("data", [])
        url = j.get("paging", {}).get("next")
        params = None  # a URL do next já vem completa
    return out


def get_ads_creatives():
    """Mapa {ad_id: {thumbnail, permalink}} a partir dos criativos dos anúncios."""
    tok, acct = _cfg()
    if not tok or not acct:
        return {}
    rows = _paginated(f"{GRAPH}/act_{acct}/ads", {
        "fields": "id,creative{thumbnail_url,effective_object_story_id}",
        "limit": 200, "access_token": tok,
    })
    out = {}
    for a in rows:
        cr = a.get("creative") or {}
        story = cr.get("effective_object_story_id") or ""
        out[a["id"]] = {
            "thumbnail": cr.get("thumbnail_url") or "",
            "permalink": f"https://www.facebook.com/{story}" if story else "",
        }
    return out


def _month_ranges(since, until):
    """Gera (primeiro_dia, ultimo_dia) de cada mês entre since e until (ISO)."""
    from datetime import date, timedelta
    s = date.fromisoformat(since)
    e = date.fromisoformat(until)
    out = []
    cur = date(s.year, s.month, 1)
    while cur <= e:
        nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        first = max(cur, s)
        last = min(nxt - timedelta(days=1), e)
        out.append((first.isoformat(), last.isoformat()))
        cur = nxt
    return out


def get_ad_insights_daily(since="2025-01-01", until=None):
    """
    Substitui a planilha do Adveronix: insights por ANÚNCIO por DIA, direto da API.
    Retorna linhas no MESMO formato da aba `meta_ads` (data, campanha, conjunto,
    anuncio, gasto, cliques_link, impressoes, leads, permalink, thumbnail) — o ETL
    consome sem alteração. `leads` = leads reportados pela plataforma (action 'lead').

    Coleta MÊS A MÊS em paralelo: a API Meta dá erro 500 em ranges grandes de
    insights diários level=ad. Cada mês é um pedido (paginado).
    """
    import json
    from datetime import date
    from concurrent.futures import ThreadPoolExecutor
    tok, acct = _cfg()
    if not tok or not acct:
        print("    Meta API: token/conta ausentes — insights pulados.")
        return []
    until = until or date.today().isoformat()
    FIELDS = "campaign_name,adset_name,ad_name,ad_id,spend,impressions,clicks,inline_link_clicks,actions"

    def um_mes(rng):
        sm, um = rng
        return _paginated(f"{GRAPH}/act_{acct}/insights", {
            "level": "ad", "time_increment": 1, "fields": FIELDS,
            "time_range": json.dumps({"since": sm, "until": um}),
            "limit": 500, "access_token": tok,
        })

    rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for chunk in ex.map(um_mes, _month_ranges(since, until)):
            rows += chunk

    creativos = get_ads_creatives()
    out = []
    for r in rows:
        leads = 0
        for a in (r.get("actions") or []):
            if a.get("action_type") == "lead":
                leads += int(float(a.get("value", 0) or 0))
        cr = creativos.get(r.get("ad_id"), {})
        out.append({
            "data": r.get("date_start"),
            "campanha": r.get("campaign_name") or "",
            "conjunto": r.get("adset_name") or "",
            "anuncio": r.get("ad_name") or "",
            "gasto": round(float(r.get("spend", 0) or 0), 2),
            "cliques_link": int(float(r.get("inline_link_clicks", 0) or 0)),
            "impressoes": int(float(r.get("impressions", 0) or 0)),
            "leads": leads,
            "permalink": cr.get("permalink", ""),
            "thumbnail": cr.get("thumbnail", ""),
        })
    return out


if __name__ == "__main__":
    import sys, time
    from dotenv import load_dotenv
    load_dotenv()
    if "--insights" in sys.argv:
        t0 = time.time()
        rows = get_ad_insights_daily(since="2026-06-01", until="2026-06-30")
        print(f"insights junho: {len(rows)} linhas em {time.time()-t0:.1f}s")
        # confere FEIRA ABF
        abf = [r for r in rows if "FEIRA ABF" in r["campanha"].upper()]
        print(f"FEIRA ABF: {len(abf)} linhas | gasto total R$ {sum(r['gasto'] for r in abf):.2f}")
        if abf:
            print("  exemplo:", {k: abf[0][k] for k in ['data', 'campanha', 'anuncio', 'gasto', 'impressoes', 'cliques_link', 'leads']})
            print("  thumbnail?", bool(abf[0]['thumbnail']), "| permalink?", bool(abf[0]['permalink']))
    else:
        st = get_campaign_status()
        from collections import Counter
        print("campanhas:", len(st), "| status:", dict(Counter(st.values())))

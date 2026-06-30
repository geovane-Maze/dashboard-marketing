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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    st = get_campaign_status()
    from collections import Counter
    print("campanhas:", len(st), "| status:", dict(Counter(st.values())))

"""
Coletor Microsoft Clarity — Data Export API.

API oficial: https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api

Limitações importantes:
  • Apenas 10 requisições por dia, por projeto.
  • Janela de dados: apenas últimos 1, 2 ou 3 dias (sem histórico retroativo).
  • Máx 3 dimensões por requisição.
  • Máx 1.000 linhas por resposta (sem paginação).

Estratégia: 3 chamadas/dia (sobra folga de 7 requests para retentativas/debug):
  1. by_device          → Traffic + Engagement + Scroll + UX issues por Device
  2. by_url             → mesmas métricas por URL (top páginas problemáticas)
  3. by_source_medium   → mesmas métricas por UTM Source + Medium

Cada chamada retorna várias métricas no mesmo response — explodimos em linhas flat.
"""
import time
from datetime import date, datetime, timedelta

import requests
import config


ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

# Plano de coleta diária — cada item gera 1 chamada à API.
REQUESTS_PLAN = [
    {"key": "by_device",        "dims": ["Device"]},
    {"key": "by_url",           "dims": ["URL"]},
    {"key": "by_source_medium", "dims": ["Source", "Medium"]},
]


def _flatten_response(response_json, request_key, data_coleta):
    """
    Converte a resposta da API (lista de blocos por métrica) em linhas flat:

        [
          {"metricName": "Traffic", "information": [{"Device": "Mobile", "totalSessionCount": "1234", ...}, ...]},
          {"metricName": "Scroll Depth", "information": [...]},
          ...
        ]

    Vira:

        [
          {"data_coleta": "2026-05-19", "request_key": "by_device", "metric": "Traffic",
           "dimension_value": "Mobile", "totalSessionCount": 1234, ...},
          ...
        ]
    """
    rows = []
    if not isinstance(response_json, list):
        return rows

    for block in response_json:
        metric_name = block.get("metricName", "")
        for info in block.get("information", []) or []:
            row = {
                "data_coleta": data_coleta,
                "request_key": request_key,
                "metric": metric_name,
            }
            # Copia tudo o que veio no info (mistura de dimensões + valores)
            for k, v in info.items():
                row[k] = v
            rows.append(row)
    return rows


def _call_api(token, num_of_days, dims, max_retries=2):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    params = {"numOfDays": str(num_of_days)}
    for i, d in enumerate(dims, start=1):
        params[f"dimension{i}"] = d

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(ENDPOINT, params=params, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                print(f"    [429] Rate limit excedido — abortando.")
                return None
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            last_err = str(exc)
        if attempt < max_retries:
            time.sleep(2 ** attempt)  # backoff exponencial
    print(f"    ERRO após {max_retries+1} tentativas: {last_err}")
    return None


def get_clarity_data(num_of_days=1):
    """
    Faz 3 chamadas à Clarity API e retorna lista flat de linhas pronta para
    gravar/mergear em planilha. Cada linha tem:
      data_coleta, request_key, metric, dimension columns (Device/URL/Source/...),
      e os value columns retornados (totalSessionCount, scrollDepth, etc.).
    """
    print("Coletando dados do Microsoft Clarity...")
    token = config.CLARITY_API_TOKEN
    if not token:
        print("  CLARITY_API_TOKEN não configurado — pulando coleta do Clarity.")
        return []

    # Data dos dados que estamos puxando — a API entrega "últimos N dias até agora".
    # Como rodamos pela manhã, a coleta cobre o dia ANTERIOR. Usamos ontem como rótulo.
    data_coleta = (date.today() - timedelta(days=1)).isoformat()

    all_rows = []
    for req in REQUESTS_PLAN:
        print(f"  [{req['key']}] dims={req['dims']}")
        data = _call_api(token, num_of_days=num_of_days, dims=req["dims"])
        if data is None:
            continue
        rows = _flatten_response(data, req["key"], data_coleta)
        all_rows.extend(rows)
        print(f"    {len(rows)} linhas")

    print(f"  Clarity total: {len(all_rows)} linhas para {data_coleta}")
    return all_rows

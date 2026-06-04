import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
)

PROPERTY_ID = "404771405"
TOKEN_FILE = "credentials/ga4_token.json"


def _get_client():
    with open(TOKEN_FILE) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        token_data["token"] = creds.token
        with open(TOKEN_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

    return BetaAnalyticsDataClient(credentials=creds)


def _run_report(client, dimensions, metrics, start_date, end_date):
    """Roda um relatório e retorna lista de dicts (dim+met)."""
    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=100000,
    )
    response = client.run_report(request)
    dim_headers = [h.name for h in response.dimension_headers]
    met_headers = [h.name for h in response.metric_headers]
    rows = []
    for row in response.rows:
        record = {}
        for i, dim in enumerate(row.dimension_values):
            record[dim_headers[i]] = dim.value
        for i, met in enumerate(row.metric_values):
            try:
                val = float(met.value)
                record[met_headers[i]] = round(val, 4) if "." in met.value else int(val)
            except Exception:
                record[met_headers[i]] = met.value
        rows.append(record)
    return rows


def get_ga4_data(start_date="2024-01-01", end_date="today"):
    """
    Coleta GA4 em UM dataset combinado (ga4_sessions).

    Faz 2 requests no GA4 (cada um respeitando o limite de 9 dims e
    a incompatibilidade entre sessionSource e userAge/Gender):

    1) PRINCIPAL: dados de sessão completos sem demografia.
       Marca _kind='main' em cada linha. Contém métricas reais.

    2) DEMOGRAFIA: pagePath × idade × sexo × cidade × região × canal.
       Marca _kind='demo'. ETL usa SÓ pra agregar idade/sexo por LP.

    O ETL deve filtrar por _kind pra não duplicar métricas.
    """
    print("Coletando dados do Google Analytics 4...")
    client = _get_client()

    # ── Request 1: PRINCIPAL (sem demografia) ──────────────────────────────
    print("  [1/2] Métricas principais...")
    main_rows = _run_report(
        client,
        dimensions=[
            "date", "sessionSource", "pagePath", "deviceCategory",
            "region", "city", "sessionDefaultChannelGroup",
        ],
        metrics=[
            "sessions", "totalUsers", "newUsers", "screenPageViews",
            "bounceRate", "averageSessionDuration", "conversions", "eventCount",
        ],
        start_date=start_date, end_date=end_date,
    )
    for r in main_rows:
        r["_kind"] = "main"
    print(f"      Linhas principais: {len(main_rows)}")

    # ── Request 2: DEMOGRAFIA (idade + sexo por página) ────────────────────
    print("  [2/2] Demografia (idade + sexo)...")
    demo_rows = []
    try:
        demo_rows = _run_report(
            client,
            dimensions=[
                "date", "pagePath", "userAgeBracket", "userGender",
                "region", "city", "sessionDefaultChannelGroup",
            ],
            metrics=["sessions", "totalUsers"],
            start_date=start_date, end_date=end_date,
        )
        for r in demo_rows:
            r["_kind"] = "demo"
        print(f"      Linhas demografia: {len(demo_rows)}")
    except Exception as e:
        print(f"      AVISO: demografia falhou ({type(e).__name__}). Pulando.")

    total = main_rows + demo_rows
    print(f"  Total de linhas GA4: {len(total)} (main={len(main_rows)}, demo={len(demo_rows)})")
    return total

import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
    Filter,
    FilterExpression,
)


# Filtro de páginas de interesse — descarta páginas de pacientes/centros médicos
# que inflam o volume sem agregar valor pra análise de EXPANSÃO de franquia.
# Mantém: home, LPs de expansão (Franqueado/Pablo Spyer), agradecimentos e variações.
RELEVANT_PAGE_REGEX = (
    r"^/$"
    r"|^/[Ff]ranqueado/?$"
    r"|^/sejaumfranqueado.*$"
    r"|^/seja-?franqueado.*$"
    r"|^/[Pp]ablo[-.][Ss]pyer/?$"
    r"|^/agradecimento.*$"
    r"|^/obrigado.*$"
)


def _page_filter():
    """Restringe a coleta apenas às páginas relevantes pra expansão."""
    return FilterExpression(
        filter=Filter(
            field_name="pagePath",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.FULL_REGEXP,
                value=RELEVANT_PAGE_REGEX,
            ),
        )
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

    # Sempre tenta renovar — access_token expira em ~1h.
    # Se já está válido, não faz nada; se expirou, usa o refresh_token.
    if creds.refresh_token:
        try:
            creds.refresh(Request())
            token_data["token"] = creds.token
            with open(TOKEN_FILE, "w") as f:
                json.dump(token_data, f, indent=2)
        except Exception as e:
            print(f"  AVISO: falha ao renovar token GA4: {e}")

    return BetaAnalyticsDataClient(credentials=creds)


def _run_report(client, dimensions, metrics, start_date, end_date):
    """Roda um relatório com PAGINAÇÃO automática (offset incremental).

    GA4 retorna no máximo 250.000 linhas por chamada. Se a query tem mais que
    isso, o resultado é truncado silenciosamente (não dá erro!). A paginação
    resolve isso fazendo várias chamadas com offset crescente até pegar tudo.

    Sintoma do bug que isso resolve: dimensões com muitas combinações
    (date × source × pagePath × city × ...) ficavam com dados parciais
    quando o total ultrapassava o limit, levando a métricas SUBESTIMADAS.
    """
    PAGE_SIZE = 250000  # máximo permitido por chamada
    all_rows = []
    offset = 0
    dim_headers = met_headers = None

    while True:
        request = RunReportRequest(
            property=f"properties/{PROPERTY_ID}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimension_filter=_page_filter(),     # ← filtra páginas relevantes
            offset=offset,
            limit=PAGE_SIZE,
        )
        response = client.run_report(request)
        if dim_headers is None:
            dim_headers = [h.name for h in response.dimension_headers]
            met_headers = [h.name for h in response.metric_headers]

        page_rows = []
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
            page_rows.append(record)

        all_rows.extend(page_rows)
        total_rows = response.row_count  # total real (sem truncar)

        # Se já pegamos tudo OU a página voltou vazia, encerra
        if len(all_rows) >= total_rows or not page_rows:
            break
        offset += PAGE_SIZE
        print(f"      ... página com offset={offset} (já temos {len(all_rows)}/{total_rows} linhas)")

    return all_rows


def _default_start_date():
    """Retorna a data 6 meses atrás no formato YYYY-MM-DD."""
    from datetime import datetime, timedelta
    return (datetime.today() - timedelta(days=180)).strftime("%Y-%m-%d")


HOSTNAME_EXPANSAO = "franquiaclinicadacidade.com.br"


def get_metas_daily(start_date=None, end_date="today"):
    """
    Série diária pra aba "Metas e Conversão" (sessões + evento lead_prospecta).

    OBRIGATÓRIO filtrar hostName: esta propriedade GA4 recebe dados de outros
    sites (www.clinicadacidade, cdctatui, essencialclinica...) — sem o filtro,
    as sessões vêm ~2x infladas (verificado: 7.597 vs ~14.000 em 30d).
    Diferente do ga4_sessions (que filtra pagePath das LPs), aqui é o SITE
    INTEIRO de expansão — é a régua da meta semanal do consultor.
    """
    if start_date is None:
        start_date = _default_start_date()
    print("Coletando GA4 — série da aba Metas (hostName + lead_prospecta)...")
    client = _get_client()

    host_filter = FilterExpression(filter=Filter(
        field_name="hostName",
        string_filter=Filter.StringFilter(
            match_type=Filter.StringFilter.MatchType.EXACT, value=HOSTNAME_EXPANSAO),
    ))

    def _report(metrics, dim_filter):
        request = RunReportRequest(
            property=f"properties/{PROPERTY_ID}",
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimension_filter=dim_filter,
            limit=250000,
        )
        resp = client.run_report(request)
        return {r.dimension_values[0].value: int(float(r.metric_values[0].value)) for r in resp.rows}

    sessoes = _report(["sessions"], host_filter)

    from google.analytics.data_v1beta.types import FilterExpressionList
    lead_filter = FilterExpression(and_group=FilterExpressionList(expressions=[
        host_filter,
        FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT, value="lead_prospecta"),
        )),
    ]))
    leads_ev = _report(["eventCount"], lead_filter)

    rows = [
        {"date": d, "sessions": sessoes.get(d, 0), "lead_prospecta": leads_ev.get(d, 0)}
        for d in sorted(set(sessoes) | set(leads_ev))
    ]
    print(f"  Metas GA4: {len(rows)} dias · sessões={sum(sessoes.values())} · lead_prospecta={sum(leads_ev.values())}")
    return rows


def get_ga4_data(start_date=None, end_date="today"):
    if start_date is None:
        start_date = _default_start_date()
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

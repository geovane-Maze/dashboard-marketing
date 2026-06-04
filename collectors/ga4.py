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


def get_ga4_data(start_date="2024-01-01", end_date="today"):
    print("Coletando dados do Google Analytics 4...")
    client = _get_client()

    request = RunReportRequest(
        property=f"properties/{PROPERTY_ID}",
        dimensions=[
            Dimension(name="date"),
            Dimension(name="sessionSource"),
            Dimension(name="sessionMedium"),
            Dimension(name="sessionCampaignName"),
            Dimension(name="pagePath"),
            Dimension(name="deviceCategory"),
            Dimension(name="country"),
            Dimension(name="region"),            # estado/UF
            Dimension(name="city"),
            Dimension(name="sessionDefaultChannelGroup"),
            Dimension(name="userAgeBracket"),    # faixa etária (precisa Sinais do Google)
            Dimension(name="userGender"),        # gênero
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="screenPageViews"),
            Metric(name="bounceRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="conversions"),
            Metric(name="eventCount"),
        ],
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

    print(f"  Total de linhas GA4: {len(rows)}")
    return rows

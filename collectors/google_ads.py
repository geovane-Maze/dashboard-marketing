from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from datetime import datetime, timedelta
import config


def get_client():
    credentials = {
        "developer_token": config.GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": config.GOOGLE_ADS_CLIENT_ID,
        "client_secret": config.GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_ADS_REFRESH_TOKEN,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


def get_campaign_data(days_back=30):
    client = get_client()
    service = client.get_service("GoogleAdsService")
    customer_id = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")

    date_end = datetime.today().strftime("%Y-%m-%d")
    date_start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            ad_group.name,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.ctr,
            metrics.average_cpc,
            segments.date
        FROM ad_group
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
          AND campaign.status = 'ENABLED'
        ORDER BY segments.date DESC
    """

    print("Coletando dados do Google Ads...")
    rows = []

    try:
        response = service.search(customer_id=customer_id, query=query)
        for row in response:
            rows.append({
                "data": row.segments.date,
                "campanha_id": row.campaign.id,
                "campanha_nome": row.campaign.name,
                "conjunto_anuncio": row.ad_group.name,
                "impressoes": row.metrics.impressions,
                "cliques": row.metrics.clicks,
                "custo_brl": round(row.metrics.cost_micros / 1_000_000, 2),
                "conversoes": row.metrics.conversions,
                "ctr": round(row.metrics.ctr * 100, 2),
                "cpc_medio": round(row.metrics.average_cpc / 1_000_000, 2),
            })
    except GoogleAdsException as ex:
        print(f"Erro Google Ads: {ex.error.code().name}")
        for error in ex.failure.errors:
            print(f"  {error.message}")

    print(f"Total de linhas coletadas: {len(rows)}")
    return rows

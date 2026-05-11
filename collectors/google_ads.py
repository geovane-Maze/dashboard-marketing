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
        "login_customer_id": "2891779593",  # MCC customer ID (289-177-9593)
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


def get_campaign_data(days_back=90):
    client = get_client()
    service = client.get_service("GoogleAdsService")
    customer_id = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")

    date_end = datetime.today().strftime("%Y-%m-%d")
    date_start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Query FROM campaign instead of ad_group so Performance Max campaigns are included.
    # PMax campaigns have no traditional ad groups and are invisible in ad_group queries.
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            segments.date
        FROM campaign
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
          AND campaign.status != 'REMOVED'
          AND metrics.cost_micros > 0
        ORDER BY segments.date DESC
    """

    print("Coletando dados do Google Ads (API)...")
    rows = []

    try:
        response = service.search(customer_id=customer_id, query=query)
        for row in response:
            rows.append({
                "data": row.segments.date,
                "campanha": row.campaign.name,
                "gasto": round(row.metrics.cost_micros / 1_000_000, 2),
                "cliques": row.metrics.clicks,
                "impressoes": row.metrics.impressions,
                "conversoes": row.metrics.conversions,
            })
    except GoogleAdsException as ex:
        print(f"Erro Google Ads: {ex.error.code().name}")
        for error in ex.failure.errors:
            print(f"  {error.message}")

    print(f"Total de linhas coletadas: {len(rows)}")
    return rows

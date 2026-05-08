from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adsinsights import AdsInsights
from datetime import datetime, timedelta
import config


def get_campaign_data(days_back=30):
    FacebookAdsApi.init(
        app_id=config.META_APP_ID,
        app_secret=config.META_APP_SECRET,
        access_token=config.META_ACCESS_TOKEN,
    )

    date_end = datetime.today().strftime("%Y-%m-%d")
    date_start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    account = AdAccount(config.META_AD_ACCOUNT_ID)

    fields = [
        AdsInsights.Field.campaign_name,
        AdsInsights.Field.campaign_id,
        AdsInsights.Field.adset_name,
        AdsInsights.Field.ad_name,
        AdsInsights.Field.impressions,
        AdsInsights.Field.clicks,
        AdsInsights.Field.spend,
        AdsInsights.Field.actions,
        AdsInsights.Field.ctr,
        AdsInsights.Field.cpc,
        AdsInsights.Field.date_start,
    ]

    params = {
        "time_range": {"since": date_start, "until": date_end},
        "level": "ad",
        "time_increment": 1,
    }

    print("Coletando dados do Meta Ads...")
    rows = []

    insights = account.get_insights(fields=fields, params=params)

    for insight in insights:
        conversoes = 0
        for action in insight.get("actions", []):
            if action.get("action_type") in ["lead", "offsite_conversion.fb_pixel_lead"]:
                conversoes += int(action.get("value", 0))

        rows.append({
            "data": insight.get("date_start"),
            "campanha_id": insight.get("campaign_id"),
            "campanha_nome": insight.get("campaign_name"),
            "conjunto_anuncio": insight.get("adset_name"),
            "anuncio": insight.get("ad_name"),
            "impressoes": int(insight.get("impressions", 0)),
            "cliques": int(insight.get("clicks", 0)),
            "custo_brl": float(insight.get("spend", 0)),
            "conversoes_leads": conversoes,
            "ctr": float(insight.get("ctr", 0)),
            "cpc_medio": float(insight.get("cpc", 0)),
        })

    print(f"Total de linhas coletadas: {len(rows)}")
    return rows

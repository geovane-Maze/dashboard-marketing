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


def get_campaign_status():
    """
    Mapa {nome_da_campanha: 'ENABLED'|'PAUSED'|...} de TODAS as campanhas (exceto
    REMOVED) da conta — STATUS REAL via API. Espelha meta_ads_api.get_campaign_status().

    Resolve o bug "Ativo/Pausado": o dashboard antes adivinhava o status pelo gasto
    recente (heurística), marcando campanhas pausadas como ativas. Diferente de
    get_campaign_data(), NÃO filtra por custo/data — então pega pausadas sem gasto.

    Em caso de erro/credenciais ausentes, retorna {} (o front cai no fallback heurístico).
    """
    query = """
        SELECT campaign.name, campaign.status
        FROM campaign
        WHERE campaign.status != 'REMOVED'
    """
    out = {}
    print("Coletando status real das campanhas do Google Ads (API)...")
    try:
        client = get_client()
        service = client.get_service("GoogleAdsService")
        customer_id = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
        for row in service.search(customer_id=customer_id, query=query):
            nome = (row.campaign.name or "").strip()
            if not nome:
                continue
            status = row.campaign.status.name  # ENABLED / PAUSED / ...
            # Campanhas com nome repetido: marca ENABLED se QUALQUER uma estiver ativa
            # (o dashboard agrupa por nome, então o status é o "melhor" do grupo).
            if status == "ENABLED" or nome not in out:
                out[nome] = status
    except GoogleAdsException as ex:
        print(f"  AVISO status Google: {ex.error.code().name}")
    except Exception as e:
        print(f"  AVISO status Google: {e}")
    print(f"  Status Google: {len(out)} campanhas.")
    return out


def get_ad_daily(days_back=120):
    """
    Por ANÚNCIO por DIA (via API): campanha, grupo, anúncio, gasto, cliques, impressões,
    conversões, url final. Substitui a planilha Adveronix (que travou em 08/06) como fonte
    das tabelas de Grupos e Anúncios do Google — dados COMPLETOS e com a dimensão REAL de
    grupo (o mesmo que get_ad_insights_daily faz no Meta).

    NÃO cobre Performance Max (PMax não tem ad_group_ad) — mas o gasto total e a tabela de
    Campanhas vêm de get_campaign_data (FROM campaign, que inclui PMax), então o total fecha.
    """
    date_end = datetime.today().strftime("%Y-%m-%d")
    date_start = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_ad.ad.name,
            ad_group_ad.ad.final_urls,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions,
            segments.date
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
          AND metrics.cost_micros > 0
          AND ad_group_ad.status != 'REMOVED'
        ORDER BY segments.date DESC
    """
    print("Coletando anúncios/grupos do Google Ads por dia (API)...")
    rows = []
    try:
        client = get_client()
        service = client.get_service("GoogleAdsService")
        customer_id = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
        for row in service.search(customer_id=customer_id, query=query):
            urls = list(row.ad_group_ad.ad.final_urls)
            rows.append({
                "data": row.segments.date,
                "campanha": row.campaign.name,
                "grupo": row.ad_group.name,
                "anuncio": row.ad_group_ad.ad.name or "",
                "custo": round(row.metrics.cost_micros / 1_000_000, 2),
                "cliques": row.metrics.clicks,
                "impressoes": row.metrics.impressions,
                "conversoes": row.metrics.conversions,
                "url_final": urls[0] if urls else "",
            })
    except GoogleAdsException as ex:
        print(f"  AVISO get_ad_daily Google: {ex.error.code().name}")
        for error in ex.failure.errors:
            print(f"    {error.message}")
    except Exception as e:
        print(f"  AVISO get_ad_daily Google: {e}")
    print(f"  Google ad_daily: {len(rows)} linhas (anúncio/dia).")
    return rows


def get_creative_thumbnails():
    """
    Mapa {nome_do_anuncio: thumbnail_url} via API Google Ads.

    Espelha o padrao do Meta (_get_creative_thumbnails em ads_sheets): a planilha
    Adveronix da texto/metricas dos criativos, mas NAO traz a imagem/video do
    criativo do Google — so a API tem isso.

    - Imagens (Demand Gen / Display): asset.image_asset.full_size.url
      (tpc.googlesyndication.com/simgad/... — renderiza direto em <img>).
    - Videos (YouTube / Demand Gen video): img.youtube.com/vi/{id}/hqdefault.jpg.

    Escolhe 1 thumb por anuncio pela prioridade de field_type. Casa por nome
    (match exato 1:1), entao anuncios sem nome ficam de fora — consistente com a
    planilha de criativos, que tambem ignora anuncios sem nome.
    """
    PRIO = {
        "MARKETING_IMAGE": 1, "SQUARE_MARKETING_IMAGE": 2,
        "PORTRAIT_MARKETING_IMAGE": 3, "YOUTUBE_VIDEO": 4,
        "LANDSCAPE_LOGO": 9, "LOGO": 9,
    }
    query = """
        SELECT
            ad_group_ad.ad.name,
            ad_group_ad_asset_view.field_type,
            asset.type,
            asset.image_asset.full_size.url,
            asset.youtube_video_asset.youtube_video_id
        FROM ad_group_ad_asset_view
        WHERE ad_group_ad.status != 'REMOVED'
    """
    print("Coletando thumbnails de criativos do Google Ads (API)...")
    out = {}          # nome -> thumb
    best_prio = {}    # nome -> prioridade do field_type escolhido

    try:
        client = get_client()
        service = client.get_service("GoogleAdsService")
        customer_id = config.GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
        for row in service.search(customer_id=customer_id, query=query):
            nome = (row.ad_group_ad.ad.name or "").strip()
            if not nome:
                continue
            atype = row.asset.type_.name
            if atype == "IMAGE":
                thumb = row.asset.image_asset.full_size.url
            elif atype == "YOUTUBE_VIDEO":
                vid = row.asset.youtube_video_asset.youtube_video_id
                thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg" if vid else ""
            else:
                continue
            if not thumb:
                continue
            ft = row.ad_group_ad_asset_view.field_type.name
            p = PRIO.get(ft, 5)
            if nome not in best_prio or p < best_prio[nome]:
                best_prio[nome] = p
                out[nome] = thumb
    except GoogleAdsException as ex:
        print(f"  AVISO thumbnails Google: {ex.error.code().name}")
    except Exception as e:
        print(f"  AVISO thumbnails Google: {e}")

    print(f"  Thumbnails Google: {len(out)} anuncios com imagem/video.")
    return out

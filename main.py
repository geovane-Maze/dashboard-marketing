from collectors import rdstation, rdcrm, ads_sheets, ga4, google_ads, meta_ads
from sheets import writer
from datetime import datetime


def run():
    print("=" * 50)
    print(f"Dashboard Marketing — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 50)

    # RD Station
    print("\n[1/3] RD Station")
    try:
        leads = rdstation.get_all_leads()
        leads.sort(key=lambda x: x.get("criado_em") or "", reverse=True)
        writer.write_sheet("leads", leads)
    except Exception as e:
        print(f"  ERRO RD Station: {e}")

    # RD CRM
    print("\n[2/4] RD Station CRM")
    try:
        crm_data = rdcrm.get_all_crm_data()
        writer.write_sheet("crm_deals", crm_data["deals"])
        writer.write_sheet("crm_atividades", crm_data["atividades"])
        writer.write_sheet("crm_tarefas", crm_data["tarefas"])
    except Exception as e:
        print(f"  ERRO RD CRM: {e}")

    # Google Analytics 4
    print("\n[3/6] Google Analytics 4")
    try:
        ga4_data = ga4.get_ga4_data()
        writer.write_sheet("ga4_sessions", ga4_data)
    except Exception as e:
        print(f"  ERRO GA4: {e}")

    # Ads (Meta + Google via planilha)
    print("\n[4/6] Meta Ads + Google Ads (planilha)")
    try:
        meta_data, google_data = ads_sheets.get_ads_data()
        writer.write_sheet("meta_ads", meta_data)
        writer.write_sheet("google_ads", google_data)
    except Exception as e:
        print(f"  ERRO Ads Sheets: {e}")

    # Google Ads API (legado)
    print("\n[5/6] Google Ads API")
    try:
        google_data = google_ads.get_campaign_data(days_back=90)
        writer.write_sheet("google_ads", google_data)
    except Exception as e:
        print(f"  ERRO Google Ads: {e}")

    # Meta Ads API (legado)
    print("\n[6/6] Meta Ads API")
    try:
        meta_data = meta_ads.get_campaign_data(days_back=90)
        writer.write_sheet("meta_ads", meta_data)
    except Exception as e:
        print(f"  ERRO Meta Ads: {e}")

    print("\n" + "=" * 50)
    print("Coleta finalizada com sucesso!")
    print("=" * 50)


if __name__ == "__main__":
    run()

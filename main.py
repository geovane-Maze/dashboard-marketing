import sys
# Força output sem buffer pra ver progresso em tempo real (GitHub Actions e logs)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

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
        # Datas de movimentação de etapa — alimenta o "Volume comercial" da
        # aba Metas (eventos por data em que aconteceram).
        stage_events = rdcrm.get_stage_events(
            [d.get("id") for d in crm_data["deals"] if d.get("id")])
        writer.write_sheet("crm_stage_events", stage_events)
    except Exception as e:
        print(f"  ERRO RD CRM: {e}")

    # Google Analytics 4
    print("\n[3/6] Google Analytics 4")
    ga4_falhou = False
    try:
        ga4_data = ga4.get_ga4_data()
        writer.write_sheet("ga4_sessions", ga4_data)
        # Série da aba "Metas e Conversão" (site de expansão via hostName +
        # evento lead_prospecta) — mesma credencial, mesma regra de falha.
        metas_rows = ga4.get_metas_daily()
        writer.write_sheet("ga4_metas_daily", metas_rows)
    except Exception as e:
        # Falha BARULHENTA: essa coleta já ficou 44 dias quebrada em silêncio
        # (secret GA4_TOKEN_JSON malformado, jun-jul/26) com o run verde. O
        # ::error:: vira anotação vermelha e o exit 1 no fim marca o run como
        # FALHO na listagem — o workflow segue rodando o ETL mesmo assim (os
        # steps seguintes têm if: steps.coleta.outcome == 'failure').
        ga4_falhou = True
        err_txt = str(e).replace("\r", " ").replace("\n", " ")
        print(f"  ERRO GA4: {e}")
        print(f"::error::Coleta GA4 FALHOU — aba ga4_sessions NAO atualizada. "
              f"Cheque o secret GA4_TOKEN_JSON (deve ser o JSON exato do arquivo "
              f"local credentials/ga4_token.json). Erro: {err_txt}")

    # Google Ads API (inclui Performance Max via FROM campaign — a planilha
    # Adveronix NÃO captura PMax, então a API é a fonte completa).
    # Janela larga (560d) cobre todo o histórico; merge_sheet preserva o que já
    # existe e corrige retroativamente (incl. PMax) sem truncar a Evolução Mensal.
    print("\n[4/6] Google Ads API")
    google_api_ok = False
    try:
        google_data = google_ads.get_campaign_data(days_back=560)
        if google_data:
            writer.merge_sheet("google_ads", google_data,
                               dedup_keys=["data", "campanha"],
                               date_col="data", retention_days=900)
            google_api_ok = True
    except Exception as e:
        print(f"  ERRO Google Ads API: {e}")

    # Meta Ads — fonte primária: Adveronix (B2B - Facebook Banco de Dados),
    # completo no nível de anúncio e atualizado diariamente.
    print("\n[5/6] Meta Ads (Adveronix - Facebook)")
    meta_api_ok = False
    try:
        meta_data = ads_sheets.get_meta_ads_sheet_data()
        if meta_data:
            writer.write_sheet("meta_ads", meta_data)
            meta_api_ok = True
    except Exception as e:
        print(f"  ERRO Meta Ads (Adveronix): {e}")

    # Planilha externa como fallback se APIs falharam
    if not google_api_ok or not meta_api_ok:
        print("\n[6/6] Planilhas fallback")
        if not google_api_ok:
            try:
                google_data = ads_sheets.get_google_ads_sheet_data()
                if google_data:
                    # merge (não write) pra não destruir o histórico com PMax já
                    # gravado pela API em coletas anteriores.
                    writer.merge_sheet("google_ads", google_data,
                                       dedup_keys=["data", "campanha"],
                                       date_col="data", retention_days=900)
                    google_api_ok = True
            except Exception as e:
                print(f"  ERRO Google Ads planilha diária: {e}")
        if not meta_api_ok:
            try:
                meta_data, _ = ads_sheets.get_ads_data()
                writer.write_sheet("meta_ads", meta_data)
            except Exception as e:
                print(f"  ERRO Meta Ads planilha: {e}")
    else:
        print("\n[6/6] APIs OK — planilhas fallback não necessárias")

    # Google Ads creatives — texto/métricas vêm da planilha Adveronix; a imagem/
    # vídeo do criativo vem da API (a planilha não traz), casada por nome do
    # anúncio. Mesmo padrão do Meta (planilha + thumbnail por fonte separada).
    print("\n[7/7] Google Ads Criativos")
    try:
        creatives_data = ads_sheets.get_google_ads_creatives_sheet_data()
        if creatives_data:
            try:
                gthumbs = google_ads.get_creative_thumbnails()
                if gthumbs:
                    for row in creatives_data:
                        row["thumbnail"] = gthumbs.get((row.get("anuncio") or "").strip(), "")
            except Exception as e:
                print(f"  AVISO: thumbnails Google não aplicados: {e}")
            writer.write_sheet("google_ads_creatives", creatives_data)
    except Exception as e:
        print(f"  ERRO Google Ads Criativos: {e}")

    print("\n" + "=" * 50)
    if ga4_falhou:
        print("Coleta finalizada COM FALHA no GA4 (run marcado como erro).")
        print("=" * 50)
        sys.exit(1)
    print("Coleta finalizada com sucesso!")
    print("=" * 50)


if __name__ == "__main__":
    run()

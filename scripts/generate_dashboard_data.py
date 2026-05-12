#!/usr/bin/env python3
"""
Generate aggregated JSON data for the marketing dashboard.
Run after main.py. Reads from Google Sheets and writes to dashboard/data/summary.json.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REPASSE_KEYWORDS = ["taguatinga", "maringá", "maringa", "praia grande"]

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "data"
)


def get_client():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def read_sheet(gc, sheet_name):
    spreadsheet = gc.open_by_key(config.GOOGLE_SHEET_ID)
    ws = spreadsheet.worksheet(sheet_name)
    rows = ws.get_all_values()
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(cell.strip() for cell in row)]


def parse_num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", ".").replace(" ", "").replace("R$", "").strip())
    except Exception:
        return 0.0


def parse_date_to_month(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()

    # ISO: 2026-01-15T10:30:00...
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except ValueError:
            pass

    # GA4: 20251006
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m")
        except ValueError:
            pass

    # DD/MM/YYYY
    try:
        return datetime.strptime(date_str[:10], "%d/%m/%Y").strftime("%Y-%m")
    except ValueError:
        pass

    # YYYY-MM-DD
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
    except ValueError:
        pass

    # MM/DD/YYYY
    try:
        return datetime.strptime(date_str[:10], "%m/%d/%Y").strftime("%Y-%m")
    except ValueError:
        pass

    return None


def is_repasse(campaign_name):
    if not campaign_name:
        return False
    name_lower = campaign_name.lower()
    return any(kw in name_lower for kw in REPASSE_KEYWORDS)


def aggregate_leads(leads):
    monthly = defaultdict(lambda: {"total": 0, "qualificados": 0})
    by_source = defaultdict(int)
    by_canal = defaultdict(int)
    by_lifecycle = defaultdict(int)
    by_capital = defaultdict(int)
    by_prazo = defaultdict(int)
    canal_monthly = defaultdict(lambda: defaultdict(int))

    for lead in leads:
        mes = parse_date_to_month(lead.get("criado_em"))
        if mes:
            monthly[mes]["total"] += 1
            lc = str(lead.get("lifecycle_stage") or "").lower()
            if "qualif" in lc or "mql" in lc:
                monthly[mes]["qualificados"] += 1

        src = lead.get("utm_source") or lead.get("canal") or "direto"
        by_source[src] += 1

        canal = lead.get("canal") or "sem canal"
        by_canal[canal] += 1

        mes_lead = parse_date_to_month(lead.get("criado_em"))
        if mes_lead:
            canal_monthly[mes_lead][canal] += 1

        lc = lead.get("lifecycle_stage") or "sem estágio"
        by_lifecycle[lc] += 1

        capital = lead.get("capital_disponivel") or "não informado"
        by_capital[capital] += 1

        prazo = lead.get("prazo_abertura") or "não informado"
        by_prazo[prazo] += 1

    pagos = sum(v for k, v in by_canal.items() if any(kw in k.lower() for kw in ["busca paga", "paid", "cpc", " paga"]))
    organicos = len(leads) - pagos

    return {
        "total": len(leads),
        "pagos": pagos,
        "organicos": organicos,
        "monthly": [{"mes": k, **v} for k, v in sorted(monthly.items())],
        "by_source": [
            {"source": k, "total": v}
            for k, v in sorted(by_source.items(), key=lambda x: -x[1])[:15]
        ],
        "by_canal": [
            {"canal": k, "total": v}
            for k, v in sorted(by_canal.items(), key=lambda x: -x[1])
        ],
        "by_lifecycle": [
            {"stage": k, "total": v}
            for k, v in sorted(by_lifecycle.items(), key=lambda x: -x[1])
        ],
        "by_capital": [
            {"capital": k, "total": v}
            for k, v in sorted(by_capital.items(), key=lambda x: -x[1])
            if k != "não informado"
        ],
        "by_prazo": [
            {"prazo": k, "total": v}
            for k, v in sorted(by_prazo.items(), key=lambda x: -x[1])
            if k != "não informado"
        ],
        "canal_monthly": [
            {"mes": mes, "canal": c, "total": count}
            for mes, canals in sorted(canal_monthly.items())
            for c, count in canals.items()
        ],
    }


def aggregate_crm(deals):
    by_stage = defaultdict(lambda: {"total": 0, "valor": 0.0, "ganhos": 0})
    by_loss_reason = defaultdict(int)
    by_responsavel = defaultdict(lambda: {"total": 0, "ganhos": 0, "valor": 0.0})
    monthly_won = defaultdict(lambda: {"total": 0, "valor": 0.0})
    monthly_stages = defaultdict(lambda: {"reuniao_pdf": 0, "apresentacao_bp": 0, "perdidos": 0})

    total_won = 0
    total_lost = 0
    total_value = 0.0

    for deal in deals:
        etapa = deal.get("etapa") or "sem etapa"
        ganho_raw = str(deal.get("ganho") or "").lower()
        ganho = ganho_raw in ("true", "1", "sim", "yes")
        valor = parse_num(deal.get("valor_total"))

        by_stage[etapa]["total"] += 1
        by_stage[etapa]["valor"] += valor
        if ganho:
            by_stage[etapa]["ganhos"] += 1

        if ganho:
            total_won += 1
            total_value += valor
            mes = parse_date_to_month(deal.get("data_fechamento") or deal.get("criado_em"))
            if mes:
                monthly_won[mes]["total"] += 1
                monthly_won[mes]["valor"] += valor

        motivo = deal.get("motivo_perda")
        if motivo:
            by_loss_reason[motivo] += 1
            total_lost += 1

        mes_criado = parse_date_to_month(deal.get("criado_em"))
        if mes_criado:
            etapa_lower = etapa.lower()
            if "reunião pdf" in etapa_lower or "reuniao pdf" in etapa_lower:
                monthly_stages[mes_criado]["reuniao_pdf"] += 1
            if "apresentação do business plan" in etapa_lower or "apresentacao do business plan" in etapa_lower:
                monthly_stages[mes_criado]["apresentacao_bp"] += 1
            if motivo:
                monthly_stages[mes_criado]["perdidos"] += 1

        resp = deal.get("responsavel") or "sem responsável"
        by_responsavel[resp]["total"] += 1
        if ganho:
            by_responsavel[resp]["ganhos"] += 1
            by_responsavel[resp]["valor"] += valor

    total_open = len(deals) - total_won - total_lost

    funnel = sorted(by_stage.items(), key=lambda x: -x[1]["total"])

    return {
        "total_deals": len(deals),
        "total_won": total_won,
        "total_lost": total_lost,
        "total_open": total_open,
        "total_value_won": round(total_value, 2),
        "taxa_fechamento": round(total_won / len(deals) * 100, 1) if deals else 0,
        "funnel": [
            {"etapa": k, "total": v["total"], "valor": round(v["valor"], 2), "ganhos": v["ganhos"]}
            for k, v in funnel
        ],
        "losses": [
            {"motivo": k, "total": v}
            for k, v in sorted(by_loss_reason.items(), key=lambda x: -x[1])
        ],
        "by_responsavel": [
            {"responsavel": k, "total": v["total"], "ganhos": v["ganhos"], "valor": round(v["valor"], 2)}
            for k, v in sorted(by_responsavel.items(), key=lambda x: -x[1]["total"])
        ],
        "monthly_won": [
            {"mes": k, "total": v["total"], "valor": round(v["valor"], 2)}
            for k, v in sorted(monthly_won.items())
        ],
        "monthly_stages": [
            {"mes": k, "reuniao_pdf": v["reuniao_pdf"], "apresentacao_bp": v["apresentacao_bp"], "perdidos": v["perdidos"]}
            for k, v in sorted(monthly_stages.items())
        ],
    }


def aggregate_meta_ads(rows):
    monthly = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
        "expansao_gasto": 0.0, "repasse_gasto": 0.0,
        "expansao_leads": 0.0, "repasse_leads": 0.0,
    })
    campaigns = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0, "tipo": "Expansão"
    })
    camp_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))
    creatives = defaultdict(lambda: {
        "gasto": 0.0, "leads": 0.0, "impressoes": 0.0, "cliques": 0.0,
        "thumbnail": "", "campanha": "",
    })

    for row in rows:
        mes = parse_date_to_month(row.get("data"))
        if not mes:
            continue

        gasto = parse_num(row.get("gasto"))
        leads = parse_num(row.get("leads"))
        impressoes = parse_num(row.get("impressoes"))
        cliques = parse_num(row.get("cliques_link"))
        campanha = row.get("campanha") or ""
        tipo = "Repasse" if is_repasse(campanha) else "Expansão"

        monthly[mes]["gasto"] += gasto
        monthly[mes]["leads"] += leads
        monthly[mes]["impressoes"] += impressoes
        monthly[mes]["cliques"] += cliques

        if tipo == "Repasse":
            monthly[mes]["repasse_gasto"] += gasto
            monthly[mes]["repasse_leads"] += leads
        else:
            monthly[mes]["expansao_gasto"] += gasto
            monthly[mes]["expansao_leads"] += leads

        if campanha:
            campaigns[campanha]["gasto"] += gasto
            campaigns[campanha]["leads"] += leads
            campaigns[campanha]["impressoes"] += impressoes
            campaigns[campanha]["cliques"] += cliques
            campaigns[campanha]["tipo"] = tipo

            camp_monthly[campanha][mes]["gasto"] += gasto
            camp_monthly[campanha][mes]["leads"] += leads
            camp_monthly[campanha][mes]["impressoes"] += impressoes
            camp_monthly[campanha][mes]["cliques"] += cliques

        anuncio = row.get("anuncio") or ""
        if anuncio:
            creatives[anuncio]["gasto"] += gasto
            creatives[anuncio]["leads"] += leads
            creatives[anuncio]["impressoes"] += impressoes
            creatives[anuncio]["cliques"] += cliques
            if row.get("thumbnail"):
                creatives[anuncio]["thumbnail"] = row.get("thumbnail")
            if not creatives[anuncio]["campanha"]:
                creatives[anuncio]["campanha"] = campanha

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        monthly_list.append({
            "mes": mes,
            "gasto": round(d["gasto"], 2),
            "leads": int(round(d["leads"])),
            "cpl": cpl,
            "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])),
            "ctr": ctr,
            "expansao_gasto": round(d["expansao_gasto"], 2),
            "repasse_gasto": round(d["repasse_gasto"], 2),
            "expansao_leads": int(round(d["expansao_leads"])),
            "repasse_leads": int(round(d["repasse_leads"])),
        })

    campaigns_list = []
    for nome, d in sorted(campaigns.items(), key=lambda x: -x[1]["gasto"])[:30]:
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        campaigns_list.append({
            "campanha": nome, "tipo": d["tipo"],
            "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    creatives_list = []
    for nome, d in sorted(creatives.items(), key=lambda x: -x[1]["gasto"])[:50]:
        cpl = round(d["gasto"] / d["leads"], 2) if d["leads"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        creatives_list.append({
            "anuncio": nome, "campanha": d["campanha"],
            "thumbnail": d["thumbnail"],
            "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    campaign_monthly_list = []
    for camp, months in sorted(camp_monthly.items()):
        tipo = "Repasse" if is_repasse(camp) else "Expansão"
        for mes, d in sorted(months.items()):
            campaign_monthly_list.append({
                "campanha": camp, "mes": mes, "tipo": tipo,
                "gasto": round(d["gasto"], 2), "leads": int(round(d["leads"])),
                "impressoes": int(round(d["impressoes"])), "cliques": int(round(d["cliques"])),
            })

    total_gasto = sum(d["gasto"] for d in monthly.values())
    total_leads = sum(d["leads"] for d in monthly.values())

    return {
        "total_gasto": round(total_gasto, 2),
        "total_leads": int(round(total_leads)),
        "cpl_geral": round(total_gasto / total_leads, 2) if total_leads > 0 else 0,
        "monthly": monthly_list,
        "campaigns": campaigns_list,
        "campaign_monthly": campaign_monthly_list,
        "campaign_names": sorted(camp_monthly.keys()),
        "creatives": creatives_list,
    }


def aggregate_google_ads(rows):
    monthly = defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0
    })
    campaigns = defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0
    })
    camp_monthly = defaultdict(lambda: defaultdict(lambda: {
        "gasto": 0.0, "conversoes": 0.0, "impressoes": 0.0, "cliques": 0.0,
    }))

    for row in rows:
        mes = parse_date_to_month(row.get("data"))
        if not mes:
            continue

        gasto = parse_num(row.get("gasto"))
        conversoes = parse_num(row.get("conversoes"))
        impressoes = parse_num(row.get("impressoes"))
        cliques = parse_num(row.get("cliques"))
        campanha = row.get("campanha") or ""

        monthly[mes]["gasto"] += gasto
        monthly[mes]["conversoes"] += conversoes
        monthly[mes]["impressoes"] += impressoes
        monthly[mes]["cliques"] += cliques

        if campanha:
            campaigns[campanha]["gasto"] += gasto
            campaigns[campanha]["conversoes"] += conversoes
            campaigns[campanha]["impressoes"] += impressoes
            campaigns[campanha]["cliques"] += cliques

            camp_monthly[campanha][mes]["gasto"] += gasto
            camp_monthly[campanha][mes]["conversoes"] += conversoes
            camp_monthly[campanha][mes]["impressoes"] += impressoes
            camp_monthly[campanha][mes]["cliques"] += cliques

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        cpl = round(d["gasto"] / d["conversoes"], 2) if d["conversoes"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        monthly_list.append({
            "mes": mes,
            "gasto": round(d["gasto"], 2),
            "conversoes": int(round(d["conversoes"])),
            "cpl": cpl,
            "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])),
            "ctr": ctr,
        })

    campaigns_list = []
    for nome, d in sorted(campaigns.items(), key=lambda x: -x[1]["gasto"])[:30]:
        cpl = round(d["gasto"] / d["conversoes"], 2) if d["conversoes"] > 0 else 0
        ctr = round(d["cliques"] / d["impressoes"] * 100, 2) if d["impressoes"] > 0 else 0
        campaigns_list.append({
            "campanha": nome,
            "gasto": round(d["gasto"], 2), "conversoes": int(round(d["conversoes"])),
            "cpl": cpl, "impressoes": int(round(d["impressoes"])),
            "cliques": int(round(d["cliques"])), "ctr": ctr,
        })

    campaign_monthly_list = []
    for camp, months in sorted(camp_monthly.items()):
        for mes, d in sorted(months.items()):
            campaign_monthly_list.append({
                "campanha": camp, "mes": mes,
                "gasto": round(d["gasto"], 2), "conversoes": int(round(d["conversoes"])),
                "impressoes": int(round(d["impressoes"])), "cliques": int(round(d["cliques"])),
            })

    total_gasto = sum(d["gasto"] for d in monthly.values())
    total_conversoes = sum(d["conversoes"] for d in monthly.values())

    return {
        "total_gasto": round(total_gasto, 2),
        "total_conversoes": int(round(total_conversoes)),
        "cpl_geral": round(total_gasto / total_conversoes, 2) if total_conversoes > 0 else 0,
        "monthly": monthly_list,
        "campaigns": campaigns_list,
        "campaign_monthly": campaign_monthly_list,
        "campaign_names": sorted(camp_monthly.keys()),
    }


def aggregate_ga4(rows):
    monthly = defaultdict(lambda: {
        "sessions": 0, "users": 0, "new_users": 0, "conversions": 0,
        "bounce_weighted": 0.0, "duration_weighted": 0.0,
    })
    channels = defaultdict(lambda: {"sessions": 0, "users": 0, "conversions": 0})
    devices = defaultdict(int)
    pages = defaultdict(int)
    sources = defaultdict(int)

    for row in rows:
        mes = parse_date_to_month(row.get("date"))
        if not mes:
            continue

        sessions = int(parse_num(row.get("sessions")))
        users = int(parse_num(row.get("totalUsers")))
        new_users = int(parse_num(row.get("newUsers")))
        conversions = int(parse_num(row.get("conversions")))
        bounce = parse_num(row.get("bounceRate"))
        duration = parse_num(row.get("averageSessionDuration"))

        monthly[mes]["sessions"] += sessions
        monthly[mes]["users"] += users
        monthly[mes]["new_users"] += new_users
        monthly[mes]["conversions"] += conversions
        monthly[mes]["bounce_weighted"] += bounce * sessions
        monthly[mes]["duration_weighted"] += duration * sessions

        channel = row.get("sessionDefaultChannelGroup") or "outros"
        channels[channel]["sessions"] += sessions
        channels[channel]["users"] += users
        channels[channel]["conversions"] += conversions

        device = row.get("deviceCategory") or "outros"
        devices[device] += sessions

        page = row.get("pagePath") or "/"
        pages[page] += int(parse_num(row.get("screenPageViews")))

        source = row.get("sessionSource") or "direto"
        sources[source] += sessions

    monthly_list = []
    for mes, d in sorted(monthly.items()):
        s = d["sessions"]
        avg_bounce = round(d["bounce_weighted"] / s * 100, 1) if s > 0 else 0
        avg_duration = round(d["duration_weighted"] / s, 1) if s > 0 else 0
        monthly_list.append({
            "mes": mes,
            "sessions": s,
            "users": d["users"],
            "new_users": d["new_users"],
            "conversions": d["conversions"],
            "bounce_rate": avg_bounce,
            "avg_duration": avg_duration,
        })

    return {
        "total_sessions": sum(d["sessions"] for d in monthly.values()),
        "total_users": sum(d["users"] for d in monthly.values()),
        "monthly": monthly_list,
        "channels": [
            {"channel": k, "sessions": v["sessions"], "users": v["users"], "conversions": v["conversions"]}
            for k, v in sorted(channels.items(), key=lambda x: -x[1]["sessions"])
        ],
        "devices": [
            {"device": k, "sessions": v}
            for k, v in sorted(devices.items(), key=lambda x: -x[1])
        ],
        "top_pages": [
            {"page": k, "views": v}
            for k, v in sorted(pages.items(), key=lambda x: -x[1])[:20]
        ],
        "sources": [
            {"source": k, "sessions": v}
            for k, v in sorted(sources.items(), key=lambda x: -x[1])[:15]
        ],
    }


def aggregate_utm(leads):
    sources = defaultdict(int)
    mediums = defaultdict(int)
    campaigns_utm = defaultdict(int)
    sources_monthly = defaultdict(lambda: defaultdict(int))
    mediums_monthly = defaultdict(lambda: defaultdict(int))
    campaigns_monthly = defaultdict(lambda: defaultdict(int))

    for lead in leads:
        src = lead.get("utm_source") or "direto"
        med = lead.get("utm_medium") or "nenhum"
        camp = lead.get("utm_campaign")

        sources[src] += 1
        mediums[med] += 1
        if camp:
            campaigns_utm[camp] += 1

        mes = parse_date_to_month(lead.get("criado_em"))
        if mes:
            sources_monthly[mes][src] += 1
            mediums_monthly[mes][med] += 1
            if camp:
                campaigns_monthly[mes][camp] += 1

    return {
        "sources": [
            {"source": k, "total": v}
            for k, v in sorted(sources.items(), key=lambda x: -x[1])
        ],
        "mediums": [
            {"medium": k, "total": v}
            for k, v in sorted(mediums.items(), key=lambda x: -x[1])
        ],
        "campaigns": [
            {"campaign": k, "total": v}
            for k, v in sorted(campaigns_utm.items(), key=lambda x: -x[1])[:20]
        ],
        "sources_monthly": [
            {"mes": mes, "source": src, "total": count}
            for mes, srcs in sorted(sources_monthly.items())
            for src, count in srcs.items()
        ],
        "mediums_monthly": [
            {"mes": mes, "medium": m, "total": count}
            for mes, meds in sorted(mediums_monthly.items())
            for m, count in meds.items()
        ],
        "campaigns_monthly": [
            {"mes": mes, "campaign": c, "total": count}
            for mes, camps in sorted(campaigns_monthly.items())
            for c, count in camps.items()
        ],
    }


def main():
    print("Gerando dados do dashboard...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    gc = get_client()

    print("  Lendo leads...")
    leads = read_sheet(gc, "leads")

    print("  Lendo CRM deals...")
    crm_deals = read_sheet(gc, "crm_deals")

    print("  Lendo Meta Ads...")
    meta_ads = read_sheet(gc, "meta_ads")

    print("  Lendo Google Ads...")
    google_ads = read_sheet(gc, "google_ads")

    print("  Lendo GA4...")
    ga4 = read_sheet(gc, "ga4_sessions")

    print("  Agregando dados...")
    summary = {
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "totals": {
            "leads": len(leads),
            "crm_deals": len(crm_deals),
            "meta_rows": len(meta_ads),
            "google_rows": len(google_ads),
            "ga4_rows": len(ga4),
        },
        "leads": aggregate_leads(leads),
        "crm": aggregate_crm(crm_deals),
        "meta_ads": aggregate_meta_ads(meta_ads),
        "google_ads": aggregate_google_ads(google_ads),
        "ga4": aggregate_ga4(ga4),
        "utm": aggregate_utm(leads),
    }

    output_file = os.path.join(OUTPUT_DIR, "summary.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(output_file) / 1024
    print(f"  Arquivo gerado: {output_file} ({size_kb:.1f} KB)")
    print("Dashboard data gerado com sucesso!")


if __name__ == "__main__":
    main()

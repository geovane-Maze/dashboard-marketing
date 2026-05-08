import time
import requests
import config

BASE_URL = "https://crm.rdstation.com/api/v1"


def _get(endpoint, params=None):
    p = {"token": config.RD_CRM_TOKEN, "limit": 200}
    if params:
        p.update(params)
    response = requests.get(f"{BASE_URL}/{endpoint}", params=p)
    response.raise_for_status()
    return response.json()


def _paginate(endpoint, key):
    page = 1
    results = []
    while True:
        data = _get(endpoint, {"page": page})
        items = data.get(key, [])
        results.extend(items)
        total = data.get("total", 0)
        if len(results) >= total or not items:
            break
        page += 1
        time.sleep(0.2)
    return results


def get_deals():
    print("Coletando negócios (deals)...")
    raw = _paginate("deals", "deals")
    deals = []
    for d in raw:
        contact = (d.get("contacts") or [{}])[0]
        emails = contact.get("emails") or []
        phones = contact.get("phones") or []
        lost = d.get("deal_lost_reason") or {}
        deals.append({
            "id": d.get("id"),
            "nome": d.get("name"),
            "valor_total": d.get("amount_total"),
            "valor_mensal": d.get("amount_montly"),
            "valor_unico": d.get("amount_unique"),
            "ganho": d.get("win"),
            "data_fechamento": d.get("closed_at"),
            "data_previsao": d.get("prediction_date"),
            "criado_em": d.get("created_at"),
            "atualizado_em": d.get("updated_at"),
            "etapa": (d.get("deal_stage") or {}).get("name"),
            "pipeline": (d.get("deal_pipeline") or {}).get("name"),
            "responsavel": (d.get("user") or {}).get("name"),
            "fonte": (d.get("deal_source") or {}).get("name"),
            "campanha": (d.get("campaign") or {}).get("name"),
            "motivo_perda": lost.get("name"),
            "rating": d.get("rating"),
            "interacoes": d.get("interactions"),
            "contato_nome": contact.get("name"),
            "contato_email": emails[0].get("email") if emails else None,
            "contato_telefone": phones[0].get("phone") if phones else None,
            "em_espera": d.get("hold"),
        })
    print(f"  Total de negócios: {len(deals)}")
    return deals


def get_activities():
    print("Coletando atividades...")
    raw = _paginate("activities", "activities")
    activities = []
    for a in raw:
        activities.append({
            "id": a.get("id"),
            "tipo": a.get("type"),
            "descricao": a.get("subject") or a.get("description"),
            "data": a.get("date") or a.get("created_at"),
            "concluida": a.get("done"),
            "data_conclusao": a.get("done_date"),
            "deal_id": a.get("deal_id"),
            "deal_nome": (a.get("deal") or {}).get("name"),
            "responsavel": ((a.get("users") or [{}])[0]).get("name"),
            "notas": a.get("notes"),
        })
    print(f"  Total de atividades: {len(activities)}")
    return activities


def get_tasks():
    print("Coletando tarefas...")
    raw = _paginate("tasks", "tasks")
    tasks = []
    for t in raw:
        tasks.append({
            "id": t.get("id"),
            "assunto": t.get("subject"),
            "tipo": t.get("type"),
            "data": t.get("date"),
            "hora": t.get("hour"),
            "concluida": t.get("done"),
            "data_conclusao": t.get("done_date"),
            "status": t.get("status"),
            "deal_id": t.get("deal_id"),
            "deal_nome": (t.get("deal") or {}).get("name"),
            "responsavel": ((t.get("users") or [{}])[0]).get("name"),
            "notas": t.get("notes"),
            "criado_em": t.get("created_at"),
        })
    print(f"  Total de tarefas: {len(tasks)}")
    return tasks


def get_all_crm_data():
    return {
        "deals": get_deals(),
        "atividades": get_activities(),
        "tarefas": get_tasks(),
    }

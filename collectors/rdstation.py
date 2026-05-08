import os
import time
import requests
import config

BASE_URL = "https://api.rd.services"


def get_access_token():
    response = requests.post(
        f"{BASE_URL}/auth/token",
        params={"token_by": "refresh_token"},
        json={
            "client_id": config.RD_CLIENT_ID,
            "client_secret": config.RD_CLIENT_SECRET,
            "refresh_token": config.RD_REFRESH_TOKEN,
        },
    )
    response.raise_for_status()
    data = response.json()

    new_refresh_token = data.get("refresh_token")
    if new_refresh_token and new_refresh_token != config.RD_REFRESH_TOKEN:
        _update_env("RD_REFRESH_TOKEN", new_refresh_token)
        config.RD_REFRESH_TOKEN = new_refresh_token

    return data["access_token"]


def _update_env(chave, valor):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        updated = []
        found = False
        for line in lines:
            if line.startswith(f"{chave}="):
                updated.append(f"{chave}={valor}")
                found = True
            else:
                updated.append(line)
        if not found:
            updated.append(f"{chave}={valor}")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated) + "\n")
    except Exception as e:
        print(f"  Aviso: nao foi possivel atualizar .env: {e}")


def _get_segmentation_id(headers):
    response = requests.get(f"{BASE_URL}/platform/segmentations", headers=headers)
    response.raise_for_status()
    segmentations = response.json().get("segmentations", [])

    for seg in segmentations:
        if seg.get("standard") and "todos" in seg.get("name", "").lower():
            return seg["id"], seg["name"]

    if segmentations:
        return segmentations[0]["id"], segmentations[0]["name"]

    raise Exception("Nenhuma segmentacao encontrada na conta do RD Station.")


def _get_contact_details(uuid, headers):
    response = requests.get(
        f"{BASE_URL}/platform/contacts/{uuid}",
        headers=headers,
    )
    if response.status_code != 200:
        return {}
    data = response.json()
    # A API pode retornar o contato diretamente ou dentro de "contact"
    return data.get("contact", data)


def get_all_leads():
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    leads = []
    page = 1

    print("Buscando segmentacao de contatos...")
    seg_id, seg_name = _get_segmentation_id(headers)
    print(f"  Usando segmentacao: {seg_name} (ID: {seg_id})")
    print("Coletando leads do RD Station...")

    while True:
        response = requests.get(
            f"{BASE_URL}/platform/segmentations/{seg_id}/contacts",
            headers=headers,
            params={"page": page, "page_size": 20},
        )

        if response.status_code == 404:
            break

        response.raise_for_status()
        data = response.json()
        contacts = data.get("contacts", [])

        if not contacts:
            break

        for contact in contacts:
            uuid = contact.get("uuid")
            details = _get_contact_details(uuid, headers)
            time.sleep(0.1)

            # UTMs podem estar em campos aninhados na v2
            personal_fields = details.get("personal_fields", {})

            origem_raw = details.get("cf_plug_opportunity_origin") or ""
            partes = [p.strip() for p in origem_raw.split("|")] if "|" in origem_raw else [origem_raw.strip(), ""]
            canal = partes[0] if partes[0] else None
            fonte = partes[1] if len(partes) > 1 and partes[1] else None

            lead = {
                "id": uuid,
                "nome": details.get("name") or contact.get("name"),
                "email": details.get("email") or contact.get("email"),
                "telefone": details.get("mobile_phone") or details.get("personal_phone"),
                "cidade": details.get("city"),
                "estado": details.get("state"),
                "criado_em": details.get("created_at") or contact.get("created_at"),
                "atualizado_em": details.get("updated_at"),
                "tags": ", ".join(details.get("tags", [])),
                "lifecycle_stage": details.get("lifecycle_stage"),
                "canal": canal,
                "fonte": fonte,
                "origem_completa": origem_raw or None,
                "estagio_funil": details.get("cf_plug_funnel_stage"),
                "responsavel": details.get("cf_plug_contact_owner"),
                "pipeline": details.get("cf_plug_deal_pipeline"),
                "score": details.get("cf_plug_opportunity_score"),
                "valor_oportunidade": details.get("cf_plug_opportunity_value"),
                "capital_disponivel": details.get("cf_faixa_de_capital_disponivel"),
                "prazo_abertura": details.get("cf_em_quanto_tempo_pretende_abrir_a_sua_franquia_2"),
                "meio_contato": details.get("cf_melhor_meio_para_contato"),
            }
            leads.append(lead)

        print(f"  Pagina {page}: {len(contacts)} leads coletados")
        page += 1

    print(f"Total de leads coletados: {len(leads)}")
    return leads

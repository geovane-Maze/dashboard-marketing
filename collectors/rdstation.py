import os
import time
import base64
import json
import requests
from urllib.parse import parse_qs, unquote
from concurrent.futures import ThreadPoolExecutor
import threading
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


class _ApiContext:
    """Encapsula token + headers para permitir refresh durante run longo.
    Thread-safe: usa lock no refresh para evitar refresh concorrente."""
    def __init__(self):
        self.token = get_access_token()
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.failures = {"details": 0, "events": 0}
        self._lock = threading.Lock()

    def refresh(self):
        with self._lock:
            self.token = get_access_token()
            self.headers = {"Authorization": f"Bearer {self.token}"}


def _request_with_retry(url, ctx, params=None, max_retries=8, kind="details"):
    """GET com retry exponencial. Refaz token em 401. Backoff em 429/5xx.
    Mais retries (8) e backoff maior pra lidar com rate limit da API RD."""
    backoff = 2.0
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=ctx.headers, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  [Retry {attempt+1}/{max_retries}] rede falhou: {e}")
            time.sleep(backoff); backoff = min(backoff * 2, 60); continue

        if resp.status_code == 200:
            return resp
        if resp.status_code == 401:
            ctx.refresh()
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = float(resp.headers.get("Retry-After", backoff))
            time.sleep(retry_after); backoff = min(backoff * 2, 60); continue
        return resp

    ctx.failures[kind] += 1
    return None


def _get_contact_details(uuid, ctx):
    resp = _request_with_retry(
        f"{BASE_URL}/platform/contacts/{uuid}", ctx, kind="details"
    )
    if resp is None or resp.status_code != 200:
        return {}
    data = resp.json()
    return data.get("contact", data)


def _decode_traffic_source(traffic_source_raw):
    """Decodifica o campo traffic_source (Base64) e extrai UTMs da sessao atual."""
    if not traffic_source_raw:
        return {}
    try:
        encoded = traffic_source_raw.replace("encoded_", "", 1)
        # Adiciona padding se necessario
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        data = json.loads(decoded)

        # Usa current_session; fallback para first_session
        session = data.get("current_session") or data.get("first_session") or {}
        value = session.get("value", "")

        if not value or value in ("(none)", ""):
            return {}

        # Remove "+" inicial se houver
        value = value.lstrip("+")

        # Parseia query string: utm_source=x&utm_medium=y...
        # PEGADINHA (17/07/2026): links de campanha quebrados chegam como
        # '?%20utm_source=googlecpc&...' — o %20 vira ESPAÇO no nome do 1º
        # parâmetro (' utm_source') e o get("utm_source") não encontrava,
        # deixando a coluna utm_source VAZIA (lead pago caía como orgânico).
        # Normaliza as chaves (strip de espaços e '?') pra recuperar.
        params = parse_qs(value, keep_blank_values=False)
        params = {k.strip().lstrip("?").strip(): v for k, v in params.items()}
        result = {
            "utm_source": params.get("utm_source", [None])[0],
            "utm_medium": params.get("utm_medium", [None])[0],
            "utm_campaign": params.get("utm_campaign", [None])[0],
            "utm_term": params.get("utm_term", [None])[0],
            "utm_content": params.get("utm_content", [None])[0],
            "utm_id": params.get("utm_id", [None])[0],
            "origem_detalhes": value,
        }
        return result
    except Exception:
        return {}


def _get_conversion_utms(uuid, ctx):
    """Busca eventos de conversao do contato e extrai UTMs."""
    resp = _request_with_retry(
        f"{BASE_URL}/platform/contacts/{uuid}/events", ctx,
        params={"event_type": "CONVERSION"}, kind="events"
    )
    if resp is None or resp.status_code != 200:
        return {}
    try:
        events = resp.json()
        if not events:
            return {}
        for event in events:
            payload = event.get("payload", {})
            traffic_source = payload.get("traffic_source", "")
            if traffic_source and traffic_source.startswith("encoded_"):
                return _decode_traffic_source(traffic_source)
    except Exception:
        return {}
    return {}


def _fetch_contact_full(uuid_and_contact, ctx):
    """Busca details + UTMs de 1 contato. Usado pelo ThreadPoolExecutor."""
    uuid, contact = uuid_and_contact
    details = _get_contact_details(uuid, ctx)
    utms = _get_conversion_utms(uuid, ctx)

    origem_raw = details.get("cf_plug_opportunity_origin") or ""
    partes = [p.strip() for p in origem_raw.split("|")] if "|" in origem_raw else [origem_raw.strip(), ""]
    canal = partes[0] if partes[0] else None
    fonte = partes[1] if len(partes) > 1 and partes[1] else None

    return {
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
        "utm_source": utms.get("utm_source"),
        "utm_medium": utms.get("utm_medium"),
        "utm_campaign": utms.get("utm_campaign"),
        "utm_term": utms.get("utm_term"),
        "utm_content": utms.get("utm_content"),
        "utm_id": utms.get("utm_id"),
        "origem_detalhes": utms.get("origem_detalhes"),
        "estagio_funil": details.get("cf_plug_funnel_stage"),
        "responsavel": details.get("cf_plug_contact_owner"),
        "pipeline": details.get("cf_plug_deal_pipeline"),
        "score": details.get("cf_plug_opportunity_score"),
        "valor_oportunidade": details.get("cf_plug_opportunity_value"),
        "capital_disponivel": details.get("cf_faixa_de_capital_disponivel"),
        "prazo_abertura": details.get("cf_em_quanto_tempo_pretende_abrir_a_sua_franquia_2"),
        "meio_contato": details.get("cf_melhor_meio_para_contato"),
    }


def get_all_leads(max_workers=4):
    """
    Coleta todos os leads do RD Station com paginação + paralelização.
    Cada contato faz 2 chamadas (details + events). Com 8 workers em paralelo
    e leads chegando em batches de 20, ganha ~6-8x de velocidade vs serial.
    """
    ctx = _ApiContext()
    leads = []
    seen_uuids = set()
    page = 1
    duplicate_count = 0
    contacts_processed = 0

    print("Buscando segmentacao de contatos...")
    seg_id, seg_name = _get_segmentation_id(ctx.headers)
    print(f"  Usando segmentacao: {seg_name} (ID: {seg_id})")
    print(f"Coletando leads do RD Station (paralelo: {max_workers} workers)...")

    executor = ThreadPoolExecutor(max_workers=max_workers)

    try:
        while True:
            resp = _request_with_retry(
                f"{BASE_URL}/platform/segmentations/{seg_id}/contacts",
                ctx, params={"page": page, "page_size": 20}, kind="details"
            )
            if resp is None or resp.status_code == 404:
                break
            if resp.status_code != 200:
                print(f"  ERRO segmentação página {page}: HTTP {resp.status_code}")
                break

            data = resp.json()
            contacts = data.get("contacts", [])
            if not contacts:
                break

            # Filtra dedup primeiro
            to_fetch = []
            for contact in contacts:
                uuid = contact.get("uuid")
                if not uuid:
                    continue
                if uuid in seen_uuids:
                    duplicate_count += 1
                    continue
                seen_uuids.add(uuid)
                to_fetch.append((uuid, contact))

            # Refresh proativo do token a cada ~100 contatos
            if contacts_processed > 0 and contacts_processed // 100 != (contacts_processed + len(to_fetch)) // 100:
                ctx.refresh()
            contacts_processed += len(to_fetch)

            # Fetch em paralelo (cada worker pega 1 contato → 2 chamadas API)
            for lead in executor.map(lambda x: _fetch_contact_full(x, ctx), to_fetch):
                leads.append(lead)

            print(f"  Pagina {page}: {len(contacts)} leads coletados")
            page += 1
    finally:
        executor.shutdown(wait=True)

    if duplicate_count > 0:
        print(f"  Avisos: {duplicate_count} contatos duplicados (paginação RD) foram ignorados.")
    if ctx.failures["details"] > 0 or ctx.failures["events"] > 0:
        print(f"  ATENÇÃO: {ctx.failures['details']} falhas em /contacts, {ctx.failures['events']} em /events.")
    print(f"Total de leads coletados: {len(leads)}")
    return leads

# -*- coding: utf-8 -*-
"""
Previsibilidade 2026 — modelo NATIVO (calculado no pipeline).

Substitui a antiga leitura "espelho" da planilha. Consolida 3 fontes:
  - Jan-Abr : meta da planilha-base "Previsibilidade B2B - 2026" (1Bf5X...).
  - Mai-Jun : REAL do CRM (deals + deal_stage_histories via API), sem importações.
  - Jul-Dez : projeção replicando as premissas da planilha + 3 cenários (+-30%).

Saída (vai pro summary.json em `previsibilidade`):
  {
    modelo: 'nativo', ticket, ultima_atualizacao, meses:[12],
    linha:[12x {mes,key,fonte,investimento,leads,cpl,vendas,receita,meta:{...},importados?,parcial?}],
    cenarios:{pessimista|real|otimista: {vendas:[12],receita:[12],total_vendas,total_receita}},
    funil:{etapas:[15],meta_maio:[15],pcts:[15],real_maio:[15],real_junho:[15],crm_etapas:[12]},
  }
"""
import re
from datetime import datetime
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor

import requests
import gspread
from google.oauth2.service_account import Credentials

import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Planilha-base nova (modelo completo de previsibilidade)
PREVISIBILIDADE_SHEET_ID = "1Bf5XInjZ6e_fgqQ9wxDN9Cpb7KYEkFLV-wo6MY43hPA"
PREVISIBILIDADE_TAB_NAME = "PREVISIBILIDADE "   # nota: tem espaço no fim

CRM_API = "https://crm.rdstation.com/api/v1"
TICKET = 1_000_000
MAX_WORKERS = 4   # conservador (alinhado à cultura RD do projeto)

MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
         'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
KEYMES = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06',
          '2026-07', '2026-08', '2026-09', '2026-10', '2026-11', '2026-12']

# Funil EXIBIDO = as 14 etapas REAIS do CRM da Clínica (as que a equipe usa no dia a dia).
# Os 12 primeiros são estágios do pipeline "Funil CDC"; "Assinatura do Contrato" e
# "Negócio Fechado" não são estágios — são o desfecho (deal ganho), derivados de win.
ETAPAS_CRM = [
    'Entrada de Lead', 'Tentativa de Contato', 'Qualificação', 'Qualificado Não agendada',
    '1ª Reunião Agendada', '1ª Reunião Realizada', 'Reunião de BP Agendada',
    'Reunião de BP Realizada', 'Envio de COF', 'Visita / Reunião com Jamil',
    'Análise Financeira/Jurídica', 'Comitê Final', 'Assinatura do Contrato', 'Negócio Fechado',
]

# Meta de cada etapa do CRM (14, índice) vem da etapa correspondente da planilha (15, índice).
# A planilha agrupa diferente (Nutrição 1/2, Reunião Alinhamento) — mapa aproximado p/ referência.
META_MAP = {
    0: 0,    # Entrada de Lead          -> 1ª Entrada de lead
    1: 1,    # Tentativa de Contato     -> 2º Contato inicial
    2: 2,    # Qualificação             -> 3º Nutrição 1
    3: 4,    # Qualificado Não agendada -> 5º Pré-Qualificado
    4: 5,    # 1ª Reunião Agendada      -> 6º Reunião Agendada
    5: 6,    # 1ª Reunião Realizada     -> 7º Reunião Realizada
    6: 7,    # Reunião de BP Agendada   -> 8º Reunião BP
    7: 7,    # Reunião de BP Realizada  -> 8º Reunião BP
    8: 8,    # Envio de COF             -> 9º Envio de COF
    9: 10,   # Visita/Reunião com Jamil -> 11º Visita Técnica
    10: 11,  # Análise Financeira/Jur.  -> 12º Análise Jurídica
    11: 12,  # Comite Final             -> 13º Comitê
    12: 13,  # Assinatura do Contrato   -> 14º Assinatura do Contrato
    13: 14,  # Negócio Fechado          -> 15º Negócio Fechado
}


# ─────────────────────────── helpers ───────────────────────────
def parse_num(s):
    """'R$ 1.001.032,54' -> 1001032.54 ; '0,29%' -> 0.0029 ; '340' -> 340."""
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s or s in ('-', '%'):
        return 0.0
    pct = s.endswith('%')
    s = s.replace('R$', '').replace('%', '').strip()
    s = s.replace('.', '').replace(',', '.')
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return v / 100 if pct else v


def _gspread_client():
    creds = Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


# ─────────────────────────── 1) planilha (meta + projeção) ───────────────────────────
def ler_planilha():
    gc = _gspread_client()
    rows = gc.open_by_key(PREVISIBILIDADE_SHEET_ID).worksheet(PREVISIBILIDADE_TAB_NAME).get_all_values()
    cols = [1 + i * 2 for i in range(12)]   # 12 meses: valor na col, %CRM na col+1

    def linha(prefixo):
        for r in rows[8:38]:
            lab = (r[0] or '').strip().lower()
            if lab.startswith(prefixo.lower()):
                return [parse_num(r[c]) if c < len(r) else 0.0 for c in cols]
        return [0.0] * 12

    funil = []
    for r in rows[8:38]:
        lab = (r[0] or '').strip()
        if re.match(r'^\d+[ºª]\s', lab):
            vals = [parse_num(r[c]) if c < len(r) else 0.0 for c in cols]
            pcts = [parse_num(r[c + 1]) if c + 1 < len(r) else 0.0 for c in cols]
            funil.append({'etapa': lab, 'valores': vals, 'pcts': pcts})

    return {
        'investimento': linha('investimento'),
        'leads': linha('leads'),
        'cpl': linha('cpl'),
        'vendas': linha('vendas'),
        'receita': linha('receita faturada'),
        'funil': funil,
    }


# ─────────────────────────── 2) CRM real (Mai-Jun) ───────────────────────────
def _crm_token():
    return {'token': config.RD_CRM_TOKEN}


def _stage_order():
    r = requests.get(f'{CRM_API}/deal_pipelines', params=_crm_token(), timeout=30)
    r.raise_for_status()
    d = r.json()
    pipes = d if isinstance(d, list) else d.get('deal_pipelines', [])
    smap, order = {}, []
    for p in pipes:
        for st in p.get('deal_stages', []):
            smap[st['id']] = st['name']
            order.append(st['name'])
    return smap, order


def _all_deals():
    out, page = [], 1
    while True:
        r = requests.get(f'{CRM_API}/deals', params={**_crm_token(), 'limit': 200, 'page': page}, timeout=30)
        r.raise_for_status()
        j = r.json()
        it = j.get('deals', [])
        if not it:
            break
        out += it
        if len(out) >= j.get('total', 0):
            break
        page += 1
    return out


def _hist(did):
    try:
        r = requests.get(f'{CRM_API}/deals/{did}', params=_crm_token(), timeout=30)
        if r.status_code != 200:
            return did, []
        return did, (r.json().get('deal_stage_histories') or [])
    except Exception:
        return did, []


def _import_secs(deals):
    """Segundos com >=3 deals criados = assinatura de import em massa."""
    sec = Counter((d.get('created_at') or '')[:19] for d in deals)
    return {k for k, v in sec.items() if v >= 3}


def funil_real():
    """Retorna o funil real (12 etapas CRM) por mês p/ Mai e Jun, excluindo importações."""
    smap, order = _stage_order()
    idx = {n: i for i, n in enumerate(order)}
    N = len(order)
    deals = _all_deals()
    ids = [d['id'] for d in deals]

    hists = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for did, h in ex.map(_hist, ids):
            hists[did] = h

    cur_stage = {d['id']: (d.get('deal_stage') or {}).get('name') for d in deals}

    def max_reached(d):
        mx = -1
        for e in hists.get(d['id'], []):
            n = smap.get(e.get('deal_stage_id'))
            if n in idx:
                mx = max(mx, idx[n])
        cs = cur_stage.get(d['id'])
        if cs in idx:
            mx = max(mx, idx[cs])
        return mx

    bymes = defaultdict(list)
    for d in deals:
        bymes[(d.get('created_at') or '')[:7]].append(d)

    out = {}
    for M in ('2026-05', '2026-06'):
        ds = bymes.get(M, [])
        imp = _import_secs(ds)
        reais = [d for d in ds if (d.get('created_at') or '')[:19] not in imp]
        reached = [0] * N
        for d in reais:
            mr = max_reached(d)
            for i in range(N):
                if mr >= i:
                    reached[i] += 1
        out[M] = {
            'entradas': len(reais),
            'importados': len(ds) - len(reais),
            'funil': reached,
            'vendas': sum(1 for d in reais if d.get('win') is True),
            'order': order,
        }
    return out


def _real_crm14(reached12, vendas):
    """Real das 14 etapas do CRM: 12 estágios do pipeline + Assinatura/Negócio Fechado (=ganhos)."""
    base = list(reached12[:12]) + [0] * max(0, 12 - len(reached12))
    return base[:12] + [vendas, vendas]   # Assinatura e Negócio Fechado = deals ganhos


def _conv_pcts(real14):
    """Conversão real entre etapas (etapa N / etapa N-1, %). Primeira etapa fica None."""
    out = [None]
    for i in range(1, len(real14)):
        prev = real14[i - 1]
        out.append(round(real14[i] / prev * 100, 1) if prev else 0.0)
    return out


# ─────────────────────────── 3) builder ───────────────────────────
def get_previsibilidade_data(meta_monthly=None, google_monthly=None):
    """
    Monta o bloco nativo. `meta_monthly`/`google_monthly` são as listas
    `monthly` ([{mes, gasto, ...}]) já agregadas no ETL — usadas p/ o
    investimento REAL de Mai/Jun. Se não vierem, investimento real fica 0.
    """
    plan = ler_planilha()
    real = funil_real()

    mm = {x['mes']: x.get('gasto', 0) for x in (meta_monthly or [])}
    gm = {x['mes']: x.get('gasto', 0) for x in (google_monthly or [])}
    invest_real = {m: round(mm.get(m, 0) + gm.get(m, 0), 2) for m in ('2026-05', '2026-06')}

    linha = []
    for i, km in enumerate(KEYMES):
        meta = {
            'investimento': round(plan['investimento'][i], 2),
            'leads': round(plan['leads'][i]),
            'cpl': round(plan['cpl'][i], 2),
            'vendas': round(plan['vendas'][i], 2),
            'receita': round(plan['receita'][i], 2),
        }
        if i <= 3:                       # Jan-Abr: meta
            linha.append({'mes': MESES[i], 'key': km, 'fonte': 'meta', **meta, 'meta': meta})
        elif km in real:                 # Mai-Jun: real do CRM
            ld = real[km]['entradas']
            inv = invest_real.get(km, 0)
            linha.append({
                'mes': MESES[i], 'key': km, 'fonte': 'real',
                'investimento': inv, 'leads': ld,
                'cpl': round(inv / ld, 2) if ld else 0,
                'vendas': real[km]['vendas'], 'receita': real[km]['vendas'] * TICKET,
                'importados': real[km]['importados'],
                'parcial': km == '2026-06',
                'meta': meta,
            })
        else:                            # Jul-Dez: projeção
            linha.append({'mes': MESES[i], 'key': km, 'fonte': 'projecao', **meta, 'meta': meta})

    def cenario(mult):
        vendas, receita = [], []
        for i, it in enumerate(linha):
            if i >= 6:                   # projeção -> aplica ±30%
                v = round(plan['vendas'][i] * mult, 2)
                vendas.append(v)
                receita.append(round(plan['vendas'][i] * mult * TICKET, 2))
            else:                        # histórico (meta jan-abr / real mai-jun) fixo
                vendas.append(it['vendas'])
                receita.append(it['receita'])
        return {'vendas': vendas, 'receita': receita,
                'total_vendas': round(sum(vendas), 2), 'total_receita': round(sum(receita), 2)}

    cenarios = {'pessimista': cenario(0.7), 'real': cenario(1.0), 'otimista': cenario(1.3)}

    # Funil nas 14 etapas REAIS do CRM. Meta = referência mapeada da planilha (col Maio).
    real_maio = _real_crm14(real['2026-05']['funil'], real['2026-05']['vendas'])
    real_junho = _real_crm14(real['2026-06']['funil'], real['2026-06']['vendas'])
    meta_maio = [round(plan['funil'][META_MAP[i]]['valores'][4]) for i in range(len(ETAPAS_CRM))]
    funil = {
        'etapas': ETAPAS_CRM,
        'meta_maio': meta_maio,
        'pcts': _conv_pcts(real_maio),     # conversão REAL entre etapas do CRM (Maio)
        'real_maio': real_maio,
        'real_junho': real_junho,
    }

    return {
        'modelo': 'nativo',
        'ticket': TICKET,
        'ultima_atualizacao': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'meses': MESES,
        'linha': linha,
        'cenarios': cenarios,
        'funil': funil,
    }

# -*- coding: utf-8 -*-
"""
Previsibilidade 2026 — modelo NATIVO v2 (auditado jun/2026).

Reconstruído após auditoria executiva (cálculo determinístico + revisão multi-lente).
Regras-chave:
  - Jan–Jun = REALIZADO (investimento, leads, sessões reais informados pelo diretor).
  - Jul–Dez = PROJEÇÃO (investimento informado; leads = investimento / CPL do cenário).
  - CPL = investimento / leads ; CPS = investimento / sessões ; ConvLP = leads / sessões.
  - Funil = 14 etapas REAIS do CRM, por TAXA DE PASSAGEM etapa→etapa.
  - Receita = negócios fechados × ticket (NUNCA × leads).
  - Sem arredondar nas fórmulas (arredonda só na saída).

Fonte dos números reais: dados oficiais informados pelo diretor (jun/2026) — são meses
fechados, por isso ficam fixos no código (o summary do ETL tinha junho parcial/errado).
O funil REAL por etapa (camada de atingimento) é dinâmico, do CRM.
"""
from datetime import datetime
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor

import requests
import config

TICKET = 1_000_000
CRM_API = "https://crm.rdstation.com/api/v1"
MAX_WORKERS = 4

MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
MES_NOME = {'Jan': 'Janeiro', 'Fev': 'Fevereiro', 'Mar': 'Março', 'Abr': 'Abril', 'Mai': 'Maio',
            'Jun': 'Junho', 'Jul': 'Julho', 'Ago': 'Agosto', 'Set': 'Setembro', 'Out': 'Outubro',
            'Nov': 'Novembro', 'Dez': 'Dezembro'}
REAL = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun']
PROJ = ['Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
KEYMES = {'Mai': '2026-05', 'Jun': '2026-06'}

# ─────────── DADOS REAIS (Jan–Jun) — oficiais, meses fechados ───────────
INVEST_REAL = {'Jan': 23634.45, 'Fev': 27362.87, 'Mar': 10373.57, 'Abr': 18182.95, 'Mai': 21897.03, 'Jun': 20954.55}
INVEST_PROJ = {'Jul': 25000.00, 'Ago': 25000.00, 'Set': 30000.00, 'Out': 36000.00, 'Nov': 43200.00, 'Dez': 51840.00}
LEADS_REAL = {'Jan': 244, 'Fev': 188, 'Mar': 35, 'Abr': 87, 'Mai': 146, 'Jun': 79}
SESSOES = {'Jan': 6453, 'Fev': 7880, 'Mar': 3893, 'Abr': 5779, 'Mai': 6459, 'Jun': 4546}

# Funil = 14 etapas REAIS do CRM. taxa = passagem da etapa anterior -> esta (Entrada = 100%).
FUNIL = [
    ('Entrada de Lead', 1.0000),
    ('Tentativa de Contato', 0.8900),
    ('Qualificação', 0.9000),
    ('Qualificado Não Agendada', 0.3300),
    ('1ª Reunião Agendada', 0.7950),
    ('1ª Reunião Realizada', 0.5600),
    ('Reunião de BP Agendada', 0.6700),
    ('Reunião de BP Realizada', 0.4600),
    ('Envio de COF', 0.6000),
    ('Visita / Reunião com Jamil', 0.5900),
    ('Análise Financeira/Jurídica', 0.2700),
    ('Comitê Final', 0.9200),
    ('Assinatura do Contrato', 0.9700),
    ('Negócio Fechado', 0.9800),
]
IDX_1A_REUNIAO = 4   # índice de "1ª Reunião Agendada"


# ─────────── funil acumulado (taxa de passagem) ───────────
def _funil_modelo():
    vol = [1000.0]
    acum = [1.0]
    for i in range(1, len(FUNIL)):
        vol.append(vol[-1] * FUNIL[i][1])
        acum.append(acum[-1] * FUNIL[i][1])
    etapas = []
    for i, (nome, tx) in enumerate(FUNIL):
        etapas.append({
            'etapa': nome,
            'passagem': tx,
            'volume_por_1000': round(vol[i], 2),
            'acumulada': acum[i],                       # precisão cheia
            'acumulada_pct': round(acum[i] * 100, 4),
            'perda_abs_por_1000': round(0.0 if i == 0 else vol[i-1] - vol[i], 2),
            'perda_pct': round(0.0 if i == 0 else 1 - tx, 4),
        })
    # gargalos
    tx_min_i = min(range(1, len(FUNIL)), key=lambda i: FUNIL[i][1])
    perda_abs = [(FUNIL[i][0], vol[i-1] - vol[i]) for i in range(1, len(FUNIL))]
    maior_perda = max(perda_abs, key=lambda x: x[1])
    resumo = {
        'aprov_ate_1a_reuniao': acum[IDX_1A_REUNIAO],
        'entrada_ate_negocio_fechado': acum[-1],
        'leads_por_venda': 1 / acum[-1] if acum[-1] else 0,
        'gargalo_menor_taxa': FUNIL[tx_min_i][0],
        'gargalo_menor_taxa_valor': FUNIL[tx_min_i][1],
        'maior_perda_absoluta': maior_perda[0],
    }
    return etapas, acum, resumo


# ─────────── CRM real (atingimento Mai/Jun) ───────────
def _crm_token():
    return {'token': config.RD_CRM_TOKEN}


def _funil_real_crm():
    try:
        r = requests.get(f'{CRM_API}/deal_pipelines', params=_crm_token(), timeout=30)
        r.raise_for_status()
        d = r.json()
        pipes = d if isinstance(d, list) else d.get('deal_pipelines', [])
        smap, order = {}, []
        for p in pipes:
            for st in p.get('deal_stages', []):
                smap[st['id']] = st['name']; order.append(st['name'])
        idx = {n: i for i, n in enumerate(order)}

        deals, page = [], 1
        while True:
            rr = requests.get(f'{CRM_API}/deals', params={**_crm_token(), 'limit': 200, 'page': page}, timeout=30)
            rr.raise_for_status()
            j = rr.json(); it = j.get('deals', [])
            if not it:
                break
            deals += it
            if len(deals) >= j.get('total', 0):
                break
            page += 1
        ids = [x['id'] for x in deals]

        def hist(did):
            try:
                rh = requests.get(f'{CRM_API}/deals/{did}', params=_crm_token(), timeout=30)
                return did, (rh.json().get('deal_stage_histories') or []) if rh.status_code == 200 else []
            except Exception:
                return did, []
        hists = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            for did, h in ex.map(hist, ids):
                hists[did] = h
        cur = {x['id']: (x.get('deal_stage') or {}).get('name') for x in deals}

        def reached(d):
            mx = -1
            for e in hists.get(d['id'], []):
                n = smap.get(e.get('deal_stage_id'))
                if n in idx:
                    mx = max(mx, idx[n])
            if cur.get(d['id']) in idx:
                mx = max(mx, idx[cur[d['id']]])
            return mx

        bymes = defaultdict(list)
        for d in deals:
            bymes[(d.get('created_at') or '')[:7]].append(d)

        out = {}
        alvo = idx.get('1ª Reunião Agendada', 4)
        for sigla, ym in (('Mai', '2026-05'), ('Jun', '2026-06')):
            ds = bymes.get(ym, [])
            sec = Counter((d.get('created_at') or '')[:19] for d in ds)
            impsec = {k for k, v in sec.items() if v >= 3}
            reais = [d for d in ds if (d.get('created_at') or '')[:19] not in impsec]
            ent = len(reais)
            ra = sum(1 for d in reais if reached(d) >= alvo)
            out[sigla] = {'entrada': ent, 'reuniao_agendada': ra,
                          'aproveitamento': (ra / ent) if ent else 0.0,
                          'parcial': sigla == 'Jun'}
        return out
    except Exception as e:
        return {'erro': str(e)}


# ─────────── builder principal ───────────
def get_previsibilidade_data(meta_monthly=None, google_monthly=None):
    """Monta o bloco nativo v2. (meta/google_monthly mantidos por compatibilidade do ETL,
    mas o investimento real Jan–Jun usa os valores oficiais fixos — meses fechados.)"""
    etapas, acum, resumo = _funil_modelo()
    acum_nf = acum[-1]
    acum_ra = acum[IDX_1A_REUNIAO]

    # Investimento REAL Jan–Jun: deriva do summary (meta+google monthly) quando disponível,
    # em vez do valor hardcoded. Junho ficava congelado num snapshot PARCIAL de meio de mês
    # (R$ 20.954 vs R$ 26.172 real). Jan–Mai já batiam ao centavo; isso conserta junho e
    # blinda meses futuros conforme fecham. Fallback p/ o hardcode se o monthly faltar.
    invest_real = dict(INVEST_REAL)
    _by_key = defaultdict(float)
    for _row in (meta_monthly or []):
        if _row.get('mes'):
            _by_key[_row['mes']] += float(_row.get('gasto') or 0)
    for _row in (google_monthly or []):
        if _row.get('mes'):
            _by_key[_row['mes']] += float(_row.get('gasto') or 0)
    _MES2KEY = {'Jan': '2026-01', 'Fev': '2026-02', 'Mar': '2026-03',
                'Abr': '2026-04', 'Mai': '2026-05', 'Jun': '2026-06'}
    for _m, _k in _MES2KEY.items():
        if _by_key.get(_k, 0) > 0:
            invest_real[_m] = round(_by_key[_k], 2)

    # --- realizado Jan–Jun (com fórmulas) ---
    cpl_real, cps_real, conv_lp = {}, {}, {}
    for m in REAL:
        cpl_real[m] = invest_real[m] / LEADS_REAL[m]
        cps_real[m] = invest_real[m] / SESSOES[m]
        conv_lp[m] = LEADS_REAL[m] / SESSOES[m]
    tot_inv = sum(invest_real[m] for m in REAL)
    tot_leads = sum(LEADS_REAL[m] for m in REAL)
    tot_sess = sum(SESSOES[m] for m in REAL)
    conv_lp_ponderada = tot_leads / tot_sess

    # --- cenários de CPL ---
    cpl_conserv = invest_real['Jun'] / LEADS_REAL['Jun']
    cpl_base = tot_inv / tot_leads
    melhores = sorted(REAL, key=lambda m: cpl_real[m])[:3]
    cpl_otim = sum(invest_real[m] for m in melhores) / sum(LEADS_REAL[m] for m in melhores)
    CEN = {'conservador': (cpl_conserv, 'CPL de Junho (mais recente/alto)'),
           'base':        (cpl_base, 'CPL ponderado Jan–Jun'),
           'otimista':    (cpl_otim, f'CPL ponderado dos 3 melhores meses ({", ".join(melhores)})')}

    cenarios = {}
    for c, (cplv, premissa) in CEN.items():
        leads_mes = {m: INVEST_PROJ[m] / cplv for m in PROJ}
        total_leads = sum(leads_mes.values())
        nf = total_leads * acum_nf
        cenarios[c] = {
            'cpl': round(cplv, 2),
            'premissa': premissa,
            'leads_mes': {m: round(leads_mes[m], 1) for m in PROJ},
            'total_leads': round(total_leads, 1),
            'reunioes_agendadas': round(total_leads * acum_ra, 1),
            'negocios_fechados': round(nf, 4),
            'receita': round(nf * TICKET, 2),
        }

    # --- tabela mensal consolidada ---
    mensal = []
    for m in MESES:
        if m in REAL:
            mensal.append({
                'mes': m, 'nome': MES_NOME[m], 'status': 'real',
                'investimento': round(invest_real[m], 2), 'leads': LEADS_REAL[m],
                'cpl': round(cpl_real[m], 2), 'sessoes': SESSOES[m],
                'cps': round(cps_real[m], 2), 'conv_lp': round(conv_lp[m], 4),
            })
        else:
            mensal.append({
                'mes': m, 'nome': MES_NOME[m], 'status': 'proj',
                'investimento': round(INVEST_PROJ[m], 2),
                'leads': None, 'cpl': None,         # dependem do cenário (ver bloco cenarios)
                'sessoes': None, 'cps': None, 'conv_lp': None,  # n/d (não projetados)
            })

    return {
        'modelo': 'nativo-v2',
        'ticket': TICKET,
        'ultima_atualizacao': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'meses': MESES,
        'mensal': mensal,
        'realizado_totais': {
            'investimento': round(tot_inv, 2), 'leads': tot_leads, 'sessoes': tot_sess,
            'conv_lp_ponderada': round(conv_lp_ponderada, 4),
            'negocios_fechados_reais': 0, 'receita_real': 0,
            'cpl_ponderado': round(cpl_base, 2),
        },
        'cenarios': cenarios,
        'funil': etapas,
        'funil_resumo': {
            'aprov_ate_1a_reuniao': round(resumo['aprov_ate_1a_reuniao'], 4),
            'entrada_ate_negocio_fechado': round(resumo['entrada_ate_negocio_fechado'], 6),
            'leads_por_venda': round(resumo['leads_por_venda'], 1),
            'gargalo_menor_taxa': resumo['gargalo_menor_taxa'],
            'gargalo_menor_taxa_valor': round(resumo['gargalo_menor_taxa_valor'], 4),
            'maior_perda_absoluta': resumo['maior_perda_absoluta'],
        },
        'funil_real_crm': _funil_real_crm(),
        'alertas': [
            'Projeção de receita é TEÓRICA: 0 negócios fechados reais Jan–Jun (ninguém passou de Visita/Jamil no CRM).',
            'Taxas das etapas finais (pós-Visita/Jamil) são premissas-meta, sem fechamento real validando.',
            'Funil real por etapa só existe de Maio/2026 (CRM); Jan–Abr sem volumes por etapa.',
            'Conversão por LP individual não localizada (só sessões gerais); sem split por URL.',
            'Sessões Jul–Dez não projetadas (sem premissa de CPS futuro).',
            'Recomendação dos auditores: planejar pelo Base, orçar pelo Conservador.',
        ],
    }

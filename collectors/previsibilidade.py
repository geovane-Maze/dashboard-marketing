"""
Coletor da planilha de Previsibilidade 2026.

Lê a aba "PREVISIBILIDADE IA" da planilha do cliente, parseia os 2 blocos
(PREVISIBILIDADE = projeção/meta, ATINGIMENTO = real) e retorna estruturado
para o dashboard renderizar como tabela espelhando o estilo da planilha.

Estrutura esperada da aba:
  Linha 6: "2026 - PREVISIBILIDADE"
  Linha 9: header com Mês + 7 meses (cada mês ocupa 3 cols: valor | % CRM | Custo/Leads)
  Linhas 10-32: métricas (CRESCIMENTO, Investimento, Vendas, Receita, Funil, etc.)
  Linha ~35: "AÇÕES REALIZADAS" (separador)
  Linha ~38: "2026 - ATINGIMENTO"
  Linhas seguintes: mesma estrutura
"""
import gspread
from google.oauth2.service_account import Credentials
import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PREVISIBILIDADE_SHEET_ID = "1f_G15gb637rTU7JfO1lWt7lYuYJBmrM3lvMezNuj0-U"
PREVISIBILIDADE_TAB_NAME = "PREVISIBILIDADE IA"


def _get_client():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def _classify_row(label):
    """Classifica a linha em uma categoria pra colorir no front."""
    if not label:
        return "blank"
    l = label.strip().lower()

    if "crescimento" in l:
        return "kpi_crescimento"
    if "investimento" in l:
        return "kpi_topo"
    if "vendas" in l and "lead" not in l:
        return "kpi_topo"
    if "receita" in l:
        return "kpi_topo"
    if "ticket" in l:
        return "kpi_topo"
    if "taxa de aproveitamento" in l:
        return "header_secao"
    if l.startswith(("1º", "2º", "3º", "4º", "5º", "6º", "7º", "8º")):
        if l.startswith("1º"):
            return "etapa_funil_top"
        return "etapa_funil"
    if "leads" in l and "venda" not in l:
        return "metric_lead"
    if "cpl" == l:
        return "metric_lead"
    if "sess" in l:
        return "metric_lead"
    if "taxa de conversão lp" in l:
        return "metric_destaque"
    if "cps" in l or "roas" in l or "cac" in l or "lucro" in l:
        return "kpi_topo"
    if "taxa de conversão lead" in l:
        return "kpi_topo"
    return "default"


def _parse_block(rows, start_row, end_row):
    """
    Parseia um bloco (PREVISIBILIDADE ou ATINGIMENTO).

    Procura o header de meses (linha que começa com 'Mês') e lê as métricas
    até encontrar linha vazia ou final do bloco.
    """
    # Procura header dos meses dentro do range
    header_row_idx = None
    for i in range(start_row, min(end_row, len(rows))):
        row = rows[i] if i < len(rows) else []
        if row and row[0] and row[0].strip().lower() == "mês":
            header_row_idx = i
            break

    if header_row_idx is None:
        return None

    header = rows[header_row_idx]
    # Detecta os meses (a cada 3 colunas: valor | % CRM | Custo/Leads)
    meses = []
    col_indices = []  # índice da coluna de VALOR de cada mês
    i = 1
    while i < len(header):
        cell = (header[i] or "").strip()
        if cell and cell.lower() != "% crm" and "custo" not in cell.lower():
            meses.append(cell)
            col_indices.append(i)
            i += 3  # pula % CRM e Custo/Leads
        else:
            i += 1

    # Lê as linhas de métricas
    data_rows = []
    for i in range(header_row_idx + 1, min(end_row, len(rows))):
        row = rows[i] if i < len(rows) else []
        if not row:
            continue
        label = (row[0] or "").strip() if row else ""
        if not label:
            continue
        # Para se encontrar próximo bloco
        if "2026 -" in label or "AÇÕES REALIZADAS" in label.upper():
            break

        valores = []
        for col_idx in col_indices:
            valor = row[col_idx] if col_idx < len(row) else ""
            pct = row[col_idx + 1] if col_idx + 1 < len(row) else ""
            custo = row[col_idx + 2] if col_idx + 2 < len(row) else ""
            valores.append({
                "v": (valor or "").strip(),
                "pct": (pct or "").strip(),
                "custo": (custo or "").strip(),
            })

        data_rows.append({
            "label": label,
            "categoria": _classify_row(label),
            "valores": valores,
        })

    return {
        "meses": meses,
        "rows": data_rows,
    }


def get_previsibilidade_data():
    """
    Lê a aba PREVISIBILIDADE IA e retorna estruturado:
      {
        "ultima_atualizacao": "26/05/2026 09:54",
        "previsibilidade": { meses: [...], rows: [...] },
        "atingimento": { meses: [...], rows: [...] },
      }
    """
    print("Coletando Previsibilidade 2026...")
    gc = _get_client()
    sp = gc.open_by_key(PREVISIBILIDADE_SHEET_ID)
    ws = sp.worksheet(PREVISIBILIDADE_TAB_NAME)
    rows = ws.get_all_values()

    # Encontra os índices dos 2 blocos
    prev_start = None
    ating_start = None
    for i, row in enumerate(rows):
        if not row or not row[0]:
            continue
        l = row[0].strip()
        if "PREVISIBILIDADE" in l.upper() and "2026" in l:
            prev_start = i
        elif "ATINGIMENTO" in l.upper() and "2026" in l:
            ating_start = i

    if prev_start is None:
        print("  Bloco PREVISIBILIDADE não encontrado.")
        return None

    prev_block = _parse_block(rows, prev_start, ating_start or len(rows))
    ating_block = None
    if ating_start is not None:
        ating_block = _parse_block(rows, ating_start, len(rows))

    from datetime import datetime
    return {
        "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "previsibilidade": prev_block,
        "atingimento": ating_block,
    }

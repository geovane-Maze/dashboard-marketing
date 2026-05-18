# -*- coding: utf-8 -*-
"""Gera documentação técnica completa do projeto em PDF."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, ListFlowable, ListItem
)
from datetime import datetime

OUT = "Documentacao_Dashboard_Marketing.pdf"

# ============ COLORS ============
PRIMARY = HexColor("#0D3B66")
SECONDARY = HexColor("#3A86FF")
ACCENT = HexColor("#E67E22")
LIGHT_BG = HexColor("#F5F7FA")
GRAY = HexColor("#6B7280")
GREEN = HexColor("#15803D")

# ============ STYLES ============
styles = getSampleStyleSheet()

H1 = ParagraphStyle('H1', parent=styles['Heading1'],
    fontSize=22, textColor=PRIMARY, spaceAfter=14, spaceBefore=6,
    fontName='Helvetica-Bold', alignment=TA_LEFT)
H2 = ParagraphStyle('H2', parent=styles['Heading2'],
    fontSize=16, textColor=PRIMARY, spaceAfter=10, spaceBefore=18,
    fontName='Helvetica-Bold')
H3 = ParagraphStyle('H3', parent=styles['Heading3'],
    fontSize=13, textColor=SECONDARY, spaceAfter=6, spaceBefore=12,
    fontName='Helvetica-Bold')
BODY = ParagraphStyle('Body', parent=styles['Normal'],
    fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=8,
    fontName='Helvetica')
BODY_TIGHT = ParagraphStyle('BodyT', parent=BODY, spaceAfter=4)
CODE = ParagraphStyle('Code', parent=styles['Code'],
    fontSize=9, leading=12, fontName='Courier',
    backColor=LIGHT_BG, borderColor=GRAY, borderWidth=0.5,
    borderPadding=8, spaceAfter=10, leftIndent=10, rightIndent=10)
BULLET = ParagraphStyle('Bullet', parent=BODY, leftIndent=18, bulletIndent=6, spaceAfter=4)
CAPTION = ParagraphStyle('Caption', parent=BODY, fontSize=9, textColor=GRAY,
    alignment=TA_CENTER, spaceAfter=14)
COVER_TITLE = ParagraphStyle('CoverTitle', parent=styles['Title'],
    fontSize=32, textColor=PRIMARY, alignment=TA_CENTER, fontName='Helvetica-Bold',
    spaceAfter=8, leading=38)
COVER_SUB = ParagraphStyle('CoverSub', parent=styles['Normal'],
    fontSize=14, textColor=GRAY, alignment=TA_CENTER, spaceAfter=30)

# ============ HELPERS ============
def H(text, style=H2): return Paragraph(text, style)
def P(text): return Paragraph(text, BODY)
def Pt(text): return Paragraph(text, BODY_TIGHT)
def C(text): return Paragraph(text.replace("<", "&lt;").replace(">", "&gt;"), CODE)
def bullet_list(items):
    return ListFlowable(
        [ListItem(Paragraph(i, BODY_TIGHT), leftIndent=10) for i in items],
        bulletType='bullet', start='circle', leftIndent=14, bulletFontSize=8
    )
def section_table(rows, col_widths=None):
    t = Table(rows, colWidths=col_widths, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9.5),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 7),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, LIGHT_BG]),
        ('GRID', (0,0), (-1,-1), 0.4, GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), black),
    ]))
    return t

story = []

# ===================== CAPA =====================
story.append(Spacer(1, 5*cm))
story.append(Paragraph("Dashboard Marketing", COVER_TITLE))
story.append(Paragraph("Expansão CDC — Clínica da Cidade", COVER_SUB))
story.append(Spacer(1, 2*cm))

# Card de info da capa
info_data = [
    ["Projeto", "Dashboard Marketing — Expansão CDC"],
    ["Tipo", "Aplicação Web + Pipeline de Dados"],
    ["Linguagens", "Python 3 + HTML5 + CSS3 + JavaScript (ES6)"],
    ["Frontend", "HTML / CSS / JavaScript puro + Chart.js"],
    ["Backend", "Python 3 (scripts de coleta e agregação)"],
    ["Hospedagem", "GitHub Pages (estático)"],
    ["Repositório", "github.com/geovane-Maze/dashboard-marketing"],
    ["URL", "geovane-maze.github.io/dashboard-marketing/"],
    ["Data documento", datetime.now().strftime("%d/%m/%Y")],
]
t = Table(info_data, colWidths=[5*cm, 11*cm], hAlign='CENTER')
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (0,-1), PRIMARY),
    ('TEXTCOLOR', (0,0), (0,-1), white),
    ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
    ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
    ('FONTSIZE', (0,0), (-1,-1), 10),
    ('PADDING', (0,0), (-1,-1), 8),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('GRID', (0,0), (-1,-1), 0.3, GRAY),
    ('BACKGROUND', (1,0), (1,-1), LIGHT_BG),
]))
story.append(t)
story.append(PageBreak())

# ===================== 1. VISÃO GERAL =====================
story.append(H("1. Visão Geral do Projeto", H1))
story.append(P(
    "O <b>Dashboard Marketing</b> é uma aplicação web responsiva desenvolvida para "
    "consolidar e visualizar, em um único painel, todos os indicadores de marketing "
    "e vendas da expansão da rede <b>Clínica da Cidade (CDC)</b>. O sistema integra "
    "automaticamente dados de cinco fontes distintas — RD Station Marketing, RD "
    "Station CRM, Google Ads, Meta Ads e Google Analytics 4 — e os apresenta em "
    "9 páginas distintas com KPIs, gráficos interativos, filtros por período e "
    "campanha, e detalhamento por criativo."
))
story.append(P(
    "O objetivo principal é fornecer ao time de marketing visibilidade em tempo "
    "quase real sobre captação de leads (orgânicos e pagos), performance de "
    "campanhas, custo por lead (CPL), funil de vendas no CRM, e atribuição "
    "por canal — sem depender de ferramentas pagas de BI."
))

story.append(H("Páginas do Dashboard", H3))
story.append(bullet_list([
    "<b>Visão Executiva</b> — KPIs principais, alertas e resumo consolidado",
    "<b>Evolução Mensal</b> — gráficos com últimos 4 meses (com filtro local)",
    "<b>Funil CRM</b> — pipeline de vendas com etapas ativas e taxas de conversão",
    "<b>Gargalos &amp; Perdas</b> — análise de motivos de perda de negócios",
    "<b>Meta Ads</b> — performance de campanhas Facebook/Instagram",
    "<b>Google Ads</b> — performance de campanhas Google (incluindo Performance Max)",
    "<b>Criativos</b> — top criativos Meta Ads com filtros de período, campanha e status",
    "<b>UTM / Atribuição</b> — leads por source, medium, campaign e canal",
    "<b>Google Analytics 4</b> — métricas de tráfego do site",
]))

# ===================== 2. LINGUAGENS =====================
story.append(H("2. Linguagens e Tecnologias", H1))

story.append(H("2.1 Stack Tecnológico", H2))
story.append(P(
    "O projeto foi construído com tecnologias <b>nativas e gratuitas</b>, sem "
    "depender de frameworks pesados, o que torna a manutenção simples e o deploy "
    "extremamente leve."
))

stack_data = [
    ["Camada", "Linguagem", "Tecnologia / Biblioteca"],
    ["Coleta de Dados", "Python 3", "requests, gspread, google-auth, facebook-business"],
    ["Pipeline / Agregação", "Python 3", "gspread, pandas, json (stdlib)"],
    ["Frontend", "JavaScript (ES6)", "JavaScript puro (vanilla), sem frameworks"],
    ["Visualização", "JavaScript", "Chart.js 4.4 (gráficos)"],
    ["Estilização", "CSS3", "CSS Grid + Flexbox + variáveis CSS"],
    ["Estrutura", "HTML5", "HTML5 semântico"],
    ["Armazenamento", "JSON", "Arquivo summary.json (gerado pelo Python)"],
    ["Hospedagem", "GitHub Pages", "Servidor estático gratuito"],
    ["Versionamento", "Git / GitHub", "Controle de versão completo"],
]
story.append(section_table(stack_data, [3.5*cm, 3.5*cm, 9*cm]))

story.append(H("2.2 Por que essas escolhas?", H3))
story.append(P(
    "<b>Python para o backend</b> — Linguagem ideal para integrações com APIs, "
    "manipulação de dados e automação. Possui SDKs oficiais para Google (gspread, "
    "google-ads, google-analytics-data) e Meta (facebook-business)."
))
story.append(P(
    "<b>JavaScript vanilla no frontend</b> — Decisão consciente para evitar "
    "complexidade de build (sem Webpack, sem React, sem Node.js). O dashboard "
    "carrega instantaneamente, é fácil de manter e roda em qualquer navegador "
    "moderno sem etapa de compilação."
))
story.append(P(
    "<b>Chart.js</b> — Biblioteca de gráficos leve (~80KB), com excelente "
    "qualidade visual, suporte a responsividade e API simples. Roda direto do CDN."
))
story.append(P(
    "<b>JSON como camada de dados</b> — O Python gera um único arquivo <i>summary.json</i> "
    "consolidado, que o frontend lê em uma única requisição. Isso elimina a necessidade "
    "de um banco de dados ou API server-side."
))

story.append(H("2.3 Bibliotecas Python (requirements.txt)", H3))
story.append(C(
    "requests              # chamadas HTTP às APIs\n"
    "gspread               # leitura/escrita no Google Sheets\n"
    "google-auth           # autenticação Google (Service Account)\n"
    "google-auth-oauthlib  # OAuth para tokens GA4 / Google Ads\n"
    "google-analytics-data # SDK GA4\n"
    "google-ads            # SDK Google Ads\n"
    "facebook-business     # SDK Meta Ads\n"
    "python-dotenv         # carregar variáveis do .env\n"
    "pandas                # manipulação tabular (writer de planilhas)\n"
))

story.append(PageBreak())

# ===================== 3. ARQUITETURA =====================
story.append(H("3. Arquitetura do Projeto", H1))

story.append(P(
    "O sistema funciona em três camadas independentes que se comunicam por meio "
    "de uma planilha Google Sheets central (camada de persistência) e um arquivo "
    "JSON (camada de leitura pelo frontend):"
))

arq_data = [
    ["#", "Camada", "Função"],
    ["1", "Coletores (Python)", "Buscam dados das APIs externas e gravam na planilha"],
    ["2", "Pipeline (Python)", "Lê planilha, agrega e gera o summary.json"],
    ["3", "Dashboard (Frontend)", "Lê o summary.json e renderiza gráficos/KPIs"],
]
story.append(section_table(arq_data, [1*cm, 4.5*cm, 10.5*cm]))

story.append(Spacer(1, 0.5*cm))
story.append(H("3.1 Fluxo de Dados", H3))
story.append(C(
    "  [APIs Externas]\n"
    "   |  RD Station Marketing   (api.rd.services)\n"
    "   |  RD Station CRM         (crm.rdstation.com)\n"
    "   |  Google Ads             (planilha de export)\n"
    "   |  Meta Ads               (planilha de export)\n"
    "   |  Google Analytics 4     (analyticsdata.googleapis.com)\n"
    "   v\n"
    "  [main.py]  --grava--> [Google Sheets (planilha central)]\n"
    "                                  |\n"
    "                                  v\n"
    "  [generate_dashboard_data.py]  --le e agrega--> [summary.json]\n"
    "                                                          |\n"
    "                                                          v\n"
    "  [git push origin main]  --deploy--> [GitHub Pages]\n"
    "                                            |\n"
    "                                            v\n"
    "                                  [index.html + Chart.js]\n"
    "                                  Renderiza dashboard\n"
))

# ===================== 4. ESTRUTURA DE ARQUIVOS =====================
story.append(H("4. Estrutura de Arquivos", H1))

story.append(C(
    "dashboard-marketing/\n"
    "|\n"
    "|-- main.py                         # Orquestrador principal da coleta\n"
    "|-- config.py                       # Carrega variáveis do .env\n"
    "|-- requirements.txt                # Dependências Python\n"
    "|-- .env                            # Tokens e credenciais (NUNCA versionado)\n"
    "|-- .env.example                    # Modelo de .env\n"
    "|-- index.html                      # Redireciona para /dashboard\n"
    "|\n"
    "|-- collectors/                     # Módulos de coleta (1 por fonte)\n"
    "|   |-- rdstation.py                # RD Station Marketing (leads)\n"
    "|   |-- rdcrm.py                    # RD Station CRM (deals/atividades)\n"
    "|   |-- google_ads.py               # Google Ads via API oficial\n"
    "|   |-- meta_ads.py                 # Meta Ads via API oficial\n"
    "|   |-- ga4.py                      # Google Analytics 4\n"
    "|   |-- ads_sheets.py               # Fallback: lê planilhas exportadas\n"
    "|\n"
    "|-- sheets/\n"
    "|   |-- writer.py                   # Grava nas abas da planilha central\n"
    "|\n"
    "|-- scripts/\n"
    "|   |-- generate_dashboard_data.py  # Pipeline de agregação\n"
    "|\n"
    "|-- dashboard/                      # FRONTEND (publicado no GitHub Pages)\n"
    "|   |-- index.html                  # Dashboard (HTML + CSS + JS inline)\n"
    "|   |-- data/\n"
    "|       |-- summary.json            # Dados consolidados (gerado pelo pipeline)\n"
    "|\n"
    "|-- credentials/                    # Service Account JSON (NUNCA versionado)\n"
    "|\n"
    "|-- gerar_token_rd.py               # Gera refresh_token RD Station\n"
    "|-- gerar_token_ga4.py              # Gera token OAuth do GA4\n"
    "|-- gerar_token_google_ads.py       # Gera refresh_token Google Ads\n"
))

story.append(PageBreak())

# ===================== 5. COLETORES =====================
story.append(H("5. Coletores de Dados", H1))
story.append(P(
    "Cada coletor é um módulo Python independente, responsável por uma fonte de "
    "dados. Todos seguem o mesmo padrão: autenticam, paginam (se aplicável), "
    "normalizam os dados e retornam uma lista de dicionários."
))

story.append(H("5.1 rdstation.py — RD Station Marketing", H2))
story.append(P(
    "Coleta todos os contatos (leads) da plataforma RD Station Marketing. "
    "Endpoint base: <font name='Courier'>https://api.rd.services</font>"
))
story.append(P("<b>Etapas:</b>"))
story.append(bullet_list([
    "Autentica via OAuth 2.0 com refresh_token, gerando access_token",
    "Lista segmentações (<font name='Courier'>/platform/segmentations</font>) e usa &quot;Todos os contatos da base de Leads&quot;",
    "Pagina contatos da segmentação (20 por página)",
    "Para cada contato: busca detalhes (<font name='Courier'>/platform/contacts/{uuid}</font>) e eventos de conversão",
    "Decodifica o campo <i>traffic_source</i> (Base64) para extrair UTMs",
    "Aplica dedup por UUID (RD pode repetir contatos entre páginas)",
    "Retorna lista com nome, email, telefone, cidade, estado, lifecycle, UTMs, canal/fonte (cf_plug_opportunity_origin), capital disponível, prazo de abertura, etc.",
]))
story.append(P("<b>Robustez (fix aplicado em 14/05):</b>"))
story.append(bullet_list([
    "<b>Retry exponencial</b> em 429/5xx (backoff 1s → 2s → 4s → 8s)",
    "<b>Refresh automático</b> de token em 401",
    "<b>Refresh proativo</b> a cada 100 contatos (evita expiração mid-run)",
    "<b>Sleep de 0,25s</b> entre chamadas (margem de rate limit)",
    "<b>Logging explícito</b> de falhas no fim do run",
]))

story.append(H("5.2 rdcrm.py — RD Station CRM", H2))
story.append(P(
    "Coleta negócios (deals), atividades e tarefas da plataforma RD Station CRM. "
    "Endpoint base: <font name='Courier'>https://crm.rdstation.com/api/v1</font>"
))
story.append(P("<b>Coleta três tipos de entidades:</b>"))
story.append(bullet_list([
    "<b>Deals</b> — oportunidades de venda com valor, estágio, responsável, motivo de perda",
    "<b>Atividades</b> — registros de interação (calls, e-mails, reuniões)",
    "<b>Tarefas</b> — to-dos e follow-ups",
]))
story.append(P(
    "Autentica via API Key. Os deals alimentam o Funil CRM, a Visão Executiva "
    "(leads abertos/perdidos) e os gráficos de motivos de perda."
))

story.append(H("5.3 google_ads.py — Google Ads API", H2))
story.append(P(
    "Coleta dados de campanhas Google Ads via API oficial. Atualmente em status "
    "de fallback (a API requer aprovação manual do customer_id pela conta). "
    "Quando indisponível, o sistema usa o coletor <i>ads_sheets.py</i> como fallback."
))

story.append(H("5.4 meta_ads.py — Meta Ads API", H2))
story.append(P(
    "Coleta dados de campanhas Meta (Facebook + Instagram) via Facebook Business "
    "SDK. Também opera com fallback para a planilha quando há erro de autenticação."
))

story.append(H("5.5 ga4.py — Google Analytics 4", H2))
story.append(P(
    "Coleta métricas do GA4 (sessions, users, conversions, bounceRate, channels, "
    "devices, pages, sources) via google-analytics-data SDK. Autentica via OAuth 2.0."
))

story.append(H("5.6 ads_sheets.py — Fallback de Planilhas", H2))
story.append(P(
    "Coletor de fallback que lê <b>planilhas exportadas manualmente</b> do Google Ads "
    "e Meta Ads (caso as APIs estejam indisponíveis). Detecta automaticamente dois "
    "formatos:"
))
story.append(bullet_list([
    "<b>Formato DIÁRIO</b> — com coluna &quot;Dia&quot;, gera dados granulares por data",
    "<b>Formato AGREGADO</b> — totais por campanha sem breakdown diário (preserva histórico)",
]))

story.append(PageBreak())

# ===================== 6. PIPELINE =====================
story.append(H("6. Pipeline de Agregação", H1))
story.append(P(
    "O arquivo <font name='Courier'>scripts/generate_dashboard_data.py</font> é o coração "
    "do sistema. Ele lê as abas brutas da planilha Google Sheets, aplica regras "
    "de negócio (qualificação, atribuição, normalização de etapas) e gera o "
    "<b>summary.json</b> que o dashboard consome."
))

story.append(H("Principais Funções", H3))
agg_data = [
    ["Função", "O que produz"],
    ["aggregate_leads()", "monthly, daily, by_source, by_canal, by_lifecycle, by_capital, by_prazo"],
    ["aggregate_crm()", "active_funnel, total_active, total_won, total_lost, monthly_stages, monthly_won"],
    ["aggregate_meta_ads()", "monthly, daily, campaigns, campaign_monthly, creatives, total_gasto"],
    ["aggregate_google_ads()", "monthly, daily, campaigns, campaign_monthly, total_gasto"],
    ["aggregate_ga4()", "monthly, channels, devices, pages, sources"],
    ["aggregate_utm()", "sources, mediums, campaigns, *_monthly, *_daily"],
]
story.append(section_table(agg_data, [4.5*cm, 11.5*cm]))

story.append(Spacer(1, 0.5*cm))
story.append(H("Regras de Negócio Importantes", H3))
story.append(bullet_list([
    "<b>Dedup defensivo</b> por id em leads e crm_deals (mesmo que a coleta já dedupe)",
    "<b>Normalização de etapas</b> CRM (Reunião PDF, Apresentação BP, Workshop, etc.)",
    "<b>Exclusão de etapas mortas</b> do funil ativo (Etapa Descarte, Sem etapa, ganhos/perdidos)",
    "<b>Classificação Repasse vs Expansão</b> de campanhas (keywords: taguatinga, maringá, praia grande)",
    "<b>Qualificação</b> de leads pelo lifecycle_stage (qualif ou mql)",
    "<b>Conversão de datas</b> para formato YYYY-MM (mês) e YYYY-MM-DD (dia)",
]))

# ===================== 7. DASHBOARD FRONTEND =====================
story.append(H("7. Dashboard Frontend", H1))
story.append(P(
    "Todo o dashboard está em um <b>único arquivo HTML</b> (~2.300 linhas), com "
    "CSS e JavaScript inline. Isso simplifica o deploy (nada para compilar) e "
    "garante carregamento rápido em qualquer dispositivo."
))

story.append(H("7.1 Tecnologias do Frontend", H3))
front_data = [
    ["Tecnologia", "Uso"],
    ["HTML5", "Estrutura semântica de 9 seções (uma por página)"],
    ["CSS3", "Layout responsivo (Grid + Flexbox), variáveis CSS para tema"],
    ["JavaScript ES6+", "Lógica de filtros, renderização e interatividade"],
    ["Chart.js 4.4", "Gráficos de barra, linha, pizza, donut e mistos"],
    ["Fetch API", "Carrega o summary.json no boot"],
    ["LocalStorage", "(não usado) — toda a sessão é stateless"],
]
story.append(section_table(front_data, [4*cm, 12*cm]))

story.append(H("7.2 Padrão de Renderização", H3))
story.append(P(
    "O dashboard usa um padrão simples de <b>render por seção</b>. Quando o usuário "
    "navega para uma página, a função <font name='Courier'>render&lt;NomeDaSecao&gt;()</font> é chamada "
    "com base no filtro global. Funções principais:"
))
story.append(bullet_list([
    "<font name='Courier'>renderExec()</font> — Visão Executiva",
    "<font name='Courier'>renderEvolucao()</font> — Evolução Mensal (filtro local)",
    "<font name='Courier'>renderCRM()</font> — Funil CRM",
    "<font name='Courier'>renderPerdas()</font> — Gargalos &amp; Perdas",
    "<font name='Courier'>renderMeta()</font> — Meta Ads",
    "<font name='Courier'>renderGoogle()</font> — Google Ads",
    "<font name='Courier'>renderCreatives()</font> — Criativos",
    "<font name='Courier'>renderUTM()</font> — UTM / Atribuição",
    "<font name='Courier'>renderGA4()</font> — Google Analytics 4",
]))

story.append(H("7.3 Sistema de Filtros", H3))
story.append(bullet_list([
    "<b>Filtro global</b> (header) — período (De/Até) + campanha. Aplica em todas as páginas.",
    "<b>Filtro local Evolução Mensal</b> — De/Até em meses (independente do global, autoload últimos 4 meses).",
    "<b>Filtro local Criativos</b> — Período + Campanha (com tags Ativo/Pausado) + Status + Ordenação.",
    "<b>Atalhos rápidos</b> — Hoje, Últimos 7 dias, Este mês, Mês passado, Personalizado.",
]))

story.append(H("7.4 Mobile / Responsividade", H3))
story.append(P(
    "Em telas ≤ 600px o dashboard troca a sidebar fixa por um <b>menu hambúrguer "
    "com drawer lateral</b>. KPIs viram cards empilhados, gráficos ocupam 100% da "
    "largura e tabelas têm scroll horizontal."
))

story.append(PageBreak())

# ===================== 8. CONFIGURAÇÃO =====================
story.append(H("8. Configuração e Setup", H1))

story.append(H("8.1 Pré-requisitos", H3))
story.append(bullet_list([
    "Python 3.10+ instalado",
    "Conta Google com acesso à planilha central",
    "Service Account JSON (Google Cloud) com permissão Editor na planilha",
    "Refresh tokens válidos: RD Station Marketing, RD Station CRM, GA4, Google Ads",
    "Token de acesso Meta Business (caso queira usar API)",
]))

story.append(H("8.2 Arquivo .env", H3))
story.append(C(
    "# Google\n"
    "GOOGLE_CREDENTIALS_FILE=credentials/service-account.json\n"
    "GOOGLE_SHEET_ID=<id_da_planilha_central>\n"
    "\n"
    "# RD Station Marketing\n"
    "RD_CLIENT_ID=...\n"
    "RD_CLIENT_SECRET=...\n"
    "RD_REFRESH_TOKEN=...\n"
    "\n"
    "# RD Station CRM\n"
    "RDCRM_TOKEN=...\n"
    "\n"
    "# GA4\n"
    "GA4_PROPERTY_ID=...\n"
    "\n"
    "# Google Ads\n"
    "GOOGLE_ADS_DEVELOPER_TOKEN=...\n"
    "GOOGLE_ADS_CLIENT_ID=...\n"
    "GOOGLE_ADS_CLIENT_SECRET=...\n"
    "GOOGLE_ADS_REFRESH_TOKEN=...\n"
    "GOOGLE_ADS_CUSTOMER_ID=...\n"
    "\n"
    "# Meta Ads\n"
    "META_ACCESS_TOKEN=...\n"
    "META_AD_ACCOUNT_ID=...\n"
))

story.append(H("8.3 Instalação", H3))
story.append(C(
    "# 1. Clone o repositório\n"
    "git clone https://github.com/geovane-Maze/dashboard-marketing.git\n"
    "cd dashboard-marketing\n"
    "\n"
    "# 2. Instale dependências Python\n"
    "pip install -r requirements.txt\n"
    "\n"
    "# 3. Configure o .env (copie do .env.example)\n"
    "cp .env.example .env\n"
    "# Edite o .env com seus tokens\n"
    "\n"
    "# 4. Coloque o service account JSON em credentials/\n"
    "\n"
    "# 5. Rode o pipeline completo\n"
    "python main.py                       # Coleta dados\n"
    "python scripts/generate_dashboard_data.py  # Gera summary.json\n"
    "\n"
    "# 6. Commit e push para deploy\n"
    "git add dashboard/data/summary.json\n"
    "git commit -m 'update data'\n"
    "git push origin main\n"
))

# ===================== 9. DEPLOY =====================
story.append(H("9. Deploy via GitHub Pages", H1))
story.append(P(
    "O dashboard é hospedado gratuitamente no <b>GitHub Pages</b>, servido a "
    "partir da pasta <font name='Courier'>/dashboard</font> do branch <font name='Courier'>main</font>. "
    "Qualquer push para o main que altere arquivos dentro de <font name='Courier'>/dashboard</font> "
    "dispara um deploy automático em aproximadamente 1 minuto."
))

story.append(H("Workflow de Atualização", H3))
story.append(C(
    "Atualizar dados:\n"
    "  python main.py                              (~3 minutos)\n"
    "  python scripts/generate_dashboard_data.py   (~10 segundos)\n"
    "  git add dashboard/data/summary.json\n"
    "  git commit -m 'update <data>'\n"
    "  git push origin main\n"
    "\n"
    "Aguardar ~1 min para o GitHub Pages atualizar.\n"
    "Hard refresh no navegador: Ctrl+Shift+R\n"
))

# ===================== 10. MANUTENÇÃO =====================
story.append(H("10. Manutenção e Operações Comuns", H1))

story.append(H("10.1 Atualizar Planilha do Google Ads", H3))
story.append(P(
    "Quando o Google Ads envia um novo relatório de campanhas, atualiza-se "
    "<font name='Courier'>collectors/ads_sheets.py</font>:"
))
story.append(C(
    "GOOGLE_ADS_SHEET_ID = '<novo_id_da_planilha>'\n"
    "GOOGLE_ADS_TAB_NAME = '<nome_exato_da_aba>'\n"
))
story.append(P(
    "Depois é só rodar o pipeline e fazer push. O sistema detecta automaticamente "
    "se o formato é diário ou agregado."
))

story.append(H("10.2 Tokens Expirados", H3))
story.append(bullet_list([
    "<b>RD Station Marketing</b> — rode <font name='Courier'>python gerar_token_rd.py</font>",
    "<b>GA4</b> — rode <font name='Courier'>python gerar_token_ga4.py</font>",
    "<b>Google Ads</b> — rode <font name='Courier'>python gerar_token_google_ads.py</font>",
]))

story.append(H("10.3 Resolução de Problemas Frequentes", H3))
trouble_data = [
    ["Sintoma", "Causa Provável", "Solução"],
    ["Dashboard não atualiza", "GitHub Pages em cache", "Ctrl+Shift+R no navegador"],
    ["Leads com dados em branco", "Rate limit RD Station", "Já corrigido em 14/05 (retry exponencial)"],
    ["Duplicatas em leads", "API RD repete paginação", "Já corrigido em 14/05 (dedup por UUID)"],
    ["Google Ads desatualizado", "Planilha em formato agregado", "Solicitar export com coluna Dia"],
    ["GA4 retorna 401", "Token expirado", "Rodar gerar_token_ga4.py"],
]
t = Table(trouble_data, colWidths=[4*cm, 5*cm, 7*cm], hAlign='LEFT')
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), PRIMARY),
    ('TEXTCOLOR', (0,0), (-1,0), white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,-1), 9),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('PADDING', (0,0), (-1,-1), 6),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, LIGHT_BG]),
    ('GRID', (0,0), (-1,-1), 0.4, GRAY),
]))
story.append(t)

story.append(PageBreak())

# ===================== 11. HISTÓRICO DE MELHORIAS =====================
story.append(H("11. Histórico de Correções Críticas", H1))
story.append(P(
    "Esta seção documenta correções importantes aplicadas ao longo do desenvolvimento, "
    "que valem ser conhecidas por quem for manter o projeto."
))

fixes_data = [
    ["Data", "Problema", "Correção"],
    ["13/05",
     "Filtro global não funcionava nas páginas Meta/Google/UTM/GA4",
     "Migrou agregações de monthly para daily; usa getDateFilter() em vez de getFilteredMonths()"],
    ["13/05",
     "Meta/Google Ads mostravam contagem errada de leads (vinha da plataforma)",
     "Trocou para utm.sources_daily filtrado por source='metaads' / 'googlecpc' (fonte: RD Station)"],
    ["14/05",
     "Criativos: dropdown listava campanhas que não existiam no período",
     "Adicionou filtro de Período que controla o dropdown + tags Ativo/Pausado por campanha"],
    ["14/05",
     "Lead duplicado (CARLOS DE SOUZA PEREIRA) inflando contagem Google Ads",
     "Dedup tripla: rdstation.py + generate_dashboard_data.py + limpeza imediata da aba"],
    ["14/05",
     "119 de 300 leads (40%) com telefone/cidade/canal/UTM vazios",
     "Reescrita do _get_contact_details com retry exponencial, refresh de token e logging. 119 → 2 leads."],
    ["14/05",
     "Google Ads: nova planilha em formato agregado quebrava o histórico",
     "Detector automático de formato (diário vs agregado) — agregado preserva histórico existente"],
]
t = Table(fixes_data, colWidths=[1.5*cm, 6*cm, 8.5*cm], hAlign='LEFT')
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), PRIMARY),
    ('TEXTCOLOR', (0,0), (-1,0), white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,-1), 8.5),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('PADDING', (0,0), (-1,-1), 6),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, LIGHT_BG]),
    ('GRID', (0,0), (-1,-1), 0.4, GRAY),
]))
story.append(t)

# ===================== 12. MÉTRICAS ATUAIS =====================
story.append(H("12. Snapshot de Métricas Atuais", H1))
story.append(P(
    "Estado do dashboard em <b>15/05/2026</b> (última atualização do pipeline):"
))

metrics_data = [
    ["Fonte", "Volume Coletado"],
    ["Leads (RD Marketing)", "306 contatos únicos"],
    ["Deals (RD CRM)", "679 negócios"],
    ["Atividades CRM", "126 registros"],
    ["Tarefas CRM", "489 registros"],
    ["Meta Ads", "14.865 linhas (dados de criativos por dia)"],
    ["Google Ads", "Histórico diário Jan-Mai 2026 preservado"],
    ["Tamanho do summary.json", "289 KB"],
]
story.append(section_table(metrics_data, [6*cm, 10*cm]))

# ===================== 13. CONTATOS / RESUMO =====================
story.append(Spacer(1, 1*cm))
story.append(H("13. Resumo Final", H1))
story.append(P(
    "O <b>Dashboard Marketing Expansão CDC</b> é um projeto leve, robusto e "
    "totalmente gratuito de hospedar. Construído em <b>Python + JavaScript "
    "vanilla + Chart.js</b>, integra 5 fontes de dados em um único painel "
    "responsivo. Após as correções críticas de maio/2026, o sistema garante:"
))
story.append(bullet_list([
    "<b>Zero duplicatas</b> de leads (dedup em 3 camadas)",
    "<b>Zero perda de dados</b> em coleta longa (retry exponencial + refresh de token)",
    "<b>Detecção automática</b> de formato de planilhas (diário vs agregado)",
    "<b>Filtros precisos</b> por dia exato em todas as páginas relevantes",
    "<b>Interface mobile</b> 100% funcional",
    "<b>Deploy gratuito</b> via GitHub Pages com atualização em ~1 minuto",
]))

story.append(Spacer(1, 0.6*cm))
story.append(Paragraph(
    "<para alignment='center'><i>Documento gerado automaticamente em " +
    datetime.now().strftime("%d/%m/%Y às %H:%M") + ".</i></para>",
    CAPTION
))

# ============ BUILD ============
def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(2*cm, 1*cm, "Dashboard Marketing - Documentação Técnica")
    canvas.drawRightString(A4[0] - 2*cm, 1*cm, f"Página {doc.page}")
    canvas.restoreState()

doc = SimpleDocTemplate(OUT, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=1.8*cm, bottomMargin=1.8*cm,
    title="Documentação Dashboard Marketing", author="Geovane Maze")

doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
print(f"PDF gerado: {OUT}")

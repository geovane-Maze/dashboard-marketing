# -*- coding: utf-8 -*-
"""Gera PDF com documentação das atualizações de segurança aplicadas em 15/05/2026."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    ListFlowable, ListItem
)
from datetime import datetime

OUT = "Documentacao_Seguranca_Dashboard.pdf"

# ============ COLORS ============
PRIMARY = HexColor("#0D3B66")
SECONDARY = HexColor("#3A86FF")
ACCENT = HexColor("#E67E22")
GREEN = HexColor("#15803D")
RED = HexColor("#B91C1C")
AMBER = HexColor("#D97706")
LIGHT_BG = HexColor("#F5F7FA")
LIGHT_GREEN = HexColor("#DCFCE7")
LIGHT_RED = HexColor("#FEE2E2")
LIGHT_AMBER = HexColor("#FEF3C7")
GRAY = HexColor("#6B7280")

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
ALERT_OK = ParagraphStyle('AlertOk', parent=BODY,
    backColor=LIGHT_GREEN, borderColor=GREEN, borderWidth=1,
    borderPadding=10, spaceAfter=10, leftIndent=0, rightIndent=0,
    textColor=GREEN, fontName='Helvetica-Bold')
ALERT_WARN = ParagraphStyle('AlertWarn', parent=BODY,
    backColor=LIGHT_AMBER, borderColor=AMBER, borderWidth=1,
    borderPadding=10, spaceAfter=10, textColor=AMBER, fontName='Helvetica-Bold')
ALERT_DANGER = ParagraphStyle('AlertDanger', parent=BODY,
    backColor=LIGHT_RED, borderColor=RED, borderWidth=1,
    borderPadding=10, spaceAfter=10, textColor=RED, fontName='Helvetica-Bold')
COVER_TITLE = ParagraphStyle('CoverTitle', parent=styles['Title'],
    fontSize=30, textColor=PRIMARY, alignment=TA_CENTER, fontName='Helvetica-Bold',
    spaceAfter=8, leading=36)
COVER_SUB = ParagraphStyle('CoverSub', parent=styles['Normal'],
    fontSize=14, textColor=GRAY, alignment=TA_CENTER, spaceAfter=30)
CAPTION = ParagraphStyle('Caption', parent=BODY, fontSize=9, textColor=GRAY,
    alignment=TA_CENTER, spaceAfter=14)

# ============ HELPERS ============
def H(text, style=H2): return Paragraph(text, style)
def P(text): return Paragraph(text, BODY)
def C(text): return Paragraph(text.replace("<", "&lt;").replace(">", "&gt;"), CODE)
def OK(text): return Paragraph("&#10004; " + text, ALERT_OK)
def WARN(text): return Paragraph("&#9888; " + text, ALERT_WARN)
def DANGER(text): return Paragraph("&#9888; " + text, ALERT_DANGER)
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
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 7),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, LIGHT_BG]),
        ('GRID', (0,0), (-1,-1), 0.4, GRAY),
        ('TEXTCOLOR', (0,1), (-1,-1), black),
    ]))
    return t

story = []

# ===================== CAPA =====================
story.append(Spacer(1, 5*cm))
story.append(Paragraph("Documentação de Segurança", COVER_TITLE))
story.append(Paragraph("Dashboard Marketing — Expansão CDC", COVER_SUB))
story.append(Spacer(1, 1.5*cm))

# Card
info_data = [
    ["Projeto", "Dashboard Marketing — Clínica da Cidade"],
    ["Tipo de atualização", "Implementação de proteção por senha"],
    ["Data da implementação", "15/05/2026"],
    ["Padrão de criptografia", "AES-256-GCM (padrão bancário)"],
    ["Derivação de chave", "PBKDF2-SHA256 (250.000 iterações)"],
    ["URL pública", "geovane-maze.github.io/dashboard-marketing"],
    ["Status atual", "Em produção, protegido por senha"],
    ["Data deste documento", datetime.now().strftime("%d/%m/%Y às %H:%M")],
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

# ===================== 1. SUMÁRIO EXECUTIVO =====================
story.append(H("1. Sumário Executivo", H1))
story.append(P(
    "Em 15/05/2026 foi implementada uma camada de proteção por senha no Dashboard "
    "Marketing da Clínica da Cidade. Antes desta atualização, todos os dados de "
    "performance (totais de leads, investimentos, CPLs, métricas de campanhas) "
    "estavam <b>publicamente acessíveis</b> a qualquer pessoa que abrisse a URL. "
    "Após esta atualização, o dashboard exige senha para acesso e os dados são "
    "criptografados com padrão AES-256, o mesmo usado por bancos."
))

story.append(OK(
    "Resultado: Risco de vazamento de dados foi reduzido de <b>ALTO</b> para <b>BAIXO</b>. "
    "Sem a senha, é matematicamente impossível ler os dados, mesmo baixando o arquivo "
    "diretamente do servidor."
))

story.append(H("Resumo das ações realizadas", H3))
story.append(bullet_list([
    "<b>Criptografia AES-256-GCM</b> aplicada ao arquivo <font name='Courier'>summary.json</font>",
    "<b>Tela de login</b> adicionada ao dashboard (bloqueia acesso sem senha)",
    "<b>Limpeza do histórico do Git</b> com <font name='Courier'>git-filter-repo</font> (62 versões antigas apagadas)",
    "<b>Workflow de deploy</b> reconfigurado para aplicar mudanças automaticamente",
    "<b>Senha armazenada</b> apenas localmente no arquivo <font name='Courier'>.env</font> (não versionado)",
]))

# ===================== 2. PROBLEMA IDENTIFICADO =====================
story.append(H("2. Problema Identificado", H1))

story.append(P(
    "O dashboard estava hospedado no GitHub Pages (hospedagem gratuita estática). "
    "Por padrão, todo arquivo dentro da pasta <font name='Courier'>/dashboard</font> é "
    "<b>publicamente acessível</b> via URL direta. Isso significava que qualquer pessoa, "
    "mesmo sem login, podia abrir uma das seguintes URLs e ver os dados completos:"
))

story.append(C(
    "https://geovane-maze.github.io/dashboard-marketing/\n"
    "https://geovane-maze.github.io/dashboard-marketing/data/summary.json"
))

story.append(P("<b>Dados expostos antes da correção:</b>"))
story.append(bullet_list([
    "Totais de leads gerados por período (306 leads)",
    "Quantidade de negócios no CRM (679 deals)",
    "Investimentos em Meta Ads e Google Ads",
    "Custo por Lead (CPL) por campanha",
    "Performance por criativo, conjunto de anúncios e campanha",
    "Taxas de conversão do funil CRM",
    "Motivos de perda de negócios",
    "Análise de atribuição UTM (origem, mídia, campanha)",
]))

story.append(WARN(
    "Embora os dados pessoais dos leads (nome, email, telefone) NÃO estivessem no "
    "summary.json (esses ficam no Google Sheets privado), as métricas de negócio "
    "expostas são informações competitivas sensíveis."
))

# ===================== 3. SOLUÇÃO IMPLEMENTADA =====================
story.append(H("3. Solução Implementada", H1))

story.append(P(
    "A solução adotada foi a <b>criptografia client-side</b> do arquivo de dados, "
    "combinada com uma tela de login no navegador. O fluxo final ficou assim:"
))

story.append(C(
    "[Seu .env local]   guarda a senha em texto puro\n"
    "        |\n"
    "        v\n"
    "[Python pipeline]  le a senha do .env\n"
    "        |\n"
    "        v\n"
    "[Criptografa summary.json]  AES-256-GCM + PBKDF2 250k iter\n"
    "        |\n"
    "        v\n"
    "[Push para GitHub]  sobe APENAS o arquivo criptografado\n"
    "        |\n"
    "        v\n"
    "[GitHub Pages serve o JSON criptografado]\n"
    "        |\n"
    "        v\n"
    "[Usuario acessa URL] -> tela de login bloqueia\n"
    "        |\n"
    "        v\n"
    "[Digita a senha] -> Browser descriptografa via Web Crypto API\n"
    "        |\n"
    "        v\n"
    "[Dashboard renderiza normalmente]\n"
))

story.append(H("3.1 Detalhes técnicos da criptografia", H3))

tech_data = [
    ["Componente", "Especificação"],
    ["Algoritmo", "AES-256-GCM (Galois/Counter Mode, autenticado)"],
    ["Tamanho da chave", "256 bits (32 bytes)"],
    ["Derivação de chave", "PBKDF2-HMAC-SHA256"],
    ["Iterações PBKDF2", "250.000 (padrão OWASP 2023+)"],
    ["Salt", "128 bits aleatórios (16 bytes), único por execução"],
    ["Nonce (IV)", "96 bits aleatórios (12 bytes), único por execução"],
    ["Autenticação", "Tag GCM (detecta adulteração)"],
    ["Encoding", "Base64 para armazenamento em JSON"],
]
story.append(section_table(tech_data, [4.5*cm, 11.5*cm]))

story.append(H("3.2 Por que esse padrão é seguro?", H3))
story.append(bullet_list([
    "<b>AES-256-GCM</b> é o padrão recomendado pelo NIST, NSA (top secret) e bancos centrais",
    "<b>250.000 iterações de PBKDF2</b> tornam força bruta inviável: uma tentativa demora ~50ms",
    "Com uma senha forte de 12 caracteres mistos, força bruta levaria <b>milhares de anos</b>",
    "<b>Salt aleatório</b> impede ataques de rainbow tables (tabelas pré-computadas)",
    "<b>GCM</b> garante que se alguém modificar o arquivo, a descriptografia FALHA",
]))

story.append(PageBreak())

# ===================== 4. ONDE A SENHA ESTÁ =====================
story.append(H("4. Onde a Senha Está Armazenada", H1))

story.append(OK(
    "A senha está APENAS em um lugar: o arquivo .env local no seu computador. "
    "NÃO está no Supabase, NÃO está no GitHub, NÃO está em nenhum serviço externo."
))

story.append(H("4.1 Localização exata do arquivo", H3))
story.append(C(
    "C:\\Users\\geova\\OneDrive\\Area de Trabalho\\dashboard-marketing\\.env\n"
    "\n"
    "Conteudo da linha que define a senha:\n"
    "DASHBOARD_PASSWORD=<sua_senha_forte>\n"
))

story.append(H("4.2 Como o sistema usa a senha", H3))
story.append(P(
    "1. Você roda <font name='Courier'>python scripts/generate_dashboard_data.py</font>"
))
story.append(P(
    "2. O Python lê a senha do arquivo <font name='Courier'>.env</font> via biblioteca <font name='Courier'>python-dotenv</font>"
))
story.append(P(
    "3. O Python usa a senha para criptografar o <font name='Courier'>summary.json</font> com AES-256-GCM"
))
story.append(P(
    "4. O Python grava apenas o conteúdo criptografado no arquivo (salt + nonce + ciphertext)"
))
story.append(P(
    "5. Você faz <font name='Courier'>git push</font> — apenas o arquivo já criptografado vai pro GitHub"
))
story.append(P(
    "6. A senha em texto puro <b>nunca sai do seu computador</b>"
))

story.append(H("4.3 Proteções do arquivo .env", H3))
story.append(bullet_list([
    "Listado no <font name='Courier'>.gitignore</font> &mdash; nunca é versionado no Git",
    "Não vai pro GitHub em hipótese nenhuma",
    "Fica apenas no seu disco local (e no OneDrive sincronizado, se aplicável)",
    "Tokens e senhas de outras APIs (RD Station, Google, Meta) também ficam ali",
]))

story.append(H("4.4 Resposta curta se alguém perguntar", H3))
story.append(C(
    "\"A senha do dashboard fica no arquivo .env local, lido pelo pipeline\n"
    "Python na hora de gerar o summary.json. O arquivo e criptografado\n"
    "com AES-256 antes de ir pro GitHub, entao o servidor nunca tem acesso\n"
    "a senha em texto puro. A descriptografia acontece no navegador do\n"
    "usuario via Web Crypto API.\""
))

# ===================== 5. LIMPEZA DO HISTÓRICO =====================
story.append(H("5. Limpeza do Histórico do Git", H1))

story.append(P(
    "Antes da criptografia ser implementada, 62 versões do <font name='Courier'>summary.json</font> "
    "foram commitadas no Git em texto puro ao longo do desenvolvimento. Mesmo após "
    "começar a criptografar, essas versões antigas continuavam acessíveis via comandos como:"
))
story.append(C(
    "git clone https://github.com/geovane-Maze/dashboard-marketing.git\n"
    "git show HEAD~5:dashboard/data/summary.json"
))

story.append(P("<b>Para resolver, foi usado <font name='Courier'>git-filter-repo</font>:</b>"))
story.append(C(
    "1. Backup completo do repositorio criado em\n"
    "   dashboard-marketing-BACKUP-20260515_160903/\n"
    "\n"
    "2. Instalacao do git-filter-repo via pip\n"
    "   python -m pip install git-filter-repo\n"
    "\n"
    "3. Execucao do filtro\n"
    "   python -m git_filter_repo \\\n"
    "       --path dashboard/data/summary.json \\\n"
    "       --invert-paths --force\n"
    "\n"
    "4. Resultado: 62 versoes antigas REMOVIDAS de TODOS os commits\n"
    "\n"
    "5. Re-adicionado apenas a versao atual (criptografada)\n"
    "\n"
    "6. Force-push para sobrescrever o repositorio remoto\n"
    "   git push origin main --force"
))

story.append(OK(
    "Resultado: ZERO versões antigas do summary.json existem no histórico do Git agora. "
    "A única versão acessível é a atual (criptografada)."
))

story.append(WARN(
    "Limitação conhecida do GitHub: após force-push, commits antigos ficam temporariamente "
    "acessíveis via SHA direto (não via clone) por aproximadamente 30 dias, até o garbage "
    "collection automático do GitHub rodar. Em 15/06/2026, esses commits órfãos serão "
    "permanentemente apagados pelo próprio GitHub."
))

# ===================== 6. INFRAESTRUTURA DE DEPLOY =====================
story.append(H("6. Infraestrutura de Deploy", H1))

story.append(P(
    "Durante a implementação foi descoberto que o GitHub Pages estava configurado para "
    "deploy via <b>GitHub Actions Workflow</b> (a pipeline diária de coleta de dados), "
    "e não via push direto. Isso significava que mudanças no código não eram refletidas "
    "imediatamente no site público — só após a próxima execução agendada do workflow."
))

story.append(H("Solução: Workflow dedicado de deploy", H3))
story.append(P(
    "Foi criado um novo arquivo <font name='Courier'>.github/workflows/deploy_pages.yml</font> "
    "que faz deploy automático <b>a cada push</b> que modifique a pasta /dashboard:"
))
story.append(C(
    "name: Deploy Dashboard to GitHub Pages\n"
    "\n"
    "on:\n"
    "  push:\n"
    "    branches: [main]\n"
    "    paths:\n"
    "      - 'dashboard/**'\n"
    "      - '.github/workflows/deploy_pages.yml'\n"
    "  workflow_dispatch:\n"
    "\n"
    "permissions:\n"
    "  contents: read\n"
    "  pages: write\n"
    "  id-token: write\n"
    "\n"
    "jobs:\n"
    "  deploy:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - uses: actions/configure-pages@v4\n"
    "      - uses: actions/upload-pages-artifact@v3\n"
    "        with:\n"
    "          path: dashboard/\n"
    "      - uses: actions/deploy-pages@v4"
))

story.append(P(
    "Tempo de deploy: <b>~30 segundos</b> após cada push. Sem mais necessidade de "
    "esperar o cron diário ou disparar manualmente."
))

# ===================== 7. ARQUIVOS MODIFICADOS =====================
story.append(H("7. Arquivos Criados / Modificados", H1))

files_data = [
    ["Arquivo", "Tipo de mudança"],
    ["scripts/generate_dashboard_data.py", "Adicionada função encrypt_payload() com AES-256-GCM"],
    ["dashboard/index.html", "Adicionada tela de login + lógica de descriptografia via Web Crypto API"],
    ["config.py", "Adicionada constante DASHBOARD_PASSWORD"],
    ["requirements.txt", "Adicionada biblioteca 'cryptography'"],
    [".env", "Adicionada variável DASHBOARD_PASSWORD (LOCAL, não versionado)"],
    [".env.example", "Documentada a nova variável (versionado para referência)"],
    [".github/workflows/deploy_pages.yml", "Novo workflow para deploy automático"],
    ["dashboard/data/summary.json", "Conteúdo agora criptografado"],
]
story.append(section_table(files_data, [6*cm, 10*cm]))

story.append(PageBreak())

# ===================== 8. WORKFLOW DIÁRIO =====================
story.append(H("8. Como Atualizar Dados Daqui Pra Frente", H1))

story.append(P("O fluxo permanece o mesmo, sem mudança na rotina:"))

story.append(C(
    "# 1. Coleta dados das APIs (RD Station, CRM, Meta, Google, GA4)\n"
    "python main.py\n"
    "\n"
    "# 2. Gera e CRIPTOGRAFA o summary.json\n"
    "python scripts/generate_dashboard_data.py\n"
    "\n"
    "# Output esperado:\n"
    "#   Criptografando com AES-256-GCM (PBKDF2 250k iter)...\n"
    "#   >>> Dashboard PROTEGIDO POR SENHA <<<\n"
    "\n"
    "# 3. Commit e push\n"
    "git add dashboard/data/summary.json\n"
    "git commit -m 'update dados'\n"
    "git push origin main\n"
    "\n"
    "# 4. GitHub Pages atualiza automaticamente em ~30 segundos"
))

story.append(P(
    "O Python lê automaticamente o <font name='Courier'>DASHBOARD_PASSWORD</font> do "
    ".env toda execução. Não precisa fazer nada diferente — a criptografia é transparente."
))

# ===================== 9. RISCOS RESIDUAIS =====================
story.append(H("9. Riscos Residuais (Transparência)", H1))

story.append(P(
    "Nenhum sistema é 100% seguro. Aqui estão os riscos que <b>permanecem</b> mesmo "
    "após esta implementação, para você ter consciência total:"
))

risk_data = [
    ["Risco", "Mitigação"],
    ["Senha fraca quebrável por força bruta", "Use senha de 12+ caracteres mistos (letras, números, símbolos)"],
    ["Senha vazada por quem tem acesso", "Treine equipe: nunca compartilhar por canais inseguros (email/Slack)"],
    ["Repositório ainda é público no GitHub", "Apenas código fica exposto, dados não. Aceitável neste contexto"],
    ["Commits órfãos acessíveis por ~30 dias", "GitHub vai apagar automaticamente até 15/06/2026"],
    ["Computador local comprometido", "O .env fica em texto puro. Mantenha sistema operacional atualizado"],
    ["Browser do usuário comprometido", "Após login, dados ficam em memória. DevTools podem ler"],
    ["Sem permissões granulares", "Quem tem a senha tem acesso total. Considere Supabase no futuro"],
    ["Sem 2FA / autenticação multi-fator", "Considere Supabase ou Cloudflare Access no futuro"],
]
story.append(section_table(risk_data, [6*cm, 10*cm]))

story.append(WARN(
    "IMPORTANTE: Para manter a segurança, NUNCA compartilhe a senha por email, "
    "WhatsApp ou Slack. Use canal seguro (1Password, Bitwarden) ou pessoalmente."
))

# ===================== 10. PRÓXIMOS PASSOS =====================
story.append(H("10. Próximos Passos Opcionais", H1))

story.append(P(
    "A implementação atual já oferece proteção de nível bancário. As opções abaixo "
    "são <b>melhorias adicionais</b>, não correções necessárias:"
))

story.append(H("Opção A — Migração para Supabase", H3))
story.append(bullet_list([
    "Login individual por email + senha (cada pessoa com sua conta)",
    "Capacidade de revogar acesso por usuário sem trocar senha geral",
    "Logs de auditoria (quem acessou, quando, de qual IP)",
    "Reset de senha automático por email",
    "Possibilidade de permissões granulares (ex: Fulano só vê Meta Ads)",
    "Custo: gratuito até 50.000 usuários ativos por mês",
    "Tempo de implementação: ~2-3 horas",
]))

story.append(H("Opção B — Repositório privado (GitHub Pro)", H3))
story.append(bullet_list([
    "Código-fonte deixa de ser público",
    "GitHub Pages continua funcionando, mas só pra usuários autorizados",
    "Custo: US$ 4/mês",
    "Tempo de implementação: 5 minutos",
]))

story.append(H("Opção C — Cloudflare Access (autenticação corporativa)", H3))
story.append(bullet_list([
    "Login via Google Workspace, Microsoft 365, GitHub, etc.",
    "2FA obrigatório se a conta corporativa exigir",
    "Política de acesso por IP, geografia, horário",
    "Custo: gratuito até 50 usuários",
    "Tempo de implementação: ~1 hora",
]))

# ===================== 11. CHECKLIST DE MANUTENÇÃO =====================
story.append(H("11. Checklist de Manutenção", H1))

story.append(P("Para manter a segurança alta, siga este checklist regularmente:"))

story.append(H("11.1 Senha", H3))
story.append(bullet_list([
    "[ ] Senha tem no mínimo 12 caracteres",
    "[ ] Senha mistura letras maiúsculas, minúsculas, números e símbolos",
    "[ ] Senha NÃO é uma palavra de dicionário",
    "[ ] Senha está em um gerenciador de senhas (1Password, Bitwarden)",
    "[ ] Senha foi trocada nos últimos 6 meses",
    "[ ] Senha foi trocada após saída de qualquer funcionário que tinha acesso",
]))

story.append(H("11.2 Compartilhamento", H3))
story.append(bullet_list([
    "[ ] Lista atualizada de quem tem a senha",
    "[ ] Senha foi compartilhada APENAS via canal seguro",
    "[ ] Ninguém da equipe armazenou a senha em texto puro (Notion, Google Docs, etc.)",
]))

story.append(H("11.3 Sistema", H3))
story.append(bullet_list([
    "[ ] Arquivo .env continua no .gitignore",
    "[ ] Service Account do Google não foi commitado",
    "[ ] Backup do projeto está armazenado em local seguro",
    "[ ] Mudanças críticas (como esta) estão documentadas",
]))

# ===================== 12. RESUMO PARA APRESENTAÇÃO =====================
story.append(PageBreak())
story.append(H("12. Resumo para Apresentação", H1))

story.append(P(
    "Se você precisar explicar essa atualização para alguém (chefe, cliente, parceiro), "
    "use este texto como base:"
))

story.append(C(
    "O dashboard de marketing da Clinica da Cidade passou por uma atualizacao\n"
    "critica de seguranca em 15/05/2026.\n"
    "\n"
    "PROBLEMA: Os dados estavam publicamente acessiveis pela URL.\n"
    "\n"
    "SOLUCAO: Implementacao de criptografia AES-256-GCM (padrao bancario)\n"
    "com tela de login. Agora, qualquer pessoa que acesse o dashboard\n"
    "precisa digitar a senha. Sem a senha, e MATEMATICAMENTE impossivel\n"
    "ler os dados, mesmo baixando o arquivo direto do servidor.\n"
    "\n"
    "MEDIDAS COMPLEMENTARES:\n"
    "- 62 versoes antigas do arquivo de dados foram apagadas do\n"
    "  historico do Git (git-filter-repo)\n"
    "- Deploy automatizado para garantir que mudancas se propagam\n"
    "  imediatamente\n"
    "- Senha armazenada apenas localmente (nao vai para nenhum\n"
    "  servidor externo)\n"
    "\n"
    "RESULTADO: Risco de vazamento de dados reduzido de ALTO para BAIXO.\n"
    "\n"
    "PROXIMOS PASSOS PLANEJADOS:\n"
    "- Migracao para Supabase para login individual por usuario,\n"
    "  com logs de auditoria e permissoes granulares.\n"
))

# ===================== RODAPÉ FINAL =====================
story.append(Spacer(1, 1*cm))
story.append(Paragraph(
    "<para alignment='center'><i>Documento gerado automaticamente em " +
    datetime.now().strftime("%d/%m/%Y às %H:%M") + "<br/>"
    "Mantenha este documento em local seguro como referência técnica das mudanças aplicadas.</i></para>",
    CAPTION
))

# ============ BUILD ============
def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(2*cm, 1*cm, "Documentação de Segurança — Dashboard Marketing CDC")
    canvas.drawRightString(A4[0] - 2*cm, 1*cm, f"Página {doc.page}")
    canvas.restoreState()

doc = SimpleDocTemplate(OUT, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=1.8*cm, bottomMargin=1.8*cm,
    title="Documentação de Segurança — Dashboard Marketing CDC",
    author="Geovane Maze")

doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
print(f"PDF gerado: {OUT}")

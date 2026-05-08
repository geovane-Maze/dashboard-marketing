import requests
import config
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CLIENT_ID = config.RD_CLIENT_ID
CLIENT_SECRET = config.RD_CLIENT_SECRET
CALLBACK_URL = "http://localhost:8080"
BASE_URL = "https://api.rd.services"
ENV_PATH = ".env"

codigo_capturado = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global codigo_capturado
        params = parse_qs(urlparse(self.path).query)
        codigo_capturado = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        if codigo_capturado:
            self.wfile.write(b"<h2>Autorizado! Pode fechar esta aba.</h2>")
        else:
            self.wfile.write(b"<h2>Erro: codigo nao encontrado.</h2>")

    def log_message(self, format, *args):
        pass


def salvar_token_no_env(chave, valor):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
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

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(updated) + "\n")

        print(f"{chave} salvo no .env")
    except Exception as e:
        print(f"Erro ao salvar no .env: {e}")


def trocar_codigo_por_token(code):
    response = requests.post(
        f"{BASE_URL}/auth/token",
        params={"token_by": "code"},
        json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": CALLBACK_URL,
        }
    )
    response.raise_for_status()
    data = response.json()
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")

    print(f"\nRefresh Token: {refresh_token}")
    print(f"Access Token:  {access_token[:60]}...")

    if refresh_token:
        salvar_token_no_env("RD_REFRESH_TOKEN", refresh_token)

    return refresh_token, access_token


def testar_refresh_token(refresh_token):
    print("\nTestando refresh token...")
    response = requests.post(
        f"{BASE_URL}/auth/token",
        params={"token_by": "refresh_token"},
        json={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
    )
    print(f"Status: {response.status_code}")
    data = response.json()

    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        print("Refresh token rotacionado — salvando novo token...")
        salvar_token_no_env("RD_REFRESH_TOKEN", new_refresh)

    if response.status_code == 200:
        print("OK — Refresh token valido!")
    else:
        print(f"Erro: {response.text[:200]}")


if __name__ == "__main__":
    auth_url = (
        f"{BASE_URL}/auth/dialog"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
    )

    print("Iniciando servidor local na porta 8080...")
    server = HTTPServer(("localhost", 8080), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    print("Abrindo navegador para autorizacao...")
    webbrowser.open(auth_url)

    thread.join(timeout=120)

    if codigo_capturado:
        print(f"\nCodigo capturado: {codigo_capturado}")
        refresh_token, _ = trocar_codigo_por_token(codigo_capturado)
        if refresh_token:
            testar_refresh_token(refresh_token)
    else:
        print("Tempo esgotado ou codigo nao capturado.")

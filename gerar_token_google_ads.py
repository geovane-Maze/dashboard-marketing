#!/usr/bin/env python3
"""
Gera o refresh token do Google Ads via OAuth2.
Execute uma vez localmente. O refresh token gerado vai no .env e no GitHub Secrets.
"""

import json
import os
import re
import sys
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import urlopen, Request
from urllib.error import URLError
import http.server
import threading

import config
CLIENT_ID = config.GOOGLE_ADS_CLIENT_ID
CLIENT_SECRET = config.GOOGLE_ADS_CLIENT_SECRET
SCOPE = "https://www.googleapis.com/auth/adwords"
REDIRECT_URI = "http://localhost:8080"

auth_code = None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>Autorizado! Pode fechar esta aba.</h2>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def get_auth_code():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)
    print(f"\nAbrindo navegador para autorização...")
    print(f"Se não abrir automaticamente, acesse:\n{url}\n")
    webbrowser.open(url)

    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()


def exchange_code_for_token(code):
    data = urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urlopen(req) as resp:
        return json.loads(resp.read())


ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def save_token_to_env(refresh_token):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    if "GOOGLE_ADS_REFRESH_TOKEN=" in content:
        content = re.sub(
            r"GOOGLE_ADS_REFRESH_TOKEN=.*",
            f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}",
            content,
        )
    else:
        content += f"\nGOOGLE_ADS_REFRESH_TOKEN={refresh_token}\n"

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Token salvo automaticamente em {ENV_FILE}")


def main():
    print("=" * 50)
    print("Gerador de Refresh Token — Google Ads")
    print("=" * 50)

    get_auth_code()

    if not auth_code:
        print("ERRO: Não foi possível obter o código de autorização.")
        return

    print("Código obtido. Trocando por refresh token...")
    tokens = exchange_code_for_token(auth_code)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(f"ERRO: Sem refresh token na resposta: {tokens}")
        return

    save_token_to_env(refresh_token)

    print("\n" + "=" * 50)
    print("SUCESSO!")
    print("=" * 50)
    print(f"\nGOOGLE_ADS_REFRESH_TOKEN={refresh_token}")
    print(f"\nAtualize também o GitHub Secret GOOGLE_ADS_REFRESH_TOKEN com esse valor.")
    print("=" * 50)


if __name__ == "__main__":
    main()

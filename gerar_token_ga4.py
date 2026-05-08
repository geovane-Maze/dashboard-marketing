import json
import webbrowser
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
CLIENT_SECRETS = "credentials/ga4_oauth_client.json"
TOKEN_FILE = "credentials/ga4_token.json"

def main():
    print("Iniciando autorizacao do Google Analytics...")
    print("O navegador vai abrir. Faca login com geovane@mazemidia.com.br")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"Token salvo em {TOKEN_FILE}")
    print("Autorizacao concluida com sucesso!")

if __name__ == "__main__":
    main()

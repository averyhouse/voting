from google_auth_oauthlib.flow import InstalledAppFlow

# Google API scopes
SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

flow = InstalledAppFlow.from_client_secrets_file("oauth.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("authorized_user.json", "w") as token:
    token.write(creds.to_json())

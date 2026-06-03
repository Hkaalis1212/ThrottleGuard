"""
setup_secrets.py — writes .streamlit/secrets.toml from Railway env vars.
Run before `streamlit run` so native st.login() has credentials at startup.
"""
import os
import pathlib

client_id     = os.environ.get("GOOGLE_CLIENT_ID", "")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
redirect_uri  = os.environ.get("REDIRECT_URI", "")
cookie_secret = os.environ.get("SESSION_SECRET", "throttleguard-default")

pathlib.Path(".streamlit").mkdir(exist_ok=True)

if client_id and client_secret:
    with open(".streamlit/secrets.toml", "w") as f:
        f.write(f"""[auth]
redirect_uri = "{redirect_uri}"
cookie_secret = "{cookie_secret}"

[auth.google]
client_id = "{client_id}"
client_secret = "{client_secret}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
""")
    print("secrets.toml written")
else:
    print("Google env vars not set — skipping secrets.toml (password login only)")

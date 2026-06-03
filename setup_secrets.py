"""
setup_secrets.py — writes .streamlit/secrets.toml from Railway env vars.
Run before `streamlit run` so native st.login() has credentials at startup.
"""
import os
import pathlib

client_id     = os.environ.get("GOOGLE_CLIENT_ID", "")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
cookie_secret = os.environ.get("SESSION_SECRET", "")
redirect_uri  = os.environ.get("REDIRECT_URI", "")

# cookie_secret must be set and stable — if it changes between restarts the
# auth cookie is invalidated and users get a login loop.
if not cookie_secret:
    raise RuntimeError(
        "SESSION_SECRET env var is not set. "
        "Add it in Railway Variables → SESSION_SECRET=<any long random string>. "
        "Without it the auth cookie is invalidated on every restart."
    )

# Streamlit native OAuth always uses /oauth2/callback as the callback path.
# Ensure the redirect_uri ends with it regardless of what was set in REDIRECT_URI.
if redirect_uri and not redirect_uri.endswith("/oauth2/callback"):
    redirect_uri = redirect_uri.rstrip("/") + "/oauth2/callback"

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
    print(f"[setup_secrets] secrets.toml written")
    print(f"[setup_secrets] redirect_uri = {redirect_uri}")
    print(f"[setup_secrets] cookie_secret = {'*' * len(cookie_secret)} ({len(cookie_secret)} chars)")
else:
    print("[setup_secrets] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set — skipping (password login only)")

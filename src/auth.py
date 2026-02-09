import os
import hashlib
import streamlit as st

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def require_login():
    """Einfaches Login per gemeinsamem Passwort.
    Passwort kommt aus:
    - st.secrets['APP_PASSWORD'] (empfohlen) oder
    - ENV APP_PASSWORD
    """
    secret = None
    try:
        secret = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        secret = None
    if not secret:
        secret = os.environ.get("APP_PASSWORD")

    if not secret:
        st.error("APP_PASSWORD ist nicht gesetzt. Setze es in .streamlit/secrets.toml oder als ENV APP_PASSWORD.")
        st.stop()

    # Support: falls jemand einen SHA256 Hash einträgt, akzeptieren wir das auch.
    # Erkennung: 64 hex chars
    def is_hash(x):
        x = x.strip().lower()
        return len(x) == 64 and all(c in "0123456789abcdef" for c in x)

    stored_hash = secret.strip()
    if not is_hash(stored_hash):
        stored_hash = _sha256(stored_hash)

    if st.session_state.get("authed"):
        return

    with st.sidebar:
        st.markdown("## 🔐 Login")
        pw = st.text_input("Gemeinsames Passwort", type="password")
        if st.button("Anmelden"):
            if _sha256(pw) == stored_hash:
                st.session_state["authed"] = True
                st.success("Angemeldet.")
                st.rerun()
            else:
                st.error("Falsches Passwort.")
        st.caption("Tipp: Passwort in `.streamlit/secrets.toml` oder als ENV `APP_PASSWORD` setzen.")
    st.stop()

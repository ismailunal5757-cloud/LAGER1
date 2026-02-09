import os
import time
import mimetypes

def save_upload(data_dir: str, uploaded_file):
    """Speichert Upload unter data/uploads und gibt (stored_path, mime, size) zurück."""
    uploads_dir = os.path.join(data_dir, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # eindeutiger Dateiname
    ts = int(time.time() * 1000)
    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_")
    stored_name = f"{ts}__{safe_name}"
    stored_path = os.path.join(uploads_dir, stored_name)

    content = uploaded_file.getbuffer()
    with open(stored_path, "wb") as f:
        f.write(content)

    mime = uploaded_file.type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    size = len(content)
    return stored_path, mime, size

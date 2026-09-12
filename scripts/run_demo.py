"""Offline demonstration in a fresh profile; never reads the real .env or DB."""
import argparse
from contextlib import ExitStack
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile


def run(check=False):
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use Python 3.12 with Middleware/requirements.txt installed")
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    # Start from OS/runtime settings, never inherit provider or integration keys.
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    environment = {k: v for k, v in os.environ.items() if k.upper() in keep}
    os.environ.clear()
    os.environ.update(environment)

    def local_connection(original):
        def connect(sock, address):
            # Windows asyncio uses loopback sockets internally.
            if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
                return original(sock, address)
            raise OSError("External connections are disabled in the offline demo")
        return connect
    socket.socket.connect = local_connection(socket.socket.connect)
    socket.socket.connect_ex = local_connection(socket.socket.connect_ex)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "Middleware"))
    with tempfile.TemporaryDirectory(prefix="diplom-demo-") as profile, ExitStack() as cleanup:
        os.environ.update({"JWT_SECRET": secrets.token_hex(32), "RATE_LIMIT_ENABLED": "false",
                           "SQLITE_DB_PATH": str(Path(profile) / "demo.db"),
                           "METADATA_DATA_DIR": profile, "METADATA_ML_ENABLED": "false"})
        from main import app
        from app.services.auth_service import engine as auth_engine
        from app.services.kanban_service import engine as kanban_engine
        cleanup.callback(auth_engine.dispose)
        cleanup.callback(kanban_engine.dispose)
        if check:
            from fastapi.testclient import TestClient
            with TestClient(app) as client:
                assert client.get("/health").status_code == 200
                for user in ("employee", "director"):
                    login = client.post("/auth/login", json={"username": user, "password": user + "123"})
                    assert login.status_code == 200
                    headers = {"X-Auth-Token": login.json()["access_token"]}
                    response = client.post("/chat", headers=headers, json={"messages": [{"role": "user", "text": "Какой кассовый разрыв?"}]})
                    assert response.status_code == 200
                    assert response.json()["action"] == ("access_denied" if user == "employee" else "cash_gap_forecast")
                    task = client.post("/kanban/tasks", headers=headers, json={"title": "Synthetic demo task"})
                    assert task.status_code == 200
                assert client.get("/").status_code == 200
            print("PASS: clean offline profile; health, personal login, RBAC, chat, tasks, web page")
        else:
            import uvicorn
            print("Offline demo: http://127.0.0.1:8000; synthetic accounts only; data removed on exit.", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="In-process smoke check; no listening server")
    run(parser.parse_args().check)

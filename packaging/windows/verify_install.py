"""Exercise an installed copy on a disposable Windows runner."""
import builtins
import getpass
import os
import secrets
import subprocess
import sys

import httpx
import launcher

password = secrets.token_urlsafe(24)
conversation = None


def check_browser(url):
    global conversation
    with httpx.Client(base_url=url, timeout=1000) as client:
        assert 'id="root"' in client.get("/").raise_for_status().text
        health = client.get("/health").raise_for_status().json()
        assert health["llm"] == "openai_compat" and health["db"] == "postgres"
        token = client.post("/auth/login", json={"email":"owner@uyut.by","password":password}).raise_for_status().json()
        client.headers["Authorization"] = "Bearer " + token["access_token"]
        for route in ("overview", "orders", "purchases", "staff", "sales/imports"):
            client.get("/agent/"+route).raise_for_status()
        if conversation:
            client.get("/agent/conversations/"+conversation).raise_for_status()
            assert client.get("/agent/sales/imports").json()["items"]
            return
        import psycopg2
        with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
            assert cur.fetchone()[0] == "0.8.2"
            cur.execute("SELECT sku FROM products WHERE company_id=1 LIMIT 1")
            sku = cur.fetchone()[0]
        csv = f"date,order_id,sku,quantity,price\n2026-11-20,SMOKE-1,{sku},1,11.00\n"
        for confirm in ("false", "true"):
            client.post("/agent/sales/import", files={"file":("test.csv",csv,"text/csv")},
                        data={"confirm":confirm}).raise_for_status()
        answer = client.post("/agent/chat", json={"message":"Сколько будет 12 плюс 7? Напиши ответ цифрами."}).raise_for_status().json()
        assert "19" in answer["message"], answer
        conversation = answer["conversation_id"]
        subprocess.run([sys.executable, "-c", "import launcher; launcher.webbrowser.open=lambda url:None; launcher.main()"], check=True, timeout=30)
        print("Verified AI answer:", answer["message"], flush=True)


if __name__ == "__main__":
    getpass.getpass = lambda prompt: password
    launcher.webbrowser.open = check_browser
    builtins.input = lambda prompt: ""
    for _ in range(2):
        launcher.main()
        assert not (launcher.DATA/"ready").exists()

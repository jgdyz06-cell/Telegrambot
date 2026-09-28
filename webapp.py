# -*- coding: utf-8 -*-

"""Web App واجهة ملونة للبوت."""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0,
               maximum-scale=1.0, user-scalable=no">

<title>قطوف الأكلم</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 20px 14px 35px;
    font-family: Arial, sans-serif;
    background:
        linear-gradient(145deg, #171329, #24183d, #101827);
    color: white;
    min-height: 100vh;
}

.container {
    max-width: 520px;
    margin: auto;
}

.header {
    text-align: center;
    padding: 15px 10px 22px;
}

.header .logo {
    font-size: 48px;
    margin-bottom: 5px;
}

.header h1 {
    margin: 0;
    font-size: 28px;
}

.header p {
    margin-top: 8px;
    opacity: 0.75;
    font-size: 15px;
}

.grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}

button {
    border: none;
    color: white;
    min-height: 76px;
    border-radius: 20px;
    padding: 12px 8px;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    box-shadow:
        0 7px 18px rgba(0,0,0,0.28);
    transition: transform 0.12s;
}

button:active {
    transform: scale(0.96);
}

.purple {
    background: linear-gradient(135deg, #7c3aed, #a855f7);
}

.orange {
    background: linear-gradient(135deg, #f97316, #fb923c);
}

.pink {
    background: linear-gradient(135deg, #db2777, #f472b6);
}

.yellow {
    background: linear-gradient(135deg, #d97706, #facc15);
    color: #211500;
}

.cyan {
    background: linear-gradient(135deg, #0891b2, #22d3ee);
}

.sky {
    background: linear-gradient(135deg, #2563eb, #38bdf8);
}

.teal {
    background: linear-gradient(135deg, #0f766e, #2dd4bf);
}

.dark {
    background: linear-gradient(135deg, #374151, #6b7280);
}

.full {
    grid-column: 1 / -1;
}

.footer {
    text-align: center;
    margin-top: 25px;
    opacity: 0.55;
    font-size: 13px;
}

</style>
</head>

<body>

<div class="container">

    <div class="header">
        <div class="logo">🎓</div>
        <h1>قطوف الأكلم 📚</h1>
        <p>اختر الخدمة التي تريدها</p>
    </div>

    <div class="grid">

        <button class="purple"
                onclick="send('sm')">
            📄<br>
            الملخصات
        </button>

        <button class="orange"
                onclick="send('qm')">
            📝<br>
            الاختبارات
        </button>

        <button class="cyan"
                onclick="send('me')">
            📊<br>
            نتائجي
        </button>

        <button class="pink"
                onclick="send('sc')">
            📅<br>
            الجدول الأسبوعي
        </button>

        <button class="yellow"
                onclick="send('rp')">
            📑<br>
            طلب تقرير
        </button>

        <button class="teal"
                onclick="send('ct')">
            📞<br>
            تواصل معنا
        </button>

        <button class="sky full"
                onclick="send('ai')">
            🤖<br>
            الذكاء الاصطناعي
        </button>

        <button class="dark full"
                onclick="closeApp()">
            ❌ إغلاق
        </button>

    </div>

    <div class="footer">
        قطوف الأكلم ©
    </div>

</div>

<script>

function send(data) {

    if (
        window.Telegram &&
        Telegram.WebApp
    ) {

        Telegram.WebApp.ready();

        Telegram.WebApp.sendData(
            data
        );

    } else {

        alert(
            "هذه الواجهة تعمل من داخل Telegram."
        );

    }
}

function closeApp() {

    if (
        window.Telegram &&
        Telegram.WebApp
    ) {
        Telegram.WebApp.close();
    }

}

if (
    window.Telegram &&
    Telegram.WebApp
) {
    Telegram.WebApp.ready();
    Telegram.WebApp.expand();
}

</script>

</body>
</html>
"""


class WebAppHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/" or self.path == "/web":

            content = HTML.encode("utf-8")

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )

            self.send_header(
                "Content-Length",
                str(len(content))
            )

            self.end_headers()

            self.wfile.write(content)

            return

        self.send_response(404)

        self.end_headers()

        self.wfile.write(
            b"Not Found"
        )

    def log_message(
        self,
        format,
        *args
    ):

        return


def start_web_server():

    port = int(
        os.getenv(
            "PORT",
            "8080"
        )
    )

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            port
        ),
        WebAppHandler
    )

    print(
        f"Web App server running on port {port}",
        flush=True
    )

    server.serve_forever()

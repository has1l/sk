"""Пароль на весь сайт для публичного прототипа.

Своя страница входа вместо системного окна Basic-аутентификации: браузерное
окно выглядит как ошибка и не похоже на продукт. После верного пароля
браузер получает куку — подпись пароля, а не сам пароль, — и дальше
прикладывает её к fetch, потоку ответа и ссылкам выгрузки сам. Клиенту ничего
знать не нужно. Смена пароля обнуляет все выданные куки.

Без SITE_PASSWORD ворота открыты: локально пароль не нужен.

Открыто всегда: проверка живости (по ней Railway решает, жив ли контейнер),
значок и шрифты (без них страница входа не похожа на сайт).
"""

import hashlib
import hmac
import html
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

COOKIE = "klodik_pass"
LOGIN_PATH = "/login"
OPEN_PATHS = {"/api/health", "/favicon.svg"}
OPEN_PREFIXES = ("/fonts/",)
MAX_BODY = 4096
TRIES_PER_MINUTE = 10
COOKIE_DAYS = 30


def token(password: str) -> str:
    return hmac.new(password.encode(), b"klodik-site-v1", hashlib.sha256).hexdigest()


def _cookie(headers: dict[bytes, bytes]) -> str | None:
    for part in headers.get(b"cookie", b"").decode("latin-1").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value
    return None


def _safe_next(target: str) -> str:
    """Куда вернуть после входа. Только свой путь — иначе форма входа
    становится открытым редиректом на чужой сайт."""
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


class PasswordGate:
    def __init__(self, app: ASGIApp, password: str) -> None:
        self.app = app
        self.password = password
        self.expected = token(password) if password else ""
        self.tries: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not self.password
            or path in OPEN_PATHS
            or path.startswith(OPEN_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        given = _cookie(headers)
        if given and hmac.compare_digest(given, self.expected):
            await self.app(scope, receive, send)
            return

        if path == LOGIN_PATH and scope["method"] == "POST":
            await self._login(scope, receive, send)
            return
        if path.startswith("/api/"):
            await _send(send, 401, "application/json", '{"detail":"Нужен пароль"}')
            return
        query = scope.get("query_string", b"").decode("latin-1")
        target = path + (f"?{query}" if query else "")
        await _send(send, 401, "text/html", login_page(_safe_next(target)))

    async def _login(self, scope: Scope, receive: Receive, send: Send) -> None:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if len(body) > MAX_BODY or not message.get("more_body"):
                break
        form = parse_qs(body[:MAX_BODY].decode("utf-8", "replace"))
        target = _safe_next(form.get("next", ["/"])[0])

        host = scope["client"][0] if scope.get("client") else "?"
        now = time.monotonic()
        recent = self.tries[host]
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) >= TRIES_PER_MINUTE:
            await _send(send, 429, "text/html", login_page(target, "Слишком много попыток — подождите минуту"))
            return
        recent.append(now)

        password = form.get("password", [""])[0]
        if not hmac.compare_digest(token(password), self.expected):
            await _send(send, 401, "text/html", login_page(target, "Пароль не подошёл"))
            return

        recent.clear()
        secure = "; Secure" if scope.get("scheme") == "https" else ""
        cookie = (
            f"{COOKIE}={self.expected}; Path=/; Max-Age={COOKIE_DAYS * 86400}; "
            f"HttpOnly; SameSite=Lax{secure}"
        )
        await send({
            "type": "http.response.start",
            "status": 303,
            "headers": [
                (b"location", target.encode("latin-1", "ignore") or b"/"),
                (b"set-cookie", cookie.encode()),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": b""})


async def _send(send: Send, status: int, kind: str, text: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", f"{kind}; charset=utf-8".encode()),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({"type": "http.response.body", "body": text.encode()})


PET = """<svg viewBox="0 0 56 56" width="64" height="64" shape-rendering="crispEdges" aria-hidden="true">
<rect width="56" height="56" rx="14" fill="var(--accent-fill)"/>
<g fill="#fff"><rect x="16" y="18" width="24" height="15"/><rect x="12" y="24" width="4" height="5"/>
<rect x="40" y="24" width="4" height="5"/><rect x="17" y="33" width="3" height="5"/>
<rect x="23" y="33" width="3" height="5"/><rect x="30" y="33" width="3" height="5"/>
<rect x="36" y="33" width="3" height="5"/></g>
<g class="eyes" fill="var(--accent-fill)"><rect x="21" y="23" width="3" height="4"/>
<rect x="32" y="23" width="3" height="4"/></g></svg>"""


def login_page(target: str, error: str = "") -> str:
    alert = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Клодик — вход</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script>try{{var t=localStorage.getItem("puzzle.theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>
@font-face{{font-family:Inter;font-weight:100 900;font-display:swap;src:url(/fonts/inter-cyrillic.woff2) format("woff2");unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:Inter;font-weight:100 900;font-display:swap;src:url(/fonts/inter-latin.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F,U+20AC,U+2122}}
@font-face{{font-family:"Source Serif";font-weight:200 900;font-display:swap;src:url(/fonts/serif-cyrillic.woff2) format("woff2");unicode-range:U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}}
@font-face{{font-family:"Source Serif";font-weight:200 900;font-display:swap;src:url(/fonts/serif-latin.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F,U+20AC,U+2122}}
:root{{--paper:#f5f4ee;--raised:#fff;--ink:#1f1e1c;--ink-2:#5a574e;--ink-muted:#8c887c;--line:rgba(31,30,28,.09);--line-2:rgba(31,30,28,.16);
--accent:#a84a2b;--accent-fill:#b4502f;--accent-ring:rgba(180,80,47,.28);--critical:#a93226;
--shadow:0 1px 3px rgba(31,30,28,.06),0 24px 60px -24px rgba(31,30,28,.28);color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#1b1a17;--raised:#2a2825;--ink:#efede4;--ink-2:#b5b0a3;--ink-muted:#8a857a;--line:rgba(239,237,228,.1);--line-2:rgba(239,237,228,.18);
--accent:#e08a66;--accent-fill:#c4663f;--accent-ring:rgba(224,138,102,.32);--critical:#e0705f;--shadow:0 1px 3px rgba(0,0,0,.4),0 24px 60px -24px rgba(0,0,0,.7);color-scheme:dark}}}}
:root[data-theme="dark"]{{--paper:#1b1a17;--raised:#2a2825;--ink:#efede4;--ink-2:#b5b0a3;--ink-muted:#8a857a;--line:rgba(239,237,228,.1);--line-2:rgba(239,237,228,.18);
--accent:#e08a66;--accent-fill:#c4663f;--accent-ring:rgba(224,138,102,.32);--critical:#e0705f;--shadow:0 1px 3px rgba(0,0,0,.4),0 24px 60px -24px rgba(0,0,0,.7);color-scheme:dark}}
*{{box-sizing:border-box}}
html{{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}}
body{{margin:0;min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:24px 16px;
background:var(--paper);color:var(--ink);font:400 15px/1.5 Inter,system-ui,sans-serif}}
main{{width:min(380px,100%);text-align:center;animation:rise .5s cubic-bezier(.16,1,.3,1) backwards}}
.pet{{display:inline-block;margin-bottom:20px}}
.pet .eyes{{animation:blink 5s infinite;transform-origin:center 25px}}
h1{{margin:0;font:500 34px/1.15 "Source Serif",Georgia,serif;letter-spacing:-.01em}}
.lead{{margin:8px 0 28px;color:var(--ink-2);text-wrap:pretty}}
form{{background:var(--raised);border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:var(--shadow);text-align:left}}
label{{display:block;font-weight:500;font-size:13px;color:var(--ink-2);margin-bottom:8px}}
input{{width:100%;height:44px;padding:0 14px;border-radius:12px;border:1px solid var(--line-2);background:var(--paper);color:var(--ink);font:inherit;font-size:16px;
transition:border-color .15s,box-shadow .15s}}
input:focus{{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-ring)}}
button{{margin-top:12px;width:100%;height:44px;border:0;border-radius:12px;background:var(--accent-fill);color:#fff;font:500 15px Inter,system-ui,sans-serif;cursor:pointer;
transition:filter .15s,transform .15s}}
button:hover{{filter:brightness(1.06)}}
button:active{{transform:scale(.97)}}
button:focus-visible{{outline:none;box-shadow:0 0 0 4px var(--accent-ring)}}
.error{{margin:12px 0 0;color:var(--critical);font-size:13px;animation:nudge .32s}}
.hint{{margin:20px 0 0;color:var(--ink-muted);font-size:13px}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}}}
@keyframes blink{{0%,94%,100%{{transform:scaleY(1)}}97%{{transform:scaleY(.1)}}}}
@keyframes nudge{{25%{{transform:translateX(-4px)}}75%{{transform:translateX(4px)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
</head>
<body>
<main>
<span class="pet">{PET}</span>
<h1>Клодик</h1>
<p class="lead">Аналитика продаж в чате. Прототип закрыт паролем — его выдаёт команда</p>
<form method="post" action="{LOGIN_PATH}">
<input type="hidden" name="next" value="{html.escape(target)}">
<label for="password">Пароль</label>
<input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Войти</button>
{alert}
</form>
<p class="hint">Вход запоминается на этом устройстве на 30 дней</p>
</main>
</body>
</html>"""

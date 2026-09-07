"""Optional owner-authenticated, read-only view of committed Git data.

No agent credentials authorize HTTP reads. No writes, pushes, checkouts, working
file serving, repository credentials in responses, or on-disk content cache.
"""
from __future__ import annotations

import argparse
import base64
from collections import deque
from dataclasses import dataclass
import getpass
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

import megabrain
import operations

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60
MAX_CONTENT = 128 * 1024 * 1024


class LiveError(operations.OperationError):
    pass


def origin_url(value: str, *, local_http: bool = False) -> str:
    try:
        if not isinstance(value, str) or re.search(r"[\s\x00-\x1f\x7f]", value):
            raise ValueError
        parsed = urlsplit(value)
        port = parsed.port
        valid = (parsed.scheme == "https" or (local_http and parsed.scheme == "http"
                 and parsed.hostname == "127.0.0.1"))
        if (not valid or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or re.fullmatch(r"[A-Za-z0-9.:-]+", parsed.netloc) is None
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError
        authority = parsed.hostname if parsed.scheme == "https" and port == 443 else parsed.netloc
        return f"{parsed.scheme}://{authority.lower()}"
    except ValueError:
        raise LiveError("LIVE_ORIGIN_INVALID", "Use a dedicated HTTPS origin without a path, query or credentials.") from None


def password_record(password: str) -> dict:
    if not 16 <= len(password) <= 256:
        raise LiveError("LIVE_PASSWORD_INVALID", "Use a unique owner passphrase of 16 to 256 characters.")
    salt = secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return {"schema": "megabrain.live-owner.v1", "iterations": ITERATIONS,
            "salt": salt.hex(), "digest": digest.hex()}


def read_owner(path: Path) -> dict:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError
            value = json.loads(stream.read(2049))
        if (value.get("schema") != "megabrain.live-owner.v1" or value.get("iterations") != ITERATIONS
                or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(key, ""))) is None
                       for key in ("salt", "digest"))):
            raise ValueError
        return value
    except (OSError, ValueError, AttributeError):
        raise LiveError("LIVE_OWNER_UNAVAILABLE", "Owner sign-in is unavailable. Check the owner-only credential file.") from None


class OwnerAuth:
    """In-memory sessions. Rotation/removal of the verifier revokes all sessions."""
    def __init__(self, path: Path):
        self.path = path
        self.guard = threading.Lock()
        self.sessions: dict[str, tuple[float, str]] = {}
        self.attempts: deque[float] = deque()
        read_owner(path)

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(read_owner(self.path), sort_keys=True).encode()).hexdigest()

    def login(self, password: str) -> str | None:
        with self.guard:
            now = time.monotonic()
            while self.attempts and self.attempts[0] <= now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 5:
                raise LiveError("LIVE_RATE_LIMIT", "Too many sign-in attempts. Wait one minute and try again.")
            self.attempts.append(now)
            value = read_owner(self.path)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(value["salt"]), ITERATIONS)
            if not hmac.compare_digest(digest.hex(), value["digest"]):
                return None
            token = secrets.token_urlsafe(32)
            self.sessions = {key: session for key, session in self.sessions.items() if session[0] > now}
            if len(self.sessions) >= 16:
                self.sessions.pop(next(iter(self.sessions)))
            verified_fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + SESSION_SECONDS, verified_fingerprint)
            return token

    def allowed(self, token: str) -> bool:
        with self.guard:
            key = hashlib.sha256(token.encode()).hexdigest()
            session = self.sessions.get(key)
            try:
                valid = bool(session and session[0] > time.monotonic()
                             and hmac.compare_digest(session[1], self.fingerprint()))
            except LiveError:
                valid = False
            if not valid:
                self.sessions.pop(key, None)
            return valid

    def logout(self, token: str) -> None:
        with self.guard:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)


@dataclass(frozen=True)
class Projection:
    commit: str
    payload: dict
    documents: dict[str, bytes]


class LiveView:
    def __init__(self, root: Path, interval: int = 15):
        if not 10 <= interval <= 300:
            raise LiveError("LIVE_INTERVAL_INVALID", "Refresh interval must be between 10 and 300 seconds.")
        self.root, self.interval = root.resolve(), interval
        self.guard = threading.Lock()
        self.refresh_guard = threading.Lock()
        self.projection: Projection | None = None
        self.last_synced: str | None = None
        self.reason: str | None = "connecting"
        self.checked_at = 0.0
        self.stop = threading.Event()

    def capture(self, commit: str) -> Projection:
        listing = operations.git_text(self.root, "ls-tree", "-rl", commit, "--", "brain", "megabrain.json")
        sizes = [line.split(None, 4)[3] for line in listing.splitlines()]
        if any(not size.isdigit() for size in sizes) or sum(int(size) for size in sizes) > MAX_CONTENT:
            raise LiveError("LIVE_SOURCE_UNSAFE", "Committed content exceeds viewer limits or contains unsafe objects.")
        sync = {"synced": True, "stale": False, "pending_local_commits": False}
        with operations.snapshot(self.root, "brain", "megabrain.json", commit=commit) as snapshot:
            megabrain.require_compatible_runtime(snapshot, writing=False)
            if not megabrain.command_validate(snapshot)["ok"]:
                raise LiveError("LIVE_SOURCE_INVALID", "Committed Brain validation failed.")
            # Deliberately no trusted_context: owner login is NOT an agent policy.
            payload = megabrain._browser_payload(snapshot, sync)
            payload["snapshot_commit"] = commit
            visible = {memory["id"] for memory in payload["memories"]}
            for memory in payload["memories"]:
                memory["supersedes"] = [item for item in memory["supersedes"] if item in visible]
            documents = {}
            for item in [*payload["memories"], *payload["resources"]]:
                path = item["path"]
                documents[path] = (snapshot / path).read_bytes()
        if len(json.dumps(payload).encode()) + sum(map(len, documents.values())) > MAX_CONTENT:
            raise LiveError("LIVE_SOURCE_TOO_LARGE", "The viewer projection exceeds its safe size limit.")
        return Projection(commit, payload, documents)

    def refresh(self) -> None:
        with self.refresh_guard:
            try:
                with operations.lock(self.root), operations.deadline(25):
                    if operations.git_text(self.root, "status", "--porcelain", "--untracked-files=all"):
                        raise LiveError("LIVE_DIRTY_CLONE", "The viewer clone has local changes. Nothing was repaired.")
                    result = operations.run(["git", "fetch", "--no-tags", "origin",
                                             "refs/heads/main:refs/remotes/origin/main"], self.root)
                    offline = result.returncode != 0
                    commit = operations.git_text(self.root, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
                    if operations.run(["git", "merge-base", "--is-ancestor", "HEAD", commit], self.root).returncode:
                        raise LiveError("LIVE_LOCAL_COMMITS", "Use a dedicated viewer clone without local commits.")
                    previous = self.projection
                    if previous and operations.run(["git", "merge-base", "--is-ancestor", previous.commit, commit], self.root).returncode:
                        raise LiveError("LIVE_HISTORY_CHANGED", "Remote history changed. Owner review is required.")
                    projection = previous if previous and previous.commit == commit else self.capture(commit)
                    with self.guard:
                        self.projection = projection
                        self.reason = "remote_unavailable" if offline else None
                        self.checked_at = time.monotonic()
                        if not offline:
                            self.last_synced = megabrain.utc_now()
            except (operations.OperationError, megabrain.BrainError, OSError, ValueError):
                # Invalid, dirty or unavailable committed state must not keep being served.
                with self.guard:
                    self.projection = None
                    self.reason = "viewer_needs_attention"

    def status(self) -> dict:
        reason = self.reason
        if reason is None and time.monotonic() - self.checked_at > self.interval + 30:
            reason = "refresh_delayed"
        return {"mode": "live", "read_only": True, "scope": "general_only",
                "interval_seconds": self.interval, "last_synced_at": self.last_synced,
                "stale": reason is not None, "reason": reason,
                "runtime_version": megabrain.runtime_manifest()["version"]}

    def data(self) -> dict:
        with self.guard:
            if self.projection is None:
                return {"available": False, "live": self.status()}
            return {"available": True, "live": self.status(), "data": self.projection.payload}

    def document(self, path: str) -> bytes | None:
        with self.guard:
            return self.projection.documents.get(path) if self.projection else None

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.refresh()
            except Exception:
                # Keep the listener recoverable, but never report a dead worker as live.
                with self.guard:
                    self.projection = None
                    self.reason = "viewer_needs_attention"
            self.stop.wait(self.interval)


def shell() -> str:
    data = {"memories": [], "resources": [], "agents": [], "imports": [], "conflicts": [],
            "review": [], "stats": {"current": 0, "history": 0, "conflicts": 0, "agents": 0, "imports": 0},
            "live": {"mode": "live", "interval_seconds": 15, "stale": True, "reason": "connecting"},
            "sync": {"stale": True}}
    html = (ASSETS / "browser.html").read_text(encoding="utf-8").replace("__MEGABRAIN_DATA__", json.dumps(data))
    return re.sub(r'  <meta http-equiv="Content-Security-Policy"[^>]+>\n', "", html)


def content_policy(html: str) -> str:
    def hashes(tag: str) -> str:
        return " ".join("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
                        for body in re.findall(rf"<{tag}>(.*?)</{tag}>", html, re.S))
    scripts, styles = hashes("script") or "'none'", hashes("style") or "'none'"
    return (f"default-src 'none'; script-src {scripts}; "
            f"style-src {styles}; connect-src 'self'; "
            "img-src data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'")


class LiveServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, address: tuple[str, int], view: LiveView, auth: OwnerAuth, origin: str,
                 *, local_http: bool = False, tls: ssl.SSLContext | None = None):
        self.view, self.auth = view, auth
        self.origin = origin_url(origin, local_http=local_http)
        self.authority = urlsplit(self.origin).netloc
        self.cookie_name = "megabrain_local" if local_http else "__Host-megabrain"
        self.secure = not local_http
        self.tls = tls
        self.slots = threading.BoundedSemaphore(16)
        self.html = shell()
        self.login_html = (ASSETS / "live-login.html").read_text(encoding="utf-8")
        super().__init__(address, LiveHandler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(10)
            if self.tls:
                request = self.tls.wrap_socket(request, server_side=True)
            super().process_request_thread(request, client_address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Base implementation prints tracebacks and locals may contain credentials.
        pass


class LiveHandler(BaseHTTPRequestHandler):
    server: LiveServer
    server_version = "MegaBrain"
    sys_version = ""

    def log_message(self, format, *args):
        pass  # No URL, cookie, password, repository path or source text logging.

    def send_error(self, code, message=None, explain=None):
        self.respond(code, "Request not accepted.")

    def respond(self, code: int, body: str | bytes = b"", *, content_type: str = "text/plain; charset=utf-8",
                headers: dict | None = None, inert: bool = False):
        encoded = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", content_policy(body) if isinstance(body, str) and content_type.startswith("text/html")
                         else "default-src 'none'; frame-ancestors 'none'; base-uri 'none'" + ("; sandbox" if inert else ""))
        if self.server.secure:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def cookie(self, token: str, *, clear: bool = False) -> str:
        return (f"{self.server.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={0 if clear else SESSION_SECONDS}" + ("; Secure" if self.server.secure else ""))

    def token(self) -> str:
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            item = cookies.get(self.server.cookie_name)
            value = item.value if item else ""
            return value if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) else ""
        except CookieError:
            return ""

    def safe_request(self) -> bool:
        if (self.headers.get_all("Host") != [self.server.authority]
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
                or not self.path.startswith("/") or self.path.startswith("//")):
            self.respond(403, "Request not accepted.")
            return False
        return True

    def do_GET(self):
        if not self.safe_request():
            return
        if self.path == "/login":
            self.respond(200, self.server.login_html, content_type="text/html; charset=utf-8")
            return
        if not self.server.auth.allowed(self.token()):
            if self.path == "/":
                self.respond(303, headers={"Location": "/login"})
            else:
                self.respond(401, "Owner sign-in required.")
            return
        if self.path == "/":
            self.respond(200, self.server.html, content_type="text/html; charset=utf-8")
        elif self.path == "/api/snapshot":
            self.respond(200, json.dumps(self.server.view.data(), ensure_ascii=True), content_type="application/json")
        elif self.path.startswith("/source?"):
            try:
                query = parse_qs(urlsplit(self.path).query, strict_parsing=True, max_num_fields=1)
                path = query["path"][0]
            except (ValueError, KeyError):
                path = ""
            document = self.server.view.document(path)
            self.respond(404 if document is None else 200, document if document is not None else "Source unavailable.", inert=True)
        else:
            self.respond(404, "Not found.")

    def do_POST(self):
        if not self.safe_request():
            return
        if self.headers.get_all("Origin") != [self.server.origin]:
            self.respond(403, "Open Live Home directly before signing in or out.")
            return
        if self.path == "/logout":
            self.server.auth.logout(self.token())
            self.respond(303, headers={"Location": "/login", "Set-Cookie": self.cookie("", clear=True),
                                      "Clear-Site-Data": '"cache", "cookies", "storage"'})
            return
        if self.path != "/login":
            self.respond(405, "Live Home is read-only.", headers={"Allow": "GET"})
            return
        try:
            lengths = self.headers.get_all("Content-Length") or []
            if (len(lengths) != 1 or not lengths[0].isdigit() or not 1 <= int(lengths[0]) <= 4096
                    or self.headers.get("Transfer-Encoding")
                    or self.headers.get("Content-Type") != "application/x-www-form-urlencoded"):
                raise ValueError
            fields = parse_qs(self.rfile.read(int(lengths[0])).decode(), strict_parsing=True, max_num_fields=1)
            password = fields["password"][0]
            if len(password) > 256:
                raise ValueError
            token = self.server.auth.login(password)
        except (ValueError, KeyError, UnicodeError):
            self.respond(400, "Sign-in request not accepted.")
            return
        except LiveError as error:
            self.respond(429 if error.code == "LIVE_RATE_LIMIT" else 503, error.message,
                         headers={"Retry-After": "60"})
            return
        if token is None:
            html = self.server.login_html.replace('id="login-status" role="status">', 'id="login-status" role="status">Sign-in failed. Check your passphrase and try again. ')
            self.respond(401, html, content_type="text/html; charset=utf-8")
        else:
            self.respond(303, headers={"Location": "/", "Set-Cookie": self.cookie(token)})


def saved_url(home: Path) -> str | None:
    path = home / ".megabrain" / "live-home.json"
    if not path.exists():
        return None
    try:
        return origin_url(json.loads(path.read_text())["url"])
    except (OSError, ValueError, KeyError, TypeError):
        raise LiveError("LIVE_LINK_INVALID", "The saved Live Home link is invalid. Configure it again or use open --local.") from None


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser("live", help="configure or serve optional read-only Live Home")
    actions = parser.add_subparsers(dest="live_action", required=True)
    link = actions.add_parser("link", help="save the approved owner URL on this device")
    link.add_argument("--url", required=True)
    link.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    unlink = actions.add_parser("unlink", help="return to local snapshots on this device")
    unlink.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    owner = actions.add_parser("owner", help="set or rotate the owner passphrase without printing it")
    owner.add_argument("--auth-file", type=Path, required=True)
    serve = actions.add_parser("serve", help="serve a dedicated read-only replica; see docs/live-home.md")
    serve.add_argument("--root", type=Path, required=True)
    serve.add_argument("--auth-file", type=Path, required=True)
    serve.add_argument("--origin", required=True)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--interval", type=int, default=15)
    transport = serve.add_mutually_exclusive_group(required=True)
    transport.add_argument("--cert", type=Path, help="TLS certificate chain supplied by the operator")
    transport.add_argument("--behind-proxy", action="store_true", help="HTTPS reverse proxy to loopback only")
    transport.add_argument("--local-http", action="store_true", help="loopback-only synthetic development, never remote access")
    serve.add_argument("--key", type=Path, help="TLS private key reference, never copied into MegaBrain")


def command(args) -> str:
    if args.live_action == "link":
        url = origin_url(args.url)
        operations.atomic_write(args.home / ".megabrain" / "live-home.json", json.dumps({"url": url}) + "\n")
        return "Live Home link saved for this device. Owner sign-in is still required."
    if args.live_action == "unlink":
        (args.home / ".megabrain" / "live-home.json").unlink(missing_ok=True)
        return "Local snapshots restored on this device. The viewer service was not stopped."
    if args.live_action == "owner":
        if not os.isatty(0):
            raise LiveError("LIVE_OWNER_TTY_REQUIRED", "Set the owner passphrase in a private interactive terminal, not through an agent prompt.")
        password = getpass.getpass("New Live Home owner passphrase: ")
        if password != getpass.getpass("Confirm passphrase: "):
            raise LiveError("LIVE_PASSWORD_MISMATCH", "Passphrases did not match. Nothing was changed.")
        operations.atomic_write(args.auth_file.expanduser().absolute(), json.dumps(password_record(password)) + "\n")
        return "Owner verifier saved privately. Previous browser sessions are now revoked."
    origin = origin_url(args.origin, local_http=args.local_http)
    if not 1 <= args.port <= 65535:
        raise LiveError("LIVE_PORT_INVALID", "Choose a port from 1 to 65535.")
    if (args.local_http or args.behind_proxy) and args.bind != "127.0.0.1":
        raise LiveError("LIVE_TRANSPORT_UNSAFE", "Unencrypted listener must bind to 127.0.0.1 only.")
    if args.local_http and origin != f"http://127.0.0.1:{args.port}":
        raise LiveError("LIVE_ORIGIN_INVALID", "The local origin must match the loopback listener.")
    tls = None
    if args.cert:
        if not args.key:
            raise LiveError("LIVE_TLS_REQUIRED", "Supply the TLS key reference with the certificate.")
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(args.cert, args.key)
    elif args.key:
        raise LiveError("LIVE_TLS_INVALID", "A TLS key requires a certificate.")
    root = args.root.expanduser().resolve()
    if not root.is_dir() or not (root / ".git").is_dir():
        raise LiveError("LIVE_CLONE_REQUIRED", "Use a dedicated existing clone, not an agent worktree or bare repository.")
    auth_file = args.auth_file.expanduser().absolute()
    if root == auth_file.resolve() or root in auth_file.resolve().parents:
        raise LiveError("LIVE_AUTH_IN_CLONE", "Keep the owner verifier outside the data replica.")
    view = LiveView(root, args.interval)
    with operations.lock(root, name="live-service", timeout=0):
        server = LiveServer((args.bind, args.port), view, OwnerAuth(auth_file),
                            origin, local_http=args.local_http, tls=tls)
        worker = threading.Thread(target=view.run, daemon=True)
        worker.start()
        print("Live Home listener started. Owner sign-in required; general-only, read-only. Stop with Ctrl-C.", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            view.stop.set()
            server.server_close()
            worker.join(timeout=30)
    return "Live Home stopped. Agent use is unaffected."

"""Optional local AI for the Helper – runs entirely on this PC.

Two ways to get one:
* GAMbit's own: downloads llama.cpp's llama-server (free, open source) and a small
  instruction model (Qwen2.5 Instruct, Apache-2.0) into GAMbit's app-data folder, once. After
  that it works with no internet. Files can also be copied in from another PC or a USB stick.
* Ollama: if Ollama is already installed and has a model, GAMbit uses it.

Either way GAMbit talks to it on 127.0.0.1 only, and nothing leaves the computer.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

from ..settings import settings

LLAMA_RELEASES = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
MODELS = {
    "standard": {"label": "Standard – best answers (about 2 GB, 8 GB RAM or more)",
                 "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
                 "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/"
                        "qwen2.5-3b-instruct-q4_k_m.gguf", "min_mb": 1500},
    "small": {"label": "Small – faster on older PCs (about 1 GB, 4 GB RAM or more)",
              "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
              "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
                     "qwen2.5-1.5b-instruct-q4_k_m.gguf", "min_mb": 700},
}
IS_WIN = sys.platform.startswith("win")
SERVER_EXE = "llama-server.exe" if IS_WIN else "llama-server"


def folder() -> str:
    from PySide6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.expanduser("~")
    d = os.path.join(base, "local-ai")
    os.makedirs(d, exist_ok=True)
    return d


def enabled() -> bool:
    return bool(settings.get("helper/ai_on", False))


def set_enabled(on: bool):
    settings.set("helper/ai_on", bool(on))


def engine() -> str:
    return settings.get("helper/ai_engine", "builtin") or "builtin"   # builtin | ollama


# ================================================================ files ===
def server_path() -> str:
    custom = settings.get("helper/server_path", "") or ""
    if custom and os.path.isfile(custom):
        return custom
    for dirpath, _d, files in os.walk(os.path.join(folder(), "llama")):
        if SERVER_EXE in files:
            return os.path.join(dirpath, SERVER_EXE)
    return ""


def model_path() -> str:
    custom = settings.get("helper/model_path", "") or ""
    if custom and os.path.isfile(custom):
        return custom
    for m in MODELS.values():
        p = os.path.join(folder(), m["file"])
        if os.path.isfile(p):
            return p
    return ""


def is_gguf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"GGUF"
    except OSError:
        return False


def installed() -> bool:
    if engine() == "ollama":
        return bool(ollama_models())
    return bool(server_path() and model_path())


def status() -> str:
    if engine() == "ollama":
        ms = ollama_models()
        return (f"Using Ollama ({settings.get('helper/ollama_model', '') or ms[0]})" if ms
                else "Ollama isn't running or has no models (try: ollama pull qwen2.5:3b)")
    s, m = server_path(), model_path()
    if s and m:
        return f"Ready – {os.path.basename(m)} ({os.path.getsize(m) // 1_000_000:,} MB)"
    if s:
        return "The AI program is here, but no model yet."
    if m:
        return "The model is here, but not the AI program (llama-server)."
    return "Not installed."


# ============================================================ downloads ===
def _pick_llama_asset(assets: list[dict]) -> dict | None:
    """The CPU build for this OS from a llama.cpp release."""
    names = [a["name"] for a in assets]
    if IS_WIN:
        prefs = ["bin-win-cpu-x64.zip", "bin-win-avx2-x64.zip", "bin-win-noavx-x64.zip"]
    elif sys.platform == "darwin":
        prefs = ["bin-macos-arm64.zip", "bin-macos-x64.zip"]
    else:
        prefs = ["bin-ubuntu-x64.zip"]
    for p in prefs:
        for a in assets:
            if a["name"].endswith(p):
                return a
    return next((a for a in assets if a["name"] in names and "cpu" in a["name"]
                 and a["name"].endswith(".zip")), None)


def download_server(progress=None, log=print) -> str:
    from .. import net
    rel = net.get_json(LLAMA_RELEASES, timeout=30)
    asset = _pick_llama_asset(rel.get("assets", []))
    if not asset:
        raise RuntimeError("Couldn't find a llama.cpp download for this computer.")
    dest = os.path.join(folder(), asset["name"])
    log(f"Downloading {asset['name']} ({asset.get('size', 0) // 1_000_000} MB) …")
    net.download(asset["browser_download_url"], dest, progress)
    out = os.path.join(folder(), "llama")
    os.makedirs(out, exist_ok=True)
    root = os.path.realpath(out)
    with zipfile.ZipFile(dest) as z:
        for n in z.namelist():
            p = os.path.realpath(os.path.join(out, n))
            if os.path.commonpath([root, p]) != root:
                raise RuntimeError(f"Unsafe path in download: {n}")
        z.extractall(out)
    os.remove(dest)
    p = server_path()
    if not p:
        raise RuntimeError("The download didn't contain llama-server.")
    if not IS_WIN:
        os.chmod(p, 0o755)
    log(f"AI program ready ({rel.get('tag_name', '')}).")
    return p


def download_model(which: str = "standard", progress=None, log=print,
                   cancelled=None) -> str:
    from .. import net
    m = MODELS[which]
    dest = os.path.join(folder(), m["file"])
    part = dest + ".part"
    log(f"Downloading the {which} model ({m['file']}) – this is a big file …")
    net.download(m["url"], part, progress, cancelled)
    if os.path.getsize(part) < m["min_mb"] * 1_000_000 or not is_gguf(part):
        os.remove(part)
        raise RuntimeError("The model download was incomplete – try again.")
    os.replace(part, dest)
    log("Model ready.")
    return dest


# ===================================================== llama.cpp server ===
class Server:
    _proc: subprocess.Popen | None = None
    _port = 0
    _lock = threading.Lock()

    @classmethod
    def url(cls) -> str:
        return f"http://127.0.0.1:{cls._port}"

    @classmethod
    def running(cls) -> bool:
        return cls._proc is not None and cls._proc.poll() is None

    @classmethod
    def start(cls, wait: float = 120) -> str:
        with cls._lock:
            if cls.running():
                return cls.url()
            exe, model = server_path(), model_path()
            if not exe or not model:
                raise RuntimeError("The local AI isn't installed yet (Helper → Local AI).")
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                cls._port = s.getsockname()[1]
            threads = max(2, (os.cpu_count() or 4) // 2)
            args = [exe, "-m", model, "--host", "127.0.0.1", "--port", str(cls._port),
                    "-c", "4096", "-t", str(threads), "-ngl", "0"]
            flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
            cls._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                         creationflags=flags, cwd=os.path.dirname(exe))
        end = time.time() + wait
        while time.time() < end:
            if not cls.running():
                raise RuntimeError("The local AI stopped while starting (not enough memory?).")
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(cls.url() + "/health", timeout=2) as r:
                    if r.status == 200:
                        return cls.url()
            except Exception:  # noqa: BLE001 – still loading the model
                pass
            time.sleep(0.7)
        cls.stop()
        raise RuntimeError("The local AI took too long to start.")

    @classmethod
    def stop(cls):
        with cls._lock:
            if cls._proc and cls._proc.poll() is None:
                cls._proc.terminate()
                try:
                    cls._proc.wait(5)
                except subprocess.TimeoutExpired:
                    cls._proc.kill()
            cls._proc = None


# =============================================================== Ollama ===
def ollama_models(base: str = "http://127.0.0.1:11434") -> list[str]:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/api/tags", timeout=1.5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


# ================================================================= chat ===
def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    # local only – never through a proxy
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(messages: list[dict], max_tokens: int = 700, timeout: float = 240) -> str:
    if engine() == "ollama":
        models = ollama_models()
        if not models:
            raise RuntimeError("Ollama isn't running or has no models.")
        model = settings.get("helper/ollama_model", "") or models[0]
        res = _post("http://127.0.0.1:11434/v1/chat/completions",
                    {"model": model, "messages": messages, "temperature": 0.2,
                     "max_tokens": max_tokens, "stream": False}, timeout)
    else:
        base = Server.start()
        res = _post(base + "/v1/chat/completions",
                    {"messages": messages, "temperature": 0.2, "max_tokens": max_tokens,
                     "stream": False}, timeout)
    return (res.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


SYSTEM = """You are GAMbit Helper, an assistant inside GAMbit – a Windows app that gives a
school district's IT staff buttons for GAM (the Google Workspace command-line tool).
Rules:
- Answer in plain, friendly English for non-programmers. Short paragraphs or numbered steps.
- Prefer pointing to the GAMbit page and button that does the job (names are in CONTEXT).
- When a GAM command helps, put each command on its own line inside a ```gam block, WITHOUT
  the word "gam" at the start. Only use command words that appear in CONTEXT or that you are
  sure GAM 7 accepts. Use placeholders like <email> when you don't know a value.
- Never invent GAMbit pages or buttons. If you aren't sure, say so.
- Never ask for or repeat passwords, tokens or keys."""


def answer(question: str, context: str, history: list[dict] | None = None) -> str:
    msgs = [{"role": "system", "content": SYSTEM + "\n\nCONTEXT:\n" + context[:7000]}]
    for h in (history or [])[-4:]:
        msgs.append(h)
    msgs.append({"role": "user", "content": question})
    return chat(msgs)

"""GAMbit Builder – one window to build the exe, the installer, and publish an update.

Run from the project folder:   python builder/gambit_builder.py

Steps (each can be switched on/off):
  0. Get latest     – pull the current files from GitHub (git pull, or a download when the
                      folder isn't a git clone – your own edits are backed up first)
  1. Set version      – writes the new version into gambit/version.py
  2. Build exe        – PyInstaller using GAMbit.spec  ->  dist/GAMbit/GAMbit.exe
  3. Build installer  – Inno Setup (ISCC.exe)          ->  dist/installer/GAMbit-Setup-X.exe
     (optional) code signing of the exe, installer and uninstaller with signtool.exe
  4. Write latest.json
  5. Publish          – (optional) push the source (git, or the GitHub API without git),
                        create a GitHub release, upload the installer, then publish
                        latest.json so every GAMbit sees the update.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gambit.ui.theme import apply_theme  # noqa: E402
import github_sync  # noqa: E402  (builder/github_sync.py)
import signing  # noqa: E402  (builder/signing.py)
import release_key  # noqa: E402  (builder/release_key.py)

VERSION_FILE = os.path.join(ROOT, "gambit", "version.py")
LATEST_JSON = os.path.join(ROOT, "latest.json")
SPEC = os.path.join(ROOT, "GAMbit.spec")
ISS = os.path.join(ROOT, "installer", "GAMbit.iss")
IS_WIN = sys.platform.startswith("win")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
# Use python.exe (not pythonw.exe) for PyInstaller so its output can be captured.
PYTHON = re.sub(r"pythonw(\.exe)?$", lambda m: "python" + (m.group(1) or ""), sys.executable)


# --------------------------------------------------------------- helpers ---
def read_version_info() -> dict:
    text = open(VERSION_FILE, encoding="utf-8").read()
    get = lambda key: (re.search(rf'^{key}\s*=\s*"([^"]*)"', text, re.M) or [None, ""])[1]
    return {"version": get("__version__"), "repo": get("GITHUB_REPO"),
            "branch": get("GITHUB_BRANCH") or "main"}


def write_version(version: str):
    text = open(VERSION_FILE, encoding="utf-8").read()
    text = re.sub(r'^__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"', text, flags=re.M)
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def bump(version: str, part: str) -> str:
    nums = [int(n) for n in re.findall(r"\d+", version)[:3]] + [0, 0, 0]
    major, minor, patch = nums[:3]
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _vt(v: str) -> tuple:
    return tuple(int(n) for n in (re.findall(r"\d+", v or "") + ["0", "0", "0"])[:3])


def is_git_clone() -> bool:
    return os.path.isdir(os.path.join(ROOT, ".git")) and bool(shutil.which("git"))


def find_iscc() -> str:
    candidates = [
        shutil.which("ISCC") or "",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    ]
    return next((c for c in candidates if c and os.path.isfile(c)), "")


def installer_name(version: str) -> str:
    return f"GAMbit-Setup-{version}.exe"


def release_download_url(repo: str, version: str) -> str:
    return f"https://github.com/{repo}/releases/download/v{version}/{installer_name(version)}"


# ---------------------------------------------------------- GitHub API ---

def _seal_token(tok: str) -> str:
    """The GitHub token can publish releases, so it's only kept DPAPI-encrypted for this
    Windows user (never in plain text in the registry)."""
    if not tok:
        return ""
    from gambit import secrets_store
    return secrets_store.seal(tok)


def _open_token(stored: str) -> str:
    from gambit import secrets_store
    if stored and not stored.startswith(secrets_store.PREFIX):
        return stored              # saved in plain text by an older Builder – re-saved sealed
    return secrets_store.unseal(stored) or ""

class GitHub:
    def __init__(self, repo: str, token: str, log):
        self.repo, self.token, self.log = repo, token, log
        self.ctx = ssl.create_default_context()

    def _req(self, method, url, data=None, content_type="application/json"):
        if isinstance(data, (dict, list)):
            data = json.dumps(data).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GAMbit-Builder",
            "Content-Type": content_type,
        })
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=300) as r:
                body = r.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 404 and method == "GET":
                return None
            raise RuntimeError(f"GitHub {method} {url} failed ({e.code}): {detail}") from None

    def api(self, method, path, data=None):
        return self._req(method, f"https://api.github.com/repos/{self.repo}{path}", data)

    def create_release(self, tag, name, notes, branch, prerelease=False):
        existing = self.api("GET", f"/releases/tags/{tag}")
        if existing:
            self.log(f"Release {tag} already exists – reusing it.")
            if existing.get("prerelease") and not prerelease:
                self.log("Promoting it from beta to a normal release.")
                existing = self.api("PATCH", f"/releases/{existing['id']}",
                                    {"prerelease": False}) or existing
            return existing
        self.log(f"Creating GitHub release {tag} …")
        return self.api("POST", "/releases", {
            "tag_name": tag, "target_commitish": branch, "name": name,
            "body": notes, "draft": False, "prerelease": prerelease})

    def upload_asset(self, release, path):
        name = os.path.basename(path)
        for asset in release.get("assets", []):
            if asset["name"] == name:
                self.log(f"Replacing existing asset {name} …")
                self.api("DELETE", f"/releases/assets/{asset['id']}")
        url = release["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(name)
        size = os.path.getsize(path) / 1e6
        self.log(f"Uploading {name} ({size:.1f} MB) – this can take a minute …")
        with open(path, "rb") as fh:
            asset = self._req("POST", url, fh.read(), "application/octet-stream")
        self.log(f"Uploaded: {asset.get('browser_download_url')}")
        return asset

    def put_file(self, repo_path, content: bytes, message, branch):
        current = self.api("GET", f"/contents/{repo_path}?ref={branch}")
        data = {"message": message, "branch": branch,
                "content": base64.b64encode(content).decode()}
        if current and "sha" in current:
            data["sha"] = current["sha"]
        self.log(f"Publishing {repo_path} to {self.repo}@{branch} …")
        return self.api("PUT", f"/contents/{repo_path}", data)


# ---------------------------------------------------------- build job ----
class BuildJob(QObject):
    log = Signal(str, str)  # text, color
    finished = Signal(bool, str)

    def __init__(self, opts: dict):
        super().__init__()
        self.o = opts
        self._proc = None
        self._cancel = False

    def cancel(self):
        self._cancel = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def say(self, text, color=""):
        self.log.emit(text, color)

    def step(self, title):
        if self._cancel:
            raise RuntimeError("Cancelled")
        self.say(f"\n=== {title} ===", "#7cc4ff")

    def sh(self, args, cwd=ROOT, check=True, show=None):
        self.say("> " + " ".join(f'"{a}"' if " " in a else a for a in (show or args)),
                 "#9aa4ae")
        self._proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True,
                                      encoding="utf-8", errors="replace",
                                      creationflags=NO_WINDOW)
        out = []
        for line in self._proc.stdout:
            line = line.rstrip()
            out.append(line)
            self.say(line)
        code = self._proc.wait()
        if check and code != 0:
            raise RuntimeError(f"Command failed with exit code {code}")
        return code, "\n".join(out)

    def _signing(self) -> bool:
        return self.o.get("sign", {}).get("mode", "off") != "off"

    def _signtool(self) -> str:
        tool = self.o["sign"].get("signtool") or signing.find_signtool()
        if not tool or not os.path.isfile(tool):
            raise RuntimeError("signtool.exe not found. Install the Windows SDK "
                               "(Signing Tools for Desktop Apps) or set its path.")
        return tool

    def sign(self, path):
        args = [self._signtool(), *signing.sign_args(self.o["sign"]), path]
        self.sh(args, show=signing.masked(args))
        self.sh([self._signtool(), "verify", "/pa", path])
        self.say(f"Signed {os.path.basename(path)}", "#7ee787")

    def run(self):
        try:
            self._run()
            self.finished.emit(True, "All done!")
        except github_sync.Conflict as exc:
            self.conflict_files = exc.files
            self.say(f"\n✖ {exc}", "#ff8a80")
            self.finished.emit(False, "CONFLICT")
        except Exception as exc:  # noqa: BLE001
            self.say(f"\n✖ {exc}", "#ff8a80")
            self.finished.emit(False, str(exc))

    def _remote_has_commits(self) -> bool:
        try:
            return bool(github_sync.Api(self.o["repo"], self.o.get("token", ""),
                                        self.say).head(self.o["branch"]))
        except Exception:  # noqa: BLE001 – let git report its own problem
            return True

    def pull_latest(self):
        o = self.o
        repo, branch = o["repo"], o["branch"]
        if is_git_clone() and o.get("sync_mode", "auto") != "download" and \
                self._remote_has_commits():
            self.step(f"0. Get the latest files from GitHub (git pull {branch})")
            self.sh(["git", "fetch", "origin", branch])
            code, out = self.sh(["git", "pull", "--ff-only", "--autostash", "origin", branch],
                                check=False)
            if code != 0:
                raise RuntimeError("git couldn't update this folder automatically (your "
                                   "changes and GitHub's overlap). Sort it out with git, then "
                                   "build again.")
        else:
            self.step(f"0. Get the latest files from GitHub ({repo}@{branch})")
            api = github_sync.Api(repo, o.get("token", ""), self.say)
            plan = github_sync.pull(ROOT, api, branch, log=self.say,
                                    conflicts=o.get("conflicts", "stop"))
            for rel in plan["applied"][:40]:
                self.say(f"  updated {rel}")
            if len(plan["applied"]) > 40:
                self.say(f"  …and {len(plan['applied']) - 40} more")
            for rel in plan["delete"]:
                self.say(f"  removed {rel}")
            for rel in plan["keep_local"][:20]:
                self.say(f"  kept your version of {rel}")
        self.say("This folder now has GitHub's latest files.", "#7ee787")

    def _run(self):
        o = self.o
        ver, repo, branch = o["version"], o["repo"], o["branch"]
        installer = os.path.join(ROOT, "dist", "installer", installer_name(ver))

        if o.get("pull_first") or o.get("only_pull"):
            self.pull_latest()
            if o.get("only_pull"):
                return
            pulled = read_version_info()["version"]
            if _vt(ver) <= _vt(pulled):
                raise RuntimeError(f"GitHub's code is already at version {pulled}. Choose a "
                                   f"higher version than {pulled} and build again.")

        if o.get("run_tests"):
            self.step("0. Run the automated tests")
            code, _out = self.sh([PYTHON, "-m", "pytest", "-q"], check=False)
            if code != 0:
                raise RuntimeError("Some tests failed – nothing was built. Fix them (or untick "
                                   "“Run the tests first”) and build again.")
            self.say("All tests passed.", "#7ee787")

        self.step(f"1. Set version to {ver}")
        write_version(ver)
        self.say("gambit/version.py updated.")
        rel_priv, rel_pub = release_key.load_or_create()
        release_key.write_keys_module(rel_pub, o["sign"].get("thumbprint", "")
                                      if self._signing() and o["sign"].get("mode") == "store"
                                      else "")
        self.say("Release key " + release_key.fingerprint() + " written to "
                 "gambit/release_keys.py (installed copies only accept updates it signs). "
                 f"Keep a backup of {release_key.key_path()}.")

        if o["build_exe"]:
            self.step("2. Build exe with PyInstaller")
            self.sh([PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean", SPEC])
            self.say("Built dist/GAMbit/GAMbit.exe", "#7ee787")
            if self._signing():
                self.step("2b. Sign GAMbit.exe")
                self.sign(os.path.join(ROOT, "dist", "GAMbit", "GAMbit.exe"))

        if o["build_installer"]:
            self.step("3. Build installer with Inno Setup")
            if not o["iscc"] or not os.path.isfile(o["iscc"]):
                raise RuntimeError("ISCC.exe not found. Install Inno Setup 6 or set its path.")
            if not os.path.isdir(os.path.join(ROOT, "dist", "GAMbit")):
                raise RuntimeError("dist/GAMbit is missing – build the exe first.")
            cmd = [o["iscc"], f"/DMyAppVersion={ver}"]
            show = list(cmd)
            if self._signing():
                switch = signing.inno_sign_switch(self._signtool(), o["sign"])
                cmd += ["/DSIGN=1", switch]
                show += ["/DSIGN=1", signing.inno_sign_switch(
                    self._signtool(), {**o["sign"], "password": "********"})
                    if o["sign"].get("password") else switch]
            self.sh(cmd + [ISS], show=show + [ISS])
            self.say(f"Built {installer}", "#7ee787")
            if self._signing():
                self.step("3b. Check the installer's signature")
                self.sh([self._signtool(), "verify", "/pa", installer])

        beta = o.get("channel") == "beta"
        json_name = "latest-beta.json" if beta else "latest.json"
        json_path = os.path.join(ROOT, json_name)
        self.step(f"4. Write {json_name}" + (" (beta testers only)" if beta else ""))
        latest = {"version": ver, "url": release_download_url(repo, ver),
                  "notes": o["notes"],
                  "released": datetime.date.today().isoformat()}
        if os.path.isfile(installer):
            latest = release_key.signed_release(latest, installer, rel_priv)
        else:
            self.say("No installer was built, so latest.json has no checksum or signature – "
                     "installed copies won't take this update automatically.", "#f2cc60")
        latest_bytes = (json.dumps(latest, indent=2) + "\n").encode()
        release_json = os.path.join(ROOT, "dist", "release.json")
        os.makedirs(os.path.dirname(release_json), exist_ok=True)
        with open(release_json, "wb") as fh:
            fh.write(latest_bytes)          # also attached to the release (for rollbacks)
        with open(json_path, "wb") as fh:
            fh.write(latest_bytes)
        self.say(json.dumps(latest, indent=2))

        if not o["publish"]:
            self.say("\nPublishing is off – nothing was sent to GitHub.", "#f2cc60")
            return

        if not os.path.isfile(installer):
            raise RuntimeError(f"Installer not found: {installer}")
        if not o["token"]:
            raise RuntimeError("A GitHub token is needed to publish.")
        gh = GitHub(repo, o["token"], self.say)
        msg = f"GAMbit v{ver}"

        target = branch
        if o["use_git"] and not is_git_clone():
            self.say("This folder isn't a git clone, so the source code is uploaded with the "
                     "GitHub API instead of git.", "#f2cc60")
            o["use_git"], o["push_source"] = False, True
        if o["use_git"]:
            self.step("5a. Commit and push source code (git)")
            self.sh(["git", "add", "-A"])
            self.sh(["git", "reset", "-q", "--", json_name], check=False)
            code, _ = self.sh(["git", "commit", "-m", f"Release v{ver}"], check=False)
            if code != 0:
                self.say("(nothing new to commit)")
            self.sh(["git", "push", "origin", f"HEAD:{branch}"])
        elif o.get("push_source"):
            self.step("5a. Upload source code changes (GitHub API, no git needed)")
            api = github_sync.Api(repo, o["token"], self.say)
            sha = github_sync.push(ROOT, api, branch, f"Release v{ver}", log=self.say,
                                   exclude=(json_name,))
            if sha:
                target = sha            # the release points at exactly what was built

        if not o["use_git"] and not o.get("push_source") and \
                not github_sync.Api(repo, o["token"], self.say).head(branch):
            raise RuntimeError(f"{repo} is still empty, so there's nothing to attach a release "
                               "to. Choose “Upload my source code changes and latest.json with "
                               "the GitHub API” and publish again.")
        self.step("5b. Create GitHub release and upload installer")
        release = gh.create_release(f"v{ver}", msg + (" (beta)" if beta else ""), o["notes"],
                                    target, prerelease=beta)
        gh.upload_asset(release, installer)
        gh.upload_asset(release, release_json)

        # latest.json goes last, so clients never see an update before the file exists.
        self.step(f"5c. Publish {json_name}")
        if o["use_git"]:
            self.sh(["git", "add", json_name])
            self.sh(["git", "commit", "-m", f"{json_name} -> v{ver}"], check=False)
            self.sh(["git", "push", "origin", f"HEAD:{branch}"])
        else:
            res = gh.put_file(json_name, latest_bytes, f"{json_name} -> v{ver}", branch) or {}
            if os.path.isfile(os.path.join(ROOT, github_sync.MANIFEST)):
                github_sync.note_remote_file(ROOT, json_name, latest_bytes,
                                             (res.get("commit") or {}).get("sha", ""))
        self.say(f"\n✔ GAMbit {ver} is live. Installed copies will offer the update "
                 "the next time they check (GitHub can take ~5 minutes to refresh).",
                 "#7ee787")


# --------------------------------------------------------------- window ---
class BuilderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GAMbit Builder")
        icon = os.path.join(ROOT, "assets", "gambit.ico")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.resize(980, 900)
        self.store = QSettings("GAMbit", "GAMbitBuilder")
        info = read_version_info()
        self.thread = None

        page = QWidget(objectName="Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 16, 22, 14)
        lay.addWidget(QLabel("GAMbit Builder", objectName="PageTitle"))
        sub = QLabel(f"Project: {ROOT}", objectName="PageSub")
        sub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(sub)

        # version
        box = QGroupBox("Release")
        form = QFormLayout(box)
        self.current = info["version"]
        self.version = QLineEdit(bump(self.current, "patch"))
        bumps = QHBoxLayout()
        bumps.addWidget(self.version)
        for part in ("patch", "minor", "major"):
            b = QPushButton(f"+ {part}")
            b.clicked.connect(lambda _=False, p=part: self.version.setText(bump(self.current, p)))
            bumps.addWidget(b)
        form.addRow(f"New version (current {self.current})", bumps)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("What's new in this version? (shown to users in the "
                                      "update prompt and on the GitHub release)")
        self.notes.setFixedHeight(90)
        form.addRow("Release notes", self.notes)
        lay.addWidget(box)

        # get latest
        box = QGroupBox("Get the latest code from GitHub")
        form = QFormLayout(box)
        self.pull_first = QCheckBox("Before building, get the latest files from GitHub")
        self.pull_first.setChecked(self.store.value("pull_first", "true") == "true")
        self.sync_state = QLabel("", objectName="Muted")
        self.sync_state.setWordWrap(True)
        pull_now = QPushButton("Get latest now")
        pull_now.clicked.connect(self.pull_now)
        prow = QHBoxLayout()
        prow.addWidget(self.pull_first)
        prow.addStretch(1)
        prow.addWidget(pull_now)
        form.addRow(prow)
        form.addRow(self.sync_state)
        lay.addWidget(box)

        # build
        box = QGroupBox("Build")
        form = QFormLayout(box)
        self.build_exe = QCheckBox("Build GAMbit.exe with PyInstaller")
        self.build_exe.setChecked(True)
        self.build_inst = QCheckBox("Build the installer with Inno Setup")
        self.build_inst.setChecked(True)
        self.iscc = QLineEdit(self.store.value("iscc", "") or find_iscc())
        self.iscc.setPlaceholderText("Path to ISCC.exe (Inno Setup 6)")
        pick = QPushButton("Browse…")
        pick.clicked.connect(self._pick_iscc)
        row = QHBoxLayout()
        row.addWidget(self.iscc)
        row.addWidget(pick)
        get_inno = QPushButton("Get Inno Setup")
        get_inno.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://jrsoftware.org/isdl.php")))
        row.addWidget(get_inno)
        self.run_tests = QCheckBox("Run the tests first (stop if any fail)")
        self.run_tests.setChecked(self.store.value("run_tests", "true") == "true")
        form.addRow(self.run_tests)
        form.addRow(self.build_exe)
        form.addRow(self.build_inst)
        form.addRow("Inno Setup compiler", row)
        lay.addWidget(box)

        # signing
        box = QGroupBox("Code signing (stops the Windows “unknown publisher” warning)")
        form = QFormLayout(box)
        self.sign_mode = QComboBox()
        for label, val in (("Don't sign", "off"), ("Certificate file (.pfx)", "pfx"),
                           ("Certificate in Windows store / USB token (EV)", "store"),
                           ("Azure Trusted Signing", "azure")):
            self.sign_mode.addItem(label, val)
        st = self.store
        self.sign_mode.setCurrentIndex(max(0, self.sign_mode.findData(
            st.value("sign/mode", "off"))))
        self.signtool = QLineEdit(st.value("sign/signtool", "") or signing.find_signtool())
        self.signtool.setPlaceholderText("Path to signtool.exe (Windows SDK)")
        self.pfx = QLineEdit(st.value("sign/pfx", ""))
        self.pfx_pw = QLineEdit()
        self.pfx_pw.setEchoMode(QLineEdit.Password)
        self.pfx_pw.setPlaceholderText("Certificate password (not saved)")
        self.thumb = QLineEdit(st.value("sign/thumbprint", ""))
        self.thumb.setPlaceholderText("SHA-1 thumbprint, 40 characters")
        self.dlib = QLineEdit(st.value("sign/dlib", ""))
        self.dlib.setPlaceholderText("…\\bin\\x64\\Azure.CodeSigning.Dlib.dll")
        self.metadata = QLineEdit(st.value("sign/metadata", ""))
        self.metadata.setPlaceholderText("metadata.json (Endpoint, CodeSigningAccountName, "
                                         "CertificateProfileName)")
        self.ts_url = QLineEdit(st.value("sign/timestamp", ""))
        self.ts_url.setPlaceholderText("Timestamp server – blank uses the usual one")
        form.addRow("Sign with", self.sign_mode)
        self._sign_rows = {}

        def add(label, w, modes, browse=None):
            row = QHBoxLayout()
            row.addWidget(w)
            if browse:
                b = QPushButton("Browse…")
                b.clicked.connect(lambda: self._browse_into(w, browse))
                row.addWidget(b)
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            form.addRow(label, holder)
            self._sign_rows[holder] = (modes, form.labelForField(holder))
        add("signtool.exe", self.signtool, ("pfx", "store", "azure"),
            "signtool.exe (signtool.exe)")
        add("Certificate file", self.pfx, ("pfx",), "Certificates (*.pfx *.p12)")
        add("Password", self.pfx_pw, ("pfx",))
        add("Thumbprint", self.thumb, ("store",))
        add("Dlib", self.dlib, ("azure",), "Azure.CodeSigning.Dlib.dll (*.dll)")
        add("Metadata", self.metadata, ("azure",), "metadata.json (*.json)")
        add("Timestamp", self.ts_url, ("pfx", "store", "azure"))
        help_lbl = QLabel("Signs GAMbit.exe, the installer and the uninstaller. "
                          "<a href='https://learn.microsoft.com/azure/trusted-signing/'>"
                          "Azure Trusted Signing</a> is usually the cheapest option; an OV or "
                          "EV certificate from a certificate authority works too.")
        help_lbl.setOpenExternalLinks(True)
        help_lbl.setWordWrap(True)
        form.addRow("", help_lbl)
        self.sign_mode.currentIndexChanged.connect(self._sign_visibility)
        self._sign_visibility()
        lay.addWidget(box)

        # publish
        box = QGroupBox("Publish update to GitHub")
        form = QFormLayout(box)
        self.publish = QCheckBox("Publish this version (release + latest.json)")
        self.publish.setChecked(self.store.value("publish", "false") == "true")
        self.repo = QLineEdit(info["repo"])
        self.branch = QLineEdit(info["branch"])
        self.token = QLineEdit(_open_token(self.store.value("token", "") or "")
                               or os.environ.get("GITHUB_TOKEN", ""))
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("Fine-grained token with Contents: Read and write")
        self.remember = QCheckBox("Remember token on this PC")
        self.remember.setChecked(bool(self.store.value("token", "")))
        self.via_src = QRadioButton("Upload my source code changes and latest.json with the "
                                    "GitHub API (no git needed)")
        self.via_api = QRadioButton("Upload only latest.json with the GitHub API (I push the "
                                    "code myself)")
        self.via_git = QRadioButton("Commit && push my source code with git, then latest.json")
        how = self.store.value("publish_how", "") or (
            "git" if self.store.value("use_git", "false") == "true" else "source")
        {"git": self.via_git, "json": self.via_api}.get(how, self.via_src).setChecked(True)
        form.addRow(self.publish)
        self.ch_stable = QRadioButton("Everyone (latest.json)")
        self.ch_beta = QRadioButton("Beta testers only (latest-beta.json, GitHub pre-release)")
        (self.ch_beta if self.store.value("channel", "stable") == "beta"
         else self.ch_stable).setChecked(True)
        chrow = QHBoxLayout()
        chrow.addWidget(self.ch_stable)
        chrow.addWidget(self.ch_beta)
        chrow.addStretch(1)
        form.addRow("Release to", chrow)
        form.addRow("Repository", self.repo)
        form.addRow("Branch", self.branch)
        trow = QHBoxLayout()
        trow.addWidget(self.token)
        trow.addWidget(self.remember)
        form.addRow("GitHub token", trow)
        form.addRow("", self.via_src)
        form.addRow("", self.via_api)
        form.addRow("", self.via_git)
        lay.addWidget(box)

        # actions
        actions = QHBoxLayout()
        self.go_btn = QPushButton("Build")
        self.go_btn.setProperty("kind", "primary")
        self.go_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("kind", "danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        for text, slot in (("Open dist folder", self._open_dist),
                           ("Check live latest.json", self._check_live)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch(1)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.go_btn)
        self.publish.toggled.connect(self._label)
        self._label()
        self._show_sync_state()

        self.log = QPlainTextEdit(objectName="Log")
        self.log.setReadOnly(True)

        top = QWidget()
        top.setLayout(lay)
        lay.addLayout(actions)
        split = QSplitter(Qt.Vertical)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        top.setObjectName("Page")
        scroll.setWidget(top)
        split.addWidget(scroll)
        split.addWidget(self.log)
        split.setSizes([600, 220])
        self.setCentralWidget(split)

    # ----------------------------------------------------------------
    def _show_sync_state(self):
        if is_git_clone():
            self.sync_state.setText("This folder is a git clone – “Get latest” runs "
                                    "git pull (your uncommitted changes are kept).")
            return
        m = github_sync.load_manifest(ROOT)
        if m.get("commit"):
            self.sync_state.setText(f"Last synced with GitHub: commit {m['commit'][:7]} on "
                                    f"{m.get('when', '')[:16].replace('T', ' ')}. Files you "
                                    "change here are kept; if GitHub changed the same file you choose which "
                                    "to keep.")
        else:
            self.sync_state.setText("Not synced with GitHub yet. The first “Get latest” "
                                    "downloads GitHub's files; where a file here differs, "
                                    "you choose which version to keep (yours is backed up "
                                    f"to {github_sync.BACKUP_DIR}/ either way).")

    def pull_now(self):
        self.start(only_pull=True)

    def _label(self):
        self.go_btn.setText("Build && Publish" if self.publish.isChecked() else "Build")

    def _sign_visibility(self, *_):
        mode = self.sign_mode.currentData()
        for holder, (modes, lbl) in self._sign_rows.items():
            holder.setVisible(mode in modes)
            if lbl:
                lbl.setVisible(mode in modes)

    def _browse_into(self, edit, filt):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file", edit.text(),
                                              f"{filt};;All files (*)")
        if path:
            edit.setText(os.path.normpath(path))

    def sign_opts(self) -> dict:
        return dict(mode=self.sign_mode.currentData(), signtool=self.signtool.text().strip(),
                    pfx=self.pfx.text().strip(), password=self.pfx_pw.text(),
                    thumbprint=self.thumb.text().strip(), dlib=self.dlib.text().strip(),
                    metadata=self.metadata.text().strip(), timestamp=self.ts_url.text().strip(),
                    description="GAMbit")

    def _pick_iscc(self):
        path, _ = QFileDialog.getOpenFileName(self, "Find ISCC.exe", self.iscc.text(),
                                              "ISCC.exe (ISCC.exe);;All files (*)")
        if path:
            self.iscc.setText(os.path.normpath(path))

    def _open_dist(self):
        d = os.path.join(ROOT, "dist")
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _check_live(self):
        url = (f"https://raw.githubusercontent.com/{self.repo.text().strip()}/"
               f"{self.branch.text().strip()}/latest.json")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GAMbit-Builder",
                                                       "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode()
            QMessageBox.information(self, "Live latest.json", f"{url}\n\n{text}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Live latest.json", f"{url}\n\n{exc}")

    def append(self, text, color=""):
        cur = self.log.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        cur.insertText(text + "\n", fmt)
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def start(self, only_pull=False, conflicts="stop"):
        if self.thread and self.thread.isRunning():
            return
        ver = self.version.text().strip()
        if not only_pull and not re.fullmatch(r"\d+\.\d+\.\d+", ver):
            QMessageBox.warning(self, "Version", "Use a version like 1.2.3")
            return
        if self.publish.isChecked() and not only_pull:
            if not self.token.text().strip():
                QMessageBox.warning(self, "GitHub token", "Enter a GitHub token to publish.")
                return
            if not self.notes.toPlainText().strip():
                if QMessageBox.question(self, "No release notes",
                                        "Publish without release notes?") != QMessageBox.Yes:
                    return
            if QMessageBox.question(
                    self, "Publish?",
                    f"Publish GAMbit {ver} to {self.repo.text()}?\n\n" +
                    ("Only PCs set to the Beta update channel will be offered it."
                     if self.ch_beta.isChecked() else
                     "Every installed copy will be offered this update.")) != QMessageBox.Yes:
                return
        self._save_prefs()
        opts = dict(version=ver, notes=self.notes.toPlainText().strip(),
                    build_exe=self.build_exe.isChecked(),
                    build_installer=self.build_inst.isChecked(),
                    iscc=self.iscc.text().strip(), publish=self.publish.isChecked(),
                    repo=self.repo.text().strip(), branch=self.branch.text().strip() or "main",
                    token=self.token.text().strip(), use_git=self.via_git.isChecked(),
                    push_source=self.via_src.isChecked(), only_pull=only_pull,
                    conflicts=conflicts,
                    pull_first=self.pull_first.isChecked(),
                    sign=self.sign_opts(), run_tests=self.run_tests.isChecked(),
                    channel="beta" if self.ch_beta.isChecked() else "stable")
        if opts["sign"]["mode"] != "off" and not only_pull:
            try:
                signing.sign_args(opts["sign"])
            except RuntimeError as exc:
                QMessageBox.warning(self, "Code signing", str(exc))
                return
        self.log.clear()
        self.job = BuildJob(opts)
        self.thread = QThread()
        self.job.moveToThread(self.thread)
        self.thread.started.connect(self.job.run)
        self.job.log.connect(self.append)
        self.job.finished.connect(self._done)
        self.job.finished.connect(self.thread.quit)
        self.go_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.thread.start()

    def cancel(self):
        if self.thread and self.thread.isRunning():
            self.job.cancel()

    def _done(self, ok, msg):
        self.go_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.current = read_version_info()["version"]
        self._show_sync_state()
        if ok and self.job.o.get("only_pull"):
            # the pulled version.py may be newer – offer the next version after it
            if re.fullmatch(r"\d+\.\d+\.\d+", self.current):
                self.version.setText(bump(self.current, "patch"))
            QMessageBox.information(self, "Builder", "This folder now has GitHub's latest "
                                    "files. Restart the Builder if the Builder itself was "
                                    "updated.")
            return
        if not ok and "already at version" in msg and \
                re.fullmatch(r"\d+\.\d+\.\d+", self.current):
            self.version.setText(bump(self.current, "patch"))
            msg += f"\n\nThe version box now says {self.version.text()} – click Build again."
        if not ok and msg == "CONFLICT":
            self._resolve(getattr(self.job, "conflict_files", []))
            return
        if ok:
            QMessageBox.information(self, "Builder", msg)
        else:
            QMessageBox.warning(self, "Builder", f"The build stopped:\n\n{msg}")

    def _resolve(self, files: list[str]):
        mb = QMessageBox(self)
        mb.setWindowTitle("Changed in both places")
        mb.setText(f"{len(files)} file(s) were changed both in this folder and on GitHub:\n\n"
                   + "\n".join(files[:15]) + ("\n…" if len(files) > 15 else "") +
                   "\n\nWhich version should this folder keep?")
        theirs = mb.addButton("Use GitHub's (back up mine)", QMessageBox.AcceptRole)
        mine = mb.addButton("Keep mine (upload them next publish)", QMessageBox.ActionRole)
        mb.addButton(QMessageBox.Cancel)
        mb.exec()
        choice = {theirs: "theirs", mine: "mine"}.get(mb.clickedButton())
        if choice:
            self.start(only_pull=True, conflicts=choice)

    def _save_prefs(self):
        self.store.setValue("iscc", self.iscc.text().strip())
        self.store.setValue("run_tests", "true" if self.run_tests.isChecked() else "false")
        self.store.setValue("channel", "beta" if self.ch_beta.isChecked() else "stable")
        so = self.sign_opts()
        for k in ("mode", "signtool", "pfx", "thumbprint", "dlib", "metadata", "timestamp"):
            self.store.setValue(f"sign/{k}", so[k])
        self.store.setValue("publish", "true" if self.publish.isChecked() else "false")
        self.store.setValue("use_git", "true" if self.via_git.isChecked() else "false")
        self.store.setValue("publish_how", "git" if self.via_git.isChecked() else
                            "json" if self.via_api.isChecked() else "source")
        self.store.setValue("pull_first", "true" if self.pull_first.isChecked() else "false")
        self.store.setValue("token", _seal_token(self.token.text().strip())
                            if self.remember.isChecked() else "")

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            if QMessageBox.question(self, "Builder", "A build is running. Cancel it and quit?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.job.cancel()
            self.thread.quit()
            self.thread.wait(5000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    w = BuilderWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

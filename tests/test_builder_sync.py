"""Builder: get the latest files from GitHub and upload source changes, without git."""

import base64
import hashlib
import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "builder"))
import github_sync as gs  # noqa: E402


class FakeGitHub:
    """Just enough of the GitHub REST API, in memory."""

    def __init__(self, files: dict[str, bytes]):
        self.commits = {}        # sha -> {files, parent}
        self.head = self._commit(dict(files), None) if files else ""
        self.blobs, self.trees = {}, {}

    def _commit(self, files, parent):
        sha = hashlib.sha1(json.dumps({k: v.decode() for k, v in sorted(files.items())},
                                      sort_keys=True).encode() + str(parent).encode()).hexdigest()
        self.commits[sha] = {"files": files, "parent": parent}
        return sha

    def edit(self, path, data):       # someone else pushes
        files = dict(self.commits[self.head]["files"])
        if data is None:
            files.pop(path, None)
        else:
            files[path] = data
        self.head = self._commit(files, self.head)

    def opener(self, req):
        url, method = req.full_url, req.get_method()
        body = json.loads(req.data) if req.data else None
        path = url.split("/repos/o/r", 1)[1]
        if not self.head and not (method == "PUT" and path.startswith("/contents/")):
            import urllib.error
            raise urllib.error.HTTPError(url, 409, "Conflict", {}, io.BytesIO(
                b'{"message":"Git Repository is empty.","status":"409"}'))
        if method == "PUT" and path.startswith("/contents/"):
            files = dict(self.commits[self.head]["files"]) if self.head else {}
            files[path.split("/contents/", 1)[1]] = base64.b64decode(body["content"])
            self.head = self._commit(files, self.head or None)
            return _Resp(json.dumps({"commit": {"sha": self.head}}).encode())
        if method == "GET" and path.startswith("/commits/"):
            out = {"sha": self.head}
        elif method == "GET" and path.startswith("/zipball/"):
            sha = path.split("/")[-1]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for p, d in self.commits[sha]["files"].items():
                    z.writestr(f"o-r-{sha[:7]}/{p}", d)
            return _Resp(buf.getvalue())
        elif method == "GET" and path.startswith("/git/commits/"):
            out = {"tree": {"sha": "tree-" + path.split("/")[-1]}}
        elif method == "POST" and path == "/git/blobs":
            data = base64.b64decode(body["content"])
            sha = hashlib.sha1(data).hexdigest()
            self.blobs[sha] = data
            out = {"sha": sha}
        elif method == "POST" and path == "/git/trees":
            base = self.commits[body["base_tree"][5:]]["files"]
            files = dict(base)
            for e in body["tree"]:
                if e["sha"] is None:
                    files.pop(e["path"], None)
                else:
                    files[e["path"]] = self.blobs[e["sha"]]
            sha = "t" + hashlib.sha1(os.urandom(8)).hexdigest()
            self.trees[sha] = files
            out = {"sha": sha}
        elif method == "POST" and path == "/git/commits":
            assert body["parents"] == [self.head]
            out = {"sha": self._commit(self.trees[body["tree"]], self.head)}
            self._pending = out["sha"]
        elif method == "PATCH" and path.startswith("/git/refs/heads/"):
            self.head = body["sha"]
            out = {}
        else:
            raise AssertionError(f"unexpected {method} {path}")
        return _Resp(json.dumps(out).encode())

    def files(self):
        return self.commits[self.head]["files"]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _api(fake):
    return gs.Api("o/r", "tok", lambda *_a: None, opener=fake.opener)


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def test_first_pull_into_empty_folder(tmp_path):
    fake = FakeGitHub({"main.py": b"v1", "gambit/a.py": b"A", ".gitignore": b"dist/\n"})
    root = str(tmp_path)
    plan = gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    assert sorted(plan["applied"]) == [".gitignore", "gambit/a.py", "main.py"]
    assert _read(root, "gambit/a.py") == "A"
    assert gs.load_manifest(root)["commit"] == fake.head


def test_three_way_pull_and_conflicts(tmp_path):
    fake = FakeGitHub({"a.py": b"A1", "b.py": b"B1", "c.py": b"C1", "gone.py": b"G"})
    root = str(tmp_path)
    gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    _write(root, "b.py", "B-mine")              # changed here only
    _write(root, "c.py", "C-mine")              # changed in both places
    _write(root, "dist/GAMbit.exe", "x")        # ignored build output
    fake.edit("a.py", b"A2")                    # changed on GitHub only
    fake.edit("c.py", b"C2")
    fake.edit("gone.py", None)                  # deleted on GitHub
    fake.edit("new.py", b"N")
    with pytest.raises(gs.Conflict) as e:
        gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    assert e.value.files == ["c.py"]
    assert _read(root, "a.py") == "A1"          # nothing touched when stopping
    plan = gs.pull(root, _api(fake), "main", log=lambda *_a: None, conflicts="theirs")
    assert _read(root, "a.py") == "A2" and _read(root, "b.py") == "B-mine"
    assert _read(root, "c.py") == "C2" and _read(root, "new.py") == "N"
    assert not os.path.exists(os.path.join(root, "gone.py"))
    backups = os.listdir(os.path.join(root, gs.BACKUP_DIR))
    assert open(os.path.join(root, gs.BACKUP_DIR, backups[0], "c.py")).read() == "C-mine"
    assert "b.py" in plan["keep_local"]


def test_keep_mine_then_push(tmp_path):
    fake = FakeGitHub({"a.py": b"A1", "latest.json": b"{}"})
    root = str(tmp_path)
    gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    _write(root, "a.py", "A-mine")
    fake.edit("a.py", b"A-theirs")
    gs.pull(root, _api(fake), "main", log=lambda *_a: None, conflicts="mine")
    assert _read(root, "a.py") == "A-mine"
    _write(root, "gambit/version.py", '__version__ = "1.0.1"')
    _write(root, "latest.json", '{"version": "1.0.1"}')
    _write(root, "__pycache__/x.pyc", "junk")
    sha = gs.push(root, _api(fake), "main", "Release v1.0.1", log=lambda *_a: None,
                  exclude=("latest.json",))
    assert sha == fake.head
    f = fake.files()
    assert f["a.py"] == b"A-mine" and f["gambit/version.py"].startswith(b"__version__")
    assert f["latest.json"] == b"{}"            # left for the end of the release
    assert "__pycache__/x.pyc" not in f
    # latest.json uploaded separately later: baseline follows without a false change
    gs.note_remote_file(root, "latest.json", b'{"version": "1.0.1"}', sha)
    assert gs.push_plan(gs.local_files(root), gs.load_manifest(root)["files"]) == \
        {"add": [], "change": [], "delete": []}


def test_push_refuses_when_github_moved(tmp_path):
    fake = FakeGitHub({"a.py": b"A1"})
    root = str(tmp_path)
    gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    _write(root, "a.py", "mine")
    fake.edit("b.py", b"someone else")
    with pytest.raises(RuntimeError, match="since your last pull"):
        gs.push(root, _api(fake), "main", "x", log=lambda *_a: None)
    with pytest.raises(RuntimeError, match="latest files from GitHub first"):
        gs.push(str(tmp_path / "other"), _api(fake), "main", "x")


def test_ignore_rules():
    pats = gs.ALWAYS_SKIP + ["build/", "*.spec.bak"]
    assert gs.ignored("build/x/y.txt", pats) and gs.ignored("gambit/__pycache__/a.pyc", pats)
    assert not gs.ignored("builder/gambit_builder.py", pats)
    assert gs.ignored("GAMbit.spec.bak", pats) and gs.ignored(".builder_sync.json", pats)
    assert not gs.ignored("GAMbit.spec", pats)


def test_zip_paths_are_safe():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("o-r-1/ok.py", "x")
        z.writestr("o-r-1/../evil.py", "x")
    assert list(gs.remote_files(buf.getvalue())) == ["ok.py"]


def test_version_compare():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gb", os.path.join(os.path.dirname(gs.__file__), "gambit_builder.py"))
    gb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gb)
    assert gb._vt("1.0.10") > gb._vt("1.0.9") and gb._vt("2.0.0") > gb._vt("1.9.9")


def test_empty_repository_first_publish(tmp_path):
    """An empty GitHub repo: pulling finds nothing, and the first push uploads everything."""
    fake = FakeGitHub({})
    root = str(tmp_path)
    _write(root, ".gitignore", "dist/\n")
    _write(root, "main.py", "print(1)")
    _write(root, "gambit/version.py", '__version__ = "1.0.1"')
    _write(root, "latest.json", "{}")
    plan = gs.pull(root, _api(fake), "main", log=lambda *_a: None)
    assert plan.get("empty") and _read(root, "main.py") == "print(1)"
    sha = gs.push(root, _api(fake), "main", "Release v1.0.1", log=lambda *_a: None,
                  exclude=("latest.json",))
    assert sha == fake.head
    assert sorted(fake.files()) == [".gitignore", "gambit/version.py", "main.py"]
    # later pulls work normally
    assert gs.pull(root, _api(fake), "main", log=lambda *_a: None)["conflict"] == []

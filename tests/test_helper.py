"""The offline Helper: understanding plain English (with typos), slots, recipes, the GAM
syntax check, walkthroughs, the local-AI plumbing and the dock panel."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gambit.helper import brain, commands as hc, knowledge, local_ai, verify

USERS = [{"email": "jdoe@hancockschools.net", "name": "Jane Doe", "ou": "/Staff/Teachers"},
         {"email": "mjones@hancockschools.net", "name": "Mary Jones",
          "ou": "/Students/Hancock Middle/Grade 5"},
         {"email": "jsmith@hancockschools.net", "name": "Jane Smith", "ou": "/Staff"}]
GROUPS = [{"email": "science@hancockschools.net", "name": "Science Dept"},
          {"email": "staff@hancockschools.net", "name": "All Staff"}]
OUS = ["/", "/Students", "/Students/Hancock Middle", "/Students/Hancock Middle/Grade 5",
       "/Staff", "/Staff/Teachers", "/Chromebooks/Hancock Middle"]


class Dir:
    users, groups, ous = USERS, GROUPS, OUS


@pytest.fixture(scope="module")
def k():
    return knowledge.build()


@pytest.fixture
def b(k):
    return brain.Brain(k, Dir())


def cmd(a):
    assert a.suggestions, a.text
    return " ".join(a.suggestions[0].args)


# ---------------------------------------------------------------- commands ---
@pytest.mark.parametrize("r", hc.RECIPES, ids=lambda r: r.id)
def test_every_recipe_builds_a_command_gam_knows(r):
    s = hc.Slots(users=["jdoe@hancockschools.net", "mjones@hancockschools.net"],
                 groups=["staff@hancockschools.net"], ous=["/Students/Hancock Middle"],
                 serials=["5CD123ABC"], assets=["HMS-0123"], days=30,
                 quoted=["Back Monday"], other_emails=["helpdesk@hancockschools.net"])
    sug = hc.make(r, s, "", USERS)
    ok, how = verify.check(sug.args)
    assert ok, f"{r.id}: {' '.join(sug.args)} → {how}"


@pytest.mark.parametrize("q,want", [
    ("reset jane doe's pasword", "update user jdoe@hancockschools.net password"),
    ("can you lock jdoe's acount", "update user jdoe@hancockschools.net suspended on"),
    ("unsuspend mary jones", "update user mjones@hancockschools.net suspended off"),
    ("what grups is jane doe in", "print groups member jdoe@hancockschools.net"),
    ("whos in the staff group", "print group-members group staff@hancockschools.net"),
    ("list chromebooks not seen in 30 days", "querytime1 -30d"),
    ("find the chromebok with asset HMS-0123", "query asset_id:HMS-0123"),
    ("give jane does drive files to mary jones",
     "create datatransfer jdoe@hancockschools.net googledrive mjones@hancockschools.net"),
    ("whats the serial for mary jones chromebook", "query user:mjones@hancockschools.net"),
    ("take mary jones out of the staff group",
     "update group staff@hancockschools.net remove users mjones@hancockschools.net"),
    ("sign jane doe out of everything", "user jdoe@hancockschools.net signout"),
    ("add jane doe to science group", "update group science@hancockschools.net add"),
    ("turn off 2 step for jdoe", "user jdoe@hancockschools.net turnoff2sv"),
    ("where do i find chromebooks with old updates", "autoupdateexpiration"),
])
def test_plain_english_to_commands(b, q, want):
    assert want in cmd(b.respond(q))


def test_follow_up_question_fills_the_missing_person(b):
    a = b.respond("reset a password")
    assert not a.suggestions and "who" in a.text.lower()
    a = b.respond("mary jones")
    assert "update user mjones@hancockschools.net password" in cmd(a)


def test_two_janes_asks_which_one(b):
    a = b.respond("reset jane's password")
    assert not a.suggestions and len(a.chips) == 2
    assert "update user jsmith@hancockschools.net" in cmd(b.respond(a.chips[1]))


def test_pronoun_uses_the_last_person(b):
    b.respond("what groups is mary jones in")
    assert "mjones@hancockschools.net" in cmd(b.respond("reset her password"))


def test_suspend_is_marked_as_a_change(b):
    assert b.respond("suspend jdoe@hancockschools.net").suggestions[0].change
    assert not b.respond("what groups is jdoe in").suggestions[0].change


# ----------------------------------------------------------------- guide ---
@pytest.mark.parametrize("q,page", [
    ("how do i set up a new teacher", "Workflows"),
    ("someone is leaving the district what do i do", "Workflows"),
    ("how do i aprove requests", "Approvals"),
    ("how do i give someone admin rights", "More services"),
    ("show me how to do bulk changes with a csv", "Bulk (CSV)"),
])
def test_questions_find_the_right_page(b, q, page):
    a = b.respond(q)
    assert a.links and a.links[0].page == page, (q, a.text[:80])


def test_walkthrough_has_steps(b):
    a = b.respond("walk me through chromebooks")
    assert a.walkthrough is not None and a.walkthrough.page == "Chromebooks"
    assert len(a.walkthrough.steps) >= 3


def test_this_page(b):
    a = b.respond("how do i use this page", page="Groups")
    assert a.links[0].page == "Groups"


def test_what_is_dry_run_explains(b):
    assert "dry run" in b.respond("what is dry run").text.lower()


def test_nonsense_is_not_a_confident_answer(b):
    a = b.respond("my printer is on fire")
    assert not a.suggestions and not a.confident


def test_explains_a_pasted_command(b):
    a = b.respond("what does gam user jdoe@hancockschools.net print forward do")
    assert "✔" in a.text and "reads" in a.text


def test_typo_correction(k):
    assert "password" in k.norm.words("pasword")
    assert "chromebook" in k.norm.words("chromebok")


# ---------------------------------------------------------------- verify ---
def test_verify_rejects_made_up_commands():
    assert verify.check("print users")[0]
    assert verify.check("gam user jdoe@x.net print forward")[0]
    assert not verify.check("frobnicate users all")[0]
    assert not verify.check("print unicorns")[0]


def test_extract_commands_from_ai_text():
    t = "Try this:\n```gam\ngam print users\n# comment\ninfo user jdoe@x.net\n```\nDone."
    assert verify.extract_commands(t) == ["print users", "info user jdoe@x.net"]
    assert verify.extract_commands("Run:\ngam print groups\n") == ["print groups"]


# -------------------------------------------------------------- local AI ---
def test_pick_llama_asset_prefers_cpu_zip(monkeypatch):
    monkeypatch.setattr(local_ai, "IS_WIN", True)
    assets = [{"name": "llama-b1-bin-win-cuda-x64.zip"},
              {"name": "llama-b1-bin-win-cpu-x64.zip"}, {"name": "llama-b1-bin-macos.zip"}]
    assert local_ai._pick_llama_asset(assets)["name"].endswith("win-cpu-x64.zip")


def test_chat_talks_to_a_local_openai_style_server(monkeypatch):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps({"choices": [{"message": {"content": " ready "}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(local_ai, "engine", lambda: "builtin")
        monkeypatch.setattr(local_ai.Server, "start",
                            classmethod(lambda cls, wait=0: f"http://127.0.0.1:{srv.server_port}"))
        ans = local_ai.answer("hi", "[Users]: manage accounts")
        assert ans == "ready"
        assert seen["body"]["messages"][0]["role"] == "system"
        assert "CONTEXT" in seen["body"]["messages"][0]["content"]
    finally:
        srv.shutdown()


def test_status_without_install(monkeypatch, tmp_path):
    monkeypatch.setattr(local_ai, "folder", lambda: str(tmp_path))
    monkeypatch.setattr(local_ai, "engine", lambda: "builtin")
    assert not local_ai.installed()
    assert local_ai.status() == "Not installed."
    (tmp_path / "m.gguf").write_bytes(b"GGUF" + b"0" * 10)
    assert local_ai.is_gguf(str(tmp_path / "m.gguf"))


def test_unsure_hands_over_to_the_ai_when_on(k):
    b = brain.Brain(k, Dir(), ai_available=lambda: True)
    a = b.respond("my printer is on fire")
    assert a.needs_ai


# ----------------------------------------------------------------- panel ---
def test_helper_panel_suggests_and_walks(qapp):
    from PySide6.QtWidgets import QMainWindow

    from gambit.ui.helper_panel import HelperDock

    class App(QMainWindow):
        pages = {}
        directory = Dir()

        def go(self, name):
            pass

    app = App()
    h = HelperDock(app)
    h.ensure_brain()
    h.input.setText("lock jdoe@hancockschools.net")
    h.send()
    assert h.cmds and h.cmds[-1]["change"] and h.cmds[-1]["verified"]
    assert "Run" in h.blocks[-1]
    d = h.brain.k.page("Chromebooks")
    h.start_walk(d)
    assert h.walk_bar.isVisibleTo(h) and "step 1 of" in h.walk_title.text()
    for _ in d.steps:
        h._walk_step(1)
    assert h.walk is None


def test_help_and_thanks_during_a_follow_up(b):
    b.respond("create a group called robotics club")
    assert "three ways" in b.respond("help").text
    assert "welcome" in b.respond("thanks").text


def test_several_asset_ids_and_serials(b):
    c = cmd(b.respond("find chromebooks with asset HS0116, HS0189"))
    assert "queries asset_id:HS0116,asset_id:HS0189" in c
    assert "asset_id:HS0116" in cmd(b.respond("whats the serial for asset tag HS0116"))
    assert "cros_sn 5CD123ABC,5CD999XYZ" in cmd(b.respond("disable chromebooks 5CD123ABC,5CD999XYZ"))


def test_chromebook_search_splits_lists():
    from gambit.ui.pages.devices import asset_query, query_args, split_items
    assert query_args([asset_query(x) for x in split_items("HS0116,HS0189")]) == \
        ["queries", "asset_id:HS0116,asset_id:HS0189"]
    assert split_items("HS0116 HS0189") == ["HS0116", "HS0189"]
    assert split_items("HS0116\nHS0189;HS0116") == ["HS0116", "HS0189"]
    assert split_items("Cart 3") == ["Cart 3"]
    assert query_args(["status:ACTIVE model:x"]) == ["query", "status:ACTIVE model:x"]

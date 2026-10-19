"""Parent-facing report for principals: how many students at each school have a
guardian connected in Google Classroom (accepted), are waiting on an invitation, or
have nobody – and the student list behind each number."""

from __future__ import annotations

import csv
import datetime
import json
import os

from .settings import settings

TASK = {"name": "GAMbit guardian report", "args": ["--task", "guardians"],
        "freq": "monthly", "time": "06:50",
        "what": "Emails each principal their school's guardian report (1st of the month)",
        "standard": False}


def options() -> dict:
    try:
        o = json.loads(settings.get("guardians/report", "{}") or "{}")
    except ValueError:
        o = {}
    return {"root": "/Students", "principals": "", "district_to": "", **o}


def save_options(o: dict):
    settings.set("guardians/report", json.dumps(o))


def parse_principals(text: str) -> dict[str, list[str]]:
    out = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            to = [x.strip() for x in v.replace(";", ",").split(",") if "@" in x]
            if k.strip() and to:
                out[k.strip().lower()] = to
    return out


def school_of(ou: str, root: str) -> str:
    from .oupath import under
    ou, root = (ou or "/").rstrip("/"), (root or "/").rstrip("/")
    rest = ou[len(root):].strip("/") if under(ou, root) else ou.strip("/")
    return rest.split("/")[0] if rest else "(top level)"


def status_by_student(current: list[dict]) -> dict[str, dict]:
    """student email -> {"accepted": [..], "pending": [(guardian, since)]}"""
    out: dict[str, dict] = {}
    for c in current:
        s = out.setdefault(c["student"], {"accepted": [], "pending": []})
        if c["kind"] == "guardian":
            s["accepted"].append(c["guardian"])
        elif c["state"] == "PENDING":
            s["pending"].append((c["guardian"], c.get("since", "")))
    return out


def details(students: list[dict], current: list[dict], root: str) -> list[dict]:
    st = status_by_student(current)
    rows = []
    for u in students:
        e = u["email"].lower()
        s = st.get(e, {"accepted": [], "pending": []})
        if s["accepted"]:
            status = "Connected"
        elif s["pending"]:
            status = "Invited – waiting since " + min(x[1] or "?" for x in s["pending"])
        else:
            status = "Nobody invited"
        rows.append({"School": school_of(u.get("ou", ""), root), "Student": u.get("name", ""),
                     "Email": e, "Org unit": u.get("ou", ""), "Status": status,
                     "Guardians": ", ".join(s["accepted"] + [g for g, _ in s["pending"]])})
    rows.sort(key=lambda r: (r["School"], r["Org unit"], r["Student"]))
    return rows


def summary(detail_rows: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for r in detail_rows:
        b = by.setdefault(r["School"], {"School": r["School"], "Students": 0,
                                        "Connected": 0, "Invited (waiting)": 0,
                                        "Nobody invited": 0})
        b["Students"] += 1
        if r["Status"] == "Connected":
            b["Connected"] += 1
        elif r["Status"].startswith("Invited"):
            b["Invited (waiting)"] += 1
        else:
            b["Nobody invited"] += 1
    out = []
    for b in sorted(by.values(), key=lambda x: x["School"]):
        b["% connected"] = f"{100 * b['Connected'] / b['Students']:.0f}%" if b["Students"] else "–"
        out.append(b)
    if out:
        tot = {k: sum(b[k] for b in out) for k in ("Students", "Connected",
                                                   "Invited (waiting)", "Nobody invited")}
        out.append({"School": "District total", **tot,
                    "% connected": f"{100 * tot['Connected'] / tot['Students']:.0f}%"})
    return out


def write_csv(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if not rows:
            fh.write("No students\n")
            return
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def email_text(school: str, s: dict) -> str:
    return (f"Guardian report for {school} – {datetime.date.today():%B %d, %Y}\n\n"
            f"Students: {s['Students']}\n"
            f"A parent or guardian connected in Google Classroom: {s['Connected']} "
            f"({s['% connected']})\n"
            f"Invited but not accepted yet: {s['Invited (waiting)']}\n"
            f"Nobody invited: {s['Nobody invited']}\n\n"
            "The attached list shows every student and their status. Families who were "
            "invited can look for an email from Google Classroom; invitations expire after "
            "120 days. Send corrected parent email addresses to the technology department.")


def build(run_csv=None, root: str = "") -> tuple[list[dict], list[dict]]:
    """Read students and guardians from Google. Returns (detail rows, summary rows)."""
    from . import guardians
    from .directory import load_users, run_gam_text
    root = root or options()["root"]
    students = [u for u in load_users() if not u.get("suspended") and
                (u.get("ou", "") + "/").lower().startswith(root.rstrip("/").lower() + "/")]
    code, out = (run_csv or run_gam_text)(["ou_and_children", root, "print", "guardians",
                                           "all", "showstudentemails"], 3600)
    if code != 0:
        raise RuntimeError("Couldn't list guardians: " +
                           (out.strip().splitlines()[-1] if out.strip() else str(code)))
    d = details(students, guardians.parse_current(out), root)
    return d, summary(d)


def send(log=print, run_text=None) -> int:
    """Email each principal their school's numbers and list. Returns failures."""
    from . import google_io
    from .directory import run_gam_text
    from .scheduler import default_output_dir
    run_text = run_text or run_gam_text
    o = options()
    principals = parse_principals(o.get("principals", ""))
    if not principals and not o.get("district_to"):
        log("No principals are set up for the guardian report.")
        return 0
    d, s = build(run_text, o["root"])
    out_dir = os.path.join(settings.get("schedule/out", "") or default_output_dir(),
                           "Guardian report")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    bad = 0
    sums = {r["School"].lower(): r for r in s}
    for school, to in principals.items():
        srow = sums.get(school)
        if not srow:
            log(f"No students found for “{school}” – check the school name matches the "
                "org unit.")
            continue
        path = os.path.join(out_dir, f"guardians_{school.replace(' ', '_')}_{stamp}.csv")
        write_csv(path, [r for r in d if r["School"].lower() == school])
        args = google_io.email_args(",".join(to), f"Guardian report – {srow['School']}",
                                    email_text(srow["School"], srow)) + ["attach", path]
        code, out = run_text(args, 180)
        if code:
            bad += 1
            log(f"FAILED emailing {srow['School']}: {out.strip()[-200:]}")
        else:
            log(f"Sent {srow['School']} to {', '.join(to)}.")
    if o.get("district_to") and s:
        path = os.path.join(out_dir, f"guardians_by_school_{stamp}.csv")
        write_csv(path, s)
        tot = s[-1]
        code, out = run_text(google_io.email_args(
            o["district_to"], "Guardian report – all schools",
            email_text("all schools", tot)) + ["attach", path], 180)
        bad += 1 if code else 0
        log("Sent the district summary." if not code else
            f"FAILED emailing the district summary: {out.strip()[-200:]}")
    return bad

"""Weekly digest email: what changed and what needs attention."""

from __future__ import annotations

from . import tempfiles as _tf
import datetime
import html
import os

from .settings import settings


def build(days: int = 7) -> dict:
    from . import activity, offboard, scheduler, team
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    acts = [a for a in activity.load(days, team=True) if a.get("time", "") >= since]
    created = sorted({a["command"].split()[3] for a in acts
                      if a.get("code") == 0 and a.get("command", "").startswith("gam create user ")
                      and len(a["command"].split()) > 3})
    failed = [a for a in acts if a.get("change") and a.get("code") not in (0, None)
              and a.get("status") != "cancelled"]
    leaving = [r for r in offboard.load_all() if r.get("started", "") >= since]
    today = datetime.date.today().isoformat()
    week = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    due = []
    for r in offboard.load_all():
        st = offboard.next_stage(r)
        if r.get("status") == "active" and st and st["due"] <= week:
            due.append((r["email"], st["title"], st["due"]))
    pending = team.list_requests("pending") if team.folder() else []
    try:
        jobs = scheduler.list_tasks()
    except Exception:  # noqa: BLE001
        jobs = []
    bad_jobs = [j for j in jobs if j.get("Last result", "") not in ("", "0", "267011", "267009")]
    dash = {}
    try:
        from . import dashboard
        from .directory import load_users
        dash = dashboard.gather(load_users())
    except Exception as exc:  # noqa: BLE001
        dash = {"error": str(exc)}
    by_tech: dict[str, int] = {}
    for a in acts:
        if a.get("change") and a.get("code") == 0:
            by_tech[a.get("who") or "?"] = by_tech.get(a.get("who") or "?", 0) + 1
    try:
        from . import tasks_health
        runs = tasks_health.runs_since(datetime.datetime.now() - datetime.timedelta(days=days))
        bg_failed = [r for r in runs if not r.get("ok") and not r.get("skipped")]
        bg_ok = sum(1 for r in runs if r.get("ok"))
        for r in bg_failed:
            r["label"] = tasks_health.label_for(r["key"])
    except Exception:  # noqa: BLE001
        bg_failed, bg_ok = [], 0
    watch = []
    for mod, fn in (("gam_keys", "attention"), ("sso_watch", "attention"),
                    ("maildns", "attention"),
                    ("activity", "integrity_attention")):
        try:
            import importlib
            watch += [t for _l, t in getattr(importlib.import_module(f".{mod}", __package__),
                                             fn)()]
        except Exception:  # noqa: BLE001
            pass
    return {"watch": watch, "days": days, "created": created, "leaving": leaving,
            "failed": failed,
            "due": due, "pending": pending, "bad_jobs": bad_jobs, "dash": dash,
            "today": today, "by_tech": by_tech, "bg_failed": bg_failed, "bg_ok": bg_ok,
            "low_licenses": low_licenses(dash.get("license_breakdown") or {})}


SEATS_KEY = "digest/license_seats"


def seats() -> dict[str, int]:
    """Settings → Weekly digest: “Google Workspace for Education Plus = 1200” per line."""
    out = {}
    for ln in (settings.get(SEATS_KEY, "") or "").splitlines():
        if "=" in ln:
            k, v = ln.rsplit("=", 1)
            try:
                out[k.strip().lower()] = int(v.strip().replace(",", ""))
            except ValueError:
                continue
    return out


def low_licenses(used: dict, warn_at: float = 0.95) -> list[tuple[str, int, int]]:
    """(license, used, seats) for licenses at 95%+ of what you bought."""
    s = seats()
    out = []
    for name, n in used.items():
        total = s.get(str(name).strip().lower())
        if total and n >= total * warn_at:
            out.append((name, int(n), total))
    return sorted(out, key=lambda x: x[1] / x[2], reverse=True)


def render(d: dict) -> tuple[str, str]:
    """(subject, html)"""
    esc = html.escape
    dash = d["dash"]
    attention = len(d["failed"]) + len(d["pending"]) + len(d["bad_jobs"]) + \
        int(dash.get("alerts", 0) or 0) + len(d.get("bg_failed", [])) + \
        len(d.get("low_licenses", [])) + len(d.get("watch", []))
    subject = (f"GAMbit weekly digest – {len(d['created'])} new, {len(d['leaving'])} leaving"
               + (f", {attention} to check" if attention else ""))

    def section(title, items, empty="Nothing this week."):
        body = "".join(f"<li>{i}</li>" for i in items[:40]) or f"<li style='color:#57606a'>" \
                                                                f"{empty}</li>"
        more = f"<p style='color:#57606a'>…and {len(items) - 40} more</p>" if len(items) > 40 \
            else ""
        return f"<h3 style='margin:18px 0 4px'>{title}</h3><ul>{body}</ul>{more}"

    parts = [f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#1f2328'>"
             f"<h2>GAMbit weekly digest</h2><p>The last {d['days']} days, as of "
             f"{datetime.date.today():%A %B %d, %Y}.</p>"]
    tiles = [("New accounts", len(d["created"])), ("Leaving", len(d["leaving"])),
             ("Waiting for approval", len(d["pending"])),
             ("Failed changes", len(d["failed"])),
             ("Security alerts", dash.get("alerts", "–")),
             ("Chromebooks not seen in 30 days", dash.get("cros_stale", "–")),
             ("Background jobs failed", len(d.get("bg_failed", [])))]
    parts.append("<table cellpadding='8' style='border-collapse:collapse'><tr>" + "".join(
        f"<td style='border:1px solid #d0d7de;text-align:center'><div style='font-size:20px;"
        f"font-weight:bold'>{v}</div><div style='color:#57606a'>{esc(t)}</div></td>"
        for t, v in tiles) + "</tr></table>")
    if d.get("watch"):
        parts.append(section("Sign-in, email security and log checks",
                             [esc(t) for t in d["watch"]]))
    parts.append(section("Waiting for approval",
                         [f"{esc(r.get('title', ''))} – asked by {esc(r.get('by', ''))}"
                          for r in d["pending"]]))
    parts.append(section("Changes that failed",
                         [f"{esc(a.get('time', '')[:16].replace('T', ' '))} "
                          f"{esc(a.get('who', ''))}: <code>{esc(a.get('command', ''))}</code>"
                          for a in d["failed"]]))
    parts.append(section("Scheduled jobs that failed last time",
                         [esc(f"{j['Name']} (last run {j.get('Last run', '')})")
                          for j in d["bad_jobs"]]))
    parts.append(section("Background jobs that failed",
                         [esc(f"{r.get('label', r['key'])} – {r.get('ended', '')[:16]}"
                              .replace("T", " ") + (f": {r['summary']}" if r.get('summary')
                                                     else "")) for r in d.get("bg_failed", [])],
                         f"None – {d.get('bg_ok', 0)} ran fine."))
    parts.append(section("Licenses running low",
                         [esc(f"{n}: {u:,} of {t:,} used") for n, u, t in
                          d.get("low_licenses", [])],
                         "None (set how many you bought in Settings → Weekly digest)."
                         if not seats() else "None."))
    parts.append(section("Changes by each tech",
                         [esc(f"{w}: {n} change(s)") for w, n in
                          sorted(d.get("by_tech", {}).items(), key=lambda x: -x[1])],
                         "No changes this week."))
    parts.append(section("Offboarding steps due in the next 7 days",
                         [esc(f"{e}: {t} on {due}") for e, t, due in d["due"]]))
    parts.append(section("New accounts", [esc(e) for e in d["created"]]))
    parts.append(section("People leaving / graduating",
                         [esc(f"{r['email']} – {r.get('started', '')[:10]}")
                          for r in d["leaving"]]))
    if dash.get("error"):
        parts.append(f"<p style='color:#9a6700'>Some numbers are missing: {esc(dash['error'])}"
                     "</p>")
    parts.append("<p style='color:#57606a'>Sent by GAMbit.</p></div>")
    return subject, "".join(parts)


def send(to: str = "", log=print) -> str:
    from . import google_io
    from .directory import run_gam_text
    to = to or (settings.get("digest/to", "") or "")
    if "@" not in to:
        raise RuntimeError("Set who gets the weekly digest first.")
    subject, body = render(build())
    path = os.path.join(_tf.folder(), "digest.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    args = google_io.email_args(to, subject, "")
    i = args.index("message")
    args[i:i + 2] = ["htmlfile", path]
    code, out = run_gam_text(args, 180)
    if code != 0:
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "sendemail failed")
    settings.set("digest/last", datetime.datetime.now().isoformat(timespec="minutes"))
    log(f"Digest sent to {to}: {subject}")
    return subject

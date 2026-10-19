"""Email signature template: {Tag} placeholders filled from each person's Google fields."""

from __future__ import annotations

import html
import re

# {Tag} in a signature / auto-reply  ->  GAM user field
TAGS = {
    "FullName": "name.fullname",
    "FirstName": "name.givenname",
    "LastName": "name.familyname",
    "Email": "email.primaryemail",
    "Title": "organization.title",
    "Department": "organization.department",
    "WorkPhone": "phone.value.type.work",
}

SIGNATURE_TEMPLATE = (
    "<div style=\"font-family:Arial,sans-serif;font-size:13px;color:#333\">\n"
    "  <b>{FullName}</b><br>\n"
    "  {RT}{Title}<br>{/RT}\n"
    "  {RT}{Department}<br>{/RT}\n"
    "  Your School Name<br>\n"
    "  <a href=\"mailto:{Email}\">{Email}</a>{RT} · {WorkPhone}{/RT}\n"
    "</div>")


def tag_replacements(text: str) -> list[str]:
    args: list[str] = []
    for tag, field in TAGS.items():
        if "{" + tag + "}" in text:
            args += ["replace", tag, f"field:{field}"]
    return args


def render(template: str, person: dict) -> str:
    """Preview a signature for one person. person keys: name, first, last, email, title,
    department, phone. {RT}…{/RT} parts vanish when a tag inside them is empty (like GAM)."""
    vals = {"FullName": person.get("name") or
            f"{person.get('first', '')} {person.get('last', '')}".strip(),
            "FirstName": person.get("first", ""), "LastName": person.get("last", ""),
            "Email": person.get("email", ""), "Title": person.get("title", ""),
            "Department": person.get("department", ""), "WorkPhone": person.get("phone", "")}

    def fill(text):
        return re.sub(r"\{(\w+)\}", lambda m: html.escape(vals[m.group(1)])
                      if m.group(1) in vals else m.group(0), text)

    def rt(m):
        inner = m.group(1)
        tags = [t for t in re.findall(r"\{(\w+)\}", inner) if t in vals]
        return "" if any(not vals[t] for t in tags) else fill(inner)
    return fill(re.sub(r"\{RT\}(.*?)\{/RT\}", rt, template, flags=re.S))


def gam_args(email: str, template: str) -> list[str]:
    return ["user", email, "signature", template, *tag_replacements(template),
            "html", "true"]


# ------------------------------------------------------- weekly rollout ---
ROLLOUT_TASK = {"name": "GAMbit signature rollout", "args": ["--task", "signatures"],
                "freq": "weekly", "time": "05:20",
                "what": "Re-applies the district email signature every Monday",
                "standard": False}


def rollout() -> dict:
    """{"targets": [[gam entity args], …], "html": bool, "who": text} or {}."""
    import json
    from .settings import settings
    try:
        return json.loads(settings.get("signature/rollout", "") or "{}")
    except ValueError:
        return {}


def save_rollout(targets: list[list[str]], is_html: bool, who: str):
    import json
    from .settings import settings
    settings.set("signature/rollout", json.dumps({"targets": targets, "html": is_html,
                                                   "who": who}) if targets else "")


def run_rollout(log=print, run_text=None) -> int:
    """Apply the current template to everyone in the saved rollout. Returns failures."""
    from . import activity, team
    from .directory import run_gam_text
    from .settings import settings
    run_text = run_text or run_gam_text
    r = rollout()
    if not r.get("targets"):
        log("No signature rollout is saved – set one up on Email → Signatures.")
        return 0
    tpl = team.setting("email/signature", "") or SIGNATURE_TEMPLATE
    bad = 0
    for ent in r["targets"]:
        args = [*ent, "signature", tpl, *tag_replacements(tpl), "html",
                "true" if r.get("html", True) else "false"]
        if settings.get("safety/dry_run", False):
            log("Dry run – not run: " + " ".join(ent) + " signature …")
            continue
        code, out = run_text(args, 3600)
        activity.record(args, code, "done" if code == 0 else "failed", None,
                        settings.get("profile/current", "") or "Default",
                        note="weekly signature rollout")
        if code:
            bad += 1
            log(f"FAILED for {' '.join(ent)}: "
                f"{out.strip().splitlines()[-1] if out.strip() else code}")
        else:
            log(f"Signature applied to {' '.join(ent)}.")
    return bad

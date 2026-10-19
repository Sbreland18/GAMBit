"""Turning a plain-English request into a ready GAM command: find the people, groups, org
units and Chromebooks it mentions (using GAMbit's directory, so “jane doe” or “lincoln 5th
grade” work), pick the matching command recipe, and explain what it will do.

Every recipe uses syntax checked against GAM's own reference (tests/test_helper.py)."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"\b[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
SERIAL = re.compile(r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9]{6,20}\b")
ASSET = re.compile(r"\b[A-Za-z]{1,6}-?\d{2,8}\b")
PATH = re.compile(r"(?<![\w@])/[A-Za-z0-9][^,;\n\"']*")
DAYS = re.compile(r"\b(\d{1,4})\s*(day|days|week|weeks|month|months)\b", re.I)
QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
ORD = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b")
WORDNUM = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
           "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
           "eleventh": "11", "twelfth": "12", "kindergarten": "k", "kinder": "k"}
PRONOUNS = {"him", "her", "them", "they", "he", "she", "that", "same", "it", "this", "those"}


@dataclass
class Slots:
    users: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    ous: list[str] = field(default_factory=list)
    serials: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    days: int = 0
    quoted: list[str] = field(default_factory=list)
    other_emails: list[str] = field(default_factory=list)   # not known users/groups
    pronoun: bool = False
    maybe_users: list[str] = field(default_factory=list)    # a first name with several matches


def _ou_tokens(s: str) -> set[str]:
    s = s.lower()
    s = ORD.sub(r"\1", s)
    for w, n in WORDNUM.items():
        s = re.sub(rf"\b{w}\b", n, s)
    s = re.sub(r"\bgrade\s*(\d+|k)\b", r"\1", s)
    s = re.sub(r"\b(\d+|k)\s*(th|st|nd|rd)?\s*grade(rs)?\b", r"\1", s)
    s = s.replace("graders", "").replace("grader", "")
    return {t for t in re.split(r"[^a-z0-9]+", s) if t and t not in ("the", "of", "in", "at")}


def extract(text: str, users: list[dict], groups: list[dict], ous: list[str],
            memory: dict | None = None) -> Slots:
    s = Slots()
    low = (text or "").lower()
    group_emails = {g["email"].lower(): g for g in groups}
    user_emails = {u["email"].lower(): u for u in users}
    domains = {e.split("@")[1] for e in list(user_emails)[:2000] if "@" in e}
    # e-mail addresses
    for e in EMAIL.findall(text or ""):
        e = e.lower().strip(".")
        if e in group_emails:
            s.groups.append(e)
        elif e in user_emails:
            s.users.append(e)
        else:
            s.other_emails.append(e)
    # bare user names (jdoe) and partial addresses (jdoe@)
    for w in re.findall(r"\b([a-z][a-z0-9._-]{2,})@?(?![a-z0-9.-]*\.[a-z])", low):
        for d in domains:
            e = f"{w}@{d}"
            if e in user_emails and e not in s.users:
                s.users.append(e)
            elif e in group_emails and e not in s.groups:
                s.groups.append(e)
    # full names: 2-3 word windows against directory names
    if users and len(s.users) < 3:
        names = {}
        for u in users:
            n = (u.get("name") or "").lower().strip()
            if n:
                names.setdefault(n, u["email"].lower())
        words = re.findall(r"[a-z][a-z'-]+", low)
        nlist = list(names)
        for size in (3, 2):
            for i in range(len(words) - size + 1):
                cand = " ".join(words[i:i + size])
                if cand in names:
                    hit = [cand]
                else:
                    hit = difflib.get_close_matches(cand, nlist, n=1, cutoff=0.88)
                if hit and names[hit[0]] not in s.users:
                    s.users.append(names[hit[0]])
    # a lone first name ("reset jane's password")
    if users and not s.users:
        firsts: dict[str, list[str]] = {}
        for u in users:
            n = (u.get("name") or "").lower().split()
            if n:
                firsts.setdefault(n[0], []).append(u["email"].lower())
        from .text import CANON, STOP
        for w in re.findall(r"[a-z][a-z'-]{2,}", low):
            w = w.rstrip("'s") if w.endswith("'s") else w
            if w in STOP or w in CANON or w not in firsts:
                continue
            if len(firsts[w]) == 1:
                s.users.append(firsts[w][0])
            else:
                s.maybe_users = firsts[w][:6]
            break
    # groups by name ("the science dept group", "hs-staff")
    if groups and not s.groups:
        lw = set(re.findall(r"[a-z0-9-]+", low))
        best, score = None, 0
        for g in groups:
            local = g["email"].split("@")[0].lower()
            gw = set(re.findall(r"[a-z0-9]+", (g.get("name") or "").lower())) | {local} | \
                set(local.replace("_", "-").split("-"))
            gw -= {"group", "the", "and", "of", ""}
            hit = len(gw & lw)
            if local in lw:
                hit += 3
            if hit > score and ("group" in lw or local in lw or hit >= 2):
                best, score = g["email"].lower(), hit
        if best:
            s.groups.append(best)
    # org units – exact path, or by their words
    for m in PATH.findall(text or ""):
        p = m.strip().rstrip(".?!")
        exact = next((o for o in ous if o.lower() == p.lower()), None)
        if exact:
            s.ous.append(exact)
        else:
            # trim words until it matches an existing org unit
            parts = p.split()
            while parts:
                cand = " ".join(parts)
                hit = next((o for o in ous if o.lower() == cand.lower()), None)
                if hit:
                    s.ous.append(hit)
                    break
                parts.pop()
            else:
                s.ous.append(p.split()[0])
    if not s.ous and ous:
        qt = _ou_tokens(low)
        best, best_s = None, 0.0
        for o in ous:
            ot = _ou_tokens(o) - {"students", "staff", "student"} or _ou_tokens(o)
            if not ot:
                continue
            cover = len(ot & qt) / len(ot)
            if cover >= 0.99 or (cover >= 0.6 and len(ot & qt) >= 2):
                sc = cover * 10 + len(ot & qt) + o.count("/") * 0.1
                if sc > best_s:
                    best, best_s = o, sc
        if best:
            s.ous.append(best)
    # Chromebooks
    s.serials = [x for x in SERIAL.findall(text or "") if "@" not in x and not
                 re.fullmatch(r"\d+", x)]
    s.assets = [x for x in ASSET.findall(text or "") if x.upper() not in s.serials and
                "-" in x]
    if re.search(r"\basset|\btags?\b", low):
        # "asset HS0116, HS0189" – the ones that look like serials are really asset IDs
        s.assets = list(dict.fromkeys(s.assets + [x for x in s.serials if ASSET.fullmatch(x)]))
        s.serials = [x for x in s.serials if x not in s.assets]
    m = DAYS.search(low)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        s.days = n * (30 if unit.startswith("month") else 7 if unit.startswith("week") else 1)
    elif "this month" in low or "a month" in low:
        s.days = 30
    elif "this week" in low or "a week" in low:
        s.days = 7
    s.quoted = QUOTED.findall(text or "")
    s.pronoun = bool(PRONOUNS & set(re.findall(r"[a-z]+", low)))
    if memory and s.pronoun:
        if not s.users and memory.get("users"):
            s.users = list(memory["users"])
        if not s.groups and memory.get("groups") and ("group" in low or "it" in low):
            s.groups = list(memory["groups"])
        if not s.serials and memory.get("serials") and ("it" in low or "that" in low):
            s.serials = list(memory["serials"])
    return s


@dataclass
class Suggestion:
    recipe: str
    title: str
    args: list[str]
    explain: str
    change: bool
    page: str = ""
    tab: str = ""
    note: str = ""


@dataclass
class Recipe:
    id: str
    need: list[set]                  # every set must have a word in the request
    slots: list[str]                 # user / users2 / group / ou / serial / days
    build: object                    # fn(slots) -> (title, args, explain[, note])
    change: bool = False
    page: str = ""
    tab: str = ""
    avoid: set = field(default_factory=set)
    ask: dict = field(default_factory=dict)
    boost: set = field(default_factory=set)


def _pw() -> str:
    try:
        from ..selfservice import _password
        return _password()
    except Exception:  # noqa: BLE001
        import secrets
        return "Gambit" + str(secrets.randbelow(9000) + 1000) + "!"


def _q(ou: str) -> str:
    return f"orgUnitPath='{ou}'"


CROS_FIELDS = "serialnumber,annotatedassetid,annotateduser,orgunitpath,status,lastsync,model"


def _recipes() -> list[Recipe]:
    R = Recipe
    U = lambda s: s.users[0]  # noqa: E731
    return [
        R("reset_password", [{"password"}], ["user"], lambda s: (
            f"Reset {U(s)}'s password", ["update", "user", U(s), "password", (pw := _pw()),
                                          "changepassword", "on"],
            f"Sets the password to {pw} and makes them choose a new one when they sign in.",
            "Give them the new password; it's shown only here."),
          True, "Student lookup", boost={"reset", "change", "forgot"}),
        R("unsuspend_user", [{"unsuspend"}], ["user"], lambda s: (
            f"Unsuspend {U(s)}", ["update", "user", U(s), "suspended", "off"],
            "Lets the account sign in again."), True, "Users", avoid={"chromebook"}),
        R("suspend_user", [{"suspend"}], ["user"], lambda s: (
            f"Suspend {U(s)}", ["update", "user", U(s), "suspended", "on"],
            "Stops the account signing in. Nothing is deleted; unsuspend any time."),
          True, "Users", avoid={"chromebook", "unsuspend"}),
        R("enable_user", [{"enable"}, {"user", "student", "staff"}], ["user"], lambda s: (
            f"Unsuspend {U(s)}", ["update", "user", U(s), "suspended", "off"],
            "Lets the account sign in again."), True, "Users", avoid={"chromebook", "2sv"}),
        R("move_user", [{"move", "transfer"}], ["user", "ou"], lambda s: (
            f"Move {U(s)} to {s.ous[0]}", ["update", "user", U(s), "ou", s.ous[0]],
            f"Moves the account into {s.ous[0]}; that org unit's settings apply from now on."),
          True, "Users", avoid={"chromebook", "file", "drive", "group"}),
        R("signout", [{"signout"}], ["user"], lambda s: (
            f"Sign {U(s)} out everywhere", ["user", U(s), "signout"],
            "Signs them out of every browser and device; they sign in again with their "
            "password."), True, "Student lookup"),
        R("turnoff_2sv", [{"2sv"}, {"disable", "remove", "delete", "reset", "off"}], ["user"],
          lambda s: (f"Turn off 2-Step Verification for {U(s)}", ["user", U(s), "turnoff2sv"],
                     "Removes their 2-Step Verification so they can sign in and set it up "
                     "again (for a lost phone)."), True, "2-Step Verification"),
        R("user_groups", [{"group"}, {"member", "list", "find", "info"}], ["user"], lambda s: (
            f"Groups {U(s)} belongs to", ["print", "groups", "member", U(s), "fields",
                                          "email,name"],
            "Lists every group they're a member of."), False, "Groups",
          avoid={"add", "remove", "delete"}),
        R("group_members", [{"member", "list", "find", "info"}], ["group"], lambda s: (
            f"Members of {s.groups[0]}", ["print", "group-members", "group", s.groups[0],
                                         "fields", "email,role,type,status"],
            "Lists everyone in the group with their role."), False, "Groups",
          avoid={"add", "remove", "delete", "create"}),
        R("add_to_group", [{"add"}, {"group"}], ["users", "group"], lambda s: (
            f"Add {', '.join(s.users)} to {s.groups[0]}",
            ["update", "group", s.groups[0], "add", _role(s), "users", ",".join(s.users)],
            f"Adds them as {_role(s)}(s) of {s.groups[0]}."), True, "Groups"),
        R("remove_from_group", [{"remove", "delete"}, {"group"}], ["users", "group"],
          lambda s: (f"Remove {', '.join(s.users)} from {s.groups[0]}",
                     ["update", "group", s.groups[0], "remove", "users", ",".join(s.users)],
                     "Takes them out of the group (their account isn't touched)."),
          True, "Groups"),
        R("create_group", [{"create"}, {"group"}], ["newgroup"], lambda s: (
            f"Create the group {s.other_emails[0]}",
            ["create", "group", s.other_emails[0], "name",
             s.quoted[0] if s.quoted else s.other_emails[0].split("@")[0]],
            "Creates an empty group – add members next."), True, "Groups",
          tab="Create a group"),
        R("user_courses", [{"course"}], ["user"], lambda s: (
            f"Classes for {U(s)}", ["print", "courses", "teacher" if "staff" in _ou_of(s) or
                                    "teach" in s.__dict__.get("_raw", "") else "student",
                                    U(s), "states", "active", "fields", "id,name,section"],
            "Lists their active Google Classroom classes."), False, "Classroom"),
        R("vacation_off", [{"vacation"}, {"disable", "off", "remove", "delete", "stop"}],
          ["user"], lambda s: (f"Turn off {U(s)}'s out-of-office reply",
                               ["user", U(s), "vacation", "off"], "Stops the automatic reply."),
          True, "Email"),
        R("vacation_on", [{"vacation"}], ["user"], lambda s: (
            f"Turn on an out-of-office reply for {U(s)}",
            ["user", U(s), "vacation", "on", "subject", "Out of office", "message",
             s.quoted[0] if s.quoted else "I'm out of the office and will reply when I'm back."],
            "Turns on an automatic reply. Put your own message in quotes to change it."),
          True, "Email", avoid={"disable", "off", "stop"}),
        R("forward", [{"forward"}], ["user"], lambda s: (
            f"Check {U(s)}'s mail forwarding", ["user", U(s), "print", "forward"],
            "Shows whether their mail is forwarded and where."), False, "Email"),
        R("delegates", [{"delegate"}], ["user"], lambda s: (
            f"Who can read {U(s)}'s mail", ["user", U(s), "print", "delegates"],
            "Lists the people who can read and send from this mailbox."), False,
          "Mailbox access review"),
        R("add_alias", [{"alias"}, {"add", "create"}], ["user", "newaddress"], lambda s: (
            f"Add the address {s.other_emails[0]} to {U(s)}",
            ["create", "alias", s.other_emails[0], "user", U(s)],
            "Mail sent to the extra address arrives in their mailbox."), True, "Users"),
        R("transfer_drive", [{"transfer", "move"}, {"drive", "file"}], ["user", "user2"],
          lambda s: (f"Give {s.users[0]}'s Drive files to {s.users[1]}",
                     ["create", "datatransfer", s.users[0], "googledrive", s.users[1]],
                     f"Moves ownership of {s.users[0]}'s files to {s.users[1]} (Google does it "
                     "in the background; it can take hours for big drives)."), True,
          "Workflows", "Staff leaving"),
        R("cros_disable", [{"chromebook"}, {"disable", "suspend"}], ["serial"], lambda s: (
            f"Disable Chromebook {', '.join(s.serials)}",
            ["cros_sn", ",".join(s.serials), "update", "action", "disable"],
            "Locks the Chromebook with a 'return this device' screen until it's re-enabled."),
          True, "Chromebooks", avoid={"enable", "unsuspend"}),
        R("cros_enable", [{"chromebook"}, {"enable", "unsuspend"}], ["serial"], lambda s: (
            f"Re-enable Chromebook {', '.join(s.serials)}",
            ["cros_sn", ",".join(s.serials), "update", "action", "reenable"],
            "Unlocks a disabled Chromebook."), True, "Chromebooks"),
        R("cros_clear_user", [{"assign", "assigned", "assignment"}, {"clear", "blank", "remove", "empty", "delete",
                                           "erase"}], ["serial"], lambda s: (
            f"Blank the assigned user on {', '.join(s.serials)}",
            ["cros_sn", ",".join(s.serials), "update", "user", ""],
            "Empties the Assigned user field. It doesn't remove profiles or wipe the device."),
          True, "Chromebook fleet", "Assigned users",
          avoid={"all", "every", "last", "recent", "everything"}),
        R("cros_set_user", [{"assign", "assigned"}, {"chromebook", "serial", "device"}],
          ["serial", "user"], lambda s: (
            f"Assign {', '.join(s.serials)} to {U(s)}",
            ["cros_sn", ",".join(s.serials), "update", "user", U(s)],
            "Sets the Chromebook's Assigned user field."), True, "Chromebook fleet",
          "Assigned users", avoid={"clear", "blank", "remove", "empty", "last", "recent",
                                   "all", "every", "sync", "erase"}),
        R("cros_move", [{"chromebook"}, {"move"}], ["serial", "ou"], lambda s: (
            f"Move Chromebook {', '.join(s.serials)} to {s.ous[0]}",
            ["cros_sn", ",".join(s.serials), "update", "ou", s.ous[0]],
            "Moves the device so that org unit's Chrome policies apply."), True,
          "Chromebooks"),
        R("cros_stale", [{"chromebook"}, {"sync", "inactive"}], ["days"], lambda s: (
            f"Chromebooks not seen in {s.days} days",
            ["print", "cros", "querytime1", f"-{s.days}d", "query", "sync:..#querytime1#",
             "fields", CROS_FIELDS] + (["limittoou", s.ous[0]] if s.ous else []),
            "Lists Chromebooks that haven't checked in with Google lately – often lost, "
            "broken or in a drawer."), False, "Chromebooks", "Find / list devices"),
        R("cros_of_user", [{"chromebook"}], ["user"], lambda s: (
            f"Chromebooks used by {U(s)}",
            ["print", "cros", "query", f"user:{U(s)}", "fields", CROS_FIELDS],
            "Lists Chromebooks assigned to or recently used by them."), False,
          "Chromebooks", avoid={"move", "disable", "enable"}),
        R("cros_info", [{"chromebook", "serial", "asset"}], ["serial"], lambda s: (
            f"Details for Chromebook {', '.join(s.serials)}",
            ["info", "cros", "cros_sn", ",".join(s.serials)],
            "Shows its user, org unit, OS version, last check-in and more."), False,
          "Chromebooks", avoid={"move", "disable", "enable"}),
        R("cros_asset", [{"chromebook", "asset", "find", "info"}], ["asset"], lambda s: (
            f"Find the Chromebook with asset ID {', '.join(s.assets)}",
            ["print", "cros", *(["query", f"asset_id:{s.assets[0]}"] if len(s.assets) == 1 else
                                ["queries", ",".join(f"asset_id:{a}" for a in s.assets)]),
             "fields", CROS_FIELDS],
            "Looks the device up by its asset tag."), False, "Chromebooks"),
        R("cros_in_ou", [{"chromebook"}, {"list", "find", "ou", "info"}], ["ou"], lambda s: (
            f"Chromebooks in {s.ous[0]}",
            ["print", "cros", "cros_ou_and_children", s.ous[0], "fields", CROS_FIELDS],
            "Lists every Chromebook in the org unit and the ones below it."), False,
          "Chromebooks", "Find / list devices", avoid={"move", "disable"}),
        R("cros_aue", [{"aue"}], [], lambda s: (
            "Chromebooks and their end of updates",
            ["print", "cros"] + (["limittoou", s.ous[0]] if s.ous else []) +
            ["fields", "serialnumber,model,autoupdateexpiration,orgunitpath,status"],
            "Lists when each Chromebook stops getting ChromeOS updates."), False,
          "Reports", "Chromebook end of updates"),
        R("users_in_ou", [{"list", "find", "info", "member"}, {"user", "student", "staff"}],
          ["ou"],
          lambda s: (f"Accounts in {s.ous[0]}",
                     ["print", "users", "query", _q(s.ous[0]), "fields",
                      "primaryemail,name,ou,suspended,lastlogintime"],
                     "Lists the accounts in that org unit (and the ones below it) with their "
                     "last sign-in."), False, "Users",
          avoid={"chromebook", "move", "group", "create"}),
        R("user_info", [{"info", "find", "list"}], ["user"],
          lambda s: (f"Everything about {U(s)}", ["info", "user", U(s)],
                     "Shows their account details: org unit, last sign-in, aliases, groups "
                     "and more."), False, "Student lookup",
          avoid={"chromebook", "group", "course", "password", "move", "suspend"}),
        R("admins", [{"admin"}, {"list", "find", "info"}], [], lambda s: (
            "Everyone with admin rights", ["print", "admins"],
            "Lists every admin role assignment."), False, "Access review"),
    ]


def _role(s: Slots) -> str:
    raw = getattr(s, "_raw", "")
    return "owner" if "owner" in raw else "manager" if "manager" in raw else "member"


def _ou_of(s: Slots) -> str:
    return getattr(s, "_ou_of_user", "")


ASK = {"user": "Who is it for? Type their name or email.",
       "users": "Who should I add or remove? Type names or emails.",
       "user2": "Who should get the files? Type their name or email.",
       "group": "Which group? Type its email or name.",
       "ou": "Which org unit? Type the path (like /Students/Lincoln) or describe it (like "
             "“Lincoln 5th grade”).",
       "serial": "What's the Chromebook's serial number?",
       "asset": "What's the asset tag?",
       "days": "How many days? (for example “30 days”)",
       "newgroup": "What should the group's email address be?",
       "newaddress": "What extra address should they get (the full email)?"}


def missing(recipe: Recipe, s: Slots) -> list[str]:
    out = []
    for need in recipe.slots:
        ok = {"user": bool(s.users), "users": bool(s.users), "user2": len(s.users) >= 2,
              "group": bool(s.groups), "ou": bool(s.ous), "serial": bool(s.serials),
              "asset": bool(s.assets), "days": bool(s.days),
              "newgroup": bool(s.other_emails), "newaddress": bool(s.other_emails)}[need]
        if not ok:
            out.append(need)
    return out


RECIPES = _recipes()


def rank(words: set[str], s: Slots) -> list[tuple[float, Recipe]]:
    """Recipes that fit the request, best first."""
    out = []
    for r in RECIPES:
        if not all(words & need for need in r.need):
            continue
        if words & r.avoid:
            continue
        score = 10 * len(r.need) + len(words & r.boost) * 2
        score -= 12 * len(missing(r, s))
        score += sum(1 for n in r.slots if n not in missing(r, s))
        out.append((score, r))
    out.sort(key=lambda x: -x[0])
    return out


def make(r: Recipe, s: Slots, raw: str = "", users: list[dict] | None = None) -> Suggestion:
    s._raw = raw.lower()                                    # type: ignore[attr-defined]
    if s.users and users:
        u = next((x for x in users if x["email"].lower() == s.users[0]), {})
        s._ou_of_user = (u.get("ou") or "").lower()         # type: ignore[attr-defined]
    res = r.build(s)
    title, args, explain = res[:3]
    note = res[3] if len(res) > 3 else ""
    return Suggestion(r.id, title, [str(a) for a in args], explain, r.change, r.page, r.tab,
                      note)

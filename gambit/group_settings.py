"""Google Group permission settings in plain English, plus ready-made presets."""

from __future__ import annotations

import json
import re

ANYONE, DOMAIN, MEMBERS, MANAGERS, OWNERS = (
    "Anyone on the internet", "Anyone in your organization", "Group members",
    "Managers and owners", "Owners only")

# (gam attribute, API field name, question, [(gam value, friendly label), …])
SETTINGS = [
    ("whocanpostmessage", "whoCanPostMessage", "Who can email / post to the group", [
        ("anyone_can_post", ANYONE + " (incl. outside email)"),
        ("all_in_domain_can_post", DOMAIN),
        ("all_members_can_post", MEMBERS),
        ("all_managers_can_post", MANAGERS),
        ("all_owners_can_post", OWNERS),
        ("none_can_post", "No one (archive only)")]),
    ("whocanviewgroup", "whoCanViewGroup", "Who can read the conversations", [
        ("anyone_can_view", ANYONE),
        ("all_in_domain_can_view", DOMAIN),
        ("all_members_can_view", MEMBERS),
        ("all_managers_can_view", MANAGERS),
        ("all_owners_can_view", OWNERS)]),
    ("whocanviewmembership", "whoCanViewMembership", "Who can see the member list", [
        ("all_in_domain_can_view", DOMAIN),
        ("all_members_can_view", MEMBERS),
        ("all_managers_can_view", MANAGERS),
        ("all_owners_can_view", OWNERS)]),
    ("whocanjoin", "whoCanJoin", "Who can join", [
        ("anyone_can_join", ANYONE),
        ("all_in_domain_can_join", DOMAIN),
        ("can_request_to_join", "People in your organization can ask to join"),
        ("invited_can_join", "Only people who are added or invited")]),
    ("whocanmoderatemembers", "whoCanModerateMembers", "Who can add and remove members", [
        ("all_members", "All members"),
        ("owners_and_managers", MANAGERS),
        ("owners_only", OWNERS),
        ("none", "No one")]),
    ("whocancontactowner", "whoCanContactOwner", "Who can contact the group owners", [
        ("anyone_can_contact", ANYONE),
        ("all_in_domain_can_contact", DOMAIN),
        ("all_members_can_contact", MEMBERS),
        ("all_managers_can_contact", MANAGERS),
        ("all_owners_can_contact", OWNERS)]),
    ("whocandiscovergroup", "whoCanDiscoverGroup", "Who can find the group in search", [
        ("anyone_can_discover", ANYONE),
        ("all_in_domain_can_discover", DOMAIN),
        ("all_members_can_discover", MEMBERS)]),
    ("messagemoderationlevel", "messageModerationLevel", "Hold messages for approval", [
        ("moderate_none", "No – deliver right away"),
        ("moderate_non_members", "From non-members"),
        ("moderate_new_members", "From new members"),
        ("moderate_all_messages", "All messages")]),
    ("allowexternalmembers", "allowExternalMembers",
     "Allow members from outside your organization", [("false", "No"), ("true", "Yes")]),
    ("includeinglobaladdresslist", "includeInGlobalAddressList",
     "Show in the directory (Global Address List)", [("true", "Yes"), ("false", "No")]),
]

PRESETS = {
    "Google's defaults (don't change anything)": {},
    "Staff / team group – members talk to each other": {
        "whocanpostmessage": "all_in_domain_can_post",
        "whocanviewgroup": "all_members_can_view",
        "whocanviewmembership": "all_members_can_view",
        "whocanjoin": "invited_can_join",
        "whocanmoderatemembers": "owners_and_managers",
        "allowexternalmembers": "false",
        "messagemoderationlevel": "moderate_none",
    },
    "Announcement list – only owners/managers can send": {
        "whocanpostmessage": "all_managers_can_post",
        "whocanviewgroup": "all_members_can_view",
        "whocanviewmembership": "all_managers_can_view",
        "whocanjoin": "invited_can_join",
        "whocanmoderatemembers": "owners_and_managers",
        "allowexternalmembers": "false",
        "messagemoderationlevel": "moderate_none",
    },
    "Student class / club – members only, no outside email": {
        "whocanpostmessage": "all_members_can_post",
        "whocanviewgroup": "all_members_can_view",
        "whocanviewmembership": "all_managers_can_view",
        "whocanjoin": "invited_can_join",
        "whocanmoderatemembers": "owners_and_managers",
        "whocancontactowner": "all_in_domain_can_contact",
        "whocandiscovergroup": "all_members_can_discover",
        "allowexternalmembers": "false",
        "messagemoderationlevel": "moderate_none",
    },
    "Help / contact address – anyone (even outside) can email it": {
        "whocanpostmessage": "anyone_can_post",
        "whocanviewgroup": "all_managers_can_view",
        "whocanviewmembership": "all_managers_can_view",
        "whocanjoin": "invited_can_join",
        "whocanmoderatemembers": "owners_and_managers",
        "allowexternalmembers": "false",
        "messagemoderationlevel": "moderate_none",
    },
}


def parse_settings(text: str) -> dict:
    """Pull our settings out of `gam info group … formatjson` (or plain) output.

    Returns {gam attribute: gam value} for every setting we recognise.
    """
    wanted = {api.lower(): attr for attr, api, _q, _o in SETTINGS}
    found: dict[str, str] = {}

    def norm(v) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v).strip().lower()

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in wanted and not isinstance(v, (dict, list)):
                    found.setdefault(wanted[key], norm(v))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    start = text.find("{")
    if start >= 0:
        try:
            walk(json.loads(text[start:text.rfind("}") + 1]))
        except ValueError:
            pass
    if not found:  # plain-text fallback:  "  whoCanJoin: INVITED_CAN_JOIN"
        for m in re.finditer(r"^\s*([A-Za-z]+):\s*(\S+)\s*$", text, re.M):
            key = m.group(1).lower()
            if key in wanted:
                found.setdefault(wanted[key], norm(m.group(2)))
    return found


def to_args(values: dict) -> list[str]:
    out: list[str] = []
    for attr, _api, _q, _opts in SETTINGS:
        if values.get(attr):
            out += [attr, values[attr]]
    return out

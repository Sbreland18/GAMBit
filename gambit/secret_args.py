"""Passwords nobody needs to know (the offboarding “lock” password) are never written down:
saved plans, the activity log, previews and dry runs all carry the placeholder TOKEN, and a
fresh random password replaces it only in the argument list handed to gam.exe."""

from __future__ import annotations

import secrets
import string

TOKEN = "{random-lock-password}"
_CHARS = string.ascii_letters + string.digits + "!#%+-.:=?@_~"


WORDS = """
acorn actor adapt agent alarm album alert alien alpha amber angle ankle apple apron
arena armor arrow atlas attic audio autumn avocado badge bagel baker bamboo banjo barn
basil basket beach beacon bean bear beaver berry bike bingo bird biscuit blanket blaze
bloom blossom board boat bonus book boot bottle branch brave bread breeze brick bridge
bright broom bubble bucket buddy bugle bunny butter button cabin cable cactus camel
camera camp candle candy canoe canyon captain carbon cargo carpet carrot castle cedar
cello chalk charm cheese cherry chess chimney cider circle citrus clam clay cliff clock
cloud clover coach coast cobra cocoa comet compass cookie coral cosmic cotton cougar
crane crayon cricket crown crystal cube cupcake curtain daisy dance delta denim desert
diamond dino dolphin donut dragon drum eagle earth echo elbow ember engine falcon
feather fern fiddle field fig finch fire flame flute forest fossil fox frog galaxy
garden garlic gecko giant ginger glacier globe goose grape gravel guitar hammer harbor
hawk hazel helmet heron hiker honey hopper horizon igloo island ivory jacket jaguar
jelly jewel jungle kayak kettle kite koala ladder lagoon lantern laser lemon lilac lion
lizard llama lobster lotus lunar magnet mango maple marble meadow melon meteor mint
mitten moose mosaic motor muffin nectar needle nickel noodle nugget oasis ocean olive
onion orbit orchid otter owl paddle panda paper parrot peach peanut pebble pecan pelican
pepper piano pickle pilot pine pirate pixel planet plum pocket polar pony popcorn potato
prism pumpkin puzzle quartz quill rabbit radar radio rainbow raven rocket rodeo rover
ruby saddle salmon sandal saturn scarf scout shadow shark shell silver skate sketch sled
sloth snow solar sparrow spider sprout squash star storm sugar summit sunny swan taco
tango teapot tiger timber toast tomato topaz torch tractor trail tulip tundra turtle
tuxedo umbrella unicorn valley velvet violin volcano waffle walnut walrus water whale
wheat willow window wizard wolf yarn yeti yogurt zebra zephyr zigzag
""".split()


def readable_password() -> str:
    """Easy to read out and type, still hard to guess: three words from a 320-word list
    and three digits (about 38 bits) – e.g. Maple-otter-comet-482."""
    w = [secrets.choice(WORDS) for _ in range(3)]
    return f"{w[0].title()}-{w[1]}-{w[2]}-{secrets.randbelow(900) + 100}"


def new_password(length: int = 24) -> str:
    while True:
        pw = "".join(secrets.choice(_CHARS) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


# A password chosen when a waiting request finally runs (requests and Run later items
# never hold a real password): whoever runs it is shown the new password.
NEWPW = "{new-password}"


def fill(args: list, collect: list | None = None) -> list[str]:
    """`args` with every TOKEN / NEWPW replaced by its own new random password. NEWPW
    values are added to `collect` as (account, password) so they can be shown once."""
    out, last_user = [], ""
    a = [str(x) for x in args]
    for i, x in enumerate(a):
        if "@" in x and x not in (TOKEN, NEWPW):
            last_user = x                     # the account the password is for
        if x == TOKEN:
            out.append(new_password())
        elif x == NEWPW:
            pw = new_password(14)
            remember(pw)
            if collect is not None:
                collect.append((last_user, pw))
            out.append(pw)
        else:
            out.append(x)
    return out


def literal_passwords(args) -> bool:
    """True if `args` carry a real password value (not a placeholder or a mask)."""
    a = [str(x) for x in args or []]
    return any(x.lower() in _SECRET_WORDS and a[i + 1] not in (TOKEN, NEWPW, MASK)
               and a[i + 1].lower() not in ("random", "uniquerandom", "blocklogin")
               for i, x in enumerate(a[:-1]))


def without_passwords(args) -> list[str]:
    """`args` with every real password value replaced by NEWPW."""
    a = [str(x) for x in args or []]
    for i in range(len(a) - 1):
        if a[i].lower() in _SECRET_WORDS and a[i + 1] not in (TOKEN, NEWPW, MASK):
            a[i + 1] = NEWPW
    return a


def has_token(args) -> bool:
    return any(str(a) == TOKEN for a in args or [])


# Passwords GAMbit put into email text this session (welcome emails, password cards):
# whatever wording a template uses, they're hidden wherever a command is shown or logged.
_KNOWN: dict[str, None] = {}
_KNOWN_MAX = 5000


def remember(secret: str):
    s = str(secret or "")
    if len(s) >= 6:
        _KNOWN.pop(s, None)
        _KNOWN[s] = None
        while len(_KNOWN) > _KNOWN_MAX:
            _KNOWN.pop(next(iter(_KNOWN)))


def hide_known(text: str) -> str:
    if not _KNOWN or not text:
        return text
    for s in _KNOWN:
        if s in text:
            text = text.replace(s, "********")
    return text


import threading

_TL = threading.local()


def generated() -> list:
    """(account, password) pairs made for NEWPW by the last GAM call on this thread."""
    return list(getattr(_TL, "made", []))


def fill_here(args) -> list[str]:
    """fill() for a direct GAM call; the made passwords are kept for generated()."""
    made: list = []
    out = fill(args, made)
    _TL.made = made
    return out


MASK = "********"
SECRET_WORDS = {"password", "newpassword", "notifypassword", "notfoundpassword"}
_SECRET_WORDS = SECRET_WORDS          # one list: hidden in logs, never left in files


def has_placeholder(args) -> bool:
    return any(str(a) in (TOKEN, NEWPW) for a in args or [])


def masked_secret(args) -> bool:
    """True if a password in `args` was blanked out ('********') when it was saved – such a
    command must never run, or that would literally become the password."""
    a = [str(x) for x in args or []]
    return any(x.lower() in _SECRET_WORDS and a[i + 1] == MASK
               for i, x in enumerate(a[:-1]))

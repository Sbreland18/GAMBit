"""A pretend GAM for GAMbit's tests: prints canned CSV for read commands, says "ok" to
changes, and logs every call (one line each) to $FAKEGAM_LOG."""

import os
import sys

USERS = """primaryEmail,name.fullName,suspended,orgUnitPath,lastLoginTime,externalIds.0.type,externalIds.0.value,organizations.0.title,organizations.0.department
jdoe@school.org,Jane Doe,False,/Staff/Teachers,2026-10-12T10:00:00.000Z,,,Teacher,Science
bsmith@school.org,Bob Smith,False,/Students/Grade 5,2026-10-01T10:00:00.000Z,,,,
mjones@school.org,Mary Jones,False,/Students/Grade 5,Never,organization,10001,,
gone@school.org,Gone Kid,False,/Students/Grade 7,2025-01-01T00:00:00.000Z,organization,10009,,
kwhite@school.org,Kim White,False,/Staff,2026-10-10T00:00:00.000Z,,,Principal,Office
"""
GROUPS = """email,name,description,directMembersCount
staff@school.org,All Staff,,120
science@school.org,Science,,3
"""
MEMBERS = """group,email,role,type,status
science@school.org,jdoe@school.org,OWNER,USER,ACTIVE
science@school.org,kwhite@school.org,MEMBER,USER,ACTIVE
science@school.org,bsmith@school.org,MEMBER,USER,ACTIVE
"""
CROS = """deviceId,serialNumber,orgUnitPath,annotatedUser,annotatedLocation,annotatedAssetId,notes
d1,SN1,/Devices,bsmith@school.org,Cart 1,A-1,
"""


def main(argv):
    log = os.environ.get("FAKEGAM_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(" ".join(argv).replace("\n", "\\n") + "\n")
    a = " ".join(argv)
    if a.startswith("select "):
        argv, a = argv[2:], " ".join(argv[2:])
    if a == "version simple":
        print("7.48.20")
    elif a == "info domain":
        print("Customer ID: C123\nPrimary Domain: school.org")
    elif a.startswith("print users"):
        sys.stdout.write(USERS)
    elif a.startswith("print groups"):
        sys.stdout.write(GROUPS)
    elif a.startswith("print group-members"):
        sys.stdout.write(MEMBERS)
    elif a.startswith("cros_sn") and " print cros" in a:
        sys.stdout.write(CROS)
    elif a.startswith("print ") or " print " in a or a.startswith("report "):
        print("id")                       # header only: nothing found
    elif "fail" in a.split():
        print("ERROR: 404: Not found", file=sys.stderr)
        return 1
    else:
        print("ok: " + a, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

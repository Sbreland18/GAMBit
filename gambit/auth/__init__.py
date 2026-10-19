"""GAMbit sign-in and access control.

* Everyone signs in with their district Google account (OAuth 2.0 with PKCE, ID token
  checked locally against Google's keys, restricted to the district's domain).
* One emergency admin per computer can sign in with a long password plus an authenticator
  code if Google sign-in is unavailable. It exists only on the PC where it was set up.
* Who may sign in, their role, page access and org-unit scope live in an access list in the
  team folder, signed with an admin's Ed25519 key. Each PC pins the admin keys it trusts and
  the newest version it has seen, so the file can't be edited or rolled back by hand.

What this protects: what people can see and do inside GAMbit. GAM itself runs with the
credentials configured on each PC, so for staff who must not have full access, give their
role a GAM profile that uses a delegated admin account with a matching Google admin role
(see the Guide → Sign-in and access).
"""

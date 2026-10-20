"""Single source of truth for the app version and update locations.

The Builder GUI rewrites __version__ automatically when you build a release.
"""

APP_NAME = "GAMbit"
__version__ = "1.1.2"

# GitHub project that hosts GAMbit releases and latest.json
GITHUB_REPO = "Sbreland18/GAMbit"
GITHUB_BRANCH = "main"

# The app checks this file to see if a newer GAMbit is available.
LATEST_JSON_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/latest.json"
)

# Beta testers (Settings → Update channel: Beta) also check this one
LATEST_BETA_JSON_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/latest-beta.json"
)

# Upstream GAM project (the command-line tool this GUI drives)
GAM_REPO = "GAM-team/GAM"
GAM_LATEST_RELEASE_API = f"https://api.github.com/repos/{GAM_REPO}/releases/latest"

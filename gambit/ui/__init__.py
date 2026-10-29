
# Labels never render unchecked HTML from Google / tickets / the team folder.
from .safe_html import install_label_guard as _guard  # noqa: E402

_guard()

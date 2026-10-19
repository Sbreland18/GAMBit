import os
import sys


def resource_path(relative: str) -> str:
    """Path to a bundled file, working both from source and from PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative)

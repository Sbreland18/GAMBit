"""A small cross-PC lock for read-modify-write of shared JSON files (the team folder is a
plain network share, so two GAMbits – or GAMbit and its background task – can otherwise
both read, both change and the last one to save wins)."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import time


@contextlib.contextmanager
def held(path: str, wait: float = 15.0, stale: float = 600.0):
    """Hold `path` (a .lock file) for the block. A lock older than `stale` seconds is from a
    GAMbit that stopped half-way and is taken over. Raises TimeoutError after `wait`."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    end = time.time() + wait
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > stale:
                    os.remove(path)
                    continue
            except OSError:
                continue                      # it just went away – try again
            if time.time() > end:
                raise TimeoutError(f"{os.path.basename(path)} is busy – try again in a moment.")
            time.sleep(0.1)
    try:
        os.write(fd, json.dumps({"pc": socket.gethostname(), "pid": os.getpid(),
                                 "at": time.time()}).encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

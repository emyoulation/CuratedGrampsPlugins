#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
"""
Environment Inspector - Gramps language for the next start (no GTK).

Gramps chooses its interface language once, at startup, from the
LANGUAGE environment variable. Gramps 6.0 has no language preference, so
a language override is applied in two ways:

- Restart now: start a new Gramps with LANGUAGE set, after this Gramps
  has quit normally (backup on exit included).
- The next start from the desktop menu (Linux), when "Later" is chosen:
  a one-shot user copy of the Gramps desktop entry whose Exec line sets
  LANGUAGE. Environment Inspector removes it again when the next Gramps
  loads it, so the language choice is a one-off. The copy carries a
  marker line, so only a copy made here is ever changed or removed.
  Starting Gramps from a terminal is not affected.
"""

import os
import subprocess
import sys

MARKER = "X-EnvironmentInspector-Override"
DESKTOP_NAMES = ("org.gramps_project.Gramps.desktop", "gramps.desktop")


def is_linux():
    return sys.platform.startswith("linux")


def _data_dirs():
    dirs = os.environ.get("XDG_DATA_DIRS", "") or "/usr/local/share:/usr/share"
    return [d for d in dirs.split(":") if d]


def find_system_desktop():
    """Path of the installed Gramps desktop entry, or None."""
    for base in _data_dirs():
        for name in DESKTOP_NAMES:
            path = os.path.join(base, "applications", name)
            if os.path.isfile(path):
                return path
    return None


def user_desktop_path(name):
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(home, "applications", name)


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def desktop_override_code():
    """The language code in our desktop-entry copy, or ""."""
    system = find_system_desktop()
    if not system:
        return ""
    user = user_desktop_path(os.path.basename(system))
    if not os.path.isfile(user):
        return ""
    for line in _read(user).splitlines():
        if line.startswith(MARKER + "="):
            return line.split("=", 1)[1].strip()
    return ""


def apply_desktop_override(code):
    """
    Write (code) or remove ("") the desktop-entry copy.

    :returns: (success, message)
    """
    if not is_linux():
        return False, "desktop entries are only changed on Linux"
    system = find_system_desktop()
    if not system:
        return False, "no installed Gramps desktop entry was found"
    user = user_desktop_path(os.path.basename(system))
    if os.path.isfile(user) and MARKER not in _read(user):
        return False, "%s is your own copy; it was not changed" % user
    if not code:
        if os.path.isfile(user):
            os.remove(user)
            return True, "removed %s" % user
        return True, "nothing to remove"
    out = []
    for line in _read(system).splitlines():
        if line.startswith("Exec="):
            line = "Exec=env LANGUAGE=%s %s" % (code, line[len("Exec=") :])
        out.append(line)
        if line.strip() == "[Desktop Entry]":
            out.append("%s=%s" % (MARKER, code))
    os.makedirs(os.path.dirname(user), exist_ok=True)
    with open(user, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    return True, "wrote %s" % user


def can_restart():
    return os.name == "posix"


def spawn_restart(code, log_path=None, extra_args=None):
    """
    Start a new Gramps that waits until this process has exited.

    The caller must then quit this Gramps normally. The new Gramps writes
    its terminal output to log_path (if given) instead of the terminal,
    which the shell has taken back by then.
    :returns: True if the new process was started.
    """
    if not can_restart():
        return False
    env = os.environ.copy()
    if code:
        env["LANGUAGE"] = code
    else:
        env.pop("LANGUAGE", None)
    argv = list(getattr(sys, "orig_argv", None) or [sys.executable] + sys.argv)
    # Reopen the current tree, unless the command already names one.
    if extra_args and not any(
        arg in ("-O", "--open") or arg.startswith("--open=") for arg in argv
    ):
        argv += list(extra_args)
    script = 'while kill -0 "$0" 2>/dev/null; do sleep 0.5; done; exec "$@"'
    output = None
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        output = open(log_path, "w", encoding="utf-8")
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", script, str(os.getpid())] + argv,
            env=env,
            start_new_session=True,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT if output else None,
        )
    finally:
        if output:
            output.close()  # the new process keeps its own copy
    return True

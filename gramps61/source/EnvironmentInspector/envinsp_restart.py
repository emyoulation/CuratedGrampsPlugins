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

Gramps chooses its interface language once, at startup. Gramps 6.0 has no
language preference, so an override is applied from outside:

- LANGUAGE picks the interface translation. LANG picks the full locale
  (dates, numbers, sorting, the spelling dictionary, and GTK's own
  locale), so a full locale such as nl_BE.UTF-8 is set together with it
  when one is chosen.
- Restart now: start a new Gramps after this Gramps has quit normally
  (backup on exit included).
  Linux and other POSIX systems: a small shell waits for this process and
  then runs the same command again with the new environment.
  macOS application bundle: the same wait, then "open -a Gramps.app",
  the way the Finder starts it.
  Windows: PowerShell waits for this process (Gramps for Windows allows
  only one Gramps at a time) and then starts the same program again.
- Later (the next start from the desktop):
  Linux: a one-shot user copy of the Gramps desktop entry whose Exec line
  sets the variables. macOS bundle: the per-application language and
  region of Gramps in the macOS defaults system (the same setting as
  System Settings > General > Language & Region > Applications), which
  Gramps reads at startup. Environment Inspector removes or restores
  these again when the next Gramps loads it, so the choice is a one-off.
  Only a copy or a value made here is ever changed or removed.
  Windows has no such mechanism here.

Gramps writes LANG and LANGUAGE back into its own environment at
startup, so the environment of this process no longer shows how Gramps
was started. baseline_locale_env() recovers that.
"""

import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys

MARKER = "X-EnvironmentInspector-Override"
DESKTOP_NAMES = ("org.gramps_project.Gramps.desktop", "gramps.desktop")
# The locale variables a restart sets or restores.
LOCALE_VARS = ("LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES")
MAC_DOMAIN = "org.gramps-project.gramps"  # as read by gramps/gen/utils/maclocale.py
DEFAULTS = "/usr/bin/defaults"


def is_linux():
    return sys.platform.startswith("linux")


def is_mac():
    return sys.platform == "darwin"


def is_windows():
    return sys.platform == "win32"


# ------------------------------------------------------------
# The locale variables of a normal start
# ------------------------------------------------------------
def _startup_environ():
    """
    The environment this process started with (Linux), or None.

    /proc/self/environ keeps the original block; later changes to
    os.environ (such as the LANG and LANGUAGE that Gramps writes back) are
    stored elsewhere and do not show there.
    """
    try:
        with open("/proc/self/environ", "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    env = {}
    for item in data.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            env[key.decode(errors="replace")] = value.decode(errors="replace")
    return env


def _windows_persistent(name):
    """A user or system environment variable as stored in the registry."""
    try:
        import winreg
    except ImportError:
        return None
    for root, path in (
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                value = winreg.QueryValueEx(key, name)[0]
                if value:
                    return str(value)
        except OSError:
            continue
    return None


def _launchctl_getenv(name):
    """A variable set for all macOS applications with launchctl setenv."""
    try:
        out = subprocess.run(
            ["/bin/launchctl", "getenv", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def baseline_locale_env():
    """
    LANG, LANGUAGE, LC_ALL and LC_MESSAGES as they were when Gramps was
    started normally.

    :returns: name -> value, for the variables that were set.
    """
    start = _startup_environ()
    if start is not None:
        return {key: start[key] for key in LOCALE_VARS if key in start}
    result = {}
    for key in ("LANG", "LANGUAGE"):
        if is_windows():
            value = _windows_persistent(key)
        elif is_mac():
            value = _launchctl_getenv(key)
        else:
            value = None
        if value:
            result[key] = value
    # Gramps does not write these two, so their current values are the
    # original ones.
    for key in ("LC_ALL", "LC_MESSAGES"):
        if os.environ.get(key):
            result[key] = os.environ[key]
    return result


def restart_env(code, locale_name, baseline):
    """
    The environment for the next Gramps.

    :param code: translation code (LANGUAGE), or "" for the system language.
    :param locale_name: full locale for LANG, or "" to keep the regional
        settings of a normal start.
    :param baseline: the result of baseline_locale_env().
    """
    env = os.environ.copy()
    for key in LOCALE_VARS:
        env.pop(key, None)
    env.update(baseline)
    if code:
        env["LANGUAGE"] = code
        if locale_name:
            env["LANG"] = locale_name
            env.pop("LC_ALL", None)  # it would override LANG
    return env


# ------------------------------------------------------------
# Full locales (LANG) for a translation
# ------------------------------------------------------------
def _lang_part(code):
    return code.split("_")[0].split("@")[0].split(".")[0]


def _locale_base(name):
    """nl_BE.UTF-8@euro -> nl_BE"""
    return name.split(".")[0].split("@")[0]


def _linux_locales():
    try:
        out = subprocess.run(
            ["locale", "-a"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in out.split():
        if ".utf8" in line.lower() or ".utf-8" in line.lower():
            head, _dot, tail = line.partition(".")
            modifier = tail.partition("@")[2]
            names.append(head + ".UTF-8" + ("@" + modifier if modifier else ""))
    return names


def _mac_locales():
    try:
        entries = os.listdir("/usr/share/locale")
    except OSError:
        return []
    return [name for name in entries if name.endswith(".UTF-8")]


def region_locales(code):
    """
    Full locales for LANG that fit a translation, sorted by name;
    default_locale() picks the one to preselect.

    On Windows, Gramps pairs each language with one Windows locale
    (win32locale._LOCALE_NAMES) and ignores the region in LANG, so the
    only choice is the translation code itself.
    """
    if is_windows():
        return [code]
    names = _mac_locales() if is_mac() else _linux_locales()
    lang = _lang_part(code)
    found = sorted(
        {name for name in names if "_" in name and _lang_part(name) == lang},
        key=str.casefold,
    )
    return found


def default_locale(code, candidates, region_hint="", baseline_lang=""):
    """
    The locale to preselect: the region in the translation code (pt_BR),
    else the region of the normal start (fr_BE -> nl_BE), else the region
    Gramps pairs with the language (region_hint), else xx_XX.
    """
    if not candidates:
        return ""
    by_base = {}
    for name in candidates:
        by_base.setdefault(_locale_base(name), name)
    lang = _lang_part(code)
    wanted = []
    parts = code.split("_")
    if len(parts) > 1 and len(parts[1]) == 2:
        wanted.append(code)
    base = _locale_base(baseline_lang or "")
    if "_" in base:
        wanted.append("%s_%s" % (lang, base.split("_")[1]))
    if region_hint:
        wanted.append("%s_%s" % (lang, region_hint.upper()))
    if lang == "en":
        wanted.append("en_US")
    wanted.append("%s_%s" % (lang, lang.upper()))
    for want in wanted:
        if want in by_base:
            return by_base[want]
    return candidates[0]


# ------------------------------------------------------------
# Linux: one-shot desktop entry
# ------------------------------------------------------------
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


def apply_desktop_override(code, locale_name=""):
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
    assign = ["LANGUAGE=%s" % code]
    if locale_name:
        assign = ["-u", "LC_ALL"] + assign + ["LANG=%s" % locale_name]
    out = []
    for line in _read(system).splitlines():
        if line.startswith("Exec="):
            line = "Exec=env %s %s" % (" ".join(assign), line[len("Exec=") :])
        out.append(line)
        if line.strip() == "[Desktop Entry]":
            out.append("%s=%s" % (MARKER, code))
    os.makedirs(os.path.dirname(user), exist_ok=True)
    with open(user, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    return True, "wrote %s" % user


# ------------------------------------------------------------
# macOS: application bundle and per-application defaults
# ------------------------------------------------------------
def mac_bundle():
    """Path of the Gramps.app bundle this Gramps runs from, or None."""
    if not is_mac():
        return None
    candidates = (
        sys.argv[0] if sys.argv else "",  # gramps_launcher.py: the bundle path
        os.environ.get("GRAMPS_RESOURCES", ""),
        sys.executable or "",
    )
    for cand in candidates:
        path = os.path.abspath(cand) if cand else ""
        while path and path != os.path.dirname(path):
            if path.endswith(".app") and os.path.isdir(path):
                return path
            path = os.path.dirname(path)
    return None


def _mac_domain():
    try:
        out = subprocess.run(
            [DEFAULTS, "export", MAC_DOMAIN, "-"],
            capture_output=True,
            timeout=10,
            check=False,
        ).stdout
        return plistlib.loads(out) if out else {}
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
        return {}
    except Exception:  # an unreadable domain counts as empty
        return {}


def _mac_write(key, value):
    if value is None:
        args = [DEFAULTS, "delete", MAC_DOMAIN, key]
    elif isinstance(value, list):
        args = [DEFAULTS, "write", MAC_DOMAIN, key, "-array"] + [str(v) for v in value]
    else:
        args = [DEFAULTS, "write", MAC_DOMAIN, key, "-string", str(value)]
    subprocess.run(args, capture_output=True, timeout=10, check=False)


def apply_mac_defaults(code, locale_name, saved):
    """
    Set (code) or restore ("") the per-application language and region
    of Gramps.

    :param saved: JSON text of the values that were there before a change
        made here, or "" if nothing was changed here.
    :returns: (success, message, saved) with the new saved text.
    """
    if not mac_bundle():
        return False, "not running from a Gramps application bundle", saved
    if not code:
        if not saved:
            return True, "nothing to restore", ""
        try:
            before = json.loads(saved)
        except ValueError:
            before = {}
        for key, value in before.items():
            _mac_write(key, value)
        return True, "restored the macOS language settings of Gramps", ""
    if not saved:
        current = _mac_domain()
        saved = json.dumps(
            {key: current.get(key) for key in ("AppleLanguages", "AppleLocale")}
        )
    _mac_write("AppleLanguages", [code])
    # AppleLocale is used only when LANG is not set (a start from the
    # Finder or the Dock). Gramps keeps only its language part.
    if locale_name:
        _mac_write("AppleLocale", _locale_base(locale_name))
    else:
        try:
            _mac_write("AppleLocale", json.loads(saved).get("AppleLocale"))
        except ValueError:
            pass
    return True, "set the macOS language of Gramps to %s" % code, saved


# ------------------------------------------------------------
# Restart now
# ------------------------------------------------------------
def _powershell():
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if found:
        return found
    path = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    return path if os.path.isfile(path) else None


def can_restart():
    if is_windows():
        return _powershell() is not None
    return os.name == "posix"


def supports_next_start():
    """True when "Later" can make the next desktop start use the language."""
    if is_linux():
        return find_system_desktop() is not None
    return mac_bundle() is not None


def restart_writes_log():
    """True when the terminal output of the restarted Gramps goes to a log."""
    return os.name == "posix"


def _command_argv(extra_args):
    """The command that started this Gramps, plus extra_args."""
    if getattr(sys, "frozen", False):  # Gramps for Windows (cx_Freeze)
        argv = [sys.executable] + sys.argv[1:]
    else:
        argv = list(getattr(sys, "orig_argv", None) or [sys.executable] + sys.argv)
    # Reopen the current tree, unless the command already names one.
    if extra_args and not any(
        arg in ("-O", "--open") or arg.startswith("--open=") for arg in argv
    ):
        argv += list(extra_args)
    return argv


def _log_header(code, locale_name, argv=None):
    """First line of the restart log: what Environment Inspector asked for."""
    import time

    text = "Environment Inspector restart, %s UTC: LANGUAGE=%s, LANG=%s" % (
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        code or "(system)",
        locale_name or "(unchanged)",
    )
    if argv:
        text += ", command: " + shlex.join(argv)
    return text


def _open_log(log_path, header=""):
    if not log_path:
        return None
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    handle = open(log_path, "w", encoding="utf-8")
    if header:
        handle.write(header + "\n")
        handle.flush()  # before the new process writes to the same file
    return handle


def _spawn_posix(script, env, log_path, argv=(), header=""):
    """Run script with $0 = this process id and $@ = argv, detached."""
    output = _open_log(log_path, header)
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", script, str(os.getpid())] + list(argv),
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


_WAIT = 'while kill -0 "$0" 2>/dev/null; do sleep 0.5; done; '


def _spawn_mac_bundle(bundle, env, code, locale_name, extra_args, log_path):
    """
    Start the bundle again with open, the way the Finder does. open does
    not always pass its own environment on to the application, so the
    variables are also given with --env, and the messages of the new
    Gramps go to the log with --stdout and --stderr. Older versions of
    open do not know these options, so the plain command is the fallback;
    the log then holds only messages from open itself.
    """
    plain = ["/usr/bin/open", "-n", "-a", bundle]
    with_env = list(plain)
    if code:
        with_env += ["--env", "LANGUAGE=%s" % code]
        if locale_name:
            with_env += ["--env", "LANG=%s" % locale_name]
    if log_path:
        # Messages of the new Gramps (open in macOS 10.15 and later).
        with_env += ["--stdout", log_path, "--stderr", log_path]
    tail = ["--args"] + list(extra_args) if extra_args else []
    script = _WAIT + shlex.join(with_env + tail)
    if with_env != plain:
        script += " || " + shlex.join(plain + tail)
    return _spawn_posix(script, env, log_path, header=_log_header(code, locale_name))


def _spawn_windows(env, argv):
    """
    PowerShell waits until this Gramps has exited, then starts it again.
    The program and its arguments travel in environment variables, so no
    quoting can go wrong; they are removed before Gramps starts.
    """
    env = dict(env)
    env["ENVINSP_EXE"] = argv[0]
    env["ENVINSP_ARGS"] = subprocess.list2cmdline(argv[1:])
    env["ENVINSP_CWD"] = os.getcwd()
    script = (
        "try { Wait-Process -Id %d -ErrorAction Stop } catch {}; "
        "Start-Sleep -Milliseconds 500; "
        "$a = @{ FilePath = $env:ENVINSP_EXE; WorkingDirectory = $env:ENVINSP_CWD }; "
        "if ($env:ENVINSP_ARGS) { $a.ArgumentList = $env:ENVINSP_ARGS }; "
        "Remove-Item Env:ENVINSP_EXE, Env:ENVINSP_ARGS, Env:ENVINSP_CWD; "
        "Start-Process @a" % os.getpid()
    )
    command = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-Command",
        script,
    ]
    create_no_window = 0x08000000
    new_group = 0x00000200
    breakaway = 0x01000000  # survive a job object that ends with Gramps
    for flags in (create_no_window | new_group | breakaway, create_no_window | new_group):
        try:
            subprocess.Popen(
                command,
                env=env,
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            continue
    return False


def spawn_restart(code, locale_name, baseline, log_path=None, extra_args=None):
    """
    Start a new Gramps that waits until this process has exited.

    The caller must then quit this Gramps normally. On Linux and other
    POSIX systems the new Gramps writes its terminal output to log_path
    (if given) instead of the terminal, which the shell has taken back by
    then.
    :returns: True if the new process was started.
    """
    if not can_restart():
        return False
    env = restart_env(code, locale_name, baseline)
    if is_windows():
        return _spawn_windows(env, _command_argv(extra_args))
    bundle = mac_bundle()
    if bundle:
        return _spawn_mac_bundle(bundle, env, code, locale_name, extra_args, log_path)
    argv = _command_argv(extra_args)
    return _spawn_posix(
        _WAIT + 'exec "$@"', env, log_path, argv, _log_header(code, locale_name, argv)
    )

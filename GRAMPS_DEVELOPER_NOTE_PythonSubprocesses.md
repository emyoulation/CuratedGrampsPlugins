# Developer Note: Using Python Subprocesses in Gramps Addons

**Author**: Claude (Anthropic AI)  
**Contributor**: Brian McCullough  
**Date**: February 17, 2026  
**Applies to**: Gramps 5.2.x, Gramps 6.0.x (desktop versions)  
**Status**: Current as of February 2026

---

**Note**: This document addresses a specific issue with Python subprocess calls in Gramps addon development. Future versions of Gramps may provide improved Python environment detection or alternative APIs that supersede this guidance. Always check current Gramps developer documentation for the latest best practices.

---

## The Problem: "Python was not found"

When developing Gramps addons, a common error appears when trying to run Python scripts as subprocesses:

```
Error: Python was not found; run without arguments to install from 
the Microsoft Store, or disable this shortcut from Settings > Apps...
```

This error occurs even though Gramps is running Python successfully. **Why?**

## Root Cause

Gramps bundles its own Python interpreter, especially on **Windows** and **macOS**:

- **Windows AIO**: Python is embedded in `C:\Program Files\GrampsAIO64-5.2.0\gramps\bin\`
- **macOS Bundle**: Python is inside the Gramps.app package
- **Linux**: Usually uses system Python, but not always

When you write code like this:

```python
import subprocess

# ❌ WRONG - Will fail on Windows/macOS bundled installations
result = subprocess.run(['python3', 'myscript.py'])
```

The `'python3'` command **does not exist** in the system PATH. It only exists in your development environment!

## The Solution: Use `sys.executable`

**Always use `sys.executable`** to run Python scripts from within Gramps:

```python
import sys
import subprocess

# ✅ CORRECT - Works on all platforms and installations
result = subprocess.run([sys.executable, 'myscript.py'])
```

**What is `sys.executable`?**

It's the **full path to the Python interpreter currently running your code**:

- **Windows Gramps**: `C:\Program Files\GrampsAIO64-5.2.0\gramps\bin\python.exe`
- **Linux**: `/usr/bin/python3` (or wherever Python is installed)
- **macOS Gramps**: `/Applications/Gramps.app/Contents/MacOS/python`
- **Development**: Whatever Python is running your test environment

It **always points to the correct Python** for that Gramps installation.

## Common Mistake Patterns

### ❌ Don't Do This:
```python
subprocess.run(['python', 'script.py'])           # Fails on many Windows systems
subprocess.run(['python3', 'script.py'])          # Fails on Windows Gramps
subprocess.run(['/usr/bin/python3', 'script.py']) # Fails on Windows, hardcoded path
```

### ✅ Do This Instead:
```python
subprocess.run([sys.executable, 'script.py'])     # Works everywhere
```

## Why This Catches Developers

1. **Works in development**: Your Linux/Mac dev environment has `python3` in PATH
2. **Breaks in production**: Windows users with Gramps AIO don't have `python3` 
3. **Hard to debug**: Error message talks about Microsoft Store, not the real issue
4. **Not obvious**: Gramps runs fine, so you assume Python is accessible

## Testing Your Addon

Before releasing, **always test on Windows** with a standard Gramps AIO installation:

```python
import sys
print(f"Python executable: {sys.executable}")
# Verify this works on Windows, Linux, and macOS
```

## Real-World Example: AddonPackShip

The AddonPackShip tool had this exact bug in v1.5.3. **All operations failed on Windows**:

```python
# v1.5.3 - BROKEN on Windows:
cmd = ['python3', make_script, command, addon_path, output_dir]

# v1.5.4 - FIXED for all platforms:
cmd = [sys.executable, make_script, command, addon_path, output_dir]
```

One line change, complete fix. The lesson: **Always use `sys.executable` for subprocess calls to Python**.

## Quick Reference

| Scenario | Use | Don't Use |
|----------|-----|-----------|
| Run Python script | `sys.executable` | `'python'` or `'python3'` |
| Run system command | `'msgfmt'`, `'git'` | Hardcoded paths |
| Run Gramps tool | Let Gramps API handle it | Subprocess to Gramps |

## Further Reading

**For Learning Developers:**
1. **Python subprocess module**: https://docs.python.org/3/library/subprocess.html - Official Python documentation on running subprocesses
2. **Gramps Addon Tutorial**: https://gramps-project.org/wiki/index.php/5.2_Addons - Start here for Gramps addon development basics
3. **Cross-platform Python**: https://docs.python.org/3/library/sys.html#sys.executable - Understanding `sys.executable` and platform differences
4. **Gramps Developer Guide**: https://gramps-project.org/wiki/index.php/Portal:Developers - Complete guide to Gramps development practices

**For Advanced Developers:**
5. **Gramps Plugin API Reference**: https://gramps-project.org/docs/ - Technical reference for Gramps plugin architecture and available APIs

---

**Remember**: Gramps is **not** a normal Python environment. It bundles dependencies, runs in isolation on some platforms, and your addon needs to work with **that** Python, not the system Python. Always use `sys.executable` for subprocess calls.

---

## Document Information

**Version**: 1.0  
**Created**: February 17, 2026  
**Author**: Claude (Anthropic AI), with contributions from Brian McCullough  
**Verified On**:
- Gramps 5.2.3 (Windows 10 AIO, Fedora Linux, macOS)
- Gramps 6.0.0-beta (preliminary testing)

**Feedback**: Report issues or suggestions for this document through Gramps Discourse forums

**License**: This document is provided under CC BY 4.0 (Creative Commons Attribution 4.0 International). You are free to share and adapt this content with appropriate attribution.

**Related Tools**: This issue was discovered and resolved during development of AddonPackShip v1.5.4 (Gramps addon packaging tool)

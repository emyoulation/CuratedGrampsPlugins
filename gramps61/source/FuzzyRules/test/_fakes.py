"""
Shared test doubles for phonexrule_test.py, doublemetaphonerule_test.py
and daitchmokotoffrule_test.py. Not itself a test module (no _test.py
suffix), so ``unittest discover`` won't try to run it directly.
"""

import sys
import types


def install_gramps_stand_ins():
    """
    Install minimal stand-ins for the pieces of Gramps these rule
    modules import at load time - but only if a real Gramps isn't
    already importable, so these tests exercise the real base class
    wherever Gramps is actually installed (e.g. on the maintainer's own
    Fedora VM) and fall back to a stand-in only where it isn't.
    """
    try:
        import gramps.gen.filters.rules  # noqa: F401

        return
    except ImportError:
        pass

    gramps_mod = types.ModuleType("gramps")
    gen_mod = types.ModuleType("gramps.gen")
    const_mod = types.ModuleType("gramps.gen.const")
    filters_mod = types.ModuleType("gramps.gen.filters")
    rules_mod = types.ModuleType("gramps.gen.filters.rules")
    # phonetic_name_parts.py imports Name/Person from here for its own
    # type hints only - it never instantiates them, so a placeholder is
    # enough to satisfy the import.
    lib_mod = types.ModuleType("gramps.gen.lib")
    lib_mod.Name = type("Name", (), {})
    lib_mod.Person = type("Person", (), {})

    class _FakeLocale:
        def get_addon_translator(self, _file):
            raise ValueError("no translator in the stand-in locale")

        class translation:
            @staticmethod
            def gettext(text):
                return text

    const_mod.GRAMPS_LOCALE = _FakeLocale()

    class _FakeRule:
        """
        Stand-in for gramps.gen.filters.rules.Rule - just enough of the
        real base class (an __init__ that calls set_list()) for these
        rules' own set_list()/prepare()/apply_to_one() overrides to run
        exactly as they would against the real thing.
        """

        def __init__(self, arg, use_regex=False, use_case=False):
            self.use_regex = use_regex
            self.use_case = use_case
            self.set_list(arg)

        def set_list(self, arg):
            self.list = list(arg or [])

    rules_mod.Rule = _FakeRule

    sys.modules.setdefault("gramps", gramps_mod)
    sys.modules.setdefault("gramps.gen", gen_mod)
    sys.modules.setdefault("gramps.gen.const", const_mod)
    sys.modules.setdefault("gramps.gen.filters", filters_mod)
    sys.modules.setdefault("gramps.gen.filters.rules", rules_mod)
    sys.modules.setdefault("gramps.gen.lib", lib_mod)


class FakeSurname:
    """Stand-in for gramps.gen.lib.Surname."""

    def __init__(self, surname="", prefix=""):
        self._surname = surname
        self._prefix = prefix

    def get_surname(self):
        return self._surname

    def get_prefix(self):
        return self._prefix


class FakeName:
    """Stand-in for gramps.gen.lib.Name - only the accessors
    phonetic_name_parts.person_words() (or a rule's own no-name-parts
    fallback) actually calls."""

    def __init__(
        self,
        surname="",
        given="",
        call="",
        nick="",
        title="",
        suffix="",
        family_nick="",
        prefix="",
        extra_surnames=(),
    ):
        self._surnames = [FakeSurname(surname, prefix)] + [
            FakeSurname(s) for s in extra_surnames
        ]
        self._given = given
        self._call = call
        self._nick = nick
        self._title = title
        self._suffix = suffix
        self._family_nick = family_nick

    def get_surname_list(self):
        return self._surnames

    def get_first_name(self):
        return self._given

    def get_call_name(self):
        return self._call

    def get_nick_name(self):
        return self._nick

    def get_title(self):
        return self._title

    def get_suffix(self):
        return self._suffix

    def get_family_nick_name(self):
        return self._family_nick


class FakePerson:
    """Stand-in for gramps.gen.lib.Person - just the primary/alternate
    name accessors."""

    def __init__(self, primary_name, alternate_names=()):
        self._primary = primary_name
        self._alternates = list(alternate_names)

    def get_primary_name(self):
        return self._primary

    def get_alternate_names(self):
        return self._alternates

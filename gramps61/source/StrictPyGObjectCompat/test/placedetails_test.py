"""
Unittests for the Place Details gramplet.

Before PyGObject 3.55.0 (stable 3.56.0), a non-string object passed as a
Gtk string property, such as Gtk.Label(label=PlaceType), was silently
converted with str(). PyGObject MR !469 ("Unify properties handling") made
constructor keyword arguments use strict typed conversion, so it now raises:

    TypeError: Must be string, not PlaceType

These tests replace Gtk.Label inside the gramplet module with a label that
is strict in the same way, so the problem is caught on every PyGObject
version and without a display. Regression test for Mantis 0014183.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from gramps.gen.lib import Place, PlaceName, PlaceType  # noqa: E402
from gramps.plugins.gramplet import placedetails  # noqa: E402
from gramps.plugins.gramplet.placedetails import PlaceDetails  # noqa: E402


class StrictLabel:
    """
    Stand-in for Gtk.Label that, like PyGObject 3.56+, accepts only str or
    None for its label, and records every label it was given.
    """

    created = []

    def __init__(self, label=None, **kwargs):
        if label is not None and not isinstance(label, str):
            raise TypeError("Must be string, not %s" % type(label).__name__)
        self.label = label
        StrictLabel.created.append(self)

    def set_markup(self, markup):
        pass

    def set_selectable(self, setting):
        pass

    def show(self):
        pass


def make_place():
    """Return a Place with a typed name, coordinates and alternative names."""
    place = Place()
    name = PlaceName()
    name.set_value("Springfield")
    place.set_name(name)
    place.set_type(PlaceType(PlaceType.CITY))
    place.set_latitude("39.7817")
    place.set_longitude("-89.6501")
    alt = PlaceName()
    alt.set_value("Calhoun")
    alt.set_language("en")
    place.add_alternative_name(alt)
    return place


class TestPlaceDetailsStrictLabels(unittest.TestCase):
    """display_place must hand only strings to Gtk.Label."""

    def setUp(self):
        StrictLabel.created = []
        fake_gtk = SimpleNamespace(
            Label=StrictLabel,
            Align=Gtk.Align,
            PositionType=Gtk.PositionType,
        )
        for target, value in (
            ("Gtk", fake_gtk),
            ("place_displayer", mock.Mock(display=lambda db, place: "Springfield")),
        ):
            patcher = mock.patch.object(placedetails, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # Build the gramplet without its GUI; only what display_place uses.
        self.gramplet = PlaceDetails.__new__(PlaceDetails)
        self.gramplet.dbstate = mock.Mock()
        self.gramplet.uistate = mock.Mock()
        self.gramplet.photo = mock.Mock()
        self.gramplet.title = mock.Mock()
        self.gramplet.grid = mock.Mock()
        self.gramplet.grid.get_children.return_value = []

    def test_display_place_passes_strings(self):
        try:
            self.gramplet.display_place(make_place())
        except TypeError as err:
            self.fail(
                "display_place passed a non-string to Gtk.Label (%s). "
                "Convert values such as PlaceType with str()." % err
            )

    def test_type_row_shows_type_name(self):
        self.gramplet.display_place(make_place())
        labels = [label.label for label in StrictLabel.created]
        self.assertIn(str(PlaceType(PlaceType.CITY)), labels)
        self.assertIn("Springfield", labels)

    def test_custom_place_type(self):
        place = make_place()
        place.set_type(PlaceType((PlaceType.CUSTOM, "Hamlet")))
        self.gramplet.display_place(place)
        labels = [label.label for label in StrictLabel.created]
        self.assertIn("Hamlet", labels)


if __name__ == "__main__":
    unittest.main()

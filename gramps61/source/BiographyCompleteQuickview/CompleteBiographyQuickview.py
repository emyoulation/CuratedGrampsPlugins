#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2017       A. Guinane
# Copyright (C) 2026       Brian McCullough
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
#
"""
Display a fuller text biography of a person: the events, families,
attributes and notes of the Complete Individual Report, told in the
informal running-prose style of the Biography quick view.

Forked from BiographyQuickview.py (A. Guinane, 2017).

Naming conventions used here (see the addon's README for the reasoning):

* The header uses the person's preferred name as of their date of death,
  in "Title Given "Call" Surname Suffix" form.
* The birth sentence uses the person's *birth* name instead, in the
  plainer "Given Surname, Suffix" form, with no title or call name.
* Every other sentence refers to the person by their common (call) name.
* When a mother is introduced alongside a father (the subject's own
  parents, or a spouse's parents), she is introduced as
  "the former <her name>" to flag that her birth surname is being used.

Privacy: anything marked private in the database (a person, a name, an
event, a place, an address, a media reference, an attribute, a note, an
LDS ordinance, a citation, or an association) is left out. Where that
omission changes what a sentence says -- a name had to be swapped out,
or a date/place had to be dropped -- the sentence gets a trailing
footnote marker; a single explanatory footnote is added at the end of
the report if that happened anywhere. Simple list-trimming (dropping
one private item out of several) is silent, but still counts toward
whether that closing footnote appears.
"""

#------------------------------------------------------------------------
#
# Internationalisation
#
#------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
try:
    trans = glocale.get_addon_translator(__file__)
except ValueError:
    trans = glocale.translation
_ = trans.gettext

from gramps.gen.lib import EventRoleType, EventType, FamilyRelType, NameType, Person
from gramps.gen.simple import SimpleAccess, SimpleDoc
from gramps.gen.plug.report import utils


# Event types already narrated by birth/baptism/christening/death/burial
# handling, or handled as part of a family (marriage/divorce), so they are
# left out of the generic "Life Events" section below.
_NARRATED_EVENT_TYPES = {
    EventType.BIRTH,
    EventType.BAPTISM,
    EventType.CHRISTEN,
    EventType.DEATH,
    EventType.BURIAL,
    EventType.CREMATION,
    EventType.MARRIAGE,
    EventType.MARR_SETTL,
    EventType.MARR_LIC,
    EventType.MARR_CONTR,
    EventType.MARR_BANNS,
    EventType.ENGAGEMENT,
    EventType.DIVORCE,
}

_MARRIAGE_VERB = {
    FamilyRelType.MARRIED: _("married"),
    FamilyRelType.UNMARRIED: _("began a relationship with"),
    FamilyRelType.CIVIL_UNION: _("entered a civil union with"),
}


#------------------------------------------------------------------------
#
# Privacy handling
#
#------------------------------------------------------------------------

def is_private(obj):
    """True if obj is a Gramps object explicitly marked private."""
    return bool(obj) and hasattr(obj, 'get_privacy') and obj.get_privacy()


class Redactions:
    """
    Tracks whether private data had to be left out of the biography.
    A single footnote is added at the end of the report if `any` ever
    became True; individual sentences that were directly changed by an
    omission (a name had to be swapped out, a date/place dropped) get
    a footnote marker via mark().
    """
    MARK = ' \u2021'
    FOOTNOTE = _(
        '\u2021 Some information above has been withheld because it is '
        'marked private in the database.'
    )

    def __init__(self):
        self.any = False

    def note(self):
        """Record a redaction that doesn't need its own marker (e.g.
        one item silently dropped out of a longer list)."""
        self.any = True

    def mark(self, text):
        """Record a redaction that changed a specific sentence, and
        return that sentence with a footnote marker appended."""
        self.any = True
        return (text + self.MARK) if text else self.MARK.strip()


#------------------------------------------------------------------------
#
# Place hierarchy: drop redundant Continent entries, and drop whatever
# higher-level context (state, country, ...) was already established
# by the immediately preceding place mentioned in the report.
#
#------------------------------------------------------------------------

def _place_chain(database, place):
    """
    Walk up the place hierarchy from `place` via its first placeref,
    returning an ordered list of (name, type_string) tuples from the
    leaf outward. Stops at the first place with no parent, or if a
    cycle is detected.
    """
    chain = []
    seen = set()
    current = place
    while current is not None and current.get_handle() not in seen:
        seen.add(current.get_handle())
        place_name = current.get_name()
        name = place_name.get_value() if place_name else ''
        chain.append((name, str(current.get_type()).strip()))
        placerefs = current.get_placeref_list()
        if not placerefs:
            break
        current = database.get_place_from_handle(
            placerefs[0].get_reference_handle())
    return chain


def _drop_redundant_continents(chain):
    """
    Remove Continent-type entries from a leaf-to-root place chain,
    unless the leaf place has no other context at all above it -- in
    that case the continent is all there is, so it stays rather than
    leaving the place with no context whatsoever. "Continent" isn't
    one of Gramps' built-in place types, so this matches on the
    (English) custom type name rather than a PlaceType constant.
    """
    if not chain:
        return chain
    leaf, rest = chain[0], chain[1:]
    filtered_rest = [entry for entry in rest
                      if entry[1].lower() != 'continent']
    if rest and not filtered_rest:
        return chain
    return [leaf] + filtered_rest


class PlaceContext:
    """
    Tracks the last place actually shown in the report (its handle and
    its full, continent-filtered leaf-to-root name chain), so the next
    place can be reduced against it:

    * If it's literally the same place again, the leaf name alone is
      enough ("...in Twin Falls. He was buried in Twin Falls.").
    * Otherwise, the leaf and its immediate parent are always kept for
      basic context, and only the matching higher levels above that
      (state, country, ...) are dropped.
    """

    def __init__(self):
        self.previous_handle = None
        self.previous_names = []

    def format(self, database, place):
        """Return the reduced, comma-joined display string for
        `place`, and update the tracked context for next time."""
        if place is None:
            return ''
        chain = _drop_redundant_continents(_place_chain(database, place))
        names = [name for name, _type in chain if name]
        if not names:
            return ''

        if place.get_handle() == self.previous_handle:
            result = names[:1]
        else:
            root_first = names[::-1]
            prev_root_first = self.previous_names[::-1]
            # Never trim into the last two entries (the place itself
            # and its immediate parent) -- that's the minimum context
            # to keep when it's a genuinely different place.
            max_trim = max(len(root_first) - 2, 0)

            common = 0
            for mine, theirs in zip(root_first, prev_root_first):
                if mine != theirs:
                    break
                common += 1
            common = min(common, max_trim)
            result = list(reversed(root_first[common:]))

        self.previous_handle = place.get_handle()
        self.previous_names = names
        return ', '.join(result)


def run(database, document, person):
    """
    Output a fuller text biography of the active person.
    """
    sa = SimpleAccess(database)
    sd = SimpleDoc(document)
    redactions = Redactions()
    place_context = PlaceContext()

    name_at_death, name_redacted = get_name_at_death(database, person)
    birth_name, birth_name_redacted = get_birth_name(person)
    common_name, common_redacted = get_common_name(person)
    if common_redacted:
        redactions.note()

    title = _("Biography of %s") % format_full_name(name_at_death)
    title += get_lifespan(database, person)
    if name_redacted:
        title = redactions.mark(title)
    sd.title(title)
    sd.paragraph('')

    # Birth Details -- always told using the birth name, not the common
    # name or the name-at-death used in the header.
    text = get_birth_sentence(database, person, birth_name,
                               birth_name_redacted, redactions, place_context)
    if text:
        sd.paragraph(text)

    text = get_simple_event_sentence(database, person, common_name,
                                      EventType.BAPTISM, _('was baptized'),
                                      redactions, place_context)
    if text:
        sd.paragraph(text)

    text = get_simple_event_sentence(database, person, common_name,
                                      EventType.CHRISTEN, _('was christened'),
                                      redactions, place_context)
    if text:
        sd.paragraph(text)

    # The parents sentence is built directly with our own common_name
    # (see get_parents_desc), so it doesn't depend on Narrator at all.
    text = get_parents_desc(database, sa, common_name, person, redactions)
    if text:
        sd.paragraph(text)
    sd.paragraph('')

    # Family Details
    for family_handle in person.get_family_handle_list():
        family = database.get_family_from_handle(family_handle)
        if not family:
            continue
        if is_private(family):
            redactions.note()
            continue

        text = get_marriage_sentence(database, sa, common_name, person,
                                      family, redactions, place_context)
        if text:
            sd.paragraph(text)

        text = get_children_sentence(database, family, redactions)
        if text:
            sd.paragraph(text)

        text = get_divorce_sentence(database, common_name, person, family,
                                     redactions, place_context)
        if text:
            sd.paragraph(text)
        sd.paragraph('')

    # Death Details
    text = get_death_sentence(database, person, common_name, redactions,
                               place_context)
    if text:
        sd.paragraph(text)

    text = get_simple_event_sentence(database, person, common_name,
                                      EventType.BURIAL, _('was buried'),
                                      redactions, place_context)
    if text:
        sd.paragraph(text)
    sd.paragraph('')

    # Also Known As -- alternate names not already used in the header or
    # the birth sentence.
    text = get_aka_sentence(common_name, person, birth_name, name_at_death,
                             redactions)
    if text:
        sd.paragraph(text)
        sd.paragraph('')

    # Life Events -- the person's own events plus every family's events
    # (other than marriage/divorce, told above), sorted together by date.
    event_lines = get_life_event_lines(database, person, redactions, place_context)
    if event_lines:
        sd.header1(_('Life Events'))
        for line in event_lines:
            sd.paragraph(line)
        sd.paragraph('')

    # Additional Details -- person attributes, plus pointers to data that
    # this narrative doesn't otherwise surface (addresses, media, LDS
    # ordinances, tags).
    detail_lines = get_attribute_lines(person, redactions)

    text = get_address_sentence(common_name, person, redactions)
    if text:
        detail_lines.append(text)

    text = get_media_sentence(common_name, person, redactions)
    if text:
        detail_lines.append(text)

    text = get_lds_sentence(common_name, person, redactions)
    if text:
        detail_lines.append(text)

    text = get_tags_line(database, person)
    if text:
        detail_lines.append(text)

    if detail_lines:
        sd.header1(_('Additional Details'))
        for line in detail_lines:
            sd.paragraph(line)
        sd.paragraph('')

    # Known Associates -- recorded associations, e.g. godparents, friends.
    associate_lines = get_associate_lines(database, person, redactions)
    if associate_lines:
        sd.header1(_('Known Associates'))
        for line in associate_lines:
            sd.paragraph(line)
        sd.paragraph('')

    # Notes
    note_texts = get_note_texts(database, person.get_note_list(), redactions)
    if note_texts:
        sd.header1(_('Notes'))
        for note_text in note_texts:
            sd.paragraph(note_text)
        sd.paragraph('')

    # Sources
    sd.header1(_('Sources'))
    for source in get_sources(database, person, redactions):
        sd.paragraph(source)

    if redactions.any:
        sd.paragraph('')
        sd.paragraph(Redactions.FOOTNOTE)


#------------------------------------------------------------------------
#
# Name formatting helpers
#
#------------------------------------------------------------------------

def format_name(name, include_title=True, include_call=True,
                 comma_before_suffix=False):
    """
    Assemble a display name from a Name object, e.g.:
        Dr. Lewis Anderson "Big Louie" Garner von Zielinski Sr.
        Ruth "Marguerite" Thompson McCullough
        Lewis Anderson Garner von Zielinski, Sr.
    Missing parts (no title, no suffix, no distinct call/nick name) are
    simply left out. The quoted name is the call name, falling back to
    the nick name, shown whenever it differs from the given name as a
    whole. If it repeats one word of a multi-word given name (e.g.
    given "Ruth Marguerite", call "Marguerite"), that word is dropped
    from the plain given text so it isn't shown twice.
    """
    if name is None:
        return ''

    given = (name.get_first_name() or '').strip()
    given_words = given.split()
    quoted = ''
    if include_call:
        call = (name.get_call_name() or '').strip()
        nick = (name.get_nick_name() or '').strip()
        if call and call != given:
            quoted = call
        elif nick and nick != given:
            quoted = nick

    display_given = given
    if quoted and quoted in given_words:
        display_given = ' '.join(w for w in given_words if w != quoted)

    parts = []
    if include_title and name.get_title():
        parts.append(name.get_title())
    if display_given:
        parts.append(display_given)
    if quoted:
        parts.append('"%s"' % quoted)
    if name.get_surname():
        parts.append(name.get_surname())
    base = ' '.join(parts)

    suffix = (name.get_suffix() or '').strip()
    if not suffix:
        return base
    if not base:
        return suffix
    if comma_before_suffix:
        return '%s, %s' % (base, suffix)
    return '%s %s' % (base, suffix)


def format_full_name(name):
    """"Title Given "Call" Surname Suffix" -- used for the header and for
    naming other people (spouses, parents, children) in the body text."""
    return format_name(name, include_title=True, include_call=True,
                        comma_before_suffix=False)


def format_birth_name(name):
    """"Given Surname, Suffix", no title and no call/nick name -- used
    only for the birth sentence."""
    return format_name(name, include_title=False, include_call=False,
                        comma_before_suffix=True)


def format_associate_name(name):
    """"Title Given "Call" Surname, Suffix" -- used for the Known
    Associates section."""
    return format_name(name, include_title=True, include_call=True,
                        comma_before_suffix=True)


def get_display_name(person, formatter=format_full_name):
    """
    Best available non-private name for a third party (spouse, parent,
    child, associate), formatted with `formatter`, and whether a
    private person or Name record had to be skipped to get it. Falls
    back to a generic placeholder if the whole person, or every one of
    their names, is private.
    """
    if person is None:
        return '', False
    if is_private(person):
        return _('a private individual'), True

    redacted = False
    for name in [person.get_primary_name()] + list(person.get_alternate_names()):
        if is_private(name):
            redacted = True
            continue
        return formatter(name), redacted
    return _('a private individual'), True


def _common_name(person, placeholder):
    """
    Best available common/call name for anyone -- the subject or a
    third party (a spouse, say) -- and whether a private person or
    Name record had to be skipped to find it. Preference order: call
    name, nick name, first given word -- checked against the primary
    name first, then alternates. Falls back to `placeholder` if the
    whole person, or every one of their names, is private (or there's
    no usable name at all).
    """
    if person is None:
        return placeholder, False
    if is_private(person):
        return placeholder, True

    redacted = False
    for name in [person.get_primary_name()] + list(person.get_alternate_names()):
        if is_private(name):
            redacted = True
            continue
        call = (name.get_call_name() or '').strip()
        if call:
            return call, redacted
        nick = (name.get_nick_name() or '').strip()
        if nick:
            return nick, redacted
        given = (name.get_first_name() or '').strip()
        if given:
            return given.split()[0], redacted
    return placeholder, True


def get_common_name(person):
    """Best available common/call name for the subject (see
    _common_name); the subject always exists, so the placeholder here
    is only reached if every one of their names is private."""
    return _common_name(person, _('This person'))


def get_birth_name(person):
    """
    Return (name, redacted): the (non-private) Name recorded with type
    Birth Name, falling back to the primary name, or to None if every
    candidate turns out to be private. redacted is True if a private
    candidate had to be skipped along the way.
    """
    redacted = False
    for name in person.get_alternate_names():
        if name.get_type() == NameType.BIRTH:
            if is_private(name):
                redacted = True
                continue
            return name, redacted
    primary = person.get_primary_name()
    if not is_private(primary):
        return primary, redacted
    return None, True


def get_name_at_death(database, person):
    """
    Return (name, redacted): the Name that was in effect at the
    person's death -- the name (primary or alternate) with the latest
    date that is not after the death date -- skipping any private
    candidates. Falls back to the primary name when there is no usable
    death date; falls back to None if every candidate is private.
    """
    primary = person.get_primary_name()
    candidates = [primary] + list(person.get_alternate_names())

    death_date = None
    death_ref = person.get_death_ref()
    if death_ref and death_ref.ref:
        death_event = database.get_event_from_handle(death_ref.ref)
        if death_event:
            death_date = death_event.get_date_object()

    if not death_date or not death_date.get_sort_value():
        if not is_private(primary):
            return primary, False
        for name in candidates:
            if not is_private(name):
                return name, True
        return None, True

    best = None
    best_sort = -1
    redacted = False
    for name in candidates:
        if is_private(name):
            redacted = True
            continue
        name_date = name.get_date_object()
        sort_value = name_date.get_sort_value() if name_date else 0
        if sort_value and sort_value <= death_date.get_sort_value():
            if sort_value > best_sort:
                best = name
                best_sort = sort_value
    if best is not None:
        return best, redacted
    if not is_private(primary):
        return primary, redacted
    for name in candidates:
        if not is_private(name):
            return name, True
    return None, True


def get_aka_sentence(common_name, person, birth_name, name_at_death, redactions):
    """
    Mention any further alternate names not already used in the header
    or the birth sentence. Private alternates are simply skipped.
    """
    others = []
    for name in person.get_alternate_names():
        if name is birth_name or name is name_at_death:
            continue
        if is_private(name):
            redactions.note()
            continue
        text = format_full_name(name)
        if text:
            others.append(text)
    if not others:
        return ''
    return _('%(name)s was also known as %(list)s.') % {
        'name': common_name,
        'list': ', '.join(others),
    }


#------------------------------------------------------------------------
#
# Date / event helpers
#
#------------------------------------------------------------------------

def get_year(date_obj):
    """Return a plain year string, or '' if there isn't a usable one."""
    if date_obj and date_obj.get_year_valid():
        return str(date_obj.get_year())
    return ''


def get_lifespan(database, person):
    """Return ' (birth_year-death_year)', or '' if neither year is known."""
    birth_year = ''
    birth_ref = person.get_birth_ref()
    if birth_ref and birth_ref.ref:
        event = database.get_event_from_handle(birth_ref.ref)
        if event and not is_private(event):
            birth_year = get_year(event.get_date_object())

    death_year = ''
    death_ref = person.get_death_ref()
    if death_ref and death_ref.ref:
        event = database.get_event_from_handle(death_ref.ref)
        if event and not is_private(event):
            death_year = get_year(event.get_date_object())

    if not birth_year and not death_year:
        return ''
    return ' (%s-%s)' % (birth_year or '?', death_year or '?')


def get_birth_sentence(database, person, birth_name, name_redacted,
                        redactions, place_context):
    """
    'Given Surname, Suffix was born on Date in Place.' -- always uses
    the birth name (not the common name or the name-at-death). If the
    birth name, or the birth event, or just its place, is private, the
    sentence is adjusted accordingly and marked -- once, even if more
    than one of those applies.
    """
    name_str = format_birth_name(birth_name) or _('This person')
    redacted = name_redacted

    birth_ref = person.get_birth_ref()
    if not (birth_ref and birth_ref.ref):
        return redactions.mark(name_str) if redacted else ''
    event = database.get_event_from_handle(birth_ref.ref)
    if not event:
        return redactions.mark(name_str) if redacted else ''

    if is_private(event):
        sentence = _('%(name)s was born.') % {'name': name_str}
        return redactions.mark(sentence)

    date_str, place_str, place_redacted = _event_date_place(
        database, event, place_context)
    redacted = redacted or place_redacted
    sentence = _compose_when_where(
        _('%(name)s was born on %(date)s in %(place)s.'),
        _('%(name)s was born on %(date)s.'),
        _('%(name)s was born in %(place)s.'),
        _('%(name)s was born.'),
        {'name': name_str}, date_str, place_str)
    return redactions.mark(sentence) if redacted else sentence


def _compose_when_where(both_fmt, date_only_fmt, place_only_fmt, neither_fmt,
                         base_map, date_str, place_str):
    """Fill in whichever of the four format strings fits what's known."""
    value_map = dict(base_map)
    value_map['date'] = date_str
    value_map['place'] = place_str
    if date_str and place_str:
        return both_fmt % value_map
    if date_str:
        return date_only_fmt % value_map
    if place_str:
        return place_only_fmt % value_map
    return neither_fmt % value_map


def _event_date_place(database, event, place_context):
    """
    Return (date_string, place_string, place_redacted) for an event.
    Assumes the event itself has already been checked for privacy;
    this only checks the place it points to. The place string is
    reduced against `place_context` (see PlaceContext).
    """
    date_obj = event.get_date_object()
    date_str = ''
    if date_obj and not date_obj.is_empty():
        date_str = glocale.get_date(date_obj)

    place_str = ''
    place_redacted = False
    place_handle = event.get_place_handle()
    if place_handle:
        place = database.get_place_from_handle(place_handle)
        if place is not None and is_private(place):
            place_redacted = True
        else:
            place_str = place_context.format(database, place)

    return date_str, place_str, place_redacted


def _find_primary_event(database, person, event_type):
    """The person's primary-role event of the given type, if any."""
    for event_ref in person.get_event_ref_list():
        if event_ref.get_role() != EventRoleType.PRIMARY:
            continue
        event = database.get_event_from_handle(event_ref.ref)
        if event and int(event.get_type()) == int(event_type):
            return event
    return None


def _age_at_death(database, person):
    """
    'X years, Y days' (locale-formatted) computed from the birth and
    death dates, or '' if either date (or its year) isn't known, or
    the birth event is private. Replicates what Narrator computes
    internally for get_died_string(include_age=True), so our own
    death sentence doesn't need Narrator to include it.
    """
    birth_ref = person.get_birth_ref()
    death_ref = person.get_death_ref()
    if not (birth_ref and birth_ref.ref and death_ref and death_ref.ref):
        return ''
    birth_event = database.get_event_from_handle(birth_ref.ref)
    death_event = database.get_event_from_handle(death_ref.ref)
    if not birth_event or not death_event or is_private(birth_event):
        return ''

    birth_date = birth_event.get_date_object()
    death_date = death_event.get_date_object()
    if not (birth_date.get_year_valid() and death_date.get_year_valid()):
        return ''

    span = death_date - birth_date
    if not (span and span.is_valid()):
        return ''
    return span.get_repr(dlocale=glocale)


def get_simple_event_sentence(database, person, common_name, event_type,
                               verb, redactions, place_context):
    """
    'Common_name <verb> on Date in Place.' for the person's primary
    event of the given type (baptism, christening, burial), or '' if
    there isn't one. `verb` is a phrase like "was baptized".
    """
    event = _find_primary_event(database, person, event_type)
    if not event:
        return ''
    if is_private(event):
        return redactions.mark(_('%(name)s %(verb)s.') % {
            'name': common_name, 'verb': verb})

    date_str, place_str, place_redacted = _event_date_place(
        database, event, place_context)
    sentence = _compose_when_where(
        _('%(name)s %(verb)s on %(date)s in %(place)s.'),
        _('%(name)s %(verb)s on %(date)s.'),
        _('%(name)s %(verb)s in %(place)s.'),
        _('%(name)s %(verb)s.'),
        {'name': common_name, 'verb': verb}, date_str, place_str)
    return redactions.mark(sentence) if place_redacted else sentence


def get_death_sentence(database, person, common_name, redactions, place_context):
    """
    'Common_name died on Date in Place at the age of Age.' Age is
    included whenever it can be computed (see _age_at_death).
    """
    death_ref = person.get_death_ref()
    if not (death_ref and death_ref.ref):
        return ''
    event = database.get_event_from_handle(death_ref.ref)
    if not event:
        return ''
    if is_private(event):
        return redactions.mark(_('%(name)s died.') % {'name': common_name})

    date_str, place_str, place_redacted = _event_date_place(
        database, event, place_context)
    age_str = _age_at_death(database, person)

    base = _compose_when_where(
        _('%(name)s died on %(date)s in %(place)s'),
        _('%(name)s died on %(date)s'),
        _('%(name)s died in %(place)s'),
        _('%(name)s died'),
        {'name': common_name}, date_str, place_str)

    if age_str:
        sentence = _('%(base)s at the age of %(age)s.') % {
            'base': base, 'age': age_str}
    else:
        sentence = base + '.'
    return redactions.mark(sentence) if place_redacted else sentence


def describe_event(database, event, redactions, place_context):
    """
    A plain "Type: description (date, place)." line for a life event
    that doesn't have its own narrative sentence. Assumes the event
    itself has already been checked for privacy by the caller.
    """
    etype = str(event.get_type())
    desc = event.get_description()
    date_str, place_str, place_redacted = _event_date_place(
        database, event, place_context)
    if place_redacted:
        redactions.note()

    if date_str and place_str:
        when_where = _(' (%(date)s, %(place)s)') % {
            'date': date_str, 'place': place_str}
    elif date_str:
        when_where = _(' (%(date)s)') % {'date': date_str}
    elif place_str:
        when_where = _(' (%(place)s)') % {'place': place_str}
    else:
        when_where = ''

    if desc:
        return '%s: %s%s.' % (etype, desc, when_where)
    return '%s%s.' % (etype, when_where)


def get_life_event_lines(database, person, redactions, place_context):
    """
    Lines for every event that isn't already told elsewhere -- the
    person's own events, plus every one of their families' events --
    combined and sorted together by date (undated events last), so a
    person's own events and their family events (moves, a spouse's
    occupation entries logged against the family, etc.) interleave
    correctly instead of being split into separate blocks. Marriage
    and Divorce get their own sentences alongside the marriage
    paragraph, so they (and birth/baptism/christening/death/burial)
    are excluded here. Private events, and events belonging to a
    private family, are skipped entirely. Sorting happens before the
    lines (and their places) are composed, so place_context sees them
    in the order they're actually displayed.
    """
    events = []

    for event_ref in person.get_event_ref_list():
        if event_ref.get_role() != EventRoleType.PRIMARY:
            continue
        event = database.get_event_from_handle(event_ref.ref)
        if not event or int(event.get_type()) in _NARRATED_EVENT_TYPES:
            continue
        if is_private(event):
            redactions.note()
            continue
        events.append(event)

    for family_handle in person.get_family_handle_list():
        family = database.get_family_from_handle(family_handle)
        if not family or is_private(family):
            if family:
                redactions.note()
            continue
        for event_ref in family.get_event_ref_list():
            event = database.get_event_from_handle(event_ref.ref)
            if not event or int(event.get_type()) in _NARRATED_EVENT_TYPES:
                continue
            if is_private(event):
                redactions.note()
                continue
            events.append(event)

    entries = []
    for event in events:
        date_obj = event.get_date_object()
        sort_value = date_obj.get_sort_value() if date_obj else 0
        entries.append((sort_value, event))
    # Undated events (sort_value 0) sort after every dated one, then by date.
    entries.sort(key=lambda entry: (entry[0] == 0, entry[0]))
    return [describe_event(database, event, redactions, place_context)
            for _sort_value, event in entries]


def get_attribute_lines(person, redactions):
    """Lines for person attributes, e.g. 'Nationality: American.'.
    Private attributes are skipped."""
    lines = []
    for attr in person.get_attribute_list():
        if is_private(attr):
            redactions.note()
            continue
        value = attr.get_value()
        if value:
            lines.append('%s: %s.' % (str(attr.get_type()), value))
    return lines


def get_address_sentence(common_name, person, redactions):
    """'There are N known addresses referencing Common.', or ''.
    Private addresses don't count towards N."""
    total = person.get_address_list()
    visible = [a for a in total if not is_private(a)]
    hidden = len(total) - len(visible)
    if hidden:
        redactions.note()

    if visible:
        if len(visible) == 1:
            sentence = _('There is 1 known address referencing '
                         '%(name)s.') % {'name': common_name}
        else:
            sentence = _('There are %(count)d known addresses '
                          'referencing %(name)s.') % {
                'count': len(visible), 'name': common_name}
        return redactions.mark(sentence) if hidden else sentence
    if hidden:
        return redactions.mark(
            _('Address information for %(name)s has been '
              'withheld.') % {'name': common_name})
    return ''


def get_media_sentence(common_name, person, redactions):
    """
    'There are N Media Objects referencing Common. Review them in the
    Deep Gallery addon gramplet.', or ''. Private media references
    don't count towards N.
    """
    total = person.get_media_list()
    visible = [m for m in total if not is_private(m)]
    hidden = len(total) - len(visible)
    if hidden:
        redactions.note()

    if visible:
        if len(visible) == 1:
            sentence = _('There is 1 Media Object referencing %(name)s. '
                         'Review it in the Deep Gallery addon '
                         'gramplet.') % {'name': common_name}
        else:
            sentence = _('There are %(count)d Media Objects referencing '
                         '%(name)s. Review them in the Deep Gallery '
                         'addon gramplet.') % {
                'count': len(visible), 'name': common_name}
        return redactions.mark(sentence) if hidden else sentence
    if hidden:
        return redactions.mark(
            _('Media information for %(name)s has been '
              'withheld.') % {'name': common_name})
    return ''


def get_lds_sentence(common_name, person, redactions):
    """'N LDS ordinances have been logged for Common.', or ''. Private
    ordinances don't count towards N."""
    total = person.get_lds_ord_list()
    visible = [o for o in total if not is_private(o)]
    hidden = len(total) - len(visible)
    if hidden:
        redactions.note()

    # Capitalize, since this sentence always starts with the name.
    name = common_name[:1].upper() + common_name[1:] if common_name else common_name

    if visible:
        if len(visible) == 1:
            sentence = _('1 LDS ordinance has been logged for '
                         '%(name)s.') % {'name': name}
        else:
            sentence = _('%(count)d LDS ordinances have been logged '
                          'for %(name)s.') % {
                'count': len(visible), 'name': name}
        return redactions.mark(sentence) if hidden else sentence
    if hidden:
        return redactions.mark(
            _('LDS ordinance information for %(name)s has been '
              'withheld.') % {'name': name})
    return ''


def get_tags_line(database, person):
    """'Tagged: Tag1, Tag2.', or '' if the person has no tags. Tags
    have no privacy flag of their own in Gramps, so nothing to redact
    here."""
    names = []
    for handle in person.get_tag_list():
        tag = database.get_tag_from_handle(handle)
        if tag:
            names.append(tag.get_name())
    if not names:
        return ''
    return _('Tagged: %s') % ', '.join(names)


def get_associate_lines(database, person, redactions):
    """
    Lines for the person's recorded associations, e.g.
    'Godfather: Henry Martel.', sorted by the association type. An
    association marked private is skipped entirely; if the associate's
    own name had to be substituted, that one line gets a marker.
    """
    entries = []
    for person_ref in person.get_person_ref_list():
        if is_private(person_ref):
            redactions.note()
            continue
        associate = database.get_person_from_handle(
            person_ref.get_reference_handle())
        name, redacted = get_display_name(associate, format_associate_name)
        if not name:
            continue
        relation = person_ref.get_relation() or _('Associate')
        line = '%s: %s.' % (relation, name)
        if redacted:
            line = redactions.mark(line)
        entries.append((relation, line))
    entries.sort(key=lambda entry: entry[0].lower())
    return [line for _relation, line in entries]


#------------------------------------------------------------------------
#
# Family / parents helpers
#
#------------------------------------------------------------------------

def _relation_word(gender):
    if gender == Person.MALE:
        return _('son')
    if gender == Person.FEMALE:
        return _('daughter')
    return _('child')


def _get_parent_names(database, sa, child_person):
    """
    Return (father_name, mother_name, redacted) for child_person's own
    parents (their main family), with the mother prefixed "the former"
    to flag that her birth surname is being used. Any of the three may
    come back '' / False if there are no parents on record (or the
    family is private).
    """
    family_handle = child_person.get_main_parents_family_handle()
    if not family_handle:
        return '', '', False
    family = database.get_family_from_handle(family_handle)
    if not family or is_private(family):
        return '', '', bool(family)

    father = sa.father(family)
    mother = sa.mother(family)
    father_name, father_redacted = get_display_name(father)
    mother_name = ''
    mother_redacted = False
    if mother:
        raw_name, mother_redacted = get_display_name(mother)
        mother_name = _('the former %s') % raw_name

    return father_name, mother_name, father_redacted or mother_redacted


def get_parents_clause(database, sa, person):
    """
    Return (clause, redacted): ", the son/daughter of Father and the
    former Mother," (or the equivalent with just one parent), or
    ('', redacted) if no parents are recorded. Used when introducing a
    spouse.
    """
    father_name, mother_name, redacted = _get_parent_names(database, sa, person)
    if not father_name and not mother_name:
        return '', redacted

    if father_name and mother_name:
        names = _('%(father)s and %(mother)s') % {
            'father': father_name, 'mother': mother_name}
    else:
        names = father_name or mother_name

    clause = _(', the %(relation)s of %(names)s,') % {
        'relation': _relation_word(person.get_gender()),
        'names': names,
    }
    return clause, redacted


def get_parents_desc(database, sa, common_name, person, redactions):
    """
    'Common_name is the son/daughter of Father and the former Mother.'
    Built directly (rather than via Narrator.get_child_string) so the
    subject is always named using our own common_name, not Narrator's
    own -- cruder -- name resolution.
    """
    father_name, mother_name, redacted = _get_parent_names(database, sa, person)
    if not father_name and not mother_name:
        if redacted:
            redactions.note()
        return ''

    if father_name and mother_name:
        names = _('%(father)s and %(mother)s') % {
            'father': father_name, 'mother': mother_name}
    else:
        names = father_name or mother_name

    sentence = _('%(name)s is the %(relation)s of %(names)s.') % {
        'name': common_name,
        'relation': _relation_word(person.get_gender()),
        'names': names,
    }
    return redactions.mark(sentence) if redacted else sentence


def get_marriage_sentence(database, sa, common_name, person, family,
                           redactions, place_context):
    """
    'Common_name married Spouse, the daughter of Father and the former
    Mother, on Date in Place.' The family itself is assumed to have
    already been checked for privacy by the caller.
    """
    spouse_handle = utils.find_spouse(person, family)
    spouse = database.get_person_from_handle(spouse_handle) \
        if spouse_handle else None

    redacted = False
    if spouse:
        spouse_name, redacted = get_display_name(spouse)
        parents_clause, parents_redacted = get_parents_clause(database, sa, spouse)
        redacted = redacted or parents_redacted
    else:
        spouse_name = _('an unknown spouse')
        parents_clause = ''

    date_str = ''
    place_str = ''
    event = utils.find_marriage(database, family)
    if event:
        if is_private(event):
            redacted = True
        else:
            date_str, place_str, place_redacted = _event_date_place(
                database, event, place_context)
            redacted = redacted or place_redacted

    if date_str and place_str:
        when = _(' on %(date)s in %(place)s') % {
            'date': date_str, 'place': place_str}
    elif date_str:
        when = _(' on %(date)s') % {'date': date_str}
    elif place_str:
        when = _(' in %(place)s') % {'place': place_str}
    else:
        when = ''

    verb = _MARRIAGE_VERB.get(int(family.get_relationship()),
                               _('was united with'))

    sentence = _('%(name)s %(verb)s %(spouse)s%(parents)s%(when)s.') % {
        'name': common_name,
        'verb': verb,
        'spouse': spouse_name,
        'parents': parents_clause,
        'when': when,
    }
    return redactions.mark(sentence) if redacted else sentence


def _find_divorce(database, family):
    """The family's Divorce event, if any (mirrors utils.find_marriage,
    which has no divorce equivalent of its own)."""
    for event_ref in family.get_event_ref_list():
        event = database.get_event_from_handle(event_ref.ref)
        if event and event.get_type().is_divorce():
            return event
    return None


def get_divorce_sentence(database, common_name, person, family, redactions,
                          place_context):
    """
    'In Date, Common and Spouse_common divorced in Place.' Uses common
    (call) names for both halves of the couple, since by this point
    they've already been fully introduced via the marriage sentence.
    '' if the family has no Divorce event.
    """
    event = _find_divorce(database, family)
    if not event:
        return ''

    spouse_handle = utils.find_spouse(person, family)
    spouse = database.get_person_from_handle(spouse_handle) \
        if spouse_handle else None
    if spouse:
        spouse_common, spouse_redacted = _common_name(
            spouse, _('a private individual'))
    else:
        spouse_common, spouse_redacted = _('an unknown spouse'), False

    if is_private(event):
        sentence = _('%(name)s and %(spouse)s divorced.') % {
            'name': common_name, 'spouse': spouse_common}
        return redactions.mark(sentence)

    date_str, place_str, place_redacted = _event_date_place(
        database, event, place_context)
    redacted = spouse_redacted or place_redacted

    sentence = _compose_when_where(
        _('In %(date)s, %(name)s and %(spouse)s divorced in %(place)s.'),
        _('In %(date)s, %(name)s and %(spouse)s divorced.'),
        _('%(name)s and %(spouse)s divorced in %(place)s.'),
        _('%(name)s and %(spouse)s divorced.'),
        {'name': common_name, 'spouse': spouse_common}, date_str, place_str)
    return redactions.mark(sentence) if redacted else sentence


def get_children_sentence(database, family, redactions):
    """'Their children were A, B and C.' Private children (or those
    with only private names) appear as 'a private individual'."""
    names = []
    redacted = False
    for child_ref in family.get_child_ref_list():
        child = database.get_person_from_handle(child_ref.ref)
        name, child_redacted = get_display_name(child)
        redacted = redacted or child_redacted
        if name:
            names.append(name)

    if not names:
        return ''
    if len(names) == 1:
        names_str = names[0]
    else:
        names_str = '%s and %s' % (', '.join(names[:-1]), names[-1])

    sentence = _('Their children were %s.') % names_str
    return redactions.mark(sentence) if redacted else sentence


#------------------------------------------------------------------------
#
# Notes / sources
#
#------------------------------------------------------------------------

def get_note_texts(database, note_handle_list, redactions):
    """Plain-text contents of a list of note handles. Private notes
    are skipped."""
    texts = []
    for handle in note_handle_list:
        note = database.get_note_from_handle(handle)
        if not note:
            continue
        if is_private(note):
            redactions.note()
            continue
        text = note.get()
        if text:
            texts.append(text)
    return texts


def get_sources(database, person, redactions):
    """
    Sources cited for the person: citations on the person directly
    (and on their names, attributes, addresses, media references, LDS
    ordinances and associations -- everything get_all_citation_lists()
    covers), plus citations on the person's own events and the events
    of any families the person is a parent in. Private citations, and
    citations of private sources, are skipped. Sorted by source title,
    then citation date, then page/volume; the date is rendered before
    the page/volume on each line.
    """
    sa = SimpleAccess(database)
    events = sa.events(person)
    for family in sa.parent_in(person):
        for event in sa.events(family):
            events.append(event)

    citation_handles = list(person.get_all_citation_lists())
    for event in events:
        if is_private(event):
            continue
        citation_handles.extend(event.citation_list)

    seen_handles = set()
    entries = []  # (title_key, has_no_date, sort_value, page_key, description)
    for handle in citation_handles:
        citation = database.get_citation_from_handle(handle)
        if not citation or is_private(citation):
            if citation:
                redactions.note()
            continue
        source = database.get_source_from_handle(citation.source_handle)
        if not source or is_private(source):
            if source:
                redactions.note()
            continue

        citation_handle = citation.get_handle()
        if citation_handle in seen_handles:
            continue
        seen_handles.add(citation_handle)

        page = citation.page or ''
        title = source.title or ''
        author = source.author

        date_obj = citation.get_date_object()
        date_str = ''
        sort_value = 0
        if date_obj and not date_obj.is_empty():
            date_str = glocale.get_date(date_obj)
            sort_value = date_obj.get_sort_value()

        if date_str and page:
            detail = _('%(date)s, %(page)s') % {
                'date': date_str, 'page': page}
        else:
            detail = date_str or page

        if author:
            source_desc = '\u2022 {}, {} - {}'.format(author, title, detail)
        else:
            source_desc = '\u2022 {} - {}'.format(title, detail)

        entries.append((title.lower(), not bool(date_str), sort_value,
                         page.lower(), source_desc))

    # Title first, then date (undated last within a title), then page/volume.
    entries.sort(key=lambda entry: entry[:4])
    return [description for *_sort_key, description in entries]

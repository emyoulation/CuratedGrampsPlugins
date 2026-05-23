# ----------------------------------------------------------------------
# LocaleChecker.py
#
# Reference Gramplet demonstrating how language, region, and locale
# information is represented and accessed in Gramps.
#
# Key takeaways for Gramps developers:
# - GrampsLocale does NOT expose a separate "country" attribute.
# - Locale information follows POSIX / gettext conventions.
# - Language, region, and variant must be derived from different sources.
#
# This gramplet intentionally shows both machine-truth (locale codes)
# and human-readable descriptions (language names with variants).
#
# ----------------------------------------------------------------------
# Process note (AI-assisted development):
#
# AI-assisted "wish-coding" tended to default to generic Python patterns
# unless Gramps-specific engine and frontend capabilities were explicitly
# named in the prompt.
#
# Notable examples:
# - Gramps provides rich locale and language awareness (e.g., GrampsLocale)
#   that should be leveraged rather than reimplemented generically.
# - This gramplet currently uses direct Gramplet text rendering rather
#   than frontend presentation abstractions such as the SimpleDoc API
#   (see:
#   https://gramps-project.org/docs/simple.html#module-gramps.gen.simple._simpledoc).
#   This reflects a "content first, presentation later" approach during
#   AI-assisted wish-coding: stabilizing locale semantics and engine
#   interactions proved more reliable than integrating GUI preference-
#   aware presentation early. Refinement to frontend abstractions is a
#   natural next step once behavior and data relationships are settled.
#
# Explicitly incorporating framework documentation and domain concepts
# into prompts produced more idiomatic, maintainable results.
# ----------------------------------------------------------------------
#
# Author: Brian McCullough
#
# This module was developed using plain-English, intent-driven prompting
# ("wish-coder" style) with assistance from ChatGPT (OpenAI), initiated
# from the GitHub repository context via the repository’s AI sidebar.
#
# The AI assisted in generating both the implementation and the detailed
# explanatory annotations, supporting an educational, reference-oriented
# coding style intended for novice Gramps developers.
# ----------------------------------------------------------------------


from gramps.gen.plug import Gramplet
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gen.const import GRAMPS_LOCALE as glocale
import os
import re

# Set up translation support for the gramplet itself.
# If the add-on translator is not available, fall back to core Gramps.
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext


class LocaleChecker(Gramplet):
    def init(self):
        # Allow simple markup (e.g., <b> headers) in the gramplet output
        self.set_use_markup(True)

        # Prevent repeated execution when the dashboard refreshes
        self.has_run = False

    def main(self):
        if self.has_run:
            return
        self.has_run = True

        # GrampsLocale is the central access point for locale information
        gl = GrampsLocale()

        # ------------------------------------------------------------------
        # Language name lookup
        #
        # get_language_dict() returns a mapping of:
        #   "English name" -> "language code"
        #
        # Example:
        #   { "English": "en", "German": "de", ... }
        #
        # We reverse it to allow:
        #   "en" -> "English"
        # ------------------------------------------------------------------
        language_dict = gl.get_language_dict()
        code_to_name = {v: k for k, v in language_dict.items()}

        # ------------------------------------------------------------------
        # Base language code
        #
        # gl.lang typically looks like:
        #   "en_US", "zh_CN", "fr", etc.
        #
        # The base language is the part before the underscore.
        # This is what Gramps uses to look up the English language name.
        # ------------------------------------------------------------------
        current_lang_base = (
            gl.lang.split("_")[0]
            if gl.lang and "_" in gl.lang
            else gl.lang
        )

        english_name = code_to_name.get(current_lang_base, "Unknown")

        # ------------------------------------------------------------------
        # Display raw locale information exactly as Gramps provides it
        # ------------------------------------------------------------------
        self.render_text("<b>Current Locale</b>\n")
        self.render_text("Locale Code: %s\n" % gl.locale_code())
        self.render_text("Language: %s\n" % current_lang_base)
        self.render_text("Lang: %s\n" % gl.lang)

        # ------------------------------------------------------------------
        # Region and variant detection
        #
        # IMPORTANT DESIGN DECISION:
        #
        # - The region (US, CN, HK, etc.) is derived ONLY from the locale code.
        # - Parentheticals in language names are treated as descriptive
        #   variants (script, spelling, or regional flavor), NOT authoritative
        #   country data.
        #
        # This avoids incorrect assumptions for languages like Chinese:
        #   zh_CN: Chinese (Simplified)
        #   zh_TW: Chinese (Traditional)
        #   zh_HK: Chinese (Hong Kong)
        # ------------------------------------------------------------------
        region = "N/A"
        variant = None

        # 1) Region from locale code (authoritative, machine-readable)
        if gl.lang and "_" in gl.lang:
            region = gl.lang.split("_", 1)[1]

        # 2) Optional variant extracted from English name parenthetical
        #    (human-readable, non-authoritative)
        if english_name:
            match = re.search(r"\(([^)]+)\)", english_name)
            if match:
                variant = match.group(1)

        # 3) Combine for display
        #    Examples:
        #      US (USA)
        #      CN (Simplified)
        #      HK (Hong Kong)
        if variant:
            region_display = f"{region} ({variant})"
        else:
            region_display = region

        self.render_text("Region: %s\n" % region_display)

        # Display the resolved English language name
        self.render_text(
            "English Name: %s (%s)\n"
            % (english_name, current_lang_base)
        )

        # ------------------------------------------------------------------
        # Locale directory inspection
        #
        # Shows which language directories are physically installed
        # under the active locale directory.
        # ------------------------------------------------------------------
        localedir = getattr(gl, "localedir", None)
        if localedir:
            self.render_text("Locale Directory: %s\n" % localedir)

            if os.path.isdir(localedir):
                langs = [
                    d for d in os.listdir(localedir)
                    if os.path.isdir(os.path.join(localedir, d))
                ]

                self.render_text(
                    "\n<b>Additional Installed Languages (%d)</b>\n"
                    % len(langs)
                )

                # List installed languages with English names when available
                for lang in sorted(langs):
                    if lang not in [".", ".."]:
                        lang_name = code_to_name.get(lang, "Unknown")
                        self.append_text(
                            "  %s: %s\n" % (lang, lang_name)
                        )

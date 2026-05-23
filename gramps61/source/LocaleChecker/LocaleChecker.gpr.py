from gramps.gui import plug
from gramps.version import major_version, VERSION_TUPLE

if VERSION_TUPLE < (5, 2, 0):
    additional_args = {
        "status": STABLE,
    }
else:
    additional_args = {
        "audience": DEVELOPER,
        "status": BETA,
        "maintainers": "Brian McCullough",
        "maintainers_email": "emyoulation@yahoo.com",
    }

register(GRAMPLET,
    id="Locale Checker Gramplet",
    name=_("Locale Checker"),
    description=_("Dashboard with the current Locale and installed languages"),
    version = '1.0.0',
    gramps_target_version=major_version,
    authors=["Claude AI"],
    authors_email=[""],
    fname="LocaleChecker.py",
    height=300,
    gramplet='LocaleChecker',
    gramplet_title=_("Locale Checker"),
    # help_url="Addon:Locale_Checker_Gramplet",
    help_url=(
        "https://github.com/emyoulation/LocalTerm/"
        "blob/master/README.md#locale-checker-gramplet"),
    navtypes=["Dashboard"],
    include_in_listing=True,
    **additional_args,
    )

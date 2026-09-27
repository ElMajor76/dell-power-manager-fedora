"""Gettext setup shared by every module with user-facing strings.

English is the source language throughout the codebase (standard practice
for a project meant to be readable/contributable-to by anyone); French is
provided as a translation in po/fr.po, selected automatically from the
user's locale like any other gettext-based application.
"""

from __future__ import annotations

import gettext
import locale
import os

DOMAIN = "platform-power-manager"

# In an installed package this is /usr/share/locale (found via the system
# locale path below); in a source checkout / when running the tests, fall
# back to the po/ directory at the repository root so translations work
# without installing anything.
_REPO_LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "po",
    "locale",
)

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

if os.path.isdir(_REPO_LOCALE_DIR):
    gettext.bindtextdomain(DOMAIN, _REPO_LOCALE_DIR)
else:
    gettext.bindtextdomain(DOMAIN, "/usr/share/locale")
gettext.textdomain(DOMAIN)

_ = gettext.gettext

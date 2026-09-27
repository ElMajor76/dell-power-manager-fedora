import os

# Force a deterministic locale for the whole test session, regardless of
# whatever LANG/LC_ALL the machine running the tests happens to have set.
# Tests assert on specific English source strings; platform_power.i18n
# picks up the locale at import time (gettext.bindtextdomain +
# locale.setlocale), so this has to run before any platform_power module
# is imported -- pytest loads conftest.py before collecting test modules,
# which is what makes that ordering reliable here.
os.environ["LANGUAGE"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LANG"] = "C"

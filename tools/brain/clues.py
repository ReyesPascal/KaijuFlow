"""The Clue library (spec #279): small reusable yes / no / can't-tell tests, registered here by name.

A Casebook entry's `confirm` is a recipe of Clue names, each with the answer that proves the cause
(tools/brain/casebook/README.md). `casebook.py check` counts a recipe as a confirming test that runs only when every
Clue it names is registered here, so no entry is proved before its Clues exist. The Clue format itself (a named test
from evidence, or a live read-only lookup, to yes / no / can't tell with the facts it saw) is set by #283; nothing is
ever deleted from the library.
"""

CLUES = {}

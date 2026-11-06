"""Importing this package registers every task.

Adding a feature means adding a module here and one line below - the web page,
the scheduler and the command line all pick it up without being told.

The order here does not matter. Each task declares its own `order` for the
sidebar, and `parent` for the ones that belong as a tab under another feature
rather than as a feature of their own.
"""
from . import library            # noqa: F401
from . import space              # noqa: F401
from . import tidy               # noqa: F401
from . import history            # noqa: F401
from . import reindex            # noqa: F401
from . import search             # noqa: F401
from . import setup              # noqa: F401
from . import unpair             # noqa: F401
from . import bydate             # noqa: F401
from . import import_places      # noqa: F401
from . import remirror           # noqa: F401
from . import remirror_previews  # noqa: F401
from . import remirror_video     # noqa: F401
from . import videos             # noqa: F401
from . import previews           # noqa: F401
from . import geotag             # noqa: F401
from . import import_timeline    # noqa: F401
from . import pin                # noqa: F401
from . import retime             # noqa: F401
from . import unlocate           # noqa: F401
from . import ratings            # noqa: F401
from . import label              # noqa: F401
from . import labels             # noqa: F401
from . import tags               # noqa: F401
from . import cull               # noqa: F401
from . import blur               # noqa: F401
from . import develop            # noqa: F401
from . import filed              # noqa: F401
from . import automation         # noqa: F401
from . import autoruns           # noqa: F401
from . import flows              # noqa: F401
from . import permissions        # noqa: F401
from . import password           # noqa: F401
from . import bands             # noqa: F401
from . import backup             # noqa: F401
from . import checklist          # noqa: F401
from . import delfolder          # noqa: F401
from . import files              # noqa: F401
from . import rename             # noqa: F401
from . import duplicates         # noqa: F401
from . import cameras            # noqa: F401
from . import cleanup            # noqa: F401
from . import compare            # noqa: F401
from . import brackets           # noqa: F401
from . import thin              # noqa: F401
from . import demo              # noqa: F401
from . import undo              # noqa: F401
from . import exposure          # noqa: F401
from . import forget            # noqa: F401
from . import timeline          # noqa: F401
from . import wording           # noqa: F401

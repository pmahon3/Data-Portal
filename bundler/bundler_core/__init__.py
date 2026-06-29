"""Only so ``import bundler_core`` works when ``bundler/`` is on ``sys.path`` (see ``README_dev.md``).

The real package lives under ``src/`` per ``pyproject.toml`` ``package-dir``. This file is not part of
the built wheel; setuptools still packages ``src/`` only.
"""

from pathlib import Path

# Library code lives under ``src/`` (setuptools ``package-dir``). The ``tests/`` tree also lives under
# this project directory and uses ``from .common import …``, so imports resolve to ``bundler_core.tests``.
# ``__path__`` must include both ``src/`` (implementation) and the project root (``tests/`` subpackage).
_root = Path(__file__).resolve().parent
__path__ = [str(_root / "src"), str(_root)]

from bundler_core.api import *  # noqa: F403, E402

import bundler_core.api as _api

__version__ = "0.1.0"
__all__ = ["__version__", *list(_api.__all__)]
del _api

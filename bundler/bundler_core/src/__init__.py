"""Bundler core: re-export the full public surface of :mod:`bundler_core.api` (``src/api.py``).

If you later add ``bundler_app/app/api.py`` as the canonical facade, replace the star-import
source with that module (and add an explicit dependency if it lives outside ``bundler_core``).
"""

from __future__ import annotations

from bundler_core.api import *  # noqa: F403  — ``api`` defines ``__all__``

import bundler_core.api as _api

__version__ = "0.1.0"
__all__ = ["__version__", *list(_api.__all__)]
del _api

"""Start the app from a source checkout: ``python main.py``.

Installed users start it with the ``maxwell-bloch-solver`` (or ``mbsolver``)
command instead. For development, ``pip install -e .`` is the better way.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mbsolver.main import main  # noqa: E402

raise SystemExit(main())

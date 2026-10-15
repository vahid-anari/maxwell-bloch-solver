"""Start the app from a source checkout: ``python main.py``.

Installed users start it with the ``maxwell-bloch-studio`` (or ``mbstudio``)
command instead. For development, ``pip install -e .`` is the better way.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mbstudio.main import main  # noqa: E402

raise SystemExit(main())

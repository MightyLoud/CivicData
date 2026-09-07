"""PR #47 adversarial strict jurisdiction-package regression wrapper."""
from __future__ import annotations

import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import jurisdiction_package_strict as strict_jp

_key = "tools.jurisdiction_package"
_original = sys.modules.get(_key)
sys.modules[_key] = strict_jp
try:
    _IMPL = ROOT / "tests" / "_pr47_jurisdiction_package_adversarial_impl.py"
    _namespace = runpy.run_path(str(_IMPL), run_name="pr47_jurisdiction_package_adversarial")
finally:
    if _original is None:
        sys.modules.pop(_key, None)
    else:
        sys.modules[_key] = _original

for _name, _value in _namespace.items():
    if _name.startswith("test_") and callable(_value):
        globals()[_name] = _value


def run():
    _namespace["run"]()


if __name__ == "__main__":
    run()

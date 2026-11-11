import importlib.util
import sys
from pathlib import Path

# scripts/ is not a package. Load capture.py under a plain module name for tests.
_p = Path(__file__).resolve().parents[1] / "scripts" / "capture.py"
_spec = importlib.util.spec_from_file_location("scripts_capture", _p)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["scripts_capture"] = _mod
_spec.loader.exec_module(_mod)

_p = Path(__file__).resolve().parents[1] / "scripts" / "manifest.py"
_spec = importlib.util.spec_from_file_location("scripts_manifest", _p)
_man = importlib.util.module_from_spec(_spec)
sys.modules["scripts_manifest"] = _man
_spec.loader.exec_module(_man)

for _name in ("write_report", "plot_hourly", "build_site"):
    _p = Path(__file__).resolve().parents[1] / "scripts" / f"{_name}.py"
    if _p.exists():
        _spec = importlib.util.spec_from_file_location(f"scripts_{_name}", _p)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[f"scripts_{_name}"] = _m
        _spec.loader.exec_module(_m)

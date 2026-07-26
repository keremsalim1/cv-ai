"""How well does the generic engine do on each captured portal? This is the
number that decides whether a platform needs an adapter."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.form_build import build_form                # noqa: E402
from app.services.page_probe import RawControl                # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "inventories"

paths = sorted(FIXTURES.glob("*.json"))
if not paths:
    print(f"no inventories in {FIXTURES}\n"
          "capture one first:  python tools/capture_page.py <url> --platform workday")
    raise SystemExit(0)

for path in paths:
    controls = [RawControl(**c) for c in json.loads(path.read_text(encoding="utf-8"))]
    form = build_form(controls)
    named = sum(1 for f in form.fields if f.label)
    print(f"{path.stem:<28} controls={len(controls):>3} "
          f"fields={len(form.fields):>3} named={named:>3}")
    for f in form.fields:
        print(f"    {f.type:<10} {f.label[:60]}")

"""Capture a real application page as a test fixture.

Usage:
    python tools/capture_page.py <url> --platform workday --slug senior-dev

Opens a visible browser and waits for you to press Enter. Log in, click through
to the actual application form, THEN press Enter — the snapshot is taken of
whatever is on screen at that moment.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.browser import PlaywrightDriver          # noqa: E402
from app.services.page_probe import probe_controls          # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "inventories"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--platform", required=True)
    ap.add_argument("--slug", default="1")
    ap.add_argument("--profile", default=".capture-profile")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    driver = PlaywrightDriver(headed=True, profile_dir=args.profile)
    try:
        driver.goto(args.url)
        input("Navigate to the application form, then press Enter to capture... ")
        controls = probe_controls(driver)
        stem = f"{args.platform}-{args.slug}"
        (OUT / f"{stem}.json").write_text(
            json.dumps([c.model_dump() for c in controls], indent=2, ensure_ascii=False),
            encoding="utf-8")
        (OUT / f"{stem}.html").write_text(driver.content(), encoding="utf-8")
        (OUT / f"{stem}.png").write_bytes(driver.screenshot())

        visible = [c for c in controls if c.visible and not c.disabled]
        named = [c for c in visible
                 if c.aria_label or c.labelledby_text or c.label_text]
        print(f"\ncaptured {stem}: {len(controls)} controls, "
              f"{len(visible)} visible, {len(named)} with an accessible name")
        for c in visible:
            name = c.aria_label or c.labelledby_text or c.label_text or "(unnamed)"
            print(f"  {c.role:<10} {name[:60]}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

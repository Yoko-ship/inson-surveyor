from pathlib import Path

p = Path("data/browser-test.db")
p.parent.mkdir(exist_ok=True)
p.unlink(missing_ok=True)

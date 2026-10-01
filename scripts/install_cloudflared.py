"""Install a checksum-verified official cloudflared release into ignored .tools/."""

import hashlib
import io
import platform
import tarfile
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
system = platform.system()
machine = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "amd64"
if system not in {"Darwin", "Linux", "Windows"}:
    raise SystemExit("Install cloudflared from the official Cloudflare instructions for your OS")
asset_name = {
    "Darwin": f"cloudflared-darwin-{machine}.tgz",
    "Linux": f"cloudflared-linux-{machine}",
    "Windows": f"cloudflared-windows-{machine}.exe",
}[system]
with httpx.Client(timeout=120, follow_redirects=True) as client:
    response = client.get("https://api.github.com/repos/cloudflare/cloudflared/releases/latest")
    response.raise_for_status()
    release = response.json()
    asset = next((a for a in release["assets"] if a["name"] == asset_name), None)
    if asset is None:
        raise SystemExit(f"No official release asset for {system}/{machine}; installation stopped")
    expected = asset.get("digest", "")
    if not expected.startswith("sha256:"):
        raise SystemExit("Release has no SHA256 digest; installation stopped")
    response = client.get(asset["browser_download_url"])
    response.raise_for_status()
    data = response.content
if hashlib.sha256(data).hexdigest() != expected.removeprefix("sha256:"):
    raise SystemExit("Cloudflared checksum mismatch")
if system == "Darwin":
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = next(m for m in archive.getmembers() if Path(m.name).name == "cloudflared" and m.isfile())
        data = archive.extractfile(member).read()
target = root / ".tools" / ("cloudflared.exe" if system == "Windows" else "cloudflared")
target.parent.mkdir(exist_ok=True)
if target.is_symlink():
    raise SystemExit("Refusing symlink destination")
target.write_bytes(data)
target.chmod(0o755)
print(f"Installed cloudflared {release['tag_name']} with verified SHA256 into .tools/")

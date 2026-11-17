"""Pre-flight checks for running the platform on another Windows computer."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import sys


ROOT = Path(__file__).resolve().parent
REQUIRED_PACKAGES = {
    "streamlit": "1.62.0",
    "openai": "3.5.0",
    "plotly": "5.24.1",
    "pandas": "2.2.3",
    "numpy": "2.1.3",
    "openpyxl": "3.1.5",
    "PyMuPDF": "1.28.2",
    "pdfplumber": "0.11.9",
    "requests": "2.32.3",
    "beautifulsoup4": "4.12.3",
    "python-pptx": "1.0.2",
}
REQUIRED_FILES = (
    "app.py",
    "step7.py",
    "step8.py",
    "report_i18n.py",
    "templates/中英文翻译词典.xlsx",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_network(host: str = "api.deepseek.com", port: int = 443) -> bool:
    try:
        with socket.create_connection((host, port), timeout=8):
            print(f"[OK] Network: {host}:{port} is reachable")
            return True
    except OSError as exc:
        print(f"[WARN] Network: cannot reach {host}:{port} ({exc})")
        print("       Local functions still work; AI calls may require an IT whitelist.")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--network",
        action="store_true",
        help="also test the default DeepSeek HTTPS endpoint",
    )
    args = parser.parse_args()
    errors = []

    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
        errors.append("Python must be 3.11-3.13; Python 3.13.5 is recommended.")

    print("\nDependency versions:")
    for package, expected in REQUIRED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "NOT INSTALLED"
        status = "OK" if actual == expected else "MISMATCH"
        print(f"[{status}] {package}: {actual} (expected {expected})")
        if actual != expected:
            errors.append(f"{package}: expected {expected}, found {actual}")

    print("\nRequired project files:")
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if path.is_file():
            print(f"[OK] {relative}")
        else:
            print(f"[MISSING] {relative}")
            errors.append(f"Missing file: {relative}")

    manifest_path = ROOT / "project_manifest.json"
    if manifest_path.is_file():
        print("\nProject integrity:")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for relative, expected_hash in manifest.get("sha256", {}).items():
                path = ROOT / relative
                if not path.is_file():
                    print(f"[MISSING] {relative}")
                    errors.append(f"Manifest file missing: {relative}")
                    continue
                actual_hash = sha256(path)
                status = "OK" if actual_hash == expected_hash else "CHANGED"
                print(f"[{status}] {relative}")
                if actual_hash != expected_hash:
                    errors.append(f"File differs from delivery package: {relative}")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"Cannot read project_manifest.json: {exc}")

    if args.network:
        print()
        check_network()

    print()
    if errors:
        print("Environment check FAILED:")
        for error in errors:
            print(f"- {error}")
        print("Run install_dependencies.bat in the intended Anaconda environment, then check again.")
        return 1

    print("Environment check PASSED. Start with: python -m streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


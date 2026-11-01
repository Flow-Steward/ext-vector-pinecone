"""Pure Python target archives preserve runtime metadata and exclude local data."""

import json
import zipfile
from pathlib import Path

import pytest
from scripts.package_extension import package_extension


@pytest.mark.parametrize("target", ["linux-amd64", "linux-arm64"])
def test_target_archive(tmp_path, target):
    root = Path(__file__).resolve().parents[1]
    a = package_extension(root, target, tmp_path)
    original = a.read_bytes()
    assert package_extension(root, target, tmp_path).read_bytes() == original
    with zipfile.ZipFile(a) as z:
        names = z.namelist()
        meta = json.loads(z.read("flowsteward_pinecone/.fs-package.yaml"))
        assert meta == {"runtime_target": target}
        assert "flowsteward_pinecone/main.py" in names
        assert "flowsteward_pinecone/icon.png" in names
        assert not any(
            "/.git/" in n or "/dist/" in n or "/.fs-python/" in n or "/bin/" in n for n in names
        )


def test_canonical_apache_license_bytes():
    import hashlib

    license_file = Path(__file__).resolve().parents[1] / "LICENSE"
    assert hashlib.sha256(license_file.read_bytes()).hexdigest() == (
        "58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd"
    )

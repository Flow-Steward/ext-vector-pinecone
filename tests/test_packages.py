"""Pure Python target archives preserve runtime metadata and exclude local data."""

import json
from pathlib import Path
import zipfile
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

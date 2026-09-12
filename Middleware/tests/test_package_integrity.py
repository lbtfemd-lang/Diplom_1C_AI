"""Packaging must reject tampering and exclude runtime state."""
import importlib.util
from pathlib import Path
import zipfile
import pytest

spec = importlib.util.spec_from_file_location("package_contest", Path(__file__).resolve().parents[2] / "scripts/package_contest.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


@pytest.mark.parametrize("tamper", [False, True])
def test_archive_payload_hash_detects_tampering(tmp_path, tamper):
    path = tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("source.py", b"changed" if tamper else b"original")
        archive.writestr("CHECKSUMS.sha256", package.digest(b"original") + "  source.py\n")
    if tamper:
        with pytest.raises(ValueError, match="Hash mismatch"):
            package.verify_package(path)
    else:
        assert package.verify_package(path) == 1


def test_selected_files_exclude_local_state():
    names = [name for name, path in package.source_files(package.ROOT)]
    assert names and len(names) == len(set(names))
    assert not any(name.endswith((".db", ".db-wal", ".env", ".pptx", ".epf")) for name in names)
    assert not any("handoffs" in name or "telegram_chats" in name or "metadata_store" in name for name in names)
    # Ensure the 3 required documents are present
    assert "Диплом_ИИ_ассистент_1С_окончательный.docx" in names
    assert "Аннотация.docx" in names
    assert "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.docx" in names
    assert "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.md" in names
    # Ensure redundant docs are excluded
    assert not any("docs/API.md" == name or "docs/SETUP_GUIDE.md" == name or "QUICKSTART" in name for name in names)

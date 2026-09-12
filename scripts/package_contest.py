"""Verified technical package. Diploma/slides are handled separately."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ZIP_NAME = "1C_AI_Assistant_Contest_Package.zip"
EXCLUDED = {".venv", "__pycache__", ".pytest_cache", "_pytest_tmp", "build", "dump_all", "scratch", "archive", "tools", "node_modules"}
SUFFIXES = {".py", ".md", ".txt", ".ini", ".html", ".css", ".js", ".svg", ".xml", ".bsl"}
TOKEN_PATTERNS = [re.compile(rb"\d{9,10}:AA[A-Za-z0-9_-]{30,}"),
                  re.compile(rb"vk1\.a\.[A-Za-z0-9_-]{20,}"),
                  re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_payload(name, data):
    for pattern in TOKEN_PATTERNS:
        for hit in pattern.findall(data):
            if b"xxxx" not in hit.lower() and not hit.startswith(b"123456789:"):
                raise ValueError(f"Possible credential in {name}; build stopped")


def source_files(root):
    for folder in ("Middleware", "1c_extensions/ai_assistant_src", "1c_extensions/kanban_board_src"):
        for path in sorted((root / folder).rglob("*")):
            rel = path.relative_to(root)
            if path.is_file() and not path.is_symlink() and not any(p in EXCLUDED for p in rel.parts):
                if path.suffix.lower() in SUFFIXES or path.name in (".env.example", "Dockerfile"):
                    yield rel.as_posix(), path

    # 1C CFE & BSL scripts
    yield "1c_extensions/AIAssistant.cfe", root / "1c_extensions/AIAssistant.cfe"
    for path in sorted((root / "1c_extensions").glob("*.bsl")):
        yield path.relative_to(root).as_posix(), path

    # Execution and build scripts
    for script_name in [
        "deploy_1c.bat",
        "run_demo.bat",
        "scripts/deploy_contest_base.py",
        "scripts/run_demo.py",
        "scripts/build_extension.py",
        "scripts/package_contest.py",
    ]:
        p = root / script_name
        if not p.is_file() or p.is_symlink():
            raise FileNotFoundError(script_name)
        yield script_name, p

    # Essential project documents requested for submission:
    # 1. Текст диплома
    diploma_docx = root / "text/Диплом_ИИ_ассистент_1С_окончательный.docx"
    if not diploma_docx.is_file():
        raise FileNotFoundError(str(diploma_docx))
    yield "Диплом_ИИ_ассистент_1С_окончательный.docx", diploma_docx

    # 2. Аннотация (из папки на защите)
    annot_docx = root / "dist/Аннотация.docx"
    if not annot_docx.is_file():
        raise FileNotFoundError(str(annot_docx))
    yield "Аннотация.docx", annot_docx

    # 3. Инструкция по развертыванию (DOCX и MD)
    instr_docx = root / "dist/ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.docx"
    if not instr_docx.is_file():
        raise FileNotFoundError(str(instr_docx))
    yield "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.docx", instr_docx

    instr_md = root / "docs/contest/ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.md"
    if not instr_md.is_file():
        raise FileNotFoundError(str(instr_md))
    yield "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.md", instr_md


def verify_package(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip():
            raise ValueError("Duplicate entries or corrupt archive")
        expected = {}
        for line in archive.read("CHECKSUMS.sha256").decode("utf-8").splitlines():
            checksum, name = line.split("  ", 1)
            expected[name] = checksum
        if set(names) != set(expected) | {"CHECKSUMS.sha256"}:
            raise ValueError("Manifest does not cover exact archive contents")
        for name, checksum in expected.items():
            data = archive.read(name)
            if digest(data) != checksum:
                raise ValueError(f"Hash mismatch: {name}")
            check_payload(name, data)
    return len(expected)


def build(root=ROOT):
    root = root.resolve()
    release, dist = root / "release", root / "dist"
    for path in (release, dist):
        if path.resolve().parent != root or path.is_symlink() or path.is_junction():
            raise ValueError(f"Unsafe build destination: {path}")
    with tempfile.TemporaryDirectory(prefix="diplom-package-") as temporary:
        stage = Path(temporary) / "release"
        stage.mkdir()
        copied = {}
        for name, source in source_files(root):
            data = source.read_bytes()
            check_payload(name, data)
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            copied[name] = digest(data)
        manifest = (
            "# Комплект материалов дипломного проекта\n\n"
            "Состав комплекта:\n"
            "1. Текст дипломного проекта: Диплом_ИИ_ассистент_1С_окончательный.docx\n"
            "2. Аннотация дипломного проекта: Аннотация.docx\n"
            "3. Руководство по развертыванию: ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.docx (.md)\n"
            "4. Разработка: расширение 1С (AIAssistant.cfe, исходные коды BSL/XML), интеграционный шлюз Middleware (FastAPI), тесты и сценарий deploy_1c.bat.\n\n"
            "## Реестр файлов\n\n" + "\n".join(f"- {name}" for name in sorted(copied)) + "\n"
        ).encode("utf-8")
        (stage / "PACKAGE_CONTENTS.md").write_bytes(manifest)
        copied["PACKAGE_CONTENTS.md"] = digest(manifest)
        (stage / "CHECKSUMS.sha256").write_text(
            "".join(f"{checksum}  {name}\n" for name, checksum in sorted(copied.items())), encoding="utf-8")
        staged_zip = Path(temporary) / ZIP_NAME
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())
        count = verify_package(staged_zip)
        checksum = digest(staged_zip.read_bytes())
        backup = Path(tempfile.mkdtemp(prefix="diplom-package-backup-"))
        if release.exists():
            shutil.copytree(release, backup / "release")
        for name in (ZIP_NAME, "CHECKSUMS.sha256", "PACKAGE_CONTENTS.md"):
            if (dist / name).exists():
                shutil.copy2(dist / name, backup / name)
        print(f"Rollback backup: {backup}", flush=True)
        try:
            if release.exists():
                shutil.rmtree(release)
            shutil.copytree(stage, release)
            dist.mkdir(exist_ok=True)
            shutil.copy2(staged_zip, dist / ZIP_NAME)
            (dist / "CHECKSUMS.sha256").write_text(f"{checksum}  {ZIP_NAME}\n", encoding="utf-8")
            shutil.copy2(stage / "PACKAGE_CONTENTS.md", dist / "PACKAGE_CONTENTS.md")
            verify_package(dist / ZIP_NAME)
        except Exception:
            if release.exists():
                shutil.rmtree(release)
            if (backup / "release").exists():
                shutil.copytree(backup / "release", release)
            for name in (ZIP_NAME, "CHECKSUMS.sha256", "PACKAGE_CONTENTS.md"):
                if (backup / name).exists():
                    shutil.copy2(backup / name, dist / name)
                elif (dist / name).exists():
                    (dist / name).unlink()
            raise
        print(f"Verified technical package: {count} payload files; SHA256 {checksum}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        print(f"Verified payload files: {verify_package(args.verify)}")
    else:
        build()

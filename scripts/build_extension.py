import subprocess
import tempfile
import os
import shutil
import sys

def build_extension():
    sys.stdout.reconfigure(encoding='utf-8')
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    src_dir = os.path.join(base_dir, "1c_extensions", "ai_assistant_src")
    output_cfe = os.path.join(base_dir, "1c_extensions", "AIAssistant.cfe")
    v8 = r"C:\Program Files\1cv8\8.5.1.1302\bin\1cv8.exe"

    if not os.path.exists(v8):
        print(f"Error: 1cv8.exe not found at {v8}", file=sys.stderr)
        return False

    print(f"Source dir: {src_dir}")
    print(f"Output CFE: {output_cfe}")

    temp_base = tempfile.mkdtemp(prefix="diplom-build-cfe-")
    staged_output = os.path.join(temp_base, "AIAssistant.cfe")

    log_file = os.path.join(temp_base, "designer_log.txt")

    try:
        # Step 1: Create clean empty infobase
        print("1. Creating temporary infobase...")
        res = subprocess.run([v8, "CREATEINFOBASE", f"File={temp_base};", "/DisableStartupDialogs"], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error creating infobase: code {res.returncode}", file=sys.stderr)
            return False

        # Step 2: Load extension from XML files
        print("2. Loading extension from XML sources...")
        res = subprocess.run([
            v8, "DESIGNER",
            "/F", temp_base,
            "/LoadConfigFromFiles", src_dir,
            "-Extension", "AIAssistant",
            "/Out", log_file,
            "/DisableStartupDialogs"
        ], capture_output=True, text=True)

        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                log_content = f.read().strip()
                if log_content:
                    print(f"Load log: {log_content}")

        if res.returncode != 0:
            print(f"Error loading extension: code {res.returncode}", file=sys.stderr)
            return False

        # Step 3: Dump extension to CFE
        print("3. Exporting extension to CFE...")
        if os.path.exists(log_file):
            os.remove(log_file)

        res = subprocess.run([
            v8, "DESIGNER",
            "/F", temp_base,
            "/DumpCfg", staged_output,
            "-Extension", "AIAssistant",
            "/Out", log_file,
            "/DisableStartupDialogs"
        ], capture_output=True, text=True)

        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                log_content = f.read().strip()
                if log_content:
                    print(f"Dump log: {log_content}")

        if res.returncode != 0:
            print(f"Error dumping CFE: code {res.returncode}", file=sys.stderr)
            return False

        if not os.path.exists(staged_output) or os.path.getsize(staged_output) == 0:
            print("Error: CFE file was not created or is empty!", file=sys.stderr)
            return False

        if os.path.exists(output_cfe):
            backup_dir = tempfile.mkdtemp(prefix="diplom-cfe-backup-")
            shutil.copy2(output_cfe, os.path.join(backup_dir, "AIAssistant.cfe"))
            print(f"Previous CFE backup: {backup_dir}")
        shutil.copy2(staged_output, output_cfe)
        print(f"SUCCESS: Built {output_cfe} ({os.path.getsize(output_cfe)} bytes)")
        return True

    finally:
        shutil.rmtree(temp_base, ignore_errors=True)

if __name__ == "__main__":
    success = build_extension()
    sys.exit(0 if success else 1)

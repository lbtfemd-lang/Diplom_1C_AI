import os
import subprocess
import shutil
import sys
import time

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')

    platform_path = r"C:\Program Files\1cv8\8.5.1.1302\bin\1cv8.exe"
    base_dir = r"d:\Share\Projects\diplom"
    cf_path = os.path.join(base_dir, "unpack_me.cf")
    temp_db_dir = os.path.join(base_dir, "temp_db")
    output_dir = os.path.join(base_dir, "config_unpacked")
    
    # Log files
    create_log = os.path.join(base_dir, "db_create.log")
    load_log = os.path.join(base_dir, "db_load.log")
    dump_log = os.path.join(base_dir, "db_dump.log")

    print(f"Platform path: {platform_path}")
    print(f"CF path: {cf_path}")
    print(f"Temp DB directory: {temp_db_dir}")
    print(f"Output directory: {output_dir}")

    # Verify platform exists
    if not os.path.exists(platform_path):
        print(f"Error: 1C executable not found at {platform_path}", file=sys.stderr)
        sys.exit(1)
        
    # Verify CF exists
    if not os.path.exists(cf_path):
        print(f"Error: CF file not found at {cf_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Clean up old temporary directories if they exist
    if os.path.exists(temp_db_dir):
        print(f"Cleaning up existing temp DB dir: {temp_db_dir}")
        shutil.rmtree(temp_db_dir, ignore_errors=True)
    os.makedirs(temp_db_dir, exist_ok=True)

    if os.path.exists(output_dir):
        print(f"Cleaning up existing output dir: {output_dir}")
        shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Step 1: Create empty infobase
        print("\n--- Step 1/3: Creating empty infobase ---")
        cmd_create = [
            platform_path,
            "CREATEINFOBASE",
            f"File={temp_db_dir};",
            "/Out", create_log
        ]
        print(f"Running command: {' '.join(cmd_create)}")
        start_time = time.time()
        res = subprocess.run(cmd_create, capture_output=True, text=True)
        print(f"Command returned: {res.returncode}")
        if os.path.exists(create_log):
            with open(create_log, "r", encoding="utf-8-sig", errors="ignore") as f:
                print(f"Create log content:\n{f.read()}")
        if res.returncode != 0:
            print("Error creating infobase. Exiting.", file=sys.stderr)
            sys.exit(res.returncode)
        print(f"Step 1 completed in {time.time() - start_time:.2f} seconds.")

        # Step 2: Load CF configuration
        print("\n--- Step 2/3: Loading CF file into infobase ---")
        cmd_load = [
            platform_path,
            "DESIGNER",
            "/F", temp_db_dir,
            "/LoadCfg", cf_path,
            "/Out", load_log
        ]
        print(f"Running command: {' '.join(cmd_load)}")
        start_time = time.time()
        res = subprocess.run(cmd_load, capture_output=True, text=True)
        print(f"Command returned: {res.returncode}")
        if os.path.exists(load_log):
            with open(load_log, "r", encoding="utf-8-sig", errors="ignore") as f:
                print(f"Load log content:\n{f.read()}")
        if res.returncode != 0:
            print("Error loading CF file. Exiting.", file=sys.stderr)
            sys.exit(res.returncode)
        print(f"Step 2 completed in {time.time() - start_time:.2f} seconds.")

        # Step 3: Dump configuration to files
        print("\n--- Step 3/3: Dumping configuration to files ---")
        cmd_dump = [
            platform_path,
            "DESIGNER",
            "/F", temp_db_dir,
            "/DumpConfigToFiles", output_dir,
            "/Out", dump_log
        ]
        print(f"Running command: {' '.join(cmd_dump)}")
        start_time = time.time()
        res = subprocess.run(cmd_dump, capture_output=True, text=True)
        print(f"Command returned: {res.returncode}")
        if os.path.exists(dump_log):
            with open(dump_log, "r", encoding="utf-8-sig", errors="ignore") as f:
                # The log can be very long, print first 200 lines and last 20 lines if it's long
                lines = f.readlines()
                if len(lines) > 220:
                    print(f"Dump log content (truncated - {len(lines)} lines total):")
                    print("".join(lines[:200]))
                    print("...\n[TRUNCATED]\n...")
                    print("".join(lines[-20:]))
                else:
                    print(f"Dump log content:\n{''.join(lines)}")
        if res.returncode != 0:
            print("Error dumping configuration to files. Exiting.", file=sys.stderr)
            sys.exit(res.returncode)
        print(f"Step 3 completed in {time.time() - start_time:.2f} seconds.")

        print("\nUnpacking successful!")

    finally:
        # Cleanup
        print("\n--- Cleaning up temporary infobase ---")
        if os.path.exists(temp_db_dir):
            # Give a small delay in case processes are still closing handles
            time.sleep(2)
            try:
                shutil.rmtree(temp_db_dir)
                print("Temporary database directory deleted.")
            except Exception as e:
                print(f"Warning: could not delete temporary database directory: {e}. You might need to delete it manually.")

if __name__ == "__main__":
    main()

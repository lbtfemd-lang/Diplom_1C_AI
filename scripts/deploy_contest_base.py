"""
Скрипт автоматизированного развёртывания демонстрационной базы «1С:УНФ 3.0» из DT-файла
для экспертного жюри Всероссийского конкурса дипломных проектов фирмы «1С».
"""
import os
import sys
import glob
import re
import shutil
import argparse
import subprocess

def find_1cv8_exe(explicit_path=None):
    if explicit_path and os.path.isfile(explicit_path):
        return explicit_path
    
    candidates = []
    for pattern in (
        r"C:\Program Files\1cv8\*\bin\1cv8.exe",
        r"C:\Program Files (x86)\1cv8\*\bin\1cv8.exe",
    ):
        candidates.extend(glob.glob(pattern))
    
    if not candidates:
        return None
        
    def ver_key(p):
        parts = re.findall(r"\d+", p)
        return [int(x) for x in parts]
        
    candidates.sort(key=ver_key, reverse=True)
    return candidates[0]

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_dt = os.path.join(root_dir, "dist", "SmallBusinessDemo.dt")
    default_base_dir = os.path.join(os.path.expanduser("~"), "Documents", "1C", "SmallBusinessDemo_AIAssistant")
    default_list_name = "1С:УНФ 3.0 — Интеллектуальный ассистент"

    parser = argparse.ArgumentParser(description="Автоматическое развёртывание базы 1С для конкурса")
    parser.add_argument("--dt", default=default_dt, help="Путь к файлу SmallBusinessDemo.dt")
    parser.add_argument("--db-dir", default=default_base_dir, help="Каталог размещения информационной базы")
    parser.add_argument("--list-name", default=default_list_name, help="Имя базы в списке 1С")
    parser.add_argument("--v8", default="", help="Путь к 1cv8.exe")
    parser.add_argument("--no-start", action="store_true", help="Не запускать 1С и Middleware после загрузки")
    args = parser.parse_args()

    print("=" * 70)
    print("РАЗВЁРТЫВАНИЕ ПРОЕКТА «ИНТЕЛЛЕКТУАЛЬНЫЙ АССИСТЕНТ ДЛЯ 1С:УНФ 3.0»")
    print("=" * 70)

    # 1. Проверка 1C
    v8_exe = find_1cv8_exe(args.v8)
    if not v8_exe:
        print("ОШИБКА: Платформа «1С:Предприятие» не обнаружена в Program Files!", file=sys.stderr)
        print("Укажите путь к 1cv8.exe через параметр --v8", file=sys.stderr)
        return 1
    print(f"Используемая платформа 1С: {v8_exe}")

    # 2. Проверка DT
    if not os.path.isfile(args.dt):
        print(f"ОШИБКА: Файл выгрузки базы не найден: {args.dt}", file=sys.stderr)
        return 1
    dt_size_mb = round(os.path.getsize(args.dt) / (1024 * 1024), 1)
    print(f"Файл выгрузки: {args.dt} ({dt_size_mb} МБ)")

    # 3. Подготовка каталога базы
    db_dir = os.path.abspath(args.db_dir)
    print(f"Целевой каталог базы: {db_dir}")
    os.makedirs(db_dir, exist_ok=True)

    # 4. Создание базы и добавление в список 1C (ibases.v8i)
    cd_file = os.path.join(db_dir, "1Cv8.1CD")
    if not os.path.isfile(cd_file):
        print("\n1. Создание информационной базы и добавление в список 1С...")
        cmd_create = [
            v8_exe, "CREATEINFOBASE",
            f"File={db_dir}",
            "/AddToList", args.list_name,
            "/DisableStartupDialogs"
        ]
        res_create = subprocess.run(cmd_create, capture_output=True, text=True)
        if res_create.returncode != 0 and not os.path.isfile(cd_file):
            print(f"ОШИБКА при создании базы: код {res_create.returncode}", file=sys.stderr)
            return 1
        print("База успешно создана и добавлена в список запуска 1С.")
    else:
        print("База уже существует в каталоге, выполняется обновление данных...")

    # 5. Восстановление из DT (/RestoreIB)
    print("\n2. Загрузка демонстрационных данных и расширений из файла DT...")
    print("Пожалуйста, подождите (процедура занимает около 1-2 минут)...")
    log_restore = os.path.join(db_dir, "restore_dt.log")
    cmd_restore = [
        v8_exe, "DESIGNER",
        "/F", db_dir,
        "/RestoreIB", args.dt,
        "/Out", log_restore,
        "/DisableStartupDialogs"
    ]
    res_restore = subprocess.run(cmd_restore, capture_output=True, text=True)
    
    if os.path.isfile(log_restore):
        with open(log_restore, "r", encoding="utf-8-sig", errors="ignore") as f:
            log_content = f.read().strip()
            if log_content:
                print(f"Журнал платформы: {log_content}")

    if res_restore.returncode != 0:
        print(f"ОШИБКА при загрузке базы из DT: код {res_restore.returncode}", file=sys.stderr)
        return 1

    if not os.path.isfile(cd_file) or os.path.getsize(cd_file) == 0:
        print("ОШИБКА: Файл 1Cv8.1CD пуст или отсутствует после загрузки!", file=sys.stderr)
        return 1

    final_size_mb = round(os.path.getsize(cd_file) / (1024 * 1024), 1)
    print(f"УСПЕШНО: База данных развёрнута (размер 1Cv8.1CD: {final_size_mb} МБ)!")

    # 6. Запуск сеансов при необходимости
    if not args.no_start:
        # Запуск Middleware в отдельном окне
        python_exe = sys.executable
        main_py = os.path.join(root_dir, "Middleware", "main.py")
        if os.path.isfile(main_py):
            print("\n3. Запуск сервера Middleware (FastAPI)...")
            subprocess.Popen([python_exe, main_py], cwd=root_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
            print("Сервер Middleware запущен на http://127.0.0.1:8000")

        # Запуск 1С:Предприятие
        print("\n4. Запуск сеанса «1С:Предприятие 8» под директором («Абдулов (директор)»)...")
        cmd_run = [
            v8_exe, "ENTERPRISE",
            "/F", db_dir,
            "/N", "Абдулов (директор)"
        ]
        subprocess.Popen(cmd_run)
        print("Окно «1С:Предприятия» запущено. Приятной демонстрации!")

    print("\n" + "=" * 70)
    print("РАЗВЁРТЫВАНИЕ УСПЕШНО ЗАВЕРШЕНО!")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())

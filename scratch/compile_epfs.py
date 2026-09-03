#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт автоматической сборки внешних обработок 1С (ЧатСАссистентом.epf, КанбанДоска.epf)
из XML-исходников и их копирования на Рабочий стол и в каталог build/.
"""

import os
import sys
import shutil
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_BUILD_SCRIPT = os.path.join(PROJECT_ROOT, ".agents", "skills", "epf-build", "scripts", "epf-build.py")
INFO_BASE_PATH = r"C:\Users\kobza\Documents\1C\SmallBusinessDemo"
DESKTOP_DIR = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\kobza"), "Desktop")
BUILD_DIR = os.path.join(PROJECT_ROOT, "1c_extensions", "build")

PROCESSORS = [
    {
        "name": "ЧатСАссистентом",
        "source": os.path.join(PROJECT_ROOT, "1c_extensions", "ai_assistant_src", "DataProcessors", "ЧатСАссистентом.xml"),
        "output_build": os.path.join(BUILD_DIR, "ЧатСАссистентом.epf"),
        "output_desktop": os.path.join(DESKTOP_DIR, "ЧатСАссистентом.epf")
    },
    {
        "name": "КанбанДоска",
        "source": os.path.join(PROJECT_ROOT, "1c_extensions", "ai_assistant_src", "DataProcessors", "КанбанДоска.xml"),
        "output_build": os.path.join(BUILD_DIR, "КанбанДоска.epf"),
        "output_desktop": os.path.join(DESKTOP_DIR, "КанбанДоска.epf")
    }
]

def compile_all():
    os.makedirs(BUILD_DIR, exist_ok=True)
    
    for item in PROCESSORS:
        name = item["name"]
        src = item["source"]
        out_build = item["output_build"]
        out_desktop = item["output_desktop"]
        
        print(f"==================================================")
        print(f"Сборка внешней обработки: {name}.epf")
        print(f"Исходник: {src}")
        print(f"Выходной файл: {out_build}")
        print(f"==================================================")
        
        cmd = [
            sys.executable,
            SKILL_BUILD_SCRIPT,
            "-SourceFile", src,
            "-OutputFile", out_build
        ]
        
        # Сборка через автоматическую базу заглушек метаданных 1С (не требует паролей)
        pass
            
        res = subprocess.run(cmd, capture_output=False)
        if res.returncode != 0:
            print(f"❌ Ошибка сборки {name}.epf (код: {res.returncode})")
        else:
            print(f"✅ {name}.epf успешно собран в {out_build}")
            try:
                shutil.copy2(out_build, out_desktop)
                print(f"✅ Скопирован на Рабочий стол: {out_desktop}")
            except Exception as e:
                print(f"⚠️ Не удалось скопировать на Рабочий стол: {e}")

if __name__ == "__main__":
    compile_all()

"""
Скрипт сборки полного текста диплома из отдельных глав.

Использование:
    python assemble_diploma.py

Создаёт файл Диплом_ИИ_ассистент_1С_полный_рерайт.md путём конкатенации
глав 00–05 в порядке нумерации и автоподстановки листингов кода в Приложения.
"""

import os

CHAPTERS = [
    "00_Введение_рерайт.md",
    "01_Глава1_Аналитика_рерайт.md",
    "02_Глава2_Проектирование_рерайт.md",
    "03_Глава3_Реализация_рерайт.md",
    "04_Глава4_БЖД_рерайт.md",
    "05_Заключение_Источники_Приложения_рерайт.md",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEXT_DIR = os.path.join(SCRIPT_DIR, "text")
OUTPUT = os.path.join(TEXT_DIR, "Диплом_ИИ_ассистент_1С_полный_рерайт.md")

# Paths to the core program files to embed (strictly limits pages to 80-90)
CODE_FILES = {
    "[CODE_1C_CHAT_PLACEHOLDER]": ("1c_extensions", "1C_Full_Code_v6_outline.md", "md"),
}


def read_code_file(parts_tuple):
    # The last element is the language, the rest are path segments
    path_segments = parts_tuple[:-1]
    lang = parts_tuple[-1]
    full_path = os.path.join(SCRIPT_DIR, *path_segments)
    
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Code file not found: {full_path}")
        
    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        code = f.read().strip()
        
    if lang == "md":
        return code
    return f"```{lang}\n{code}\n```"


def main():
    parts = []
    for chapter in CHAPTERS:
        path = os.path.join(TEXT_DIR, chapter)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Chapter not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().rstrip()
            
        # If it is the last chapter, substitute the code placeholders
        if chapter == "05_Заключение_Источники_Приложения_рерайт.md":
            print("Substituting code placeholders in Appendix...")
            for placeholder, file_info in CODE_FILES.items():
                try:
                    formatted_code = read_code_file(file_info)
                    if placeholder in content:
                        content = content.replace(placeholder, formatted_code)
                        print(f"  Successfully embedded {file_info[-2]} into {placeholder}")
                    else:
                        print(f"  Warning: Placeholder {placeholder} not found in Chapter 5")
                except Exception as e:
                    print(f"  Error loading {file_info[-2]}: {e}")
                    
        parts.append(content)

    full_text = "\n\n---\n\n".join(parts) + "\n"

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(full_text)

    size_kb = os.path.getsize(OUTPUT) / 1024
    print("Assembled %d chapters (%.1f KB)" % (len(CHAPTERS), size_kb))


if __name__ == "__main__":
    main()

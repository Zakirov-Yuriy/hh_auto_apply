#!/usr/bin/env python3
"""Скрипт для сборки exe файла приложения."""
import subprocess
import sys
from pathlib import Path

def build_exe():
    """Собирает exe файл с помощью PyInstaller."""
    print("🚀 Начинаем сборку exe файла...")
    
    # Проверяем наличие PyInstaller
    result = subprocess.run([sys.executable, "-m", "pyinstaller", "--version"], capture_output=True)
    if result.returncode != 0:
        print("❌ PyInstaller не установлен. Установляю...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Собираем exe
    spec_file = Path("hh_auto_apply.spec")
    if not spec_file.exists():
        print("❌ Файл hh_auto_apply.spec не найден!")
        return False
    
    print(f"📦 Используется конфигурация: {spec_file}")
    result = subprocess.run(
        [sys.executable, "-m", "pyinstaller", str(spec_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("❌ Ошибка при сборке:")
        print(result.stderr)
        return False
    
    exe_path = Path("dist/HH_Auto_Apply/HH_Auto_Apply.exe")
    if exe_path.exists():
        print(f"✅ Успешно собран exe файл: {exe_path}")
        print(f"📁 Размер: {exe_path.stat().st_size / (1024*1024):.1f} MB")
        return True
    else:
        print("❌ Exe файл не создан!")
        return False

if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)

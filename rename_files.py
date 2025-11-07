#!/usr/bin/env python3
"""
Скрипт для переименования файлов с опечаткой exampe -> example
"""

import os
from pathlib import Path


def rename_files_in_directory(directory_path, old_pattern, new_pattern):
    """
    Переименовывает файлы в указанной директории
    
    Args:
        directory_path: Путь к директории
        old_pattern: Старый паттерн для замены
        new_pattern: Новый паттерн для замены
    
    Returns:
        Словарь со статистикой: found, renamed, errors
    """
    dir_path = Path(directory_path)
    if not dir_path.exists():
        return None
    
    stats = {
        'found': 0,
        'renamed': 0,
        'errors': 0,
        'error_files': []
    }
    
    # Находим все файлы с опечаткой
    all_files = list(dir_path.iterdir())
    
    for file_path in all_files:
        if file_path.is_file() and old_pattern in file_path.name:
            stats['found'] += 1
            
            # Создаем новое имя файла
            new_name = file_path.name.replace(old_pattern, new_pattern)
            new_path = file_path.parent / new_name
            
            # Проверяем, не существует ли уже файл с таким именем
            if new_path.exists():
                print(f"   ПРЕДУПРЕЖДЕНИЕ: Файл {new_name} уже существует, пропускаем {file_path.name}")
                stats['errors'] += 1
                stats['error_files'].append(file_path.name)
                continue
            
            try:
                # Переименовываем файл
                file_path.rename(new_path)
                print(f"   Переименован: {file_path.name} -> {new_name}")
                stats['renamed'] += 1
            except Exception as e:
                print(f"   ОШИБКА при переименовании {file_path.name}: {e}")
                stats['errors'] += 1
                stats['error_files'].append(file_path.name)
    
    return stats


def main():
    """Основная функция скрипта"""
    # Путь к папке tests (относительно расположения скрипта)
    script_dir = Path(__file__).parent
    tests_dir = script_dir / 'tests'
    
    # Список папок для обработки
    folders_to_process = ['example1', 'example2', 'example3', 'example4']
    
    print("=" * 70)
    print("Переименование файлов: exampe -> example")
    print("=" * 70)
    print()
    
    # Общая статистика
    total_stats = {
        'found': 0,
        'renamed': 0,
        'errors': 0,
        'error_files': []
    }
    
    # Обработка каждой папки
    for folder_name in folders_to_process:
        folder_path = tests_dir / folder_name
        
        print(f"Обработка папки: {folder_name}")
        print(f"   Путь: {folder_path}")
        
        if not folder_path.exists():
            print(f"   ОШИБКА: Папка не найдена!")
            print()
            continue
        
        stats = rename_files_in_directory(folder_path, 'exampe', 'example')
        
        if stats is None:
            print(f"   ОШИБКА: Не удалось обработать папку")
            print()
            continue
        
        print(f"   Найдено файлов с опечаткой: {stats['found']}")
        print(f"   Успешно переименовано: {stats['renamed']}")
        if stats['errors'] > 0:
            print(f"   Ошибок: {stats['errors']}")
        print()
        
        # Добавляем к общей статистике
        total_stats['found'] += stats['found']
        total_stats['renamed'] += stats['renamed']
        total_stats['errors'] += stats['errors']
        total_stats['error_files'].extend(stats['error_files'])
    
    # Итоговая статистика
    print("=" * 70)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)
    print(f"Всего найдено файлов с опечаткой: {total_stats['found']}")
    print(f"Успешно переименовано: {total_stats['renamed']}")
    print(f"Ошибок: {total_stats['errors']}")
    
    if total_stats['error_files']:
        print("\nФайлы с ошибками:")
        for error_file in total_stats['error_files']:
            print(f"   - {error_file}")
    
    print("=" * 70)


if __name__ == '__main__':
    main()


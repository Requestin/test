#!/usr/bin/env python3
"""
Скрипт для анализа видео файлов в папках
Подсчитывает количество файлов, общую длительность и размер
"""

import os
import subprocess
import sys
from pathlib import Path


def get_video_duration(video_file):
    """
    Получает длительность видео в секундах используя ffprobe
    
    Args:
        video_file: Путь к видео файлу
    
    Returns:
        Длительность в секундах (float) или None если не удалось определить
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_file)
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        duration = result.stdout.strip()
        if duration and duration != 'N/A':
            return float(duration)
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


def format_duration(seconds):
    """
    Форматирует длительность в читаемый формат
    
    Args:
        seconds: Длительность в секундах
    
    Returns:
        Строка в формате "X часов Y минут Z секунд"
    """
    if seconds is None:
        return "неизвестно"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} час{'а' if 2 <= hours % 10 <= 4 and (hours % 100 < 10 or hours % 100 >= 20) else 'ов' if hours % 10 == 0 or (hours % 10 >= 5 and hours % 10 <= 9) or (hours % 100 >= 11 and hours % 100 <= 19) else ''}")
    if minutes > 0:
        parts.append(f"{minutes} минут{'ы' if 2 <= minutes % 10 <= 4 and (minutes % 100 < 10 or minutes % 100 >= 20) else '' if minutes % 10 == 1 and minutes % 100 != 11 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} секунд{'ы' if 2 <= secs % 10 <= 4 and (secs % 100 < 10 or secs % 100 >= 20) else '' if secs % 10 == 1 and secs % 100 != 11 else ''}")
    
    return " ".join(parts) if parts else "0 секунд"


def format_size(size_bytes):
    """
    Форматирует размер файла в читаемый формат
    
    Args:
        size_bytes: Размер в байтах
    
    Returns:
        Строка с размером (например, "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def analyze_directory(directory_path):
    """
    Анализирует все MP4 файлы в указанной директории
    
    Args:
        directory_path: Путь к директории
    
    Returns:
        Словарь со статистикой: count, total_duration, total_size
    """
    dir_path = Path(directory_path)
    if not dir_path.exists():
        return None
    
    stats = {
        'count': 0,
        'total_duration': 0.0,
        'total_size': 0,
        'files_with_duration': 0,
        'files_without_duration': 0
    }
    
    # Находим все MP4 файлы
    mp4_files = sorted(dir_path.glob('*.mp4'))
    
    for video_file in mp4_files:
        stats['count'] += 1
        
        # Получаем размер файла
        file_size = video_file.stat().st_size
        stats['total_size'] += file_size
        
        # Получаем длительность
        duration = get_video_duration(video_file)
        if duration is not None:
            stats['total_duration'] += duration
            stats['files_with_duration'] += 1
        else:
            stats['files_without_duration'] += 1
    
    return stats


def main():
    """Основная функция скрипта"""
    # Путь к папке tests (относительно расположения скрипта)
    script_dir = Path(__file__).parent
    tests_dir = script_dir / 'tests'
    
    # Список папок для анализа
    folders_to_analyze = ['example1', 'example2', 'example3', 'example4']
    
    print("=" * 70)
    print("Анализ видео файлов")
    print("=" * 70)
    print()
    
    # Проверка наличия ffprobe
    try:
        subprocess.run(['ffprobe', '-version'], 
                      capture_output=True, 
                      check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Предупреждение: ffprobe не найден, длительность будет недоступна")
        print()
    
    # Общая статистика
    total_stats = {
        'count': 0,
        'total_duration': 0.0,
        'total_size': 0,
        'files_with_duration': 0,
        'files_without_duration': 0
    }
    
    # Анализ каждой папки
    for folder_name in folders_to_analyze:
        folder_path = tests_dir / folder_name
        
        print(f"Анализ папки: {folder_name}")
        print(f"   Путь: {folder_path}")
        
        if not folder_path.exists():
            print(f"   ОШИБКА: Папка не найдена!")
            print()
            continue
        
        stats = analyze_directory(folder_path)
        
        if stats is None or stats['count'] == 0:
            print(f"   Предупреждение: Файлы не найдены")
            print()
            continue
        
        print(f"   Файлов: {stats['count']}")
        print(f"   Длительность: {format_duration(stats['total_duration'])} ({stats['total_duration']:.2f} сек)")
        print(f"   Размер: {format_size(stats['total_size'])}")
        
        if stats['files_without_duration'] > 0:
            print(f"   Предупреждение: Не удалось определить длительность для {stats['files_without_duration']} файлов")
        
        print()
        
        # Добавляем к общей статистике
        total_stats['count'] += stats['count']
        total_stats['total_duration'] += stats['total_duration']
        total_stats['total_size'] += stats['total_size']
        total_stats['files_with_duration'] += stats['files_with_duration']
        total_stats['files_without_duration'] += stats['files_without_duration']
    
    # Итоговая статистика
    print("=" * 70)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)
    print(f"Всего файлов: {total_stats['count']}")
    print(f"Общая длительность: {format_duration(total_stats['total_duration'])} ({total_stats['total_duration']:.2f} секунд)")
    print(f"Общий размер: {format_size(total_stats['total_size'])}")
    
    if total_stats['files_without_duration'] > 0:
        print(f"Предупреждение: Не удалось определить длительность для {total_stats['files_without_duration']} файлов из {total_stats['count']}")
    
    print("=" * 70)


if __name__ == '__main__':
    main()


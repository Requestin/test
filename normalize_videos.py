#!/usr/bin/env python3
"""
Скрипт для нормализации всех видео файлов под параметры example0.mp4
Сохраняет исходные разрешение и FPS каждого файла
"""

import os
import subprocess
import sys
import json
from pathlib import Path


def check_ffmpeg():
    """Проверяет наличие ffmpeg в системе"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, 
                      check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_reference_params(reference_file):
    """
    Получает параметры из эталонного файла example0.mp4
    
    Args:
        reference_file: Путь к эталонному файлу
    
    Returns:
        Словарь с параметрами эталона
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            str(reference_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Находим видео поток
        video_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            return None
        
        params = {
            'codec': video_stream.get('codec_name', 'h264'),
            'profile': video_stream.get('profile', ''),
            'level': video_stream.get('level', ''),
            'pix_fmt': video_stream.get('pix_fmt', 'yuv420p'),
            'bitrate': video_stream.get('bit_rate', ''),
            'encoder': video_stream.get('tags', {}).get('encoder', ''),
        }
        
        return params
    except Exception as e:
        print(f"Ошибка при чтении эталонного файла: {e}")
        return None


def get_video_params(video_file):
    """
    Получает разрешение и FPS из видео файла
    
    Args:
        video_file: Путь к видео файлу
    
    Returns:
        Словарь с width, height, fps или None
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'v:0',
            str(video_file)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        if not data.get('streams'):
            return None
        
        stream = data['streams'][0]
        
        # Получаем FPS
        fps_str = stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den > 0 else 30.0
        else:
            fps = float(fps_str) if fps_str else 30.0
        
        params = {
            'width': stream.get('width'),
            'height': stream.get('height'),
            'fps': fps
        }
        
        return params
    except Exception as e:
        print(f"  Ошибка при чтении параметров: {e}")
        return None


def normalize_video(input_file, output_file, reference_params, width, height, fps):
    """
    Нормализует видео файл под параметры эталона
    
    Args:
        input_file: Путь к исходному файлу
        output_file: Путь к выходному файлу
        reference_params: Параметры из эталонного файла
        width: Ширина (сохраняется)
        height: Высота (сохраняется)
        fps: FPS (сохраняется)
    """
    if not reference_params:
        return False
    
    # Преобразуем профиль для ffmpeg
    profile = reference_params.get('profile', 'high444')
    # "High 4:4:4 Predictive" -> "high444"
    if '4:4:4' in profile or '444' in profile.lower():
        profile_ffmpeg = 'high444'
    elif 'high' in profile.lower():
        profile_ffmpeg = 'high'
    else:
        profile_ffmpeg = 'high'
    
    # Преобразуем уровень (21 -> 2.1)
    level = reference_params.get('level', '21')
    if isinstance(level, str) and level.isdigit():
        level_int = int(level)
        level_ffmpeg = f"{level_int // 10}.{level_int % 10}"
    else:
        level_ffmpeg = str(level)
    
    # Получаем битрейт эталона
    bitrate = reference_params.get('bitrate', '')
    bitrate_int = None
    if bitrate:
        if isinstance(bitrate, str) and bitrate.isdigit():
            bitrate_int = int(bitrate)
        elif isinstance(bitrate, (int, float)):
            bitrate_int = int(bitrate)
    
    # Строим команду ffmpeg
    cmd = [
        'ffmpeg',
        '-i', str(input_file),
        '-map', '0:v:0',  # Только видео поток
        '-c:v', 'libx264',  # Кодек H.264
        '-profile:v', profile_ffmpeg,  # Профиль из эталона
        '-level:v', level_ffmpeg,  # Уровень из эталона
        '-pix_fmt', reference_params.get('pix_fmt', 'yuv420p'),  # Пиксельный формат
        '-preset', 'medium',  # Баланс скорости и качества
    ]
    
    # Используем битрейт если указан, иначе CRF для качества
    if bitrate_int:
        cmd.extend(['-b:v', str(bitrate_int)])
    else:
        cmd.extend(['-crf', '18'])  # Высокое качество
    
    cmd.extend([
        '-r', str(fps),  # Сохраняем исходный FPS
        '-s', f'{width}x{height}',  # Сохраняем исходное разрешение
        '-an',  # Без аудио (как в эталоне)
        '-y',  # Перезаписывать если существует
        str(output_file)
    ])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Ошибка при конвертации: {e.stderr[:200]}")
        return False


def process_directory(directory_path, reference_params, dry_run=False):
    """
    Обрабатывает все MP4 файлы в директории
    
    Args:
        directory_path: Путь к директории
        reference_params: Параметры эталона
        dry_run: Если True, только показывает что будет сделано
    
    Returns:
        Словарь со статистикой
    """
    dir_path = Path(directory_path)
    if not dir_path.exists():
        return None
    
    stats = {
        'processed': 0,
        'success': 0,
        'errors': 0,
        'skipped': 0
    }
    
    # Находим все MP4 файлы
    mp4_files = sorted(dir_path.glob('*.mp4'))
    
    for video_file in mp4_files:
        stats['processed'] += 1
        
        print(f"  [{stats['processed']}/{len(mp4_files)}] {video_file.name}")
        
        # Получаем параметры исходного файла
        video_params = get_video_params(video_file)
        if not video_params:
            print(f"    ОШИБКА: Не удалось получить параметры")
            stats['errors'] += 1
            continue
        
        width = video_params['width']
        height = video_params['height']
        fps = video_params['fps']
        
        print(f"    Разрешение: {width}x{height}, FPS: {fps:.2f}")
        
        if dry_run:
            print(f"    [DRY RUN] Будет перекодирован с параметрами эталона")
            stats['success'] += 1
            continue
        
        # Создаем временный файл
        temp_file = video_file.parent / f"{video_file.stem}_temp.mp4"
        output_file = video_file  # Перезаписываем исходный файл
        
        # Перекодируем во временный файл
        if normalize_video(video_file, temp_file, reference_params, width, height, fps):
            # Если успешно, заменяем исходный файл
            try:
                if output_file.exists():
                    output_file.unlink()
                temp_file.rename(output_file)
                print(f"    Успешно перекодирован")
                stats['success'] += 1
            except Exception as e:
                print(f"    ОШИБКА при замене файла: {e}")
                if temp_file.exists():
                    temp_file.unlink()
                stats['errors'] += 1
        else:
            if temp_file.exists():
                temp_file.unlink()
            stats['errors'] += 1
    
    return stats


def main():
    """Основная функция скрипта"""
    script_dir = Path(__file__).parent
    tests_dir = script_dir / 'tests'
    reference_file = tests_dir / 'example0.mp4'
    
    folders_to_process = ['example1', 'example2', 'example3', 'example4']
    
    print("=" * 70)
    print("Нормализация видео файлов под параметры example0.mp4")
    print("=" * 70)
    print()
    
    # Проверка наличия ffmpeg
    if not check_ffmpeg():
        print("ОШИБКА: ffmpeg не найден в системе!")
        sys.exit(1)
    
    # Получаем параметры эталона
    print("Чтение параметров эталонного файла example0.mp4...")
    reference_params = get_reference_params(reference_file)
    
    if not reference_params:
        print("ОШИБКА: Не удалось прочитать параметры эталона!")
        sys.exit(1)
    
    print("Параметры эталона:")
    print(f"  Кодек: {reference_params.get('codec', 'N/A')}")
    print(f"  Профиль: {reference_params.get('profile', 'N/A')}")
    print(f"  Уровень: {reference_params.get('level', 'N/A')}")
    print(f"  Пиксельный формат: {reference_params.get('pix_fmt', 'N/A')}")
    print(f"  Битрейт: {reference_params.get('bitrate', 'N/A')} bps")
    print()
    
    # Подтверждение (можно пропустить через аргумент --yes)
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    
    if not auto_confirm:
        print("ВНИМАНИЕ: Все файлы будут перекодированы и перезаписаны!")
        print("Разрешение и FPS каждого файла будут сохранены.")
        print("Остальные параметры будут приведены к эталону.")
        print()
        
        response = input("Продолжить? (yes/no): ").strip().lower()
        if response not in ['yes', 'y', 'да', 'д']:
            print("Отменено пользователем.")
            return
        
        print()
    
    # Общая статистика
    total_stats = {
        'processed': 0,
        'success': 0,
        'errors': 0,
        'skipped': 0
    }
    
    # Обработка каждой папки
    for folder_name in folders_to_process:
        folder_path = tests_dir / folder_name
        
        print(f"Обработка папки: {folder_name}")
        print(f"  Путь: {folder_path}")
        
        if not folder_path.exists():
            print(f"  ОШИБКА: Папка не найдена!")
            print()
            continue
        
        stats = process_directory(folder_path, reference_params, dry_run=False)
        
        if stats:
            print(f"  Обработано: {stats['processed']}")
            print(f"  Успешно: {stats['success']}")
            print(f"  Ошибок: {stats['errors']}")
            
            total_stats['processed'] += stats['processed']
            total_stats['success'] += stats['success']
            total_stats['errors'] += stats['errors']
            total_stats['skipped'] += stats['skipped']
        
        print()
    
    # Итоговая статистика
    print("=" * 70)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 70)
    print(f"Всего обработано: {total_stats['processed']}")
    print(f"Успешно: {total_stats['success']}")
    print(f"Ошибок: {total_stats['errors']}")
    print("=" * 70)


if __name__ == '__main__':
    main()


#!/usr/bin/env python3
"""
Скрипт для конвертации MP4 файлов с разрешением 720p в 480p и 360p
Находит файлы с "res720" в имени и создает копии с другими разрешениями
"""

import os
import subprocess
import sys
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


def find_res720_files(directory):
    """Находит все MP4 файлы с 'res720' в имени"""
    directory_path = Path(directory)
    if not directory_path.exists():
        print(f"❌ Ошибка: Папка '{directory}' не существует!")
        return []
    
    files = []
    for file in directory_path.glob('*.mp4'):
        if 'res720' in file.name:
            files.append(file)
    
    return sorted(files)


def map_codec_name(codec_name):
    """
    Преобразует имя кодека из ffprobe в имя кодека для ffmpeg
    
    Args:
        codec_name: Имя кодека из ffprobe
    
    Returns:
        Имя кодека для использования в ffmpeg
    """
    codec_mapping = {
        'h264': 'libx264',
        'hevc': 'libx265',
        'h265': 'libx265',
        'vp8': 'libvpx',
        'vp9': 'libvpx-vp9',
        'av1': 'libaom-av1',
    }
    return codec_mapping.get(codec_name.lower(), codec_name)


def get_video_info(input_file):
    """
    Определяет параметры видео из исходного файла
    
    Args:
        input_file: Путь к исходному файлу
    
    Returns:
        Словарь с параметрами: codec, bitrate, fps, profile, level и т.д.
    """
    info = {}
    
    try:
        # Получаем кодек
        cmd_codec = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(input_file)
        ]
        result = subprocess.run(cmd_codec, capture_output=True, text=True, check=True)
        info['codec'] = result.stdout.strip() or None
        
        # Получаем битрейт
        cmd_bitrate = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=bit_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(input_file)
        ]
        result = subprocess.run(cmd_bitrate, capture_output=True, text=True, check=True)
        bitrate = result.stdout.strip()
        info['bitrate'] = bitrate if bitrate and bitrate != 'N/A' else None
        
        # Получаем FPS
        cmd_fps = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(input_file)
        ]
        result = subprocess.run(cmd_fps, capture_output=True, text=True, check=True)
        fps_str = result.stdout.strip()
        if fps_str and '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            info['fps'] = num / den if den > 0 else None
        else:
            info['fps'] = None
        
        # Получаем профиль и уровень для H.264/H.265
        cmd_profile = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=profile,level',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(input_file)
        ]
        result = subprocess.run(cmd_profile, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        info['profile'] = lines[0] if lines and lines[0] else None
        info['level'] = lines[1] if len(lines) > 1 and lines[1] else None
        
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass
    
    return info


def convert_video(input_file, output_file, resolution):
    """
    Конвертирует видео в указанное разрешение, сохраняя все параметры исходного видео
    
    Args:
        input_file: Путь к исходному файлу
        output_file: Путь к выходному файлу
        resolution: Кортеж (width, height) для разрешения
    """
    width, height = resolution
    
    # Получаем параметры исходного видео
    video_info = get_video_info(input_file)
    source_codec = video_info.get('codec')
    video_codec = map_codec_name(source_codec) if source_codec else 'libx264'
    
    print(f"  📹 Кодек: {source_codec or 'не определен'} → {video_codec}", end='')
    if video_info.get('bitrate'):
        print(f" | Битрейт: {video_info['bitrate']} bps", end='')
    if video_info.get('fps'):
        print(f" | FPS: {video_info['fps']:.2f}", end='')
    print()
    
    # Строим команду ffmpeg
    cmd = [
        'ffmpeg',
        '-i', str(input_file),
        '-map', '0',  # Копируем все потоки
        '-vf', f'scale={width}:{height}',  # Меняем только разрешение
        '-c:v', video_codec,  # Используем тот же кодек видео
    ]
    
    # Сохраняем битрейт если он был определен
    if video_info.get('bitrate'):
        cmd.extend(['-b:v', video_info['bitrate']])
    
    # Сохраняем FPS если он был определен
    if video_info.get('fps'):
        cmd.extend(['-r', str(video_info['fps'])])
    
    # Сохраняем профиль и уровень для H.264/H.265
    if video_info.get('profile') and video_codec in ['libx264', 'libx265']:
        cmd.extend(['-profile:v', video_info['profile']])
    if video_info.get('level') and video_codec in ['libx264', 'libx265']:
        cmd.extend(['-level', video_info['level']])
    
    # Копируем аудио и субтитры без изменений
    cmd.extend([
        '-c:a', 'copy',  # Копируем аудио без изменений
        '-c:s', 'copy',  # Копируем субтитры без изменений
        '-map_metadata', '0',  # Копируем метаданные
        '-y',  # Перезаписывать файл если существует
        str(output_file)
    ])
    
    try:
        print(f"  ⏳ Конвертация в {width}x{height}...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Ошибка при конвертации: {e.stderr}")
        return False


def generate_output_filename(input_file, resolution_tag):
    """
    Генерирует имя выходного файла на основе входного
    
    Args:
        input_file: Path объект исходного файла
        resolution_tag: Тег разрешения ('res480' или 'res360')
    
    Returns:
        Path объект для выходного файла
    """
    # Заменяем res720 на res480 или res360
    new_name = input_file.name.replace('res720', resolution_tag)
    return input_file.parent / new_name


def main():
    """Основная функция скрипта"""
    # Путь к папке convert (относительно расположения скрипта)
    script_dir = Path(__file__).parent
    convert_dir = script_dir / 'convert'
    
    print("=" * 60)
    print("🎬 Скрипт конвертации видео")
    print("=" * 60)
    print()
    
    # Проверка наличия ffmpeg
    print("🔍 Проверка наличия ffmpeg...")
    if not check_ffmpeg():
        print("❌ Ошибка: ffmpeg не найден в системе!")
        print("   Установите ffmpeg и добавьте его в PATH")
        sys.exit(1)
    print("✅ ffmpeg найден")
    print()
    
    # Поиск файлов с res720
    print(f"📁 Поиск файлов с 'res720' в папке: {convert_dir}")
    files_to_convert = find_res720_files(convert_dir)
    
    if not files_to_convert:
        print("⚠️  Файлы с 'res720' не найдены!")
        return
    
    print(f"✅ Найдено файлов: {len(files_to_convert)}")
    for file in files_to_convert:
        print(f"   - {file.name}")
    print()
    
    # Разрешения для конвертации
    resolutions = [
        ('res480', (624, 480)),
        ('res360', (468, 360))
    ]
    
    # Конвертация каждого файла
    total_files = len(files_to_convert)
    successful_conversions = 0
    
    for idx, input_file in enumerate(files_to_convert, 1):
        print(f"[{idx}/{total_files}] Обработка: {input_file.name}")
        
        file_success = True
        
        for resolution_tag, resolution in resolutions:
            output_file = generate_output_filename(input_file, resolution_tag)
            
            # Проверяем, существует ли уже файл
            if output_file.exists():
                print(f"  ⚠️  Файл {output_file.name} уже существует, пропускаем...")
                continue
            
            if convert_video(input_file, output_file, resolution):
                print(f"  ✅ Создан: {output_file.name}")
            else:
                print(f"  ❌ Не удалось создать: {output_file.name}")
                file_success = False
        
        if file_success:
            successful_conversions += 1
        
        print()
    
    # Итоговая статистика
    print("=" * 60)
    print("📊 Итоги конвертации:")
    print(f"   Всего файлов обработано: {total_files}")
    print(f"   Успешно сконвертировано: {successful_conversions}")
    print("=" * 60)


if __name__ == '__main__':
    main()


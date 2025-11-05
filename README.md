# Установка FlashVSR

## Системные требования

1. **Ubuntu** (на Windows через WSL 2)
2. **Conda** (окружение на Python 3.11.13)
3. **CUDA Toolkit 12**
4. **PyTorch 2.5.1 + cu121** (в requirements указан 2.6.0+cu124, но это необязательно)

## Установка Block-Sparse-Attention

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/mit-han-lab/Block-Sparse-Attention.git
```

Скачиваем в корневую папку `~/`, должно получиться `~/Block-Sparse-Attention`.

### Шаг 2: Установка зависимостей

```bash
pip install packaging
pip install ninja
```

> **Примечание:** Может также потребоваться установить `gnupg`.

### Шаг 3: Настройка setup.py

Чтобы собрать Block-Sparse-Attention, нужно исправить `setup.py`:

#### 3.1. Установка количества потоков

Установить `--threads 1` (если ПК справляется и не крашится, можно увеличить, максимум пробовал 4).

Изменить функцию:

```python
def append_nvcc_threads(nvcc_extra_args):
    return nvcc_extra_args + ["--threads", "1"]
```

#### 3.2. Указание архитектуры видеокарты

Необходимо указать архитектуру своей видеокарты для сборки:

```python
cc_flag.append("-gencode")
cc_flag.append("arch=compute_86,code=sm_86")
```

**Примеры архитектур:**
- `sm_86` — для RTX A4000
- `sm_89` — для RTX 4090

> **Важно:** Строки с упоминанием `sm_90` нужно удалить, если не используется A100/A800.
> 
> Файлы `*_sm80.cu` не трогаем — это имена исходников, важны именно флаги `cc_flag`.

### Шаг 4: Сборка

Перед запуском сборки в консоли прописываем:

```bash
export MAX_JOBS=1
export CMAKE_BUILD_PARALLEL_LEVEL=1
export NINJAFLAGS="-j1"
```

> **Примечание:** Параметры можно повышать, если ПК справляется (повышал максимум до 4).

Запускаем сборку командой:

```bash
pip install --no-build-isolation -v .
```

> **Примечание:** Можно и через setup.py, как указано в гайде, но я делал так.

Если все хорошо — отлично. Если нет — понижаем вышеупомянутые параметры или обращаемся за помощью к нейронке.

## Установка FlashVSR

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/OpenImagingLab/FlashVSR.git
```

Качаем также в `~/`, получится `~/FlashVSR`.

### Шаг 2: Настройка requirements.txt

Берем `requirements.txt` и комментируем там строки:

```txt
# torch==2.6.0+cu124
# torchaudio==2.6.0+cu124
# torchvision==0.21.0+cu124
```

Остальное можно оставить.

### Шаг 3: Установка зависимостей

```bash
pip install -e .
pip install -r requirements.txt
```

### Шаг 4: Скачивание весов модели

```bash
cd examples/WanVSR
git lfs install
git lfs clone https://huggingface.co/JunhaoZhuang/FlashVSR
```

## Настройка для слабых видеокарт

На слабой видеокарте модель может не запуститься. Берем `tiny.py` и `full.py` и заменяем соответствующие `infer_flashvsr_tiny.py` и `infer_flashvsr_full.py` в папке `examples/WanVSR`. (Имена скриптов сохраняем исходные)

### Ограничение памяти

Душим модель при помощи параметра `FLASHVSR_MAX_LONG` — это максимальное выходное разрешение.

**Рекомендуемые значения:**
- RTX 4090: `1536` для tiny и `1152` для full

> **Примечание:** Остальные параметры, которые советовала нейронка (например: включить режим tiled и регулировать размеры тайлов) — не помогли, все равно все время вылетало из-за нехватки памяти.

## Тестирование

Тестировалось на видео `original.mp4` (384×384, 16 кадров).

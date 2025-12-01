import whisper
import yaml
import json
import os
import torch

def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def transcribe_audio():
    cfg = load_config()
    
    input_audio = cfg['paths']['input_audio']
    cache_dir = cfg['paths']['cache_dir']
    output_file = os.path.join(cache_dir, "transcript.json")
    
    # 1. Проверка кэша
    if os.path.exists(output_file):
        print(f"⏩ Транскрипция найдена в кэше: {output_file}")
        with open(output_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    print(f"👂 Начинаем транскрибацию: {input_audio}")
    
    # 2. Загрузка модели (Whisper хорошо работает и на CPU, и на GPU)
    # Используем device из конфига, но для Whisper лучше явно указать cuda если есть, иначе cpu
    device = cfg['models']['device']
    model_size = cfg['models']['whisper_size']
    
    print(f"   Загрузка модели Whisper ({model_size}) на {device}...")
    model = whisper.load_model(model_size, device=device)
    
    # 3. Распознавание
    result = model.transcribe(input_audio, verbose=False)
    
    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip()
        })
    
    # 4. Сохранение
    os.makedirs(cache_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Транскрипция сохранена: {output_file}")
    return segments

if __name__ == "__main__":
    transcribe_audio()
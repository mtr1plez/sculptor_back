# src/video_indexer.py
import os
import cv2
import json
import torch
import numpy as np
from PIL import Image
from tqdm import tqdm
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from sentence_transformers import SentenceTransformer

from utils import load_config

def detect_scenes(video_path, threshold=27.0, min_duration=1.0):
    """Шаг 1: Нарезка видео на сцены"""
    print(f"✂️ Ищем сцены в {os.path.basename(video_path)}...")
    
    video_manager = VideoManager([video_path])
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_duration))
    
    video_manager.start()
    scene_manager.detect_scenes(frame_source=video_manager, show_progress=True)
    scene_list = scene_manager.get_scene_list()
    
    scenes = []
    scene_id = 0  # Принудительно последовательный ID
    
    for start, end in scene_list:
        duration = end.get_seconds() - start.get_seconds()
        if duration < min_duration:
            continue
            
        scenes.append({
            "id": scene_id,  # 0, 1, 2, 3, 4... последовательно!
            "start_time": start.get_seconds(),
            "end_time": end.get_seconds(),
            "duration": duration,
            "frame_path": ""
        })
        scene_id += 1  # Инкремент только для валидных сцен
    
    print(f"✅ Найдено {len(scenes)} сцен.")
    return scenes

def extract_frames(video_path, scenes, output_dir, image_size=224):
    """Шаг 2: Извлечение кадров для каждой сцены"""
    print("📸 Извлекаем кадры...")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise IOError(f"Не удалось открыть видео: {video_path}")

    valid_scenes = []

    for scene in tqdm(scenes):
        # Берем кадр из середины сцены
        mid_time = scene["start_time"] + (scene["duration"] / 2)
        
        # Перематываем видео на нужный момент (в миллисекундах)
        cap.set(cv2.CAP_PROP_POS_MSEC, mid_time * 1000)
        ret, frame = cap.read()
        
        if ret:
            # Конвертируем BGR (OpenCV) -> RGB (PIL)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            
            # Ресайз для экономии места и скорости
            img = img.resize((image_size, image_size))
            
            filename = f"scene_{scene['id']}.jpg"
            filepath = os.path.join(output_dir, filename)
            img.save(filepath, quality=80)
            
            scene["frame_path"] = filepath
            valid_scenes.append(scene)
        else:
            print(f"⚠️ Не удалось прочитать кадр для сцены {scene['id']}")

    cap.release()
    return valid_scenes

def embed_scenes(scenes, model_name, device):
    """Шаг 3: Создание векторов через CLIP"""
    print(f"🧠 Загружаем CLIP ({model_name}) на {device}...")
    model = SentenceTransformer(model_name, device=device)
    
    image_paths = [s["frame_path"] for s in scenes]
    
    print("⚡ Генерируем эмбеддинги (векторы)...")
    # batch_size=32 оптимально для 3050Ti
    embeddings = model.encode(
        [Image.open(p) for p in image_paths], 
        batch_size=32, 
        convert_to_tensor=False, 
        show_progress_bar=True
    )
    
    return embeddings

def run_indexer():
    cfg = load_config()
    
    video_path = cfg["paths"]["input_video"]
    cache_dir = cfg["paths"]["cache_dir"]
    frames_dir = cfg["paths"]["frames_dir"]
    index_path = os.path.join(cache_dir, "scene_index.json")
    emb_path = os.path.join(cache_dir, "embeddings.npy")

    # 0. Проверка: Если индекс уже есть, не делаем работу дважды
    if os.path.exists(index_path) and os.path.exists(emb_path):
        print("📂 Индекс уже существует. Пропускаем индексацию.")
        # Тут можно добавить логику "force update", если надо
        return

    # 1. Детекция
    scenes = detect_scenes(
        video_path, 
        threshold=cfg["params"]["scene_threshold"],
        min_duration=cfg["params"]["min_scene_duration"]
    )
    
    # 2. Экстракция кадров
    scenes = extract_frames(
        video_path, 
        scenes, 
        frames_dir, 
        image_size=cfg["params"]["image_size"]
    )
    
    # 3. Эмбеддинг
    embeddings = embed_scenes(
        scenes, 
        cfg["models"]["clip_model"], 
        cfg["models"]["device"]
    )
    
    # 4. Сохранение результатов
    print("💾 Сохраняем данные...")
    
    # Сохраняем JSON (метаданные)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=4)
        
    # Сохраняем NPY (векторы)
    np.save(emb_path, embeddings)
    
    print("🎉 Индексация завершена!")

if __name__ == "__main__":
    # Для теста запускаем функцию напрямую
    run_indexer()
import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
import numpy as np
from sentence_transformers import SentenceTransformer
import re
import random

from utils import load_config


class SmartMatcher:
    """Умный матчер с учетом контекста персонажей"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
        self.device = self.cfg["models"]["device"]
        self.clip_model = self.cfg["models"]["clip_model"]
        
        print(f"🧠 Загружаю {self.clip_model} на {self.device}...")
        self.model = SentenceTransformer(self.clip_model, device=self.device)
        
        # === КОНТЕКСТ И ПЕРСОНАЖИ ===
        self.active_character = None
        
        # === РОТАЦИЯ И COOLDOWN ===
        self.frame_usage_count = {}
        self.frame_last_used_at = {}
        self.max_frame_usage = 3
        self.min_frame_cooldown = 20  # Базовый cooldown
        self.top_candidates_pool = 5
        
        # === CONTINUITY (НЕПРЕРЫВНОСТЬ) ===
        self.continuity_bonus = 0.05
        self.scene_continuity_window = 48  # ~2 секунды при 24fps
        self.last_selected_frame_idx = None
        
        # === СЛОВАРЬ ИМЕН (загружается динамически) ===
        self.name_translations = {}
    
    def load_character_names(self, names_dict_path: str) -> Dict[str, Dict]:
        """
        Загрузка словаря вариаций имен персонажей
        
        Args:
            names_dict_path: Путь к character_names.json
        
        Returns:
            Словарь вариаций
        """
        try:
            with open(names_dict_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Словарь имен не найден: {names_dict_path}")
            print("   Запусти character_detector.py для создания словаря")
            return {}
        except Exception as e:
            print(f"⚠️ Ошибка загрузки словаря: {e}")
            return {}
    
    def build_translation_map(self, char_names_dict: Dict[str, Dict]) -> Dict[str, str]:
        """
        Построение плоского словаря переводов из словаря вариаций
        
        Args:
            char_names_dict: Словарь вариаций от character_detector
        
        Returns:
            Плоский словарь {вариация: основное_имя}
        """
        translations = {}
        
        for main_name, variations in char_names_dict.items():
            # Все русские вариации
            for rus_var in variations.get('russian', []):
                translations[rus_var.lower()] = main_name
            
            # Все английские вариации
            for eng_var in variations.get('english', []):
                translations[eng_var.lower()] = main_name
            
            # Все алиасы
            for alias in variations.get('aliases', []):
                translations[alias.lower()] = main_name
        
        return translations
    
    def load_transcript(self, transcript_path: str) -> List[Dict]:
        """Загрузка транскрипта"""
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def load_character_map(self, character_map_path: str) -> Dict[str, List[int]]:
        """Загрузка карты персонажей"""
        with open(character_map_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extract_character_names(self, text: str, known_characters: List[str]) -> List[str]:
        """
        Умный NER с поддержкой русского языка
        
        Args:
            text: Текст для анализа (может быть на русском)
            known_characters: Список известных персонажей (на английском)
        
        Returns:
            Список найденных персонажей (на английском)
        """
        found = []
        text_lower = text.lower()
        
        # Сначала ищем русские варианты имен
        for rus_name, eng_name in self.name_translations.items():
            pattern = r'\b' + re.escape(rus_name) + r'\b'
            if re.search(pattern, text_lower):
                # Проверяем что такой персонаж есть в known_characters
                if eng_name in known_characters and eng_name not in found:
                    found.append(eng_name)
        
        # Потом проверяем английские имена напрямую (если есть)
        for char in known_characters:
            pattern = r'\b' + re.escape(char.lower()) + r'\b'
            if re.search(pattern, text_lower) and char not in found:
                found.append(char)
        
        return found
    
    def get_search_pool(
        self, 
        text: str, 
        character_map: Dict[str, List[int]],
        all_scene_ids: List[int]
    ) -> tuple[List[int], str]:
        """
        Определение пула сцен с умным контекстом
        
        Args:
            text: Текст чанка
            character_map: Карта персонажей
            all_scene_ids: Все доступные ID сцен
        
        Returns:
            (пул сцен, описание контекста)
        """
        known_characters = [char for char in character_map.keys() if char != "none"]
        
        # 1. Ищем явные упоминания имен
        mentioned_characters = self.extract_character_names(text, known_characters)
        
        if mentioned_characters:
            # Нашли кого-то конкретного
            primary_char = mentioned_characters[0]
            
            # Если это НОВЫЙ персонаж, переключаемся
            if primary_char != self.active_character:
                self.active_character = primary_char
                context = f"смена контекста -> {self.active_character}"
            else:
                context = f"подтверждение -> {self.active_character}"
        
        # 2. Если имен нет, проверяем "липкий контекст"
        elif self.active_character:
            # Остаемся на старом персонаже
            context = f"удержание контекста ({self.active_character})"
        else:
            context = "без контекста (общий поиск)"
        
        # 3. Выбираем пул сцен
        if self.active_character:
            pool = character_map.get(self.active_character, [])
            # Если у персонажа нет кадров, fallback на всех
            if not pool:
                pool = all_scene_ids
                context += " (пул пуст -> fallback)"
        else:
            pool = all_scene_ids
        
        return pool, context
    
    def find_best_match_with_rotation(
        self,
        text_emb: np.ndarray,
        pool_embeddings: np.ndarray,
        pool_indices: List[int],
        frame_files: List[Path],
        current_chunk_idx: int
    ) -> tuple[int, float]:
        """
        Поиск лучшего совпадения с ротацией, cooldown, рандомизацией и continuity
        
        Args:
            text_emb: Эмбеддинг текста
            pool_embeddings: Эмбеддинги кадров из пула
            pool_indices: Индексы кадров в пуле
            frame_files: Список всех файлов кадров
            current_chunk_idx: Текущий индекс чанка
        
        Returns:
            (индекс лучшего кадра, score)
        """
        # 1. Базовый Semantic Similarity (косинусное сходство)
        base_scores = pool_embeddings @ text_emb
        
        # 2. Добавляем бонус за непрерывность (Continuity Bonus)
        # Если кадр находится рядом с предыдущим, он получает буст
        final_scores = base_scores.copy()
        
        if self.last_selected_frame_idx is not None:
            for i, real_idx in enumerate(pool_indices):
                dist = abs(real_idx - self.last_selected_frame_idx)
                
                # Бонус только если кадр близко, но не тот же самый
                # ВАЖНО: dist должен быть достаточно большим, чтобы не брать соседний кадр
                if 5 < dist < self.scene_continuity_window:
                    final_scores[i] += self.continuity_bonus
        
        # 3. Динамический cooldown на основе размера пула
        pool_size = len(pool_indices)
        dynamic_cooldown = max(5, min(20, pool_size // 10))
        # 20 кадров → cooldown 5
        # 100 кадров → cooldown 10  
        # 300+ кадров → cooldown 20
        
        # 4. Сортировка и фильтрация кандидатов
        sorted_indices = np.argsort(final_scores)[::-1]
        candidates = []
        
        for pool_idx in sorted_indices:
            real_idx = pool_indices[pool_idx]
            frame_name = frame_files[real_idx].name
            
            usage_count = self.frame_usage_count.get(frame_name, 0)
            last_used = self.frame_last_used_at.get(frame_name, -999)
            
            # Лимит использований
            if usage_count >= self.max_frame_usage:
                continue
            
            # Динамический cooldown
            if (current_chunk_idx - last_used) < dynamic_cooldown:
                continue
            
            candidates.append({
                'real_idx': real_idx,
                'score': float(final_scores[pool_idx]),
                'frame_name': frame_name
            })
            
            # Собираем топ-N кандидатов
            if len(candidates) >= self.top_candidates_pool:
                break
        
        # 5. Выбор победителя
        if candidates:
            # Weighted random choice - лучшие кадры чаще выбираются
            weights = [c['score'] for c in candidates]
            chosen = random.choices(candidates, weights=weights)[0]
        else:
            # Fallback: если все в cooldown, берем лучший по score
            best_idx_raw = np.argmax(final_scores)
            chosen = {
                'real_idx': pool_indices[best_idx_raw],
                'score': float(final_scores[best_idx_raw]),
                'frame_name': frame_files[pool_indices[best_idx_raw]].name
            }
        
        # 6. Обновление состояния
        self.frame_usage_count[chosen['frame_name']] = \
            self.frame_usage_count.get(chosen['frame_name'], 0) + 1
        self.frame_last_used_at[chosen['frame_name']] = current_chunk_idx
        self.last_selected_frame_idx = chosen['real_idx']
        
        return chosen['real_idx'], chosen['score']
    
    def normalize_vector(self, vec: np.ndarray) -> np.ndarray:
        """Нормализация вектора"""
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    
    def match_audio_to_frames(
        self,
        transcript_path: str = None,
        character_map_path: str = None,
        names_dict_path: str = None,
        frames_dir: str = None,
        embeddings_path: str = None,
        output_path: str = None
    ) -> List[Dict]:
        """
        Основная функция умного матчинга
        
        Args:
            transcript_path: Путь к транскрипту
            character_map_path: Путь к карте персонажей
            names_dict_path: Путь к словарю вариаций имен
            frames_dir: Путь к папке с фреймами
            embeddings_path: Путь к эмбеддингам фреймов
            output_path: Путь для сохранения результата
        
        Returns:
            Список результатов матчинга
        """
        # Дефолтные пути
        if transcript_path is None:
            transcript_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "transcript.json"
            )
        if character_map_path is None:
            character_map_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "character_frames.json"
            )
        if names_dict_path is None:
            names_dict_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "character_names.json"
            )
        if frames_dir is None:
            frames_dir = self.cfg["paths"]["frames_dir"]
        if embeddings_path is None:
            embeddings_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "embeddings.npy"
            )
        if output_path is None:
            output_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "edit_plan.json"
            )
        
        print("📄 Загружаю данные...")
        transcript = self.load_transcript(transcript_path)
        character_map = self.load_character_map(character_map_path)
        
        # Загрузка словаря имен
        char_names_dict = self.load_character_names(names_dict_path)
        if char_names_dict:
            self.name_translations = self.build_translation_map(char_names_dict)
            print(f"📚 Загружено {len(self.name_translations)} вариаций имен")
        else:
            print("⚠️ Работаю без словаря имен (могут быть проблемы с русским)")
        
        print(f"✅ Транскрипт: {len(transcript)} сегментов")
        print(f"✅ Персонажи: {', '.join([k for k in character_map.keys() if k != 'none'])}")
        
        # Загрузка эмбеддингов и фреймов
        print("\n📂 Загружаю эмбеддинги фреймов...")
        frame_embeddings = np.load(embeddings_path)
        
        # Нормализация
        if not np.allclose(np.linalg.norm(frame_embeddings[0]), 1.0):
            print("🔧 Нормализую эмбеддинги...")
            frame_embeddings = np.array([
                self.normalize_vector(emb) for emb in frame_embeddings
            ])
        
        # Список фреймов
        frames_path = Path(frames_dir)
        frame_files = sorted([
            f for f in frames_path.iterdir() 
            if f.suffix.lower() in {'.jpg', '.jpeg', '.png'}
        ])
        
        # Создание словаря scene_id -> index
        scene_id_to_idx = {}
        for idx, frame_path in enumerate(frame_files):
            scene_id = int(frame_path.stem.split('_')[1])
            scene_id_to_idx[scene_id] = idx
        
        all_scene_ids = list(scene_id_to_idx.keys())
        
        # Валидация character_map - убираем сцены которых нет в frames
        print("🔍 Валидация карты персонажей...")
        invalid_scenes = 0
        for char, scenes in character_map.items():
            valid_scenes = [s for s in scenes if s in scene_id_to_idx]
            invalid_count = len(scenes) - len(valid_scenes)
            if invalid_count > 0:
                invalid_scenes += invalid_count
                character_map[char] = valid_scenes
        
        if invalid_scenes > 0:
            print(f"⚠️ Удалено {invalid_scenes} несуществующих сцен из карты персонажей")
        
        print(f"✅ Загружено {len(frame_files)} фреймов\n")
        
        # Получение эмбеддингов текстов
        texts = [segment["text"] for segment in transcript]
        print("⚡ Генерирую эмбеддинги текстов...")
        text_embeddings = self.model.encode(
            texts,
            batch_size=32,
            convert_to_tensor=False,
            show_progress_bar=True,
            normalize_embeddings=True
        )
        
        # Умный матчинг
        print("\n🎯 Умный матчинг с контекстом персонажей...")
        results = []
        
        for idx, (text, text_emb) in enumerate(zip(texts, text_embeddings), 1):
            # Определяем пул для поиска
            search_pool, context = self.get_search_pool(
                text, 
                character_map, 
                all_scene_ids
            )
            
            # Фильтруем эмбеддинги по пулу
            pool_indices = [scene_id_to_idx[sid] for sid in search_pool if sid in scene_id_to_idx]
            
            if not pool_indices:
                # Fallback - используем все
                pool_indices = list(range(len(frame_embeddings)))
            
            pool_embeddings = frame_embeddings[pool_indices]
            
            # Поиск лучшего совпадения с ротацией и cooldown
            best_idx, best_score = self.find_best_match_with_rotation(
                text_emb,
                pool_embeddings,
                pool_indices,
                frame_files,
                idx - 1  # Текущий индекс чанка (0-based)
            )
            
            results.append({
                "audio_text": text,
                "frame_file": str(frame_files[best_idx]),
                "frame_index": best_idx,
                "similarity_score": best_score,
                "chunk_index": idx - 1,
                "search_context": context,
                "search_pool_size": len(pool_indices)
            })
            
            print(f"  [{idx}/{len(texts)}] '{text[:40]}...'")
            print(f"      → {frame_files[best_idx].name} "
                  f"(score: {best_score:.3f})")
            print(f"      → Контекст: {context} | Пул: {len(pool_indices)} сцен")
        
        # Сохранение результатов
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Результаты сохранены: {output_path}")
        
        # Статистика использования кадров
        print("\n📊 Топ-10 самых используемых кадров:")
        sorted_usage = sorted(
            self.frame_usage_count.items(), 
            key=lambda x: -x[1]
        )[:10]
        for frame_name, count in sorted_usage:
            print(f"   {frame_name}: {count} раз")
        
        print(f"\n📊 Статистика контекста:")
        context_stats = {}
        for result in results:
            ctx = result["search_context"]
            context_stats[ctx] = context_stats.get(ctx, 0) + 1
        
        for ctx, count in sorted(context_stats.items(), key=lambda x: -x[1]):
            print(f"   {ctx}: {count} чанков")
        
        print(f"\n✅ Готово! Сматчено {len(results)} чанков")
        return results


def main():
    """Основной запуск"""
    matcher = SmartMatcher()
    
    # Проверка наличия character_frames.json
    character_map_path = os.path.join(
        matcher.cfg["paths"]["cache_dir"],
        "character_frames.json"
    )
    
    names_dict_path = os.path.join(
        matcher.cfg["paths"]["cache_dir"],
        "character_names.json"
    )
    
    if not Path(character_map_path).exists():
        print("❌ Файл character_frames.json не найден!")
        print("   Сначала запусти: python src/character_detector.py")
        return
    
    if not Path(names_dict_path).exists():
        print("⚠️ Файл character_names.json не найден!")
        print("   Рекомендуется запустить: python src/character_detector.py")
        print("   Продолжаю без словаря имен...\n")
    
    # Умный матчинг
    results = matcher.match_audio_to_frames()
    
    print("\n✅ Теперь можно запустить renderer.py для создания финального видео!")


if __name__ == "__main__":
    main()
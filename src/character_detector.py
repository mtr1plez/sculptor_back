import os
import json
from pathlib import Path
from typing import List, Dict, Set
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image

from utils import load_config

# Загрузка API ключа
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY не найден в .env файле")

genai.configure(api_key=API_KEY)


class CharacterDetector:
    """Детектор персонажей в видео через Gemini Vision"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
    
    def load_transcript(self, transcript_path: str) -> List[Dict]:
        """Загрузка транскрипта"""
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extract_characters_from_transcript(self, transcript: List[Dict]) -> List[str]:
        """
        Извлечение списка персонажей из транскрипта через Gemini
        
        Args:
            transcript: Транскрипт видео
        
        Returns:
            Список имен персонажей
        """
        # Объединяем весь текст
        full_text = " ".join([segment["text"] for segment in transcript])
        
        prompt = f"""Проанализируй этот транскрипт видео-эссе и извлеки список ГЛАВНЫХ персонажей (5-10 максимум).

ПРАВИЛА:
1. Только персонажи, которые упоминаются НЕСКОЛЬКО раз
2. Только ИМЕНА персонажей (не описания)
3. Используй КОРОТКИЕ имена (Miguel, а не Miguel O'Hara)
4. Только персонажи, которых можно УВИДЕТЬ на экране (не абстрактные концепции)
5. Отвечай ТОЛЬКО списком через запятую, без пояснений

Транскрипт:
{full_text[:8000]}

Список персонажей:"""

        try:
            response = self.model.generate_content(prompt)
            characters_text = response.text.strip()
            
            # Парсим список персонажей
            characters = [
                char.strip() 
                for char in characters_text.split(',')
                if char.strip()
            ]
            
            return characters[:10]  # Максимум 10 персонажей
        except Exception as e:
            print(f"⚠️ Ошибка извлечения персонажей: {e}")
            return []
    
    def generate_character_dictionary(
        self, 
        characters: List[str], 
        transcript: List[Dict]
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Генерация словаря вариаций имен персонажей через Gemini
        
        Args:
            characters: Список персонажей
            transcript: Транскрипт для определения языка и контекста
        
        Returns:
            Словарь вариаций имен
        """
        # Объединяем текст для контекста
        full_text = " ".join([segment["text"] for segment in transcript])
        sample_text = full_text[:2000]  # Первые 2000 символов для определения языка
        
        characters_list = ", ".join(characters)
        
        prompt = f"""Создай словарь вариаций имен персонажей для поиска в видео.

ПЕРСОНАЖИ: {characters_list}

КОНТЕКСТ (начало транскрипта):
{sample_text}

ЗАДАЧА:
Для каждого персонажа создай список вариаций имени с учетом:
1. Язык транскрипта (русский/английский/оба)
2. Все склонения (для русского: Мигель, Мигеля, Мигелю, Мигелем, Мигеле)
3. Полные и короткие версии имени
4. Альтернативные имена (прозвища, титулы)

ФОРМАТ ОТВЕТА (СТРОГО JSON, без markdown):
{{
  "Miguel": {{
    "english": ["Miguel", "Miguel O'Hara"],
    "russian": ["Мигель", "Мигеля", "Мигелю", "Мигелем", "Мигеле"],
    "aliases": ["Spider-Man 2099"]
  }},
  "Gwen": {{
    "english": ["Gwen", "Gwen Stacy"],
    "russian": ["Гвен", "Гвен Стейси"],
    "aliases": ["Spider-Gwen", "Ghost-Spider"]
  }}
}}

Ответ (только JSON):"""

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Убираем markdown если есть
            result_text = result_text.replace('```json', '').replace('```', '').strip()
            
            # Парсим JSON
            char_dict = json.loads(result_text)
            
            return char_dict
        except Exception as e:
            print(f"⚠️ Ошибка генерации словаря: {e}")
            # Fallback - простой словарь
            return {char: {"english": [char], "russian": [], "aliases": []} for char in characters}
    
    def detect_character_in_frame(
        self, 
        frame_path: Path, 
        characters: List[str]
    ) -> List[str]:
        """
        Определение какие персонажи на кадре через Gemini Vision
        
        Args:
            frame_path: Путь к кадру
            characters: Список известных персонажей
        
        Returns:
            Список персонажей на этом кадре
        """
        try:
            # Загружаем изображение
            image = Image.open(frame_path)
            
            characters_list = ", ".join(characters)
            
            prompt = f"""Посмотри на этот кадр из видео и определи, какие персонажи на нём присутствуют.

ИЗВЕСТНЫЕ ПЕРСОНАЖИ: {characters_list}

ПРАВИЛА:
1. Отвечай ТОЛЬКО именами из списка выше
2. Если персонажа НЕТ на кадре - НЕ упоминай его
3. Если кадр без персонажей (пейзаж, объекты) - напиши "none"
4. Отвечай списком через запятую без пояснений

Персонажи на кадре:"""

            response = self.model.generate_content([prompt, image])
            result_text = response.text.strip().lower()
            
            # Парсинг результата
            if result_text == "none" or "none" in result_text:
                return []
            
            detected = []
            for char in characters:
                if char.lower() in result_text:
                    detected.append(char)
            
            return detected
        except Exception as e:
            print(f"⚠️ Ошибка детекции на {frame_path.name}: {e}")
            return []
    
    def detect_all_characters(
        self,
        transcript_path: str = None,
        frames_dir: str = None,
        output_path: str = None,
        sample_rate: int = 10  # Каждый N-й кадр
    ) -> Dict[str, List[int]]:
        """
        Основная функция детекции персонажей
        
        Args:
            transcript_path: Путь к транскрипту
            frames_dir: Путь к папке с кадрами
            output_path: Путь для сохранения результата
            sample_rate: Анализировать каждый N-й кадр
        
        Returns:
            Словарь {персонаж: [список номеров сцен]}
        """
        # Дефолтные пути
        if transcript_path is None:
            transcript_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "transcript.json"
            )
        if frames_dir is None:
            frames_dir = self.cfg["paths"]["frames_dir"]
        if output_path is None:
            output_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "character_frames.json"
            )
        
        print("📄 Загружаю транскрипт...")
        transcript = self.load_transcript(transcript_path)
        
        print("🧠 Извлекаю персонажей из транскрипта...")
        characters = self.extract_characters_from_transcript(transcript)
        
        if not characters:
            print("❌ Персонажи не найдены в транскрипте!")
            return {}
        
        print(f"✅ Найдено {len(characters)} персонажей: {', '.join(characters)}\n")
        
        # Получение списка кадров
        frames_path = Path(frames_dir)
        all_frames = sorted([
            f for f in frames_path.iterdir() 
            if f.suffix.lower() in {'.jpg', '.jpeg', '.png'}
        ])
        
        # Берем каждый N-й кадр ИЗ СПИСКА (не по номеру сцены!)
        sampled_frames = all_frames[::sample_rate]
        print(f"🖼️ Анализирую {len(sampled_frames)} кадров (каждый {sample_rate}-й из {len(all_frames)} файлов)...")
        print(f"   Диапазон сцен: {all_frames[0].stem} → {all_frames[-1].stem}\n")
        
        # Инициализация словаря для хранения результатов
        character_map = {char: [] for char in characters}
        character_map["none"] = []  # Кадры без персонажей
        
        # Анализ кадров
        for i, frame_path in enumerate(sampled_frames, 1):
            # Извлекаем номер сцены из имени файла (scene_123.jpg -> 123)
            scene_num = int(frame_path.stem.split('_')[1])
            
            detected = self.detect_character_in_frame(frame_path, characters)
            
            if detected:
                for char in detected:
                    character_map[char].append(scene_num)
                status = f"Найдено: {', '.join(detected)}"
            else:
                character_map["none"].append(scene_num)
                status = "Без персонажей"
            
            print(f"  [{i}/{len(sampled_frames)}] {frame_path.name}: {status}")
        
        # Удаляем персонажей без кадров
        character_map = {
            char: scenes 
            for char, scenes in character_map.items() 
            if scenes
        }
        
        # Сохранение результата
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(character_map, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Карта персонажей сохранена: {output_path}")
        
        # Статистика
        print("\n📊 Статистика:")
        for char, scenes in character_map.items():
            if char != "none":
                print(f"   {char}: {len(scenes)} кадров")
        print(f"   Без персонажей: {len(character_map.get('none', []))} кадров")
        
        return character_map


def main():
    """Основной запуск"""
    detector = CharacterDetector()
    
    # Детекция персонажей (анализируем каждый 10-й кадр)
    character_map = detector.detect_all_characters(
        sample_rate=10  # Каждый 10-й кадр (1700 -> 170 кадров)
    )
    
    print("\n✅ Готово! Теперь запусти smart_matcher.py для умного матчинга")


if __name__ == "__main__":
    main()
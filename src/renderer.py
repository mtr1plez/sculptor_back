import os
import json
from pathlib import Path
from typing import List, Dict
import numpy as np
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips
)

from utils import load_config


class SmartVideoRenderer:
    """Рендерер видео с умной подгонкой скорости и переходами"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
        
    def load_transcript(self, transcript_path: str) -> List[Dict]:
        """Загрузка транскрипта с таймингами"""
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def load_edit_plan(self, edit_plan_path: str) -> List[Dict]:
        """Загрузка плана монтажа"""
        with open(edit_plan_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extract_scene_number(self, frame_file: str) -> int:
        """Извлечение номера сцены из имени файла (scene_123.jpg -> 123)"""
        filename = Path(frame_file).stem  # scene_123
        return int(filename.split('_')[1])
    
    def load_scene_index(self, scene_index_path: str) -> List[Dict]:
        """Загрузка индекса сцен с таймингами"""
        with open(scene_index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extend_clip_duration(
        self, 
        source_video: VideoFileClip,
        scene_start: float, 
        scene_end: float,
        target_duration: float
    ) -> VideoFileClip:
        """
        Расширение клипа до нужной длительности (продолжает видео дальше)
        
        Args:
            source_video: Исходное видео
            scene_start: Начало сцены
            scene_end: Конец сцены
            target_duration: Нужная длительность
        
        Returns:
            Клип нужной длительности
        """
        original_duration = scene_end - scene_start
        
        if original_duration >= target_duration:
            # Если сцена длиннее - обрезаем
            return source_video.subclip(scene_start, scene_start + target_duration)
        else:
            # Если сцена короче - продолжаем видео дальше
            new_end = scene_start + target_duration
            
            # Проверка на выход за границы видео
            if new_end > source_video.duration:
                new_end = source_video.duration
            
            return source_video.subclip(scene_start, new_end)
    
    def fix_duplicate_scenes(self, edit_plan: List[Dict], scene_index: List[Dict]) -> List[Dict]:
        """
        Замена повторяющихся сцен подряд на следующую доступную сцену
        
        Args:
            edit_plan: План монтажа
            scene_index: Индекс всех сцен
        
        Returns:
            План без повторов подряд (той же длины!)
        """
        if len(edit_plan) <= 1:
            return edit_plan
        
        fixed_plan = []
        last_scene_id = None
        scenes_dict = {scene["id"]: scene for scene in scene_index}
        max_scene_id = max(scenes_dict.keys())
        
        for i, item in enumerate(edit_plan):
            scene_id = self.extract_scene_number(item["frame_file"])
            
            if scene_id == last_scene_id:
                # Находим следующую доступную сцену
                replacement_id = scene_id + 5  # Прыгаем минимум на 5 кадров вперед
                
                # Ищем следующую существующую сцену
                while replacement_id not in scenes_dict and replacement_id <= max_scene_id:
                    replacement_id += 1
                
                # Если дошли до конца - берем предыдущую (но не соседнюю)
                if replacement_id not in scenes_dict:
                    replacement_id = scene_id - 5
                    while replacement_id not in scenes_dict and replacement_id >= 0:
                        replacement_id -= 1
                
                # Если все еще не нашли - оставляем оригинал (крайний случай)
                if replacement_id not in scenes_dict:
                    replacement_id = scene_id
                
                # Создаем новый item с заменой сцены
                new_item = item.copy()
                replacement_scene = scenes_dict[replacement_id]
                new_item["frame_file"] = new_item["frame_file"].replace(
                    f"scene_{scene_id}.jpg", 
                    f"scene_{replacement_id}.jpg"
                )
                new_item["frame_index"] = replacement_id
                new_item["original_scene_id"] = scene_id  # Сохраняем оригинал для отладки
                
                fixed_plan.append(new_item)
                last_scene_id = replacement_id
                
                print(f"🔄 Позиция {i}: сцена {scene_id} → {replacement_id} (избегаем повтора)")
            else:
                last_scene_id = scene_id
                fixed_plan.append(item)
        
        print(f"✅ Все {len(fixed_plan)} аудио-чанков будут использованы")
        return fixed_plan
    
    def get_safe_output_path(self, output_path: str) -> str:
        """
        Генерация безопасного пути для сохранения (с автоинкрементом)
        
        Args:
            output_path: Желаемый путь файла
        
        Returns:
            Безопасный путь (с номером если нужно)
        """
        output_file = Path(output_path)
        
        # Если файл не существует - возвращаем как есть
        if not output_file.exists():
            return output_path
        
        # Файл существует - ищем свободное имя
        base_name = output_file.stem  # final_result
        extension = output_file.suffix  # .mp4
        directory = output_file.parent
        
        counter = 1
        while True:
            new_name = f"{base_name}{counter}{extension}"
            new_path = directory / new_name
            
            if not new_path.exists():
                print(f"⚠️ Файл {output_file.name} уже существует")
                print(f"   Сохраняю как: {new_name}")
                return str(new_path)
            
            counter += 1
            
            # Защита от бесконечного цикла (маловероятно, но на всякий случай)
            if counter > 1000:
                raise RuntimeError("Слишком много версий файла! Очисти папку output")
    
    def export_timeline(
        self,
        transcript_path: str = None,
        edit_plan_path: str = None,
        scene_index_path: str = None,
        output_path: str = None
    ) -> Dict:
        """
        Экспорт timeline.json для UI редактора
        
        Args:
            transcript_path: Путь к транскрипту
            edit_plan_path: Путь к плану монтажа
            scene_index_path: Путь к индексу сцен
            output_path: Путь для сохранения timeline.json
        
        Returns:
            Timeline структура
        """
        # Дефолтные пути
        if transcript_path is None:
            transcript_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "transcript.json"
            )
        if edit_plan_path is None:
            edit_plan_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "edit_plan.json"
            )
        if scene_index_path is None:
            scene_index_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "scene_index.json"
            )
        if output_path is None:
            output_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "timeline.json"
            )
        
        print("📄 Загружаю данные для timeline...")
        transcript = self.load_transcript(transcript_path)
        edit_plan = self.load_edit_plan(edit_plan_path)
        scene_index = self.load_scene_index(scene_index_path)
        
        # Фильтрация дубликатов
        edit_plan = self.fix_duplicate_scenes(edit_plan, scene_index)
        
        if len(edit_plan) != len(transcript):
            min_len = min(len(transcript), len(edit_plan))
            transcript = transcript[:min_len]
            edit_plan = edit_plan[:min_len]
        
        print(f"✅ Транскрипт: {len(transcript)} сегментов")
        print(f"✅ План монтажа: {len(edit_plan)} сопоставлений\n")
        
        # Загрузка оригинального видео для определения границ
        video_path = self.cfg["paths"]["input_video"]
        source_video = VideoFileClip(video_path)
        video_duration = source_video.duration
        source_video.close()
        
        # Создание словаря сцен
        scenes_dict = {scene["id"]: scene for scene in scene_index}
        
        # Создание клипов для timeline
        print("🎬 Создаю timeline структуру...")
        video_clips = []
        audio_clips = []
        
        current_timeline_pos = 0.0
        
        for i, (trans_segment, edit_segment) in enumerate(zip(transcript, edit_plan)):
            audio_start = trans_segment["start"]
            audio_end = trans_segment["end"]
            audio_duration = audio_end - audio_start
            
            # Получаем matched сцену
            scene_id = self.extract_scene_number(edit_segment["frame_file"])
            
            if scene_id not in scenes_dict:
                continue
            
            scene = scenes_dict[scene_id]
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]
            scene_duration = scene_end - scene_start
            
            # Вычисляем границы расширения
            max_extend_left = scene_start  # до начала видео
            max_extend_right = min(video_duration - scene_end, 30.0)  # макс 30s вправо
            
            # Video clip
            video_clips.append({
                "id": f"v{i}",
                "text": trans_segment["text"],
                "source_in": scene_start,
                "source_out": scene_start + audio_duration,
                "timeline_start": current_timeline_pos,
                "duration": audio_duration,
                "max_extend_left": max_extend_left,
                "max_extend_right": max_extend_right,
                "scene_id": scene_id,
                "similarity_score": edit_segment.get("similarity_score", 0),
                "color": self._get_clip_color(i)
            })
            
            # Audio clip
            audio_clips.append({
                "id": f"a{i}",
                "text": trans_segment["text"],
                "source_in": audio_start,
                "source_out": audio_end,
                "timeline_start": current_timeline_pos,
                "duration": audio_duration,
                "color": "#10b981",
                "waveform": True
            })
            
            current_timeline_pos += audio_duration
        
        # Формируем timeline структуру
        timeline = {
            "project": self.cfg.get("current_project", "Unknown"),
            "source_video": video_path,
            "source_audio": self.cfg["paths"]["input_audio"],
            "total_duration": current_timeline_pos,
            "fps": 24,
            "tracks": [
                {
                    "id": "video-1",
                    "type": "video",
                    "name": "Video Track 1",
                    "clips": video_clips
                },
                {
                    "id": "audio-1",
                    "type": "audio",
                    "name": "Voice Track",
                    "clips": audio_clips
                }
            ]
        }
        
        # Сохранение
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Timeline экспортирован: {output_path}")
        print(f"   Всего клипов: {len(video_clips)}")
        print(f"   Длительность: {current_timeline_pos:.2f}s")
        
        return timeline
    
    def _get_clip_color(self, index: int) -> str:
        """Получение цвета для клипа"""
        colors = [
            "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", 
            "#10b981", "#ef4444", "#06b6d4", "#8b5cf6"
        ]
        return colors[index % len(colors)]
    
    def render_video(
        self,
        transcript_path: str = None,
        edit_plan_path: str = None,
        scene_index_path: str = None,
        output_path: str = None,
        filter_duplicates: bool = True
    ):
        """
        Основная функция рендеринга видео
        
        Args:
            transcript_path: Путь к транскрипту
            edit_plan_path: Путь к плану монтажа
            scene_index_path: Путь к индексу сцен
            output_path: Путь для сохранения результата
            filter_duplicates: Фильтровать повторяющиеся сцены подряд
        """
        # Дефолтные пути из конфига
        if transcript_path is None:
            transcript_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "transcript.json"
            )
        if edit_plan_path is None:
            edit_plan_path = os.path.join(
                self.cfg["paths"]["cache_dir"], 
                "edit_plan.json"
            )
        if scene_index_path is None:
            scene_index_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "scene_index.json"
            )
        if output_path is None:
            output_path = self.cfg["paths"]["output_video"]
        
        print("📄 Загружаю данные...")
        transcript = self.load_transcript(transcript_path)
        edit_plan = self.load_edit_plan(edit_plan_path)
        scene_index = self.load_scene_index(scene_index_path)
        
        print(f"✅ Транскрипт: {len(transcript)} сегментов")
        print(f"✅ План монтажа: {len(edit_plan)} сопоставлений")
        print(f"✅ Индекс сцен: {len(scene_index)} сцен\n")
        
        # Исправление дубликатов (замена на следующую сцену вместо удаления)
        if filter_duplicates:
            edit_plan = self.fix_duplicate_scenes(edit_plan, scene_index)
            print()
        
        # Проверка длины
        if len(edit_plan) != len(transcript):
            raise ValueError(
                f"Критическая ошибка: edit_plan ({len(edit_plan)}) != "
                f"transcript ({len(transcript)}). Проверь matcher.py!"
            )
        
        # Загрузка оригинального видео
        video_path = self.cfg["paths"]["input_video"]
        print(f"🎬 Загружаю видео: {video_path}")
        source_video = VideoFileClip(video_path)
        
        # Создание словаря сцен для быстрого доступа
        scenes_dict = {scene["id"]: scene for scene in scene_index}
        
        # Создание клипов для каждого сегмента
        print("\n🎞️ Создаю клипы...")
        clips = []
        last_scene_info = None  # Для продолжения короткой сцены
        
        for i, (trans_segment, edit_segment) in enumerate(zip(transcript, edit_plan), 1):
            # Получаем тайминги из транскрипта
            audio_start = trans_segment["start"]
            audio_end = trans_segment["end"]
            audio_duration = audio_end - audio_start
            
            # Если аудио-чанк очень короткий (< 1 секунды) - продолжаем предыдущую сцену
            if audio_duration < 1.0 and last_scene_info is not None:
                print(f"  [{i}/{len(transcript)}] Короткий чанк ({audio_duration:.2f}s) "
                      f"→ продолжаю сцену {last_scene_info['scene_id']}")
                
                # Продолжаем предыдущую сцену
                extended_clip = self.extend_clip_duration(
                    source_video,
                    last_scene_info['scene_start'],
                    last_scene_info['scene_end'],
                    audio_duration
                )
                clips.append(extended_clip)
                continue
            
            # Получаем matched сцену
            scene_id = self.extract_scene_number(edit_segment["frame_file"])
            
            if scene_id not in scenes_dict:
                print(f"⚠️ Сцена {scene_id} не найдена в индексе, пропускаю")
                continue
            
            scene = scenes_dict[scene_id]
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]
            
            # Продолжаем сцену дальше (без циклирования)
            adjusted_clip = self.extend_clip_duration(
                source_video, 
                scene_start, 
                scene_end, 
                audio_duration
            )
            
            clips.append(adjusted_clip)
            
            # Запоминаем для следующего короткого чанка
            last_scene_info = {
                'scene_id': scene_id,
                'scene_start': scene_start,
                'scene_end': scene_end
            }
            
            print(f"  [{i}/{len(transcript)}] Сцена {scene_id}: "
                  f"{scene_end - scene_start:.2f}s → {audio_duration:.2f}s "
                  f"(расширена до {adjusted_clip.duration:.2f}s, "
                  f"score: {edit_segment['similarity_score']:.3f})")
        
        if not clips:
            raise ValueError("Не удалось создать ни одного клипа!")
        
        print(f"\n✅ Создано {len(clips)} клипов")
        
        # Склеивание клипов (без переходов, метод "chain" для чистой склейки)
        print("\n🔗 Склеиваю клипы...")
        final_video = concatenate_videoclips(clips, method="chain")
        
        # Добавление аудио
        audio_path = self.cfg["paths"]["input_audio"]
        print(f"\n🎵 Добавляю аудио: {audio_path}")
        voice_audio = AudioFileClip(audio_path)
        
        # Подгонка аудио под длину видео (если нужно)
        if voice_audio.duration > final_video.duration:
            voice_audio = voice_audio.subclip(0, final_video.duration)
        
        final_video = final_video.set_audio(voice_audio)
        
        # Безопасный путь для сохранения (с проверкой существования)
        safe_output_path = self.get_safe_output_path(output_path)
        
        # Рендеринг
        print(f"\n🎬 Рендерю финальное видео: {safe_output_path}")
        output_file = Path(safe_output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        final_video.write_videofile(
            str(safe_output_path),
            codec='libx264',
            audio_codec='aac',
            fps=source_video.fps,
            preset='medium',  # medium = баланс скорость/качество
            threads=4,
            logger='bar'
        )
        
        # Очистка
        source_video.close()
        voice_audio.close()
        final_video.close()
        for clip in clips:
            clip.close()
        
        print(f"\n✅ Видео готово: {safe_output_path}")
        print(f"   Длительность: {final_video.duration:.2f}s")


def main():
    """Основной запуск"""
    renderer = SmartVideoRenderer()
    
    renderer.render_video(
        filter_duplicates=True   # Убрать ВСЕ повторяющиеся сцены подряд
    )


if __name__ == "__main__":
    main()
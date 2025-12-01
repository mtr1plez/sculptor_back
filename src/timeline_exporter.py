import os
import json
from pathlib import Path
from typing import List, Dict
from moviepy.editor import VideoFileClip

from utils import load_config


class TimelineExporter:
    """Экспорт timeline.json для UI редактора"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
    
    def load_transcript(self, transcript_path: str) -> List[Dict]:
        """Загрузка транскрипта"""
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def load_edit_plan(self, edit_plan_path: str) -> List[Dict]:
        """Загрузка плана монтажа"""
        with open(edit_plan_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def load_scene_index(self, scene_index_path: str) -> List[Dict]:
        """Загрузка индекса сцен"""
        with open(scene_index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extract_scene_number(self, frame_file: str) -> int:
        """Извлечение номера сцены из пути к файлу"""
        filename = Path(frame_file).stem
        return int(filename.split('_')[1])
    
    def get_clip_color(self, index: int) -> str:
        """Генерация цвета для клипа"""
        colors = [
            "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", 
            "#10b981", "#ef4444", "#06b6d4", "#14b8a6"
        ]
        return colors[index % len(colors)]
    
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
        
        print("📄 Загружаю данные...")
        
        # Проверка существования файлов
        for path, name in [
            (transcript_path, "transcript.json"),
            (edit_plan_path, "edit_plan.json"),
            (scene_index_path, "scene_index.json")
        ]:
            if not Path(path).exists():
                raise FileNotFoundError(f"{name} не найден: {path}")
        
        transcript = self.load_transcript(transcript_path)
        edit_plan = self.load_edit_plan(edit_plan_path)
        scene_index = self.load_scene_index(scene_index_path)
        
        print(f"✅ Транскрипт: {len(transcript)} сегментов")
        print(f"✅ План монтажа: {len(edit_plan)} сопоставлений")
        print(f"✅ Индекс сцен: {len(scene_index)} сцен\n")
        
        # Проверка длины
        if len(edit_plan) != len(transcript):
            print(f"⚠️ Несоответствие: {len(transcript)} транскрипт vs {len(edit_plan)} edit_plan")
            min_len = min(len(transcript), len(edit_plan))
            transcript = transcript[:min_len]
            edit_plan = edit_plan[:min_len]
            print(f"   Обрезано до {min_len} элементов\n")
        
        # Загрузка видео для определения границ
        video_path = self.cfg["paths"]["input_video"]
        print(f"🎬 Загружаю видео: {Path(video_path).name}")
        
        try:
            source_video = VideoFileClip(video_path)
            video_duration = source_video.duration
            source_video.close()
            print(f"   Длительность: {video_duration:.2f}s\n")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки видео: {e}")
            video_duration = 10000  # Fallback
        
        # Создание словаря сцен
        scenes_dict = {scene["id"]: scene for scene in scene_index}
        
        # Создание клипов
        print("🎞️ Создаю клипы для timeline...")
        
        video_clips = []
        audio_clips = []
        current_timeline_pos = 0.0
        
        skipped = 0
        
        for i, (trans_segment, edit_segment) in enumerate(zip(transcript, edit_plan)):
            audio_start = trans_segment["start"]
            audio_end = trans_segment["end"]
            audio_duration = audio_end - audio_start
            
            # Пропускаем слишком короткие (< 0.1s)
            if audio_duration < 0.1:
                skipped += 1
                continue
            
            # Получаем matched сцену
            scene_id = self.extract_scene_number(edit_segment["frame_file"])
            
            if scene_id not in scenes_dict:
                print(f"  ⚠️ Сцена {scene_id} не найдена в индексе")
                skipped += 1
                continue
            
            scene = scenes_dict[scene_id]
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]
            
            # Вычисляем границы расширения
            max_extend_left = min(scene_start, 10.0)  # макс 10s влево
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
                "color": self.get_clip_color(i)
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
        
        print(f"✅ Создано {len(video_clips)} клипов")
        if skipped > 0:
            print(f"   Пропущено {skipped} (слишком короткие или ошибки)\n")
        
        # Формируем timeline
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
        
        print(f"💾 Timeline сохранен: {output_path}")
        print(f"\n📊 Статистика:")
        print(f"   Всего клипов: {len(video_clips)}")
        print(f"   Длительность: {current_timeline_pos:.2f}s")
        print(f"   Проект: {timeline['project']}")
        
        return timeline


def main():
    """Основной запуск"""
    try:
        exporter = TimelineExporter()
        
        print("🎬 SculptorPro Timeline Exporter\n")
        
        timeline = exporter.export_timeline()
        
        print("\n✅ Готово! Теперь:")
        print("   1. Запусти API: python api/server.py")
        print("   2. Запусти UI: cd ui && npm run dev")
        print("   3. Открой http://localhost:5173")
        
    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
        print("\n💡 Убедись что запущены:")
        print("   1. python src/video_indexer.py")
        print("   2. python src/audio_transcriber.py")
        print("   3. python src/smart_matcher.py")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
import os
import json
from pathlib import Path
from typing import Dict, List

from utils import load_config


class SceneIndexFixer:
    """Фиксер таймингов сцен в scene_index.json"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
    
    def fix_scene_timings(
        self,
        scene_index_path: str = None,
        offset: float = 0.2,
        output_path: str = None,
        backup: bool = True
    ) -> Dict:
        """
        Сдвиг start_time всех сцен на заданное смещение
        
        Args:
            scene_index_path: Путь к scene_index.json
            offset: Смещение в секундах (положительное = вперед)
            output_path: Путь для сохранения (если None - перезаписывает)
            backup: Создать бэкап перед изменением
        
        Returns:
            Статистика изменений
        """
        # Дефолтные пути
        if scene_index_path is None:
            scene_index_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "scene_index.json"
            )
        
        if output_path is None:
            output_path = scene_index_path
        
        scene_index_file = Path(scene_index_path)
        
        if not scene_index_file.exists():
            raise FileNotFoundError(f"scene_index.json не найден: {scene_index_path}")
        
        # Бэкап
        if backup and output_path == scene_index_path:
            backup_path = scene_index_file.parent / "scene_index_backup.json"
            
            print(f"💾 Создаю бэкап: {backup_path.name}")
            
            with open(scene_index_file, 'r', encoding='utf-8') as f:
                backup_data = f.read()
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_data)
        
        # Загрузка
        print(f"📄 Загружаю scene_index.json...")
        with open(scene_index_file, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
        
        print(f"✅ Загружено {len(scenes)} сцен\n")
        
        # Анализ проблемных сцен
        print(f"🔍 Анализирую тайминги (сдвиг: +{offset}s)...\n")
        
        issues = []
        fixed_scenes = []
        
        for scene in scenes:
            old_start = scene["start_time"]
            old_end = scene["end_time"]
            old_duration = scene["duration"]
            
            # Применяем сдвиг к start_time
            new_start = old_start + offset
            new_duration = old_end - new_start
            
            # Проверка валидности
            if new_duration <= 0:
                issues.append({
                    'id': scene['id'],
                    'old_start': old_start,
                    'old_end': old_end,
                    'new_start': new_start,
                    'problem': 'negative_duration'
                })
                # Пропускаем проблемную сцену
                continue
            
            # Если сдвиг выводит start за пределы end
            if new_start >= old_end:
                issues.append({
                    'id': scene['id'],
                    'old_start': old_start,
                    'old_end': old_end,
                    'new_start': new_start,
                    'problem': 'start_after_end'
                })
                continue
            
            # Создаем исправленную сцену
            fixed_scene = scene.copy()
            fixed_scene["start_time"] = new_start
            fixed_scene["duration"] = new_duration
            
            fixed_scenes.append(fixed_scene)
        
        # Статистика
        print(f"📊 Результаты:")
        print(f"   Исправлено сцен: {len(fixed_scenes)}")
        print(f"   Проблемных сцен: {len(issues)}")
        
        if issues:
            print(f"\n⚠️ Проблемные сцены (не исправлены):")
            for issue in issues[:10]:
                print(f"   Scene {issue['id']}: {issue['old_start']:.2f}s → "
                      f"{issue['new_start']:.2f}s (end: {issue['old_end']:.2f}s) "
                      f"[{issue['problem']}]")
            if len(issues) > 10:
                print(f"   ... и еще {len(issues) - 10}")
        
        # Примеры исправлений
        if fixed_scenes:
            print(f"\n✅ Примеры исправлений:")
            for scene in fixed_scenes[:5]:
                old_scene = next(s for s in scenes if s['id'] == scene['id'])
                print(f"   Scene {scene['id']}: "
                      f"{old_scene['start_time']:.2f}s → {scene['start_time']:.2f}s "
                      f"(duration: {old_scene['duration']:.2f}s → {scene['duration']:.2f}s)")
        
        # Сохранение
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(fixed_scenes, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Сохранено: {output_path}")
        
        return {
            'total': len(scenes),
            'fixed': len(fixed_scenes),
            'issues': len(issues),
            'offset': offset,
            'output_path': output_path
        }
    
    def analyze_scene_timings(self, scene_index_path: str = None):
        """
        Анализ таймингов для определения оптимального offset
        
        Args:
            scene_index_path: Путь к scene_index.json
        """
        if scene_index_path is None:
            scene_index_path = os.path.join(
                self.cfg["paths"]["cache_dir"],
                "scene_index.json"
            )
        
        with open(scene_index_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
        
        print(f"📊 Анализ таймингов ({len(scenes)} сцен):\n")
        
        # Статистика длительностей
        durations = [s['duration'] for s in scenes]
        
        print(f"Длительность сцен:")
        print(f"   Минимум: {min(durations):.2f}s")
        print(f"   Максимум: {max(durations):.2f}s")
        print(f"   Средняя: {sum(durations)/len(durations):.2f}s")
        
        # Показываем первые 10 сцен для проверки
        print(f"\n📋 Первые 10 сцен:")
        for scene in scenes[:10]:
            print(f"   Scene {scene['id']}: {scene['duration']:.2f}s "
                  f"({scene['start_time']:.2f}s - {scene['end_time']:.2f}s)")
        
        # Подозрительно короткие сцены (для справки)
        short_scenes = [s for s in scenes if s['duration'] < 0.5]
        
        if short_scenes:
            print(f"\n⚠️ Очень короткие сцены (< 0.5s): {len(short_scenes)} шт.")
        
        # Рекомендация
        print(f"\n💡 Рекомендации:")
        if short_scenes:
            print(f"   Найдено {len(short_scenes)} очень коротких сцен")
            print(f"   Возможно детектор смен сцен срабатывает рано")
            print(f"   Рекомендуемый offset: +0.2s")
        else:
            print(f"   Тайминги выглядят нормально")


def main():
    """Основной запуск"""
    fixer = SceneIndexFixer()
    
    print("🎬 SculptorPro - Scene Index Timing Fixer\n")
    
    scene_index_path = os.path.join(
        fixer.cfg["paths"]["cache_dir"],
        "scene_index.json"
    )
    
    if not Path(scene_index_path).exists():
        print(f"❌ scene_index.json не найден: {scene_index_path}")
        print("   Сначала запусти video_indexer.py")
        return
    
    # Анализ
    print("1️⃣ Анализ текущих таймингов\n")
    fixer.analyze_scene_timings(scene_index_path)
    
    # Предложение исправить
    print("\n" + "="*60)
    print("\n2️⃣ Исправление таймингов\n")
    
    try:
        offset_input = input("Введи смещение в секундах (default: 0.2): ").strip()
        offset = float(offset_input) if offset_input else 0.2
        
        confirm = input(f"\nСдвинуть start_time всех сцен на +{offset}s? (y/n): ").strip().lower()
        
        if confirm == 'y':
            print()
            stats = fixer.fix_scene_timings(offset=offset)
            
            print(f"\n✅ Готово! Теперь перезапусти pipeline:")
            print(f"   1. python src/character_detector.py")
            print(f"   2. python src/smart_matcher.py")
            print(f"   3. python src/renderer.py")
        else:
            print("\n👋 Отменено")
    
    except KeyboardInterrupt:
        print("\n\n👋 Выход")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
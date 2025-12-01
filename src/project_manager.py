import os
import json
from pathlib import Path
from typing import Optional, List


class ProjectManager:
    """Менеджер проектов для SculptorPro"""
    
    def __init__(self, projects_root: str = "data/projects"):
        self.projects_root = Path(projects_root)
        self.config_file = Path("config.yaml")
        self.old_data_dir = Path("data")
    
    def migrate_old_structure(self, project_name: str = "migrated_project") -> bool:
        """
        Миграция старой структуры data/ в новую систему проектов
        
        Args:
            project_name: Имя для мигрированного проекта
        
        Returns:
            True если миграция выполнена
        """
        # Проверяем старую структуру
        old_input = self.old_data_dir / "input"
        old_cache = self.old_data_dir / "cache"
        old_output = self.old_data_dir / "output"
        
        has_old_data = (
            old_input.exists() or 
            old_cache.exists() or 
            old_output.exists()
        )
        
        if not has_old_data:
            return False
        
        print("\n🔄 Обнаружена старая структура data/")
        print("   Мигрирую в новую систему проектов...\n")
        
        # Создаем новый проект
        project_path = self.create_project(project_name)
        
        # Перемещаем файлы
        import shutil
        
        moved_files = []
        
        # Input файлы
        if old_input.exists():
            for file in old_input.iterdir():
                if file.is_file():
                    dest = project_path / "input" / file.name
                    shutil.move(str(file), str(dest))
                    moved_files.append(f"input/{file.name}")
        
        # Cache
        if old_cache.exists():
            for item in old_cache.iterdir():
                dest = project_path / "cache" / item.name
                if item.is_dir():
                    shutil.move(str(item), str(dest))
                    moved_files.append(f"cache/{item.name}/")
                else:
                    shutil.move(str(item), str(dest))
                    moved_files.append(f"cache/{item.name}")
        
        # Output
        if old_output.exists():
            for file in old_output.iterdir():
                if file.is_file():
                    dest = project_path / "output" / file.name
                    shutil.move(str(file), str(dest))
                    moved_files.append(f"output/{file.name}")
        
        # Удаляем пустые старые папки
        for folder in [old_input, old_cache, old_output]:
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        
        print("✅ Миграция завершена!")
        print(f"   Перемещено файлов: {len(moved_files)}")
        if moved_files:
            print("\n   Структура:")
            for f in moved_files[:10]:  # Показываем первые 10
                print(f"      ✓ {f}")
            if len(moved_files) > 10:
                print(f"      ... и еще {len(moved_files) - 10} файлов")
        
        print(f"\n   Новое расположение: data/projects/{project_name}/")
        
        return True
        
    def list_projects(self) -> List[str]:
        """Получение списка существующих проектов"""
        if not self.projects_root.exists():
            return []
        
        projects = [
            d.name for d in self.projects_root.iterdir() 
            if d.is_dir()
        ]
        return sorted(projects)
    
    def create_project(self, project_name: str) -> Path:
        """
        Создание новой структуры проекта
        
        Args:
            project_name: Имя проекта
        
        Returns:
            Путь к проекту
        """
        project_path = self.projects_root / project_name
        
        if project_path.exists():
            print(f"⚠️ Проект '{project_name}' уже существует")
            return project_path
        
        # Создание структуры папок
        (project_path / "input").mkdir(parents=True, exist_ok=True)
        (project_path / "cache" / "frames").mkdir(parents=True, exist_ok=True)
        (project_path / "output").mkdir(parents=True, exist_ok=True)
        
        print(f"✅ Создан проект: {project_name}")
        print(f"   📁 {project_path}/")
        print(f"      ├── input/     (положи сюда movie.mp4 и voice.mp3)")
        print(f"      ├── cache/     (здесь будут frames, embeddings, etc.)")
        print(f"      └── output/    (готовые видео)")
        
        return project_path
    
    def select_project(self, project_name: Optional[str] = None) -> str:
        """
        Выбор активного проекта (интерактивно или по имени)
        
        Args:
            project_name: Имя проекта (если None - интерактивный выбор)
        
        Returns:
            Имя выбранного проекта
        """
        projects = self.list_projects()
        
        # Если проектов нет - создаем первый
        if not projects:
            print("📂 Проектов не найдено. Создадим первый!\n")
            project_name = input("Введите имя проекта (например, 'spiderverse_analysis'): ").strip()
            if not project_name:
                project_name = "default_project"
            self.create_project(project_name)
            return project_name
        
        # Если имя указано - используем его
        if project_name:
            if project_name in projects:
                return project_name
            else:
                print(f"⚠️ Проект '{project_name}' не найден")
                # Fallback на интерактивный выбор
        
        # Интерактивный выбор
        print("\n📂 Доступные проекты:")
        for i, proj in enumerate(projects, 1):
            print(f"   {i}. {proj}")
        print(f"   {len(projects) + 1}. Создать новый проект")
        
        while True:
            try:
                choice = input(f"\nВыбери проект (1-{len(projects) + 1}): ").strip()
                choice_num = int(choice)
                
                if 1 <= choice_num <= len(projects):
                    selected = projects[choice_num - 1]
                    print(f"✅ Выбран проект: {selected}\n")
                    return selected
                elif choice_num == len(projects) + 1:
                    new_name = input("Введите имя нового проекта: ").strip()
                    if not new_name:
                        print("❌ Имя не может быть пустым")
                        continue
                    self.create_project(new_name)
                    return new_name
                else:
                    print(f"❌ Введи число от 1 до {len(projects) + 1}")
            except ValueError:
                print("❌ Введи число!")
            except KeyboardInterrupt:
                print("\n\n👋 Выход")
                exit(0)
    
    def update_config(self, project_name: str):
        """
        Обновление config.yaml с путями проекта
        
        Args:
            project_name: Имя проекта
        """
        import yaml
        
        project_path = self.projects_root / project_name
        
        # Читаем существующий конфиг или создаем новый
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Обновляем пути
        config['current_project'] = project_name
        config['paths'] = {
            'project_root': str(project_path),
            'input_video': str(project_path / "input" / "movie.mp4"),
            'input_audio': str(project_path / "input" / "voice.mp3"),
            'output_video': str(project_path / "output" / "final_result.mp4"),
            'cache_dir': str(project_path / "cache"),
            'frames_dir': str(project_path / "cache" / "frames"),
        }
        
        # Сохраняем
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        print(f"💾 Конфиг обновлен для проекта: {project_name}")
    
    def get_project_info(self, project_name: str) -> dict:
        """
        Получение информации о проекте
        
        Args:
            project_name: Имя проекта
        
        Returns:
            Словарь с информацией о проекте
        """
        project_path = self.projects_root / project_name
        
        if not project_path.exists():
            return {'exists': False}
        
        cache_path = project_path / "cache"
        
        info = {
            'exists': True,
            'name': project_name,
            'path': str(project_path),
            'has_video': (project_path / "input" / "movie.mp4").exists(),
            'has_audio': (project_path / "input" / "voice.mp3").exists(),
            'has_frames': (cache_path / "frames").exists() and 
                         len(list((cache_path / "frames").glob("*.jpg"))) > 0,
            'has_transcript': (cache_path / "transcript.json").exists(),
            'has_embeddings': (cache_path / "embeddings.npy").exists(),
            'has_characters': (cache_path / "character_frames.json").exists(),
            'has_edit_plan': (cache_path / "edit_plan.json").exists(),
        }
        
        return info
    
    def show_project_status(self, project_name: str):
        """
        Вывод статуса проекта
        
        Args:
            project_name: Имя проекта
        """
        info = self.get_project_info(project_name)
        
        if not info['exists']:
            print(f"❌ Проект '{project_name}' не существует")
            return
        
        print(f"\n📊 Статус проекта: {project_name}")
        print(f"   📁 Путь: {info['path']}\n")
        
        print("   Входные файлы:")
        print(f"      {'✅' if info['has_video'] else '❌'} movie.mp4")
        print(f"      {'✅' if info['has_audio'] else '❌'} voice.mp3")
        
        print("\n   Обработка:")
        print(f"      {'✅' if info['has_frames'] else '❌'} Кадры извлечены")
        print(f"      {'✅' if info['has_transcript'] else '❌'} Транскрипт создан")
        print(f"      {'✅' if info['has_embeddings'] else '❌'} Эмбеддинги созданы")
        print(f"      {'✅' if info['has_characters'] else '❌'} Персонажи детектированы")
        print(f"      {'✅' if info['has_edit_plan'] else '❌'} План монтажа готов")
        
        # Рекомендации
        print("\n   📝 Следующие шаги:")
        if not info['has_video'] or not info['has_audio']:
            print("      1. Положи movie.mp4 и voice.mp3 в папку input/")
        elif not info['has_frames']:
            print("      1. Запусти: python src/video_indexer.py")
        elif not info['has_transcript']:
            print("      1. Запусти: python src/audio_transcriber.py")
        elif not info['has_characters']:
            print("      1. Запусти: python src/character_detector.py")
        elif not info['has_edit_plan']:
            print("      1. Запусти: python src/smart_matcher.py")
        else:
            print("      1. Запусти: python src/renderer.py")
            print("      ✨ Все готово для рендеринга!")


def main():
    """Основной запуск - выбор проекта"""
    pm = ProjectManager()
    
    print("🎬 SculptorPro - Project Manager\n")
    
    # Проверяем и мигрируем старую структуру
    if pm.migrate_old_structure("spiderverse_migrated"):
        print("\n💡 Старые данные мигрированы в проект 'spiderverse_migrated'")
        print("   Можешь переименовать проект или создать новый\n")
    
    # Выбор проекта
    project_name = pm.select_project()
    
    # Обновление конфига
    pm.update_config(project_name)
    
    # Показываем статус
    pm.show_project_status(project_name)
    
    print("\n✅ Проект активирован! Теперь можно запускать модули.")


if __name__ == "__main__":
    main()
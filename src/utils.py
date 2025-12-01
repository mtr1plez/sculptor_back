import yaml
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    """
    Загрузка конфигурации с поддержкой проектов
    
    Args:
        config_path: Путь к файлу конфигурации
    
    Returns:
        Словарь конфигурации
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        print("⚠️ config.yaml не найден!")
        print("   Запусти сначала: python src/project_manager.py")
        raise FileNotFoundError(f"Конфиг не найден: {config_path}")
    
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Проверка наличия current_project
    if 'current_project' not in config:
        print("⚠️ Активный проект не выбран!")
        print("   Запусти: python src/project_manager.py")
        raise ValueError("Активный проект не задан в config.yaml")
    
    return config


def get_project_name(config_path: str = "config.yaml") -> str:
    """
    Получение имени текущего проекта
    
    Args:
        config_path: Путь к конфигу
    
    Returns:
        Имя активного проекта
    """
    config = load_config(config_path)
    return config['current_project']


def get_project_paths(config_path: str = "config.yaml") -> dict:
    """
    Получение всех путей текущего проекта
    
    Args:
        config_path: Путь к конфигу
    
    Returns:
        Словарь с путями проекта
    """
    config = load_config(config_path)
    return config['paths']
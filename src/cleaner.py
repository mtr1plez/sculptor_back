import os
import shutil
import yaml

def load_config():
    # Ищем конфиг, поднимаясь на уровень выше, так как скрипт в src/
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clean_cache():
    cfg = load_config()
    cache_dir = cfg['paths']['cache_dir']
    
    # Защита от дурака: убедимся, что путь похож на кэш
    if "cache" not in cache_dir:
        print(f"⚠️ ОПАСНОСТЬ: Попытка удалить папку {cache_dir}, которая не похожа на кэш.")
        print("Операция отменена.")
        return

    if not os.path.exists(cache_dir):
        print("🧹 Кэш уже чист (папка не существует).")
        return

    print(f"🗑️ Удаляем кэш: {cache_dir} ...")
    
    try:
        # Удаляем всё дерево папок
        shutil.rmtree(cache_dir)
        # Создаем пустую папку обратно, чтобы не было ошибок при запуске
        os.makedirs(cache_dir)
        print("✨ Готово! Кэш полностью очищен.")
    except Exception as e:
        print(f"❌ Ошибка при удалении: {e}")

if __name__ == "__main__":
    confirm = input("Вы уверены, что хотите удалить ВСЕ временные файлы (индексы, эмбеддинги)? [y/N]: ")
    if confirm.lower() == 'y':
        clean_cache()
    else:
        print("Отмена.")
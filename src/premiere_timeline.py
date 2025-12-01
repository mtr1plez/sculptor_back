import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, List
from utils import load_config


class PremiereXMLExporter:
    """
    Экспорт timeline в Final Cut Pro XML формат
    Совместим с Premiere Pro, DaVinci Resolve, Final Cut Pro
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.cfg = load_config(config_path)
    
    def export_timeline_to_xml(
        self,
        timeline_path: str = None,
        output_path: str = None
    ) -> str:
        """
        Экспорт timeline.json в Final Cut Pro XML
        
        Args:
            timeline_path: Путь к timeline.json
            output_path: Путь для сохранения XML
        
        Returns:
            Путь к созданному XML файлу
        """
        # Дефолтные пути
        if timeline_path is None:
            timeline_path = Path(self.cfg["paths"]["cache_dir"]) / "timeline.json"
        
        if output_path is None:
            output_path = Path(self.cfg["paths"]["project_root"]) / "output" / "premiere_timeline.xml"
        
        # Загрузка timeline
        with open(timeline_path, 'r', encoding='utf-8') as f:
            timeline = json.load(f)
        
        # Создание XML структуры
        xmeml = self._create_xmeml_structure(timeline)
        
        # Красивое форматирование
        xml_string = self._prettify_xml(xmeml)
        
        # Сохранение
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        
        print(f"✅ Premiere Pro XML экспортирован: {output_path}")
        return str(output_path)
    
    def _create_xmeml_structure(self, timeline: Dict) -> ET.Element:
        """Создание XML структуры Final Cut Pro"""
        
        # Root element
        xmeml = ET.Element('xmeml', version="5")
        
        # Project
        project = ET.SubElement(xmeml, 'project')
        
        # Project name
        name = ET.SubElement(project, 'name')
        name.text = timeline.get('project', 'SculptorPro Project')
        
        # Children (sequences container)
        children = ET.SubElement(project, 'children')
        
        # Main sequence
        sequence = self._create_sequence(timeline, children)
        
        return xmeml
    
    def _create_sequence(self, timeline: Dict, parent: ET.Element) -> ET.Element:
        """Создание sequence (timeline) в XML"""
        
        sequence = ET.SubElement(parent, 'sequence')
        
        # Sequence properties
        name = ET.SubElement(sequence, 'name')
        name.text = f"{timeline.get('project', 'Project')} - Timeline"
        
        duration = ET.SubElement(sequence, 'duration')
        duration.text = str(int(timeline['total_duration'] * timeline['fps']))
        
        # Rate (frame rate)
        rate = ET.SubElement(sequence, 'rate')
        timebase = ET.SubElement(rate, 'timebase')
        timebase.text = str(timeline.get('fps', 24))
        
        # Media
        media = ET.SubElement(sequence, 'media')
        
        # Video tracks
        video_section = ET.SubElement(media, 'video')
        video_tracks = [t for t in timeline['tracks'] if t['type'] == 'video']
        
        for track in video_tracks:
            self._create_video_track(track, video_section, timeline)
        
        # Audio tracks
        audio_section = ET.SubElement(media, 'audio')
        audio_tracks = [t for t in timeline['tracks'] if t['type'] == 'audio']
        
        for track in audio_tracks:
            self._create_audio_track(track, audio_section, timeline)
        
        return sequence
    
    def _create_video_track(
        self, 
        track: Dict, 
        parent: ET.Element,
        timeline: Dict
    ):
        """Создание video трека"""
        
        video_track = ET.SubElement(parent, 'track')
        
        # Track enabled
        enabled = ET.SubElement(video_track, 'enabled')
        enabled.text = 'TRUE'
        
        # Track locked
        locked = ET.SubElement(video_track, 'locked')
        locked.text = 'FALSE'
        
        # Clips
        for clip_data in track['clips']:
            self._create_video_clip(clip_data, video_track, timeline)
    
    def _create_video_clip(
        self,
        clip_data: Dict,
        parent: ET.Element,
        timeline: Dict
    ):
        """Создание video клипа"""
        
        fps = timeline.get('fps', 24)
        
        clipitem = ET.SubElement(parent, 'clipitem', id=clip_data['id'])
        
        # Clip name
        name = ET.SubElement(clipitem, 'name')
        name.text = clip_data.get('text', 'Clip')[:50]  # Ограничение длины
        
        # Duration (в frames)
        duration = ET.SubElement(clipitem, 'duration')
        duration.text = str(int(clip_data['duration'] * fps))
        
        # Rate
        rate = ET.SubElement(clipitem, 'rate')
        timebase = ET.SubElement(rate, 'timebase')
        timebase.text = str(fps)
        
        # Start (timeline position в frames)
        start = ET.SubElement(clipitem, 'start')
        start.text = str(int(clip_data['timeline_start'] * fps))
        
        # End (timeline position + duration в frames)
        end = ET.SubElement(clipitem, 'end')
        end.text = str(int((clip_data['timeline_start'] + clip_data['duration']) * fps))
        
        # In point (source_in в frames)
        in_point = ET.SubElement(clipitem, 'in')
        in_point.text = str(int(clip_data['source_in'] * fps))
        
        # Out point (source_out в frames)
        out_point = ET.SubElement(clipitem, 'out')
        out_point.text = str(int(clip_data['source_out'] * fps))
        
        # File reference
        file_elem = ET.SubElement(clipitem, 'file', id=f"file-{clip_data['id']}")
        
        # File name
        file_name = ET.SubElement(file_elem, 'name')
        file_name.text = Path(timeline['source_video']).name
        
        # File path (абсолютный путь)
        pathurl = ET.SubElement(file_elem, 'pathurl')
        abs_path = Path(timeline['source_video']).resolve()
        pathurl.text = f"file://localhost/{abs_path.as_posix()}"
        
        # File rate
        file_rate = ET.SubElement(file_elem, 'rate')
        file_timebase = ET.SubElement(file_rate, 'timebase')
        file_timebase.text = str(fps)
        
        # File duration (весь source video)
        file_duration = ET.SubElement(file_elem, 'duration')
        # Приблизительная длительность (можно улучшить через moviepy)
        file_duration.text = str(int(10000 * fps))  # 10000 секунд placeholder
        
        # Media info
        media = ET.SubElement(file_elem, 'media')
        video_media = ET.SubElement(media, 'video')
        
        # Video characteristics
        video_char = ET.SubElement(video_media, 'samplecharacteristics')
        
        width = ET.SubElement(video_char, 'width')
        width.text = '1920'
        
        height = ET.SubElement(video_char, 'height')
        height.text = '1080'
        
        # Link (track type)
        link = ET.SubElement(clipitem, 'link')
        linkclipref = ET.SubElement(link, 'linkclipref')
        linkclipref.text = f"audio-{clip_data['id']}"
    
    def _create_audio_track(
        self,
        track: Dict,
        parent: ET.Element,
        timeline: Dict
    ):
        """Создание audio трека"""
        
        audio_track = ET.SubElement(parent, 'track')
        
        # Track properties
        enabled = ET.SubElement(audio_track, 'enabled')
        enabled.text = 'TRUE'
        
        locked = ET.SubElement(audio_track, 'locked')
        locked.text = 'FALSE'
        
        # Clips
        for clip_data in track['clips']:
            self._create_audio_clip(clip_data, audio_track, timeline)
    
    def _create_audio_clip(
        self,
        clip_data: Dict,
        parent: ET.Element,
        timeline: Dict
    ):
        """Создание audio клипа"""
        
        fps = timeline.get('fps', 24)
        
        clipitem = ET.SubElement(parent, 'clipitem', id=f"audio-{clip_data['id']}")
        
        # Clip name
        name = ET.SubElement(clipitem, 'name')
        name.text = f"Audio: {clip_data.get('text', 'Clip')[:40]}"
        
        # Duration
        duration = ET.SubElement(clipitem, 'duration')
        duration.text = str(int(clip_data['duration'] * fps))
        
        # Rate
        rate = ET.SubElement(clipitem, 'rate')
        timebase = ET.SubElement(rate, 'timebase')
        timebase.text = str(fps)
        
        # Timeline positions
        start = ET.SubElement(clipitem, 'start')
        start.text = str(int(clip_data['timeline_start'] * fps))
        
        end = ET.SubElement(clipitem, 'end')
        end.text = str(int((clip_data['timeline_start'] + clip_data['duration']) * fps))
        
        # Source positions
        in_point = ET.SubElement(clipitem, 'in')
        in_point.text = str(int(clip_data['source_in'] * fps))
        
        out_point = ET.SubElement(clipitem, 'out')
        out_point.text = str(int(clip_data['source_out'] * fps))
        
        # File reference
        file_elem = ET.SubElement(clipitem, 'file', id=f"audio-file-{clip_data['id']}")
        
        file_name = ET.SubElement(file_elem, 'name')
        file_name.text = Path(timeline['source_audio']).name
        
        pathurl = ET.SubElement(file_elem, 'pathurl')
        abs_path = Path(timeline['source_audio']).resolve()
        pathurl.text = f"file://localhost/{abs_path.as_posix()}"
        
        # Audio rate (sample rate)
        audio_rate = ET.SubElement(file_elem, 'rate')
        audio_timebase = ET.SubElement(audio_rate, 'timebase')
        audio_timebase.text = str(fps)
        
        # Media info
        media = ET.SubElement(file_elem, 'media')
        audio_media = ET.SubElement(media, 'audio')
        
        # Audio characteristics
        audio_char = ET.SubElement(audio_media, 'samplecharacteristics')
        
        samplerate = ET.SubElement(audio_char, 'samplerate')
        samplerate.text = '48000'
        
        depth = ET.SubElement(audio_char, 'depth')
        depth.text = '16'
        
        # Source channel
        sourcetrack = ET.SubElement(clipitem, 'sourcetrack')
        
        media_type = ET.SubElement(sourcetrack, 'mediatype')
        media_type.text = 'audio'
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """Красивое форматирование XML"""
        rough_string = ET.tostring(elem, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        
        # XML declaration
        return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode('utf-8')


def main():
    """Основной запуск экспорта"""
    exporter = PremiereXMLExporter()
    
    print("🎬 SculptorPro → Premiere Pro XML Exporter\n")
    
    # Проверка наличия timeline.json
    timeline_path = Path(exporter.cfg["paths"]["cache_dir"]) / "timeline.json"
    
    if not timeline_path.exists():
        print("❌ timeline.json не найден!")
        print("   Сначала запусти: python src/timeline_exporter.py")
        return
    
    # Экспорт
    xml_path = exporter.export_timeline_to_xml()
    
    print(f"\n✅ Готово!")
    print(f"\n📝 Инструкция:")
    print(f"   1. Открой Premiere Pro")
    print(f"   2. File → Import")
    print(f"   3. Выбери: {xml_path}")
    print(f"   4. Твой timeline появится в проекте!")
    print(f"\n💡 Premiere автоматически найдет movie.mp4 и voice.mp3")
    print(f"   Убедись что они в той же папке!")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Unified TOON creator - tworzy jeden plik TOON z całego folderu
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add toonic to path
sys.path.insert(0, str(Path(__file__).parent))

from toonic.pipeline import Pipeline
from toonic.core.detector import SpecDetector


def create_unified_toon(source_dir: str, output_file: str, fmt: str = 'toon') -> None:
    """Tworzy jeden plik TOON z całego folderu."""
    
    source_path = Path(source_dir)
    if not source_path.is_dir():
        print(f"Błąd: {source_dir} nie jest katalogiem", file=sys.stderr)
        sys.exit(1)
    
    # Zbierz wszystkie pliki
    files_data = []
    
    print(f"Przeszukuję katalog: {source_dir}")
    
    for path in sorted(source_path.rglob('*')):
        if not path.is_file():
            continue
        if path.name.startswith('.'):
            continue
        
        try:
            # Konwertuj każdy plik na TOON
            spec = Pipeline.to_spec(str(path), fmt=fmt)
            
            files_data.append({
                'path': str(path.relative_to(source_dir)),
                'absolute_path': str(path),
                'spec': spec,
                'size': path.stat().st_size,
                'modified': path.stat().st_mtime
            })
            
            print(f"  ✓ {path.relative_to(source_path)}")
            
        except Exception as e:
            print(f"  ✗ Pominięto {path}: {e}", file=sys.stderr)
    
    if not files_data:
        print("Nie znaleziono żadnych plików do przetworzenia", file=sys.stderr)
        sys.exit(1)
    
    # Stwórz zunifikowany TOON
    unified_spec = create_unified_spec(files_data, source_dir)
    
    # Zapisz wynik
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(unified_spec, encoding='utf-8')
    
    print(f"\nUtworzono zunifikowany plik: {output_file}")
    print(f"Zawartość: {len(files_data)} plików")
    print(f"Rozmiar: {output_path.stat().st_size} bytes")


def create_unified_spec(files_data: List[Dict[str, Any]], source_dir: str) -> str:
    """Tworzy zunifikowany spec TOON."""
    
    lines = [
        f"# Unified TOON spec for directory: {source_dir}",
        f"# Generated: {len(files_data)} files",
        f"#",
        f"project:",
        f"  name: \"{Path(source_dir).name}\"",
        f"  directory: \"{source_dir}\"",
        f"  files:",
    ]
    
    for file_info in files_data:
        rel_path = file_info['path']
        lines.append(f"    - path: \"{rel_path}\"")
        lines.append(f"      size: {file_info['size']}")
        lines.append(f"      modified: {file_info['modified']}")
        lines.append(f"      spec: |")
        
        # Dodaj spec pliku z wcięciami
        spec_lines = file_info['spec'].split('\n')
        for spec_line in spec_lines:
            if spec_line.strip():
                lines.append(f"        {spec_line}")
            else:
                lines.append("        ")
        
        lines.append("")  # Pusta linia między plikami
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Tworzy jeden zunifikowany plik TOON z całego folderu'
    )
    parser.add_argument('source_dir', help='Katalog źródłowy')
    parser.add_argument('-o', '--output', required=True, help='Plik wyjściowy .toon')
    parser.add_argument('--fmt', default='toon', choices=['toon', 'yaml', 'json'],
                       help='Format spec (domyślnie: toon)')
    
    args = parser.parse_args()
    
    create_unified_toon(args.source_dir, args.output, args.fmt)


if __name__ == '__main__':
    main()

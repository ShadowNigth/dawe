"""Alias del exportador compartido; por defecto sigue compilando la USP-S."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_viewmodel import main

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Prospector CLI - Sistema de Mineração Técnica & Funil de Prospecção Ágil
Ponto de entrada principal do executável.
"""

import sys
import os

# Garante que o pacote local prospector seja encontrado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prospector.cli import main

if __name__ == "__main__":
    main()

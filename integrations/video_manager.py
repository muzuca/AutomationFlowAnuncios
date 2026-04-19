# arquivo: integrations/video_manager.py
# descricao: Gerenciador de vídeos pós-geração.
# Etapa 1: Concatena as cenas parciais em 720p (mantendo o áudio original intacto) para gerar as variantes.
# Etapa 2: Faz o upscaling (1080p) exclusivamente do vídeo que for eleito o vencedor pela IA.

import shutil
import subprocess
import time
from pathlib import Path
from typing import List
from integrations.utils import _log as log_base


def _log(msg: str):
    log_base(msg, prefixo="VIDEO_MANAGER")
    
def _criar_lista_ffmpeg(arquivos: List[Path], lista_path: Path):
    with open(lista_path, "w", encoding="utf-8") as f:
        for arq in arquivos:
            f.write(f"file '{arq.as_posix()}'\n")

def concatenar_cenas_720p(arquivos_mp4: List[Path], saida_path: Path) -> bool:
    """Junta as cenas originais (720p) mantendo o áudio original intacto."""
    _log(f"Concatenando {len(arquivos_mp4)} cenas em 720p...")
    lista_path = saida_path.parent / f"_lista_{saida_path.stem}.txt"
    _criar_lista_ffmpeg(arquivos_mp4, lista_path)
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lista_path), "-c", "copy", str(saida_path)
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=True)
        lista_path.unlink(missing_ok=True)
        return True
    except Exception as e:
        _log(f"❌ Erro na concatenação 720p: {e}")
        return False

def converter_para_1080p(entrada: Path, saida: Path) -> bool:
    """Faz o upscaling do vídeo vencedor para 1080p vertical."""
    _log(f"Fazendo upscale do vídeo vencedor para 1080p: {entrada.name}")
    cmd = [
        "ffmpeg", "-y", "-i", str(entrada),
        "-vf", "scale=1080:1920,setdar=9/16",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(saida)
    ]
    
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=True)
        _log(f"✔ Upscale concluído: {saida.name}")
        return True
    except Exception as e:
        _log(f"❌ Erro no upscale: {e}")
        return False

def limpar_arquivos_temporarios(arquivos: List[Path]):
    """Remove os arquivos individuais após a conclusão."""
    for arq in arquivos:
        try:
            if arq.exists():
                arq.unlink()
                _log(f"🗑 Removido arquivo parcial: {arq.name}")
        except Exception as e:
            _log(f"⚠ Não consegui remover {arq.name}: {e}")
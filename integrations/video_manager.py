# arquivo: integrations/video_manager.py
# descricao: Gerenciador de vídeos pós-geração.
# Etapa 1: Concatena os arquivos .mp4 de 720p gerados pelo Flow (mantendo o áudio original).
# Etapa 2: Faz o upscaling do vídeo unificado para 1080p.

import shutil
import subprocess
import time
from pathlib import Path
from typing import List

def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [VIDEO_MANAGER] {msg}")

def _criar_lista_ffmpeg(arquivos: List[Path], lista_path: Path):
    """Cria o arquivo de lista no formato exigido pelo ffmpeg concat."""
    with open(lista_path, "w", encoding="utf-8") as f:
        for arq in arquivos:
            f.write(f"file '{arq.as_posix()}'\n")

def _remover_arquivos(arquivos: List[Path]):
    """Remove os arquivos individuais após a conclusão."""
    for arq in arquivos:
        try:
            if arq.exists():
                arq.unlink()
                _log(f"🗑 Removido arquivo parcial: {arq.name}")
        except Exception as e:
            _log(f"⚠ Não consegui remover {arq.name}: {e}")

def processar_videos(arquivos_mp4: List[Path], pasta_destino: Path, nome_final: str = "Anuncio_Final_1080p.mp4", **kwargs) -> Path | None:
    """
    Junta as cenas em 720p copiando o áudio original, e depois converte o arquivo único para 1080p.
    """
    _log("Iniciando o Video Manager...")
    
    faltando = [a for a in arquivos_mp4 if not a.exists()]
    if faltando:
        _log(f"❌ Erro: Arquivos base não encontrados: {[str(a.name) for a in faltando]}")
        return None

    if len(arquivos_mp4) == 0:
        _log("❌ Erro: Nenhuma cena fornecida para processar.")
        return None
        
    pasta_destino.mkdir(parents=True, exist_ok=True)
    arquivo_final = pasta_destino / nome_final
    
    lista_path = pasta_destino / "_lista_concat.txt"
    video_temp_720p = pasta_destino / "_temp_720p.mp4"
    
    # Limpa vestígios antigos se existirem
    if arquivo_final.exists(): arquivo_final.unlink()
    if video_temp_720p.exists(): video_temp_720p.unlink()

    ffmpeg_path = "ffmpeg"

    # ==========================================================
    # ETAPA 1: CONCATENAÇÃO SIMPLES (Mantém 720p e Áudio Intacto)
    # ==========================================================
    _log("Etapa 1/2: Concatenando as cenas originais...")
    _criar_lista_ffmpeg(arquivos_mp4, lista_path)
    
    cmd_concat = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(lista_path),
        "-c", "copy", # Copia vídeo e áudio sem re-renderizar
        str(video_temp_720p)
    ]
    
    try:
        result_concat = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result_concat.returncode != 0:
            erro = result_concat.stderr.decode("utf-8", errors="replace")[-500:]
            _log(f"❌ Erro na concatenação:\n{erro}")
            lista_path.unlink(missing_ok=True)
            return None
    except Exception as e:
        _log(f"❌ Falha ao executar FFmpeg (Concatenação): {e}")
        lista_path.unlink(missing_ok=True)
        return None

    # ==========================================================
    # ETAPA 2: UPSCALING PARA 1080P (Preservando o Áudio)
    # ==========================================================
    _log("Etapa 2/2: Fazendo upscaling para 1080p...")
    cmd_scale = [
        ffmpeg_path, "-y",
        "-i", str(video_temp_720p),
        "-vf", "scale=1080:1920,setdar=9/16",
        "-c:v", "libx264",        # Re-renderiza apenas a imagem
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",           # <-- A MÁGICA: Copia o áudio original intacto!
        str(arquivo_final)
    ]

    try:
        result_scale = subprocess.run(cmd_scale, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if result_scale.returncode != 0:
            erro = result_scale.stderr.decode("utf-8", errors="replace")[-500:]
            _log(f"❌ Erro no upscaling:\n{erro}")
            return None
            
        _log(f"✔ Vídeo final 1080p gerado com sucesso: {arquivo_final.name} ({arquivo_final.stat().st_size // (1024*1024)} MB)")
        
        # Limpeza de arquivos temporários e parciais
        lista_path.unlink(missing_ok=True)
        video_temp_720p.unlink(missing_ok=True)
        _remover_arquivos(arquivos_mp4)
        
        return arquivo_final

    except Exception as e:
        _log(f"❌ Falha ao executar FFmpeg (Upscaling): {e}")
        return None
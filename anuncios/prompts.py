# arquivo: anuncios/prompts.py
# descricao: Central de Prompts Mestre para a IA (Gemini).
# Puxa os prompts do Google Drive. Se houver falha, puxa do arquivo fallback_prompts.py.

import os
from pathlib import Path
from dotenv import load_dotenv
from integrations.utils import _log

load_dotenv(override=True)
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "G:/Meu Drive/Prompts"))


# =============================================================================
# FUNÇÃO DE CARREGAMENTO INTELIGENTE (DRIVE + FALLBACK)
# =============================================================================

def carregar_prompt(nome_arquivo: str) -> str:
    """
    Carrega o prompt exclusivamente do Google Drive. 
    Se o arquivo não existir ou estiver vazio, o sistema para (Raise Error).
    """
    caminho = PROMPTS_DIR / f"{nome_arquivo}.txt"
    
    if not caminho.exists():
        msg_erro = f"🚨 ERRO FATAL: Arquivo de prompt OBRIGATÓRIO não encontrado: {caminho}"
        _log(msg_erro)
        raise FileNotFoundError(msg_erro)
        
    try:
        texto = caminho.read_text(encoding='utf-8').strip()
        if len(texto) < 10:
            raise ValueError(f"O arquivo {nome_arquivo}.txt está vazio ou muito curto.")
        
        # Log de confirmação (assim você sabe que veio do disco)
        #_log(f"✅ Prompt carregado com sucesso: {nome_arquivo}.txt ({len(texto)} chars)")
        return texto
        
    except Exception as e:
        _log(f"🚨 Erro ao ler o arquivo {nome_arquivo}.txt: {e}")
        raise e


# =============================================================================
# MAPEAMENTO DINÂMICO
# =============================================================================

PROMPT_CLASSIFICACAO_ARQUIVOS = carregar_prompt("01_classificacao_arquivos")
PROMPT_VALIDACAO_PRODUTO = carregar_prompt("02_validacao_produto")

PROMPT_DIRETOR_DE_ARTE_IMAGEM = carregar_prompt("03_diretor_de_arte")
PROMPT_GERACAO_IMAGEM_FRONTAL = carregar_prompt("04_imagem_frontal")
PROMPT_GERACAO_IMAGEM_CAMINHANDO = carregar_prompt("04_imagem_caminhando")
PROMPT_GERACAO_IMAGEM_POV = carregar_prompt("04_imagem_pov")
PROMPT_GERACAO_IMAGEM_PES = carregar_prompt("04_imagem_pes")
PROMPT_GERACAO_IMAGEM_FLAT = carregar_prompt("04_imagem_flat")

PROMPT_MESTRE_ROTEIRO = carregar_prompt("05_mestre_roteiro")
PROMPT_EXECUCAO_ROTEIRO = carregar_prompt("06_execucao_roteiro")

PROMPT_JURI_CANDIDATOS_IMAGEM_BASE = carregar_prompt("07_juri_imagem_base")
PROMPT_JURI_TESTE_AB_IMAGEM_BASE = carregar_prompt("08_juri_teste_ab")
PROMPT_JURI_VIDEO = carregar_prompt("09_juri_video")
PROMPT_JURI_LOTE_FINAL = carregar_prompt("10_juri_lote_final")
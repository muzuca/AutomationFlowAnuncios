# arquivo: integrations/acesso_humble.py
# descricao: gerencia a sincronização de credenciais a partir de um Google Doc dinâmico usando apenas o ID. 
# Extrai logins/senhas, limpa o arquivo .env e injeta as contas atualizadas para o rodízio do robô.

import os
import re
import requests
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 🚨 IMPORTAÇÃO DO LOG UNIFICADO
from integrations.utils import _log

ENV_PATH = Path(".env")

def time_now():
    return datetime.now().strftime("%H:%M:%S")

def _obter_url_exportacao() -> str:
    """Busca o ID no .env e monta a URL de exportação sem firulas."""
    load_dotenv(override=True) 
    doc_id = os.getenv("HUMBLE_DOC_ID")
    
    if not doc_id:
        raise ValueError("A variável HUMBLE_DOC_ID não foi encontrada no .env.")

    # Monta a URL direto para o formato texto
    return f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

def _extrair_credenciais_do_documento(texto: str) -> list[tuple[str, str]]:
    """Lógica de extração baseada em padrões LOGIN: e SENHA:."""
    credenciais = []
    login_atual = None
    
    for linha in texto.splitlines():
        linha_limpa = linha.strip()
        if not linha_limpa: 
            continue
            
        match_login = re.match(r"^\s*LOGIN\s*:\s*(\S+)", linha_limpa, flags=re.IGNORECASE)
        if match_login:
            login_bruto = match_login.group(1).strip().replace("[", "").replace("]", "")
            if "(mailto:" in login_bruto:
                login_bruto = login_bruto.split("(mailto:", 1)[0].strip()
            login_atual = login_bruto
            continue
            
        match_senha = re.match(r"^\s*SENHA\s*:\s*(\S+)", linha_limpa, flags=re.IGNORECASE)
        if match_senha and login_atual:
            senha = match_senha.group(1).strip()
            credenciais.append((login_atual, senha))
            login_atual = None
            
    # Remove duplicatas mantendo a ordem
    vistos = set()
    resultado = []
    for email, senha in credenciais:
        if email not in vistos:
            vistos.add(email)
            resultado.append((email, senha))
    return resultado

def _remover_bloco_humble_env(conteudo: str) -> str:
    """Remove credenciais do .env, mas PRESERVA a conta 0 (Ultra)."""
    linhas_filtradas = []
    for linha in conteudo.splitlines():
        # Se achou o marcador de início do bloco sincronizado, para de ler o resto
        if "# --- CREDENCIAIS HUMBLE (SINCRONIZADO" in linha: 
            break
        # NÃO apaga se for a HUMBLE_EMAIL_0 ou PASSWORD_0
        if re.match(r"^\s*HUMBLE_(EMAIL|PASSWORD)_0\s*=", linha):
            linhas_filtradas.append(linha)
            continue
        # Apaga as outras (1 em diante)
        if re.match(r"^\s*HUMBLE_(EMAIL|PASSWORD)_\d+\s*=", linha): 
            continue
        linhas_filtradas.append(linha)
    return "\n".join(linhas_filtradas).strip()

def sincronizar_credenciais_humble():
    """
    Versão Resiliente: Faz o download via ID com até 3 tentativas.
    Lida com erros 500 do Google sem travar o script.
    """
    max_tentativas = 3
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    for tentativa in range(1, max_tentativas + 1):
        try:
            export_url = _obter_url_exportacao()
            if tentativa == 1:
                _log("Sincronizando contas via ID do Google Doc...")
            
            response = requests.get(export_url, headers=headers, timeout=30)
            
            # Se der erro 500, força a exceção para cair no except e retentar
            response.raise_for_status()
            
            credenciais = _extrair_credenciais_do_documento(response.text)
            if not credenciais:
                _log("❌ Erro: Formato LOGIN:/SENHA: não encontrado no documento.")
                return
                
            # Atualização do .env preservando o topo
            conteudo_atual = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
            conteudo_base = _remover_bloco_humble_env(conteudo_atual)
            
            novo_bloco = ["\n# --- CREDENCIAIS HUMBLE (SINCRONIZADO VIA ID) ---"]
            for i, (email, senha) in enumerate(credenciais, start=1):
                novo_bloco.append(f"HUMBLE_EMAIL_{i}={email}")
                novo_bloco.append(f"HUMBLE_PASSWORD_{i}={senha}")
                
            conteudo_final = conteudo_base + "\n" + "\n".join(novo_bloco) + "\n"
            ENV_PATH.write_text(conteudo_final.strip() + "\n", encoding="utf-8")
            
            _log(f"✅ Sucesso: {len(credenciais)} contas carregadas para o rodízio.")
            return # Sai da função após o sucesso

        except Exception as e:
            if tentativa < max_tentativas:
                _log(f"⚠️ Google instável (Erro {tentativa}/{max_tentativas}). Retentando em 3s...")
                time.sleep(3)
            else:
                # Na última tentativa, ele avisa que vai usar o que já tem no .env
                _log(f"❌ Falha após {max_tentativas} tentativas. Mantendo cache local: {e}")

def executar_sincronizacao(driver=None):
    """Ponte de execução chamada pelo orquestrador."""
    sincronizar_credenciais_humble()

if __name__ == "__main__":
    sincronizar_credenciais_humble()
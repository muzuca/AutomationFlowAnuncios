import re
import requests
import time
from pathlib import Path
from datetime import datetime

# Configurações do Documento
DOC_ID = "1CxZmaI1Cxrgg3iyDkLxW68bA0jV63CNNrabNk4yNBLg"
EXPORT_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"
ENV_PATH = Path(".env")

def time_now():
    return datetime.now().strftime("%H:%M:%S")

def _extrair_credenciais_do_documento(texto: str) -> list[tuple[str, str]]:
    credenciais = []
    login_atual = None
    for linha in texto.splitlines():
        linha_limpa = linha.strip()
        if not linha_limpa: continue
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
    vistos = set()
    resultado = []
    for email, senha in credenciais:
        if email not in vistos:
            vistos.add(email)
            resultado.append((email, senha))
    return resultado

def _remover_bloco_humble_env(conteudo: str) -> str:
    linhas_filtradas = []
    for linha in conteudo.splitlines():
        if "# --- CREDENCIAIS HUMBLE" in linha: break
        if re.match(r"^\s*HUMBLE_(EMAIL|PASSWORD)_\d+\s*=", linha): continue
        linhas_filtradas.append(linha)
    return "\n".join(linhas_filtradas).strip()

def sincronizar_credenciais_humble():
    """Lógica original de sincronização."""
    try:
        print(f"[{time_now()}] Acessando Google Doc de Credenciais...")
        response = requests.get(EXPORT_URL, timeout=30)
        response.raise_for_status()
        credenciais = _extrair_credenciais_do_documento(response.text)
        if not credenciais:
            print("❌ Erro: Formato LOGIN:/SENHA: não encontrado no Doc.")
            return
        conteudo_atual = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        conteudo_base = _remover_bloco_humble_env(conteudo_atual)
        novo_bloco = ["\n# --- CREDENCIAIS HUMBLE (SINCRONIZADO DO GOOGLE DOC) ---"]
        for i, (email, senha) in enumerate(credenciais, start=1):
            novo_bloco.append(f"HUMBLE_EMAIL_{i}={email}")
            novo_bloco.append(f"HUMBLE_PASSWORD_{i}={senha}")
        conteudo_final = conteudo_base + "\n" + "\n".join(novo_bloco) + "\n"
        ENV_PATH.write_text(conteudo_final.strip() + "\n", encoding="utf-8")
        print(f"✅ Sincronizado: {len(credenciais)} contas carregadas no .env.")
    except Exception as e:
        print(f"❌ Falha na sincronização: {e}")

def executar_sincronizacao(driver=None):
    """Função ponte para o main.py."""
    sincronizar_credenciais_humble()

if __name__ == "__main__":
    sincronizar_credenciais_humble()
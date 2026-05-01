# arquivo: integrations/utils.py
import os
import time
import ctypes
import random
import shutil
import re
import logging
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

def is_headless(*args, **kwargs) -> bool:
    """
    Verifica direto no .env se o navegador foi configurado para rodar invisível.
    Ignora cliques físicos (PyAutoGUI) se estiver True.
    """
    load_dotenv(override=True)
    # Pega o valor do .env, joga pra minúsculo e vê se é 'true'
    return os.getenv("CHROME_HEADLESS", "False").lower() == "true"

def setup_logging() -> None:
    """Configura o nível de ruído das bibliotecas externas e o formato padrão de log do Python."""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logging.getLogger('selenium').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL)
    logging.getLogger('WDM').setLevel(logging.CRITICAL)
    logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)
    logging.getLogger('tensorflow').setLevel(logging.CRITICAL)
    logging.getLogger('absl').setLevel(logging.CRITICAL)

def _log(msg: str, prefixo: str = "SISTEMA") -> None:
    """
    Logger centralizado. 
    Console: [15:30:01] [GEMINI-IA] Iniciando
    TXT:     [2024-05-24 15:30:01] [GEMINI-IA] Iniciando
    """
    from datetime import datetime
    agora = datetime.now()
    
    # Hora para o terminal (curto)
    ts_console = agora.strftime('%H:%M:%S')
    # Data e Hora para o TXT (necessário para a faxina funcionar)
    ts_file = agora.strftime('%Y-%m-%d %H:%M:%S') 
    
    texto_console = f'[{ts_console}] [{prefixo}] {msg}'
    texto_file = f'[{ts_file}] [{prefixo}] {msg}'
    
    print(texto_console)
    
    # Salva no novo arquivo com a data
    try:
        log_file = Path("logs") / "log_execucao.txt" # <--- NOME ALTERADO AQUI
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(texto_file + "\n")
    except: pass

def log_step(message: str) -> None:
    _log(message, prefixo="SISTEMA")

def log_success(message: str) -> None:
    _log(f'OK: {message}', prefixo="SISTEMA")

def log_error(message: str) -> None:
    _log(f'ERRO: {message}', prefixo="SISTEMA")
    
def salvar_print_debug(driver, nome_fase: str):
    """Sua função mestre com a tarja vermelha de URL."""
    load_dotenv(override=True)
    if os.getenv("DISABLE_SCREENSHOTS", "False").lower() == "true":
        return
    try:
        # Agora usamos a função auxiliar e criamos a subpasta 'visao'
        pasta_visao = _get_logs_dir() / "visao"
        pasta_visao.mkdir(parents=True, exist_ok=True)
        
        # Injeta a tarja vermelha
        driver.execute_script("""
            let debugDiv = document.getElementById('debug-url-overlay') || document.createElement('div');
            debugDiv.id = 'debug-url-overlay';
            debugDiv.style = 'position:fixed;top:0;left:0;width:100%;z-index:999999;background:rgba(255,0,0,0.9);color:white;padding:10px;font-size:16px;font-weight:bold;text-align:center;';
            debugDiv.innerText = 'URL: ' + window.location.href;
            document.body.appendChild(debugDiv);
        """)
        time.sleep(0.3) 
        
        timestamp = time.strftime('%H%M%S')
        driver.save_screenshot(str(pasta_visao / f"{timestamp}_{nome_fase}.png"))
        
        # Limpa a tarja
        driver.execute_script("const el = document.getElementById('debug-url-overlay'); if(el) el.remove();")
    except: pass

def js_click(driver, elemento):
    """Executa clique via JavaScript."""
    driver.execute_script("arguments[0].click();", elemento)

def scroll_ao_fim(driver):
    """
    VERSÃO FORÇA BRUTA: Varre a página inteira atrás de contêineres com scroll.
    Essencial para o layout dinâmico do Gemini.
    """
    try:
        driver.execute_script(
            """
            // 1. Alvos conhecidos do Gemini e ferramentas Google
            const scrollers = document.querySelectorAll('infinite-scroller, #chat-history, .chat-history-scroll-container, .conversation-container, rich-textarea');
            scrollers.forEach(scroller => {
                scroller.scrollTop = scroller.scrollHeight;
            });
            
            // 2. BUSCA EXAUSTIVA: Varre absolutamente tudo que tenha barra de rolagem
            const allElements = document.querySelectorAll('*');
            for (let i = 0; i < allElements.length; i++) {
                let el = allElements[i];
                if (el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            
            // 3. Scroll da janela principal (fallback)
            window.scrollTo(0, document.documentElement.scrollHeight || document.body.scrollHeight);
            """
        )
    except Exception:
        pass
    
def forcar_fechamento_janela_windows():
    """Fala direto com a API do Windows para fechar diálogos de arquivo pendentes."""
    try:
        # Tenta achar a janela pelo título padrão do Windows em PT e EN
        titulos = ["Abrir", "Open"]
        for titulo in titulos:
            hwnd = ctypes.windll.user32.FindWindowW(None, titulo)
            if hwnd:
                _log(f"Janela '{titulo}' detectada no Windows. Forçando fechamento...", "SISTEMA")
                # Envia o comando WM_CLOSE (0x0010) para a janela
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
                time.sleep(0.5)
    except Exception as e:
        _log(f"Erro ao tentar matar janela nativa: {e}", "SISTEMA")

def _get_logs_dir() -> Path:
    """Garante e retorna o caminho absoluto para a pasta 'logs' na raiz do projeto."""
    raiz_projeto = Path(__file__).parent.parent  # Sobe de /integrations para a raiz
    logs_dir = raiz_projeto / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir

def limpar_diretorio_visao() -> None:
    """Zera o diretório de prints de monitoramento (logs/visao) para não acumular lixo."""
    try:
        pasta_visao = _get_logs_dir() / "visao"
        if pasta_visao.exists():
            _log(f"Limpando imagens antigas de monitoramento em {pasta_visao.name}...", "SISTEMA")
            for arquivo in pasta_visao.glob("*.png"):
                try:
                    arquivo.unlink()
                except Exception:
                    pass
        else:
            pasta_visao.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _log(f"Aviso: Falha ao limpar pasta logs/visao: {e}", "SISTEMA")

def salvar_ultimo_prompt(texto: str) -> None:
    """Salva o último prompt enviado para a IA num ficheiro txt centralizado nos logs."""
    try:
        arquivo_prompt = _get_logs_dir() / "ultimo_prompt.txt"
        with open(arquivo_prompt, "w", encoding="utf-8") as f:
            f.write(texto)
    except Exception as e:
        _log(f"Aviso: Não foi possível guardar o log do prompt: {e}", "SISTEMA")

def obter_proxy_aleatorio() -> str | None:
    """
    Lê a lista de proxies do arquivo proxies.txt na raiz do projeto.
    Retorna uma string no formato http://user:pass@ip:port ou None.
    """
    caminho = Path("proxies.txt")
    
    if not caminho.exists():
        _log("⚠️ Arquivo proxies.txt não encontrado na raiz.")
        return None
    
    # Lê as linhas, remove espaços e ignora linhas vazias
    linhas = caminho.read_text(encoding='utf-8').splitlines()
    proxies = [l.strip() for l in linhas if l.strip() and not l.startswith('#')]
    
    if not proxies:
        _log("⚠️ O arquivo proxies.txt está vazio.")
        return None
        
    escolhido = random.choice(proxies)
    return escolhido

def limpar_residuos_proxy():
    """Remove extensões de proxy temporárias de execuções anteriores."""
    proxy_dir = Path("logs/proxy_ext")
    if proxy_dir.exists():
        try:
            shutil.rmtree(proxy_dir)
            _log("🧹 Resíduos de extensões de proxy limpos.")
        except Exception as e:
            _log(f"⚠️ Não foi possível limpar pasta de extensões: {e}")

def formatar_roteiro_limpo(texto_bruto: str) -> str:
    """Limpa lixo da UI do Gemini e força as quebras de linha para evitar colapso no flow.py"""
    crases = chr(96) * 3
    lixos = ["Show thinking Gemini said", "Show thinking", "Gemini said", f"{crases}text", crases, "PROMPT TÉCNICO:"]
    for lixo in lixos:
        texto_bruto = texto_bruto.replace(lixo, "")
    
    match_inicio = re.search(r'\[[Cc]ena\s*1', texto_bruto, re.IGNORECASE)
    if match_inicio:
        texto_bruto = texto_bruto[match_inicio.start():]
        
    texto_bruto = re.sub(r'(\[[Cc]ena\s*\d+)', r'\n\n\1', texto_bruto, flags=re.IGNORECASE)
    texto_bruto = re.sub(r'(\[[Ll]egenda)', r'\n\n\1', texto_bruto, flags=re.IGNORECASE)
    
    texto_bruto = re.sub(r'\n{3,}', '\n\n', texto_bruto)
    return texto_bruto.strip()


def salvar_bloco_unificado(caminho_arquivo: Path, titulo_bloco: str, texto: str) -> None:
    """Salva de forma inteligente num arquivo único. Substitui o bloco se existir, ou anexa no final."""
    conteudo = caminho_arquivo.read_text(encoding='utf-8') if caminho_arquivo.exists() else ""
    marcador = f"=== {titulo_bloco} ==="
    novo_bloco = f"{marcador}\n{texto.strip()}\n\n"
    
    if marcador in conteudo:
        # Usa Regex para casar o marcador até o próximo "===" ou até o fim do arquivo, e substitui.
        padrao = rf"{marcador}.*?(?=\n===|$)"
        texto_final = re.sub(padrao, novo_bloco.strip(), conteudo, flags=re.DOTALL)
    else:
        texto_final = conteudo.strip() + "\n\n" + novo_bloco
        
    caminho_arquivo.write_text(texto_final.strip() + "\n\n", encoding='utf-8')


def extrair_e_salvar_legenda(texto_limpo: str, caminho_legenda_unificada: Path, num_roteiro: int) -> None:
    """Procura a tag da legenda no roteiro gerado e salva no arquivo unificado de legendas."""
    match = re.search(r"\[[Ll]egenda.*?\](.*)", texto_limpo, re.IGNORECASE | re.DOTALL)
    if match:
        texto_legenda = match.group(1).strip()
        marcadores_fim = ["1. EXEMPLO", "DIRETRIZ FINAL", "Confirme brevemente", "SISTEMA CALIBRADO", "[Cena"]
        for marcador in marcadores_fim:
            idx = texto_legenda.upper().find(marcador.upper())
            if idx != -1:
                texto_legenda = texto_legenda[:idx].strip()
                
        salvar_bloco_unificado(caminho_legenda_unificada, f"LEGENDA {num_roteiro}", texto_legenda)
        _log(f'OK: Legenda extraída e salva no arquivo unificado (Legenda {num_roteiro}).', "SISTEMA")


def salvar_ultima_conta_env(email: str) -> None:
    """Atualiza ou insere a variável LAST_ACCOUNT_INDEX no arquivo .env com o EMAIL da conta"""
    try:
        env_path = Path('.env')
        if not env_path.exists():
            env_path.write_text(f"LAST_ACCOUNT_INDEX={email}\n", encoding='utf-8')
            return
        
        lines = env_path.read_text(encoding='utf-8').splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith("LAST_ACCOUNT_INDEX="):
                new_lines.append(f"LAST_ACCOUNT_INDEX={email}")
                found = True
            else:
                new_lines.append(line)
        
        if not found:
            new_lines.append(f"LAST_ACCOUNT_INDEX={email}")
            
        env_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
    except Exception as e:
        _log(f"Aviso: Não foi possível salvar o email da conta no .env: {e}", "SISTEMA")            

def limpar_logs_antigos(horas: int = 12) -> None:
    """Lê o arquivo log_execucao.txt e mantém apenas as linhas das últimas X horas."""
    try:
        log_file = Path("logs") / "log_execucao.txt"
        if not log_file.exists():
            return

        with open(log_file, "r", encoding="utf-8") as f:
            linhas = f.readlines()

        agora = datetime.now()
        from datetime import timedelta # Garantindo que timedelta está disponível
        limite_tempo = agora - timedelta(hours=horas)
        
        linhas_mantidas = []
        mantendo = False 
        
        for linha in linhas:
            match_data = re.search(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', linha)
            
            if match_data:
                try:
                    tempo_linha = datetime.strptime(match_data.group(1), '%Y-%m-%d %H:%M:%S')
                    mantendo = tempo_linha >= limite_tempo
                except ValueError:
                    pass
            
            if mantendo:
                linhas_mantidas.append(linha)

        if len(linhas_mantidas) < len(linhas):
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(linhas_mantidas)

    except Exception:
        pass
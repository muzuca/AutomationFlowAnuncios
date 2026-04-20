# arquivo: integrations/utils.py
import os
import time
import ctypes
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

def _log(msg: str, prefixo: str = "SISTEMA") -> None:
    """
    Logger centralizado. 
    Uso: _log("Iniciando", "GEMINI-IA") -> [15:30:01] [GEMINI-IA] Iniciando
    """
    ts = time.strftime('%H:%M:%S')
    texto = f'[{ts}] [{prefixo}] {msg}'
    print(texto)
    
    # Salva opcionalmente num arquivo de log do dia para conferência
    try:
        log_file = Path("logs_execucao.txt")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
    except: pass

def salvar_print_debug(driver, nome_fase: str):
    """Sua função mestre com a tarja vermelha de URL."""
    load_dotenv(override=True)
    if os.getenv("DISABLE_SCREENSHOTS", "False").lower() == "true":
        return
    try:
        pasta_logs = Path("logs_visao")
        pasta_logs.mkdir(exist_ok=True)
        
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
        driver.save_screenshot(str(pasta_logs / f"{timestamp}_{nome_fase}.png"))
        
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
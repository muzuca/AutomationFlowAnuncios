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
            debugDiv.style = 'position:fixed; top:0; left:20%; width:60%; z-index:999999; background:rgba(255,0,0,0.9); color:white; padding:5px 10px; font-size:14px; font-weight:bold; text-align:center; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; box-shadow: 0px 2px 5px rgba(0,0,0,0.5);';
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
    # 1. Limpeza de lixos de interface
    lixos = ["Show thinking", "Gemini said", "```text", "```", "PROMPT TÉCNICO:"]
    for lixo in lixos:
        texto_bruto = texto_bruto.replace(lixo, "")

    # 2. SEPARAÇÃO DA LEGENDA (Para não poluir o roteiros.txt)
    # Busca a legenda para garantir que ela exista, mas removemos do roteiro técnico
    padrao_legenda = re.compile(r'\[[Ll]egenda\](.*?)$|(?<=fast-paced\.)\s*([^\.\[]*?#.*)$', re.DOTALL | re.IGNORECASE)
    match_legenda = padrao_legenda.search(texto_bruto)
    
    texto_sem_legenda = texto_bruto
    if match_legenda:
        # Remove a legenda do roteiro técnico (o que vai para o Flow)
        texto_sem_legenda = texto_bruto[:match_legenda.start()].strip()

    # 3. FORMATAÇÃO DE LEITURA (Enters entre frases técnicas)
    # Lista de palavras-chave que devem SEMPRE começar em uma nova linha
    quebras = [
        "FIRST FRAME:", "LAST FRAME:", "CAMERA —", "RULES —", 
        "ACTION SEQUENCE —", "NEGATIVE —", "VOICEOVER:", "AUDIO:"
    ]
    
    for marcador in quebras:
        # Substitui o marcador por ele mesmo com dois Enters antes, se não houver
        texto_sem_legenda = re.sub(f'\\s*{re.escape(marcador)}', f'\n{marcador}', texto_sem_legenda)

    # 4. LIMPEZA DE QUEBRAS EXCESSIVAS
    # Garante que as cenas fiquem bem separadas
    texto_sem_legenda = re.sub(r'(\[[Cc]ena\s*\d+)', r'\n\n\1', texto_sem_legenda)
    
    # Remove espaços duplos e garante parágrafos limpos
    linhas = [linha.strip() for linha in texto_sem_legenda.split('\n') if linha.strip()]
    
    return '\n'.join(linhas).strip()

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

def extrair_e_salvar_legenda(texto_roteiro: str, caminho_arquivo: Path, num_roteiro: int) -> bool:
    try:
        legenda_completa = None

        # TENTATIVA PRINCIPAL: bloco [Legenda] gerado pelo Gemini
        match = re.search(
            r'\[[Ll]egenda\]\s*\n(.+?)(?=\n---|\Z)',
            texto_roteiro,
            re.DOTALL
        )
        if match:
            legenda_completa = match.group(1).strip()

        # FALLBACK: só usa VOICEOVERs se [Legenda] não existir
        if not legenda_completa:
            matches = re.findall(r'VOICEOVER:\s*"([^"]+)"', texto_roteiro, re.IGNORECASE)
            if matches:
                legenda_completa = " ".join(m.strip() for m in matches)

        if legenda_completa:
            bloco_salvar = f"=== LEGENDA {num_roteiro} ===\n{legenda_completa}\n\n"
            if caminho_arquivo.exists():
                conteudo_atual = caminho_arquivo.read_text(encoding='utf-8')
                conteudo_atual = re.sub(
                    rf'=== LEGENDA {num_roteiro} ===.*?(?==== LEGENDA|\Z)',
                    '', conteudo_atual, flags=re.DOTALL
                )
                novo_conteudo = conteudo_atual.strip() + "\n\n" + bloco_salvar
                caminho_arquivo.write_text(novo_conteudo.strip(), encoding='utf-8')
            else:
                caminho_arquivo.write_text(bloco_salvar.strip(), encoding='utf-8')

            print(f"[SISTEMA] OK: Legenda {num_roteiro} extraída com sucesso.")
            return True

        print(f"[SISTEMA] ERRO: Legenda {num_roteiro} não encontrada.")
        return False

    except Exception as e:
        print(f"[SISTEMA] ERRO fatal ao extrair legenda: {e}")
        return False

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

def remover_caracteres_nao_bmp(texto: str) -> str:
    """
    Remove emojis e caracteres suplementares (fora do padrão BMP) 
    que causam crash no send_keys do ChromeDriver, mas preserva
    a formatação original do texto (quebras de linha, acentos, etc).
    """
    if not texto:
        return texto
    
    # Esta Regex procura especificamente a faixa alta onde vivem os emojis 
    # e outros caracteres problemáticos para o Selenium, sem tocar no texto normal.
    padrao_emoji = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)
    
    return padrao_emoji.sub('', texto)

def registrar_pid_processo(pid: int):
    """Guarda o ID do Chrome para extermínio futuro."""
    try:
        with open("meus_pids.txt", "a") as f:
            f.write(f"{pid}\n")
    except: pass

def limpar_meus_zumbis():
    """Lê o arquivo de PIDs e mata apenas os processos que este sistema criou."""
    import os
    from pathlib import Path
    arquivo_pids = Path("meus_pids.txt")
    if not arquivo_pids.exists():
        return

    with open(arquivo_pids, "r") as f:
        pids = set(f.read().splitlines()) # Set para evitar duplicados

    for pid in pids:
        if pid.strip():
            try:
                # /T mata a árvore de processos (Chrome + abas)
                os.system(f"taskkill /f /pid {pid} /T >nul 2>&1")
            except: pass
    
    arquivo_pids.unlink(missing_ok=True)

def limpar_cache_python():
    """Remove pastas __pycache__ recursivamente para evitar execução de código fantasma."""
    import shutil
    from pathlib import Path
    
    projeto_raiz = Path(__file__).parent.parent # Ajuste conforme a profundidade do arquivo
    for pycache in projeto_raiz.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache)
            # print(f"🧹 Cache limpo: {pycache}")
        except:
            pass
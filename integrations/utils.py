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
                    rf'=== LEGENDA {num_roteiro} ===.*?(?=\n=== LEGENDA|\Z)',
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

# ==========================================
# 🌐 GUARD DE CONECTIVIDADE (INTERNET)
# ==========================================
def verificar_internet(timeout: int = 5) -> bool:
    """Testa conectividade com um HEAD request rápido ao Google. Retorna True se online."""
    import urllib.request
    try:
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except Exception:
        return False

def aguardar_internet(intervalo: int = 60) -> None:
    """
    Bloqueia a execução até a internet voltar.
    Testa a cada `intervalo` segundos (padrão: 60s).
    Se já estiver online, retorna imediatamente sem logar nada.
    """
    if verificar_internet():
        return  # Já está online, segue sem logar
    
    _log("🌐 INTERNET OFFLINE DETECTADA! Pausando toda execução...", "SISTEMA")
    _log(f"🌐 Retentando conexão a cada {intervalo} segundos. O sistema retomará automaticamente.", "SISTEMA")
    
    tentativa = 0
    while True:
        tentativa += 1
        time.sleep(intervalo)
        
        if verificar_internet():
            _log(f"🌐 ✅ Internet restabelecida após {tentativa} tentativa(s)! Retomando execução...", "SISTEMA")
            # Respiro extra para garantir estabilidade da conexão
            time.sleep(5)
            return
        else:
            _log(f"🌐 Tentativa {tentativa}: Ainda offline. Próxima verificação em {intervalo}s...", "SISTEMA")

# ==========================================
# 📋 METADADOS UNIFICADO
# ==========================================
def anexar_ao_metadados(caminho_metadados: Path, titulo: str, conteudo: str) -> None:
    """Anexa uma seção formatada ao arquivo unificado metadados.txt."""
    from datetime import datetime
    timestamp = datetime.now().strftime('%H:%M:%S')
    separador = "━" * 60
    
    # =========================================================================
    # 🛡️ GUARD ANTI-BOLA-DE-NEVE: Detecta auto-referência do metadados
    # Se o conteúdo contém marcadores internos do próprio metadados, significa
    # que o sistema está tentando gravar o arquivo inteiro como conteúdo de um
    # bloco. Isso causa duplicação exponencial a cada retry.
    # =========================================================================
    _marcadores_internos = ["📦 DADOS DO PRODUTO", "🎯 PROMPT ENVIADO", "💬 RESPOSTA:", "=== PROMPT A ===", "=== PROMPT B ==="]
    if conteudo and any(m in conteudo for m in _marcadores_internos):
        _log(f"🚨 GUARD ANTI-BOLA-DE-NEVE: Conteúdo para '{titulo}' contém marcadores internos do metadados! Gravação BLOQUEADA.", "SISTEMA")
        _log(f"🚨 Tamanho do conteúdo rejeitado: {len(conteudo)} chars (esperado <2000 para um prompt).", "SISTEMA")
        return  # 🛡️ NÃO grava — impede a corrupção em cascata
    
    # --- FORMATAÇÃO PARA LEITURA HUMANA ---
    texto = conteudo.strip()
    
    # 1. Quebra de linha antes de cada [Cena X]
    texto = re.sub(r'(?<!\n)\s*(\[[Cc]ena\s*\d+\])', r'\n\n\1', texto)
    
    # 2. Quebra de linha antes de === VARIANTE X ===
    texto = re.sub(r'(?<!\n)\s*(===\s*VARIANTE\s*\d+\s*===)', r'\n\n\1', texto)
    
    # 3. Remove blocos [Legenda] (já salvos separadamente como === LEGENDA ===)
    texto = re.sub(r'\[Ll?egenda\]\s*.*?(?=\n===|\n\n|$)', '', texto, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Limpa linhas em branco excessivas (máx 2 consecutivas)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    
    bloco = f"\n\n{separador}\n{titulo} [{timestamp}]\n{separador}\n\n{texto.strip()}\n"
    
    caminho_metadados.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho_metadados, 'a', encoding='utf-8') as f:
        f.write(bloco)

def formatar_dados_produto(dados_ia: dict) -> str:
    """Formata os dados do produto para a seção inicial do metadados.txt (bonito + machine-readable)."""
    import ast
    
    nome = dados_ia.get('nome_produto', 'Não lido')
    resumido = dados_ia.get('nome_resumido', 'ProdutoGenerico')
    preco = dados_ia.get('preco_condicoes', 'Não lido')
    beneficios_raw = dados_ia.get('beneficios', 'Não lido')
    
    # Formata benefícios como lista visual
    beneficios_lista = []
    if isinstance(beneficios_raw, list):
        beneficios_lista = beneficios_raw
    elif isinstance(beneficios_raw, str):
        try:
            parsed = ast.literal_eval(beneficios_raw)
            if isinstance(parsed, list):
                beneficios_lista = parsed
        except:
            beneficios_lista = [beneficios_raw]
    
    beneficios_fmt = "\n".join(f"    • {b}" for b in beneficios_lista) if beneficios_lista else f"    • {beneficios_raw}"
    beneficios_inline = " | ".join(beneficios_lista) if beneficios_lista else str(beneficios_raw)
    
    separador = "━" * 60
    header = "═" * 58
    
    return f"""{separador}
📦 DADOS DO PRODUTO
{separador}
NOME_REAL: {nome}
NOME_RESUMIDO: {resumido}
PRECO_E_CONDICOES: {preco}
BENEFICIOS_EXTRAS: {beneficios_inline}

  Benefícios detalhados:
{beneficios_fmt}
"""


def consolidar_metadados_final(pasta_task: Path) -> None:
    """
    Consolida os 4 arquivos separados em um único metadados.txt para entrega.
    
    Ordem final:
      1. 📦 DADOS DO PRODUTO        (de metadados.txt)
      2. 📝 LEGENDAS                 (de legendas.txt)
      3. 🎬 ROTEIROS                 (Diretor de Arte [PROMPT A/B] + Roteiros técnicos [de roteiros.txt])
      4. 📋 PROMPTS E RESPOSTAS      (log completo de prompts.txt)
    """
    separador = "━" * 60
    partes = []
    
    # =====================================================================
    # 1. 📦 DADOS DO PRODUTO
    # =====================================================================
    meta_path = pasta_task / "metadados.txt"
    if meta_path.exists():
        produto = meta_path.read_text(encoding='utf-8').strip()
        # Se já tem o separador/header, usa como está
        if "DADOS DO PRODUTO" in produto:
            partes.append(produto)
        else:
            partes.append(f"{separador}\n📦 DADOS DO PRODUTO\n{separador}\n\n{produto}")
    
    # =====================================================================
    # 2. 📝 LEGENDAS
    # =====================================================================
    legendas_path = pasta_task / "legendas.txt"
    if legendas_path.exists():
        legendas = legendas_path.read_text(encoding='utf-8').strip()
        if legendas:
            partes.append(f"\n\n{separador}\n📝 LEGENDAS\n{separador}\n\n{legendas}")
    
    # =====================================================================
    # 3. 🎬 ROTEIROS (Resultados do Diretor de Arte + Roteiros técnicos)
    # =====================================================================
    secao_roteiros = []
    
    # 3a. Diretor de Arte: PROMPT A / PROMPT B (resultados — os prompts de imagem)
    prompts_path = pasta_task / "prompts.txt"
    if prompts_path.exists():
        prompts_conteudo = prompts_path.read_text(encoding='utf-8')
        
        # Extrai PROMPT A e PROMPT B
        for marcador in ["PROMPT A", "PROMPT B"]:
            tag = f"=== {marcador} ==="
            if tag in prompts_conteudo:
                bloco = prompts_conteudo.split(tag)[1]
                # Corta no próximo ===
                if "\n===" in bloco:
                    bloco = bloco.split("\n===")[0]
                # Corta no próximo separador ━━━
                if "━━━" in bloco:
                    bloco = bloco.split("━━━")[0]
                bloco = bloco.strip()
                if bloco:
                    secao_roteiros.append(f"=== {marcador} ===\n{bloco}")
    
    # 3b. Roteiros técnicos de vídeo (ROTEIRO X_VARIANTE_Y)
    roteiros_path = pasta_task / "roteiros.txt"
    if roteiros_path.exists():
        roteiros = roteiros_path.read_text(encoding='utf-8').strip()
        if roteiros:
            secao_roteiros.append(roteiros)
    
    if secao_roteiros:
        partes.append(f"\n\n{separador}\n🎬 ROTEIROS\n{separador}\n\n" + "\n\n".join(secao_roteiros))
    
    # =====================================================================
    # 4. 📋 PROMPTS E RESPOSTAS (log cronológico completo)
    # =====================================================================
    if prompts_path.exists():
        prompts_conteudo = prompts_path.read_text(encoding='utf-8').strip()
        
        # Remove os blocos === PROMPT A/B === que já foram para a seção 3
        prompts_log = prompts_conteudo
        for tag in ["=== PROMPT A ===", "=== PROMPT B ==="]:
            if tag in prompts_log:
                antes = prompts_log.split(tag)[0]
                depois_parts = prompts_log.split(tag)[1:]
                resto = ""
                for p in depois_parts:
                    # Pega tudo depois do próximo === ou ━━━
                    if "\n===" in p:
                        resto += "\n===" + p.split("\n===", 1)[1]
                    elif "━━━" in p:
                        resto += "━━━" + p.split("━━━", 1)[1]
                prompts_log = antes + resto
        
        prompts_log = re.sub(r'\n{4,}', '\n\n\n', prompts_log).strip()
        
        if prompts_log:
            partes.append(f"\n\n{separador}\n📋 LOG DE PROMPTS E RESPOSTAS\n{separador}\n\n{prompts_log}")
    
    # =====================================================================
    # GRAVA O ARQUIVO CONSOLIDADO
    # =====================================================================
    texto_final = "\n".join(partes).strip()
    texto_final = re.sub(r'\n{4,}', '\n\n\n', texto_final)
    
    meta_path.write_text(texto_final + "\n", encoding='utf-8')
    _log(f"✅ Metadados consolidado para entrega: {meta_path.name} ({len(texto_final)} chars)")


def entregar_e_limpar_tarefa(pasta_origem: Path, pasta_entrega: Path) -> None:
    """
    Consolida metadados, copia arquivos finais para entrega e limpa a origem.
    - Pasta ID "1" permanece vazia
    - Pastas com ID > 1 são completamente removidas
    """
    import shutil
    
    # 📋 Consolida os 4 arquivos em um único metadados.txt organizado
    try:
        consolidar_metadados_final(pasta_origem)
    except Exception as e_cons:
        log_error(f"⚠️ Erro ao consolidar metadados (não-fatal): {e_cons}")
    
    _log(f"🏆 Concluído! Movendo todos os arquivos gerados para: {pasta_entrega.name}")
    pasta_entrega.mkdir(parents=True, exist_ok=True)
    
    # Copia arquivos finais para entrega (exceto arquivos de trabalho)
    _arquivos_trabalho = {"roteiros.txt", "legendas.txt", "prompts.txt"}
    
    for item_final in pasta_origem.iterdir():
        if item_final.is_file():
            if item_final.name not in _arquivos_trabalho:
                shutil.copy2(str(item_final), str(pasta_entrega / item_final.name))
            # Remove TODOS os arquivos (incluindo os de trabalho)
            item_final.unlink(missing_ok=True)
    
    # 🧹 LIMPEZA DE DIRETÓRIO: ID "1" permanece vazio, demais são removidos
    id_pasta = pasta_origem.name
    if id_pasta != "1":
        try:
            shutil.rmtree(str(pasta_origem), ignore_errors=True)
            log_success(f'TAREFA CONCLUÍDA! Diretório {id_pasta} removido (entrega em {pasta_entrega.name})')
        except Exception as e_rm:
            log_error(f"⚠️ Não conseguiu remover pasta {id_pasta}: {e_rm}")
    else:
        log_success(f'TAREFA CONCLUÍDA! Diretório 1 esvaziado (entrega em {pasta_entrega.name})')


def carregar_checkpoint_roteiro(
    pasta_task: Path, r_idx: int, 
    caminho_roteiros: Path, caminho_metadados: Path
) -> dict:
    """
    Verifica se um roteiro já existe nos arquivos e carrega as variantes.
    
    Retorna dict com:
      - 'encontrado': bool
      - 'roteiro_1': str (texto da variante 1)
      - 'roteiro_2': str (texto da variante 2)
      - 'fonte': str (nome do arquivo fonte)
    """
    resultado = {'encontrado': False, 'roteiro_1': '', 'roteiro_2': '', 'fonte': ''}
    
    # Prioridade: roteiros.txt > metadados.txt (legado)
    _arquivo_roteiro_fonte = None
    if caminho_roteiros.exists():
        _arquivo_roteiro_fonte = caminho_roteiros
    elif caminho_metadados.exists():
        conteudo_check = caminho_metadados.read_text(encoding='utf-8')
        if f"=== ROTEIRO {r_idx}_VARIANTE_1 ===" in conteudo_check:
            _arquivo_roteiro_fonte = caminho_metadados
    
    if not _arquivo_roteiro_fonte:
        return resultado
    
    conteudo_total = _arquivo_roteiro_fonte.read_text(encoding='utf-8')
    marcador_roteiro = f"=== ROTEIRO {r_idx}_VARIANTE_1 ==="
    
    if marcador_roteiro not in conteudo_total:
        return resultado
    
    bloco = conteudo_total.split(marcador_roteiro)[1]
    bloco = bloco.split("\n===")[0] if "\n===" in bloco else bloco
    
    if len(bloco.strip()) < 500 or not re.search(r'\[[Cc]ena\s*1', bloco):
        log_error(f'⚠️ Roteiro {r_idx} pequeno ou sem cenas válidas. Regerando...')
        return resultado
    
    log_success(f'🚀 CHECKPOINT ROTEIRO ALCANÇADO: Roteiro {r_idx} já existe em {_arquivo_roteiro_fonte.name}.')
    
    roteiro_1 = bloco.strip()
    
    # Busca variante 2
    marcador_v2 = f"=== ROTEIRO {r_idx}_VARIANTE_2 ==="
    if marcador_v2 in conteudo_total:
        bloco_v2 = conteudo_total.split(marcador_v2)[1]
        bloco_v2 = bloco_v2.split("\n===")[0] if "\n===" in bloco_v2 else bloco_v2
        roteiro_2 = bloco_v2.strip()
    else:
        roteiro_2 = roteiro_1
    
    resultado['encontrado'] = True
    resultado['roteiro_1'] = roteiro_1
    resultado['roteiro_2'] = roteiro_2
    resultado['fonte'] = _arquivo_roteiro_fonte.name
    return resultado


def validar_e_limpar_cenas(
    cenas: list[str], qtd_esperada: int, 
    caminho_roteiros: Path, roteiro_fallback: str = ""
) -> list[str]:
    """
    Limpa marcadores vazados, valida qualidade do voiceover e quantidade de cenas.
    Levanta Exception se o roteiro estiver corrompido.
    
    Retorna lista de cenas limpas.
    """
    if not cenas:
        # Fallback dinâmico
        if roteiro_fallback:
            cenas = [c.strip() for c in re.split(r'\[Cena\s*\d+[^\]]*\]', roteiro_fallback) if len(c.strip()) > 10][:qtd_esperada]
        
        if not cenas:
            log_error("O arquivo roteiros.txt não retornou cenas válidas! Deletando lixo do Gemini...")
            caminho_roteiros.unlink(missing_ok=True)
            raise Exception("Lista de cenas vazia. O arquivo de roteiro era inválido.")
    
    # 🛡️ Limpeza de marcadores vazados
    cenas = [re.sub(r'===\s*VARIANTE\s*\d+\s*===', '', c).strip() for c in cenas]
    cenas = [re.sub(r'===\s*ROTEIRO\s*\d+[^=]*===', '', c).strip() for c in cenas]
    cenas = [c for c in cenas if len(c) > 10]
    
    # 🛡️ Validação de qualidade do voiceover (texto grudado)
    for _ci, _cena_txt in enumerate(cenas):
        _match_vo = re.search(r':\s*"([^"]{30,})"', _cena_txt)
        if _match_vo:
            _vo_text = _match_vo.group(1)
            _palavras = _vo_text.split()
            _palavras_grudadas = [p for p in _palavras if len(p) > 40]
            if _palavras_grudadas:
                log_error(f"🚨 GUARD VOICEOVER: Cena {_ci+1} tem texto GRUDADO: '{_palavras_grudadas[0][:50]}...'")
                log_error("🚨 Deletando roteiro corrompido e forçando regeneração...")
                caminho_roteiros.unlink(missing_ok=True)
                raise Exception(f"Voiceover da Cena {_ci+1} corrompido pelo Gemini (texto sem espaços). Regerando roteiro.")
    
    # 🛡️ Validação de quantidade
    if len(cenas) < qtd_esperada:
        log_error(f"❌ O roteiro retornou apenas {len(cenas)} cena(s), mas esperava {qtd_esperada}!")
        caminho_roteiros.unlink(missing_ok=True)
        raise Exception(f"Lista de cenas incompleta ({len(cenas)}/{qtd_esperada}).")
    
    return cenas

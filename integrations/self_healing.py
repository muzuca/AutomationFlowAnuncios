# arquivo: integrations/self_healing.py
# descricao: Motor de Self-Healing ULTRA RÁPIDO com cache em memória,
# caça universal de elementos, menus complexos e clique inteligente.
# Filosofia: BALA na primeira execução normal, MÉDICO só quando quebra.

import json
import time
import re
import threading
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from integrations.utils import _log as log_base, salvar_print_debug, js_click

ARQUIVO_MEMORIA = Path(__file__).parent.parent / "logs" / "memoria_seletores.json"
LOGS_EMITIDOS = set()

# 🛡️ BLOCKLIST: Tags e IDs que NUNCA devem ser aprendidos/retornados como elementos válidos
_TAGS_BLOQUEADAS = {'html', 'body', 'head', 'script', 'style', 'noscript'}
_IDS_BLOQUEADOS = {'__next', 'root', 'app', '__nuxt', 'gatsby-focus-wrapper'}
_CLASSES_BLOQUEADAS = {'conversation-title', 'sidebar', 'nav-drawer', 'nav-rail', 'side-panel'}

def _elemento_eh_container_raiz(el) -> bool:
    """Retorna True se o elemento é um container raiz ou sidebar (falso positivo)."""
    try:
        tag = el.tag_name.lower()
        if tag in _TAGS_BLOQUEADAS:
            return True
        el_id = el.get_attribute('id') or ''
        if el_id.lower() in _IDS_BLOQUEADOS:
            return True
        # Sidebar/navigation elements
        classes = (el.get_attribute('class') or '').lower()
        if any(c in classes for c in _CLASSES_BLOQUEADAS):
            return True
        # Container muito grande = provavelmente raiz da página
        size = el.size
        if size and size.get('width', 0) > 800 and size.get('height', 0) > 600:
            return True
    except:
        pass
    return False

# ==========================================
# 🧠 CACHE EM MEMÓRIA (SINGLETON ULTRA RÁPIDO)
# ==========================================
_cache_memoria: dict = {}
_cache_mtime: float = 0.0
_cache_lock = threading.Lock()

def _log(msg: str):
    log_base(msg, prefixo="HEALER")

def _carregar_cache_se_necessario():
    """Carrega o JSON apenas se o arquivo mudou desde a última leitura."""
    global _cache_memoria, _cache_mtime
    try:
        if not ARQUIVO_MEMORIA.exists():
            return
        mtime_atual = ARQUIVO_MEMORIA.stat().st_mtime
        if mtime_atual != _cache_mtime:
            with _cache_lock:
                if mtime_atual != _cache_mtime:
                    with open(ARQUIVO_MEMORIA, 'r', encoding='utf-8') as f:
                        _cache_memoria = json.load(f)
                    _cache_mtime = mtime_atual
    except Exception:
        pass

def _get_cache() -> dict:
    _carregar_cache_se_necessario()
    return _cache_memoria

# ==========================================
# VALIDAÇÃO DE PRONTIDÃO (O FILTRO BRUTO)
# ==========================================
def elemento_esta_realmente_pronto(elemento: WebElement) -> bool:
    """Verifica se o elemento está visível, habilitado e pronto para clique/interação."""
    try:
        return (elemento.is_displayed() and 
                elemento.is_enabled() and 
                elemento.get_attribute("disabled") is None)
    except:
        return False
    
# ==========================================
# GERENCIAMENTO DE MEMÓRIA (CONTEXTUALIZADO)
# ==========================================
def carregar_memoria():
    return dict(_get_cache())

def salvar_na_memoria(chave_elemento: str, seletor_css: str, etapa: str = "global"):
    """Salva o seletor isolando por etapa. Atualiza cache em memória E disco."""
    global _cache_memoria, _cache_mtime
    
    memoria = dict(_get_cache())
    
    if etapa not in memoria:
        memoria[etapa] = {}
    if chave_elemento not in memoria[etapa]:
        memoria[etapa][chave_elemento] = []
    
    # Se o seletor já é o primeiro, ignora (performance)
    if memoria[etapa][chave_elemento] and memoria[etapa][chave_elemento][0] == seletor_css:
        return

    if seletor_css in memoria[etapa][chave_elemento]:
        memoria[etapa][chave_elemento].remove(seletor_css)
    
    memoria[etapa][chave_elemento].insert(0, seletor_css)
    memoria[etapa][chave_elemento] = memoria[etapa][chave_elemento][:5]

    # Salva em disco e atualiza cache atomicamente
    with _cache_lock:
        ARQUIVO_MEMORIA.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQUIVO_MEMORIA, 'w', encoding='utf-8') as f:
            json.dump(memoria, f, indent=4)
        _cache_memoria = memoria
        _cache_mtime = ARQUIVO_MEMORIA.stat().st_mtime
    
    _log(f"💾 [{etapa}] Memória atualizada para '{chave_elemento}': {seletor_css}")

def limpar_memoria_chave(chave_elemento: str, etapa: str = "global"):
    """Remove uma chave específica da memória (usado quando o médico precisa resetar)."""
    global _cache_memoria, _cache_mtime
    memoria = dict(_get_cache())
    if etapa in memoria and chave_elemento in memoria[etapa]:
        del memoria[etapa][chave_elemento]
        with _cache_lock:
            with open(ARQUIVO_MEMORIA, 'w', encoding='utf-8') as f:
                json.dump(memoria, f, indent=4)
            _cache_memoria = memoria
            _cache_mtime = ARQUIVO_MEMORIA.stat().st_mtime
        _log(f"🗑️ [{etapa}] Memória limpa para '{chave_elemento}'")

# ==========================================
# APRENDIZAGEM AUTOMÁTICA DE SELETORES
# ==========================================
def _aprender_seletor(elemento: WebElement, chave_memoria: str, etapa: str):
    """Gera e salva um seletor CSS blindado a partir de um elemento encontrado."""
    try:
        # 🛡️ NUNCA aprende containers raiz (causa falsos positivos catastróficos)
        if _elemento_eh_container_raiz(elemento):
            return
        
        tag = elemento.tag_name
        data_test = elemento.get_attribute("data-test-id")
        jsname = elemento.get_attribute("jsname")
        aria = elemento.get_attribute("aria-label")
        el_id = elemento.get_attribute("id")
        
        if data_test:
            novo_css = f"{tag}[data-test-id='{data_test}']"
        elif jsname:
            novo_css = f"{tag}[jsname='{jsname}']"
        elif el_id and el_id.lower() not in _IDS_BLOQUEADOS and not re.search(r'\d', el_id):
            novo_css = f"{tag}#{el_id}"
        elif aria:
            aria_escapado = aria.replace("'", "\\'")
            novo_css = f"{tag}[aria-label='{aria_escapado}']"
        else:
            classes = elemento.get_attribute("class")
            classe_limpa = ".".join([c for c in classes.split() if c]) if classes else ""
            if classe_limpa:
                novo_css = f"{tag}.{classe_limpa}"
            else:
                # 🛡️ BLINDAGEM ANTI-VENENO: Seletores genéricos demais (ex: "span", "div", "button")
                # são CATASTRÓFICOS porque batem no primeiro elemento da página.
                # Tenta usar o role ou textContent como âncora. Se não tiver nada, DESISTE.
                role = elemento.get_attribute("role")
                text = (elemento.text or "").strip()
                if role:
                    novo_css = f"{tag}[role='{role}']"
                elif text and len(text) < 20:
                    # Não cacheia — texto é volátil demais para um seletor CSS puro.
                    # Simplesmente não salva na memória.
                    return
                else:
                    # Tag sem NENHUM atributo distinguível. Salvar "span" seria veneno.
                    return

        salvar_na_memoria(chave_memoria, novo_css, etapa)
    except:
        pass

# ==========================================
# O CAÇADOR UNIVERSAL (CONTEXTUAL SNIPER)
# ==========================================
def cacar_elemento_universal(
    driver, 
    chave_memoria: str, 
    descricao_para_ia: str, 
    seletores_rapidos: list, 
    palavras_semanticas: list, 
    permitir_autocura: bool = False,
    driver_acessibilidade=None, 
    url_gemini=None,
    etapa: str = "global"
) -> WebElement | None:
    
    # 1. 🚀 TENTA A MEMÓRIA (PRIORIDADE ABSOLUTA - MODO BALA)
    memoria = _get_cache()
    contextos_de_busca = [etapa, "global"] if etapa != "global" else ["global"]
    
    for ctx in contextos_de_busca:
        lista_seletores = memoria.get(ctx, {}).get(chave_memoria, [])
        for css in lista_seletores:
            try:
                elemento = driver.find_element(By.CSS_SELECTOR, css)
                if elemento.is_displayed() and elemento.is_enabled():
                    return elemento  # ⚡ BALA! Cache hit instantâneo
            except:
                continue

    # 2. ⚡ TENTA OS SELETORES RÁPIDOS (XPath ou CSS)
    for seletor in seletores_rapidos:
        try:
            if seletor.startswith('//') or seletor.startswith('(//'):
                botoes = driver.find_elements(By.XPATH, seletor)
            else:
                botoes = driver.find_elements(By.CSS_SELECTOR, seletor)
            
            for b in botoes:
                if b.is_displayed() and b.is_enabled():
                    _aprender_seletor(b, chave_memoria, etapa)
                    return b
        except:
            pass

    # 3. 🧠 BUSCA SEMÂNTICA VIA JS (1 round-trip ao browser = ~50ms vs ~5s do Python)
    log_key = f"{etapa}_{chave_memoria}"
    if log_key not in LOGS_EMITIDOS:
        _log(f"🔍 [{etapa}] '{chave_memoria}' não encontrado na memória. Buscando semântica...")
        LOGS_EMITIDOS.add(log_key)

    if palavras_semanticas:
        try:
            # JavaScript que faz TODA a busca semântica em 1 chamada
            js_script = """
                var keywords = arguments[0];
                var blockedTags = ['html','body','head','script','style','noscript'];
                var blockedIds = ['__next','root','app','__nuxt'];
                var blockedClasses = ['conversation-title','sidebar','nav-drawer','nav-rail','side-panel'];
                var tags = ['button','a','span','div'];
                
                for (var t = 0; t < tags.length; t++) {
                    var els = document.getElementsByTagName(tags[t]);
                    for (var i = els.length - 1; i >= 0; i--) {
                        var el = els[i];
                        try {
                            // Pula invisíveis
                            if (el.offsetParent === null && el.style.display !== 'fixed') continue;
                            // Pula tags bloqueadas
                            if (blockedTags.indexOf(el.tagName.toLowerCase()) >= 0) continue;
                            // Pula IDs bloqueados
                            if (el.id && blockedIds.indexOf(el.id.toLowerCase()) >= 0) continue;
                            // Pula classes bloqueadas
                            var cls = (el.className || '').toLowerCase();
                            var blocked = false;
                            for (var bc = 0; bc < blockedClasses.length; bc++) {
                                if (cls.indexOf(blockedClasses[bc]) >= 0) { blocked = true; break; }
                            }
                            if (blocked) continue;
                            // Pula containers gigantes (> 800x600)
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 800 && rect.height > 600) continue;
                            
                            // Verifica conteúdo
                            var content = ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || '')).toLowerCase();
                            for (var k = 0; k < keywords.length; k++) {
                                if (content.indexOf(keywords[k].toLowerCase()) >= 0) {
                                    return el;
                                }
                            }
                        } catch(e) { continue; }
                    }
                }
                return null;
            """
            el = driver.execute_script(js_script, palavras_semanticas)
            if el:
                _aprender_seletor(el, chave_memoria, etapa)
                return el
        except: pass

    # 4. 🚑 ÚLTIMO RECURSO: AUTOCURA VIA IA
    if permitir_autocura and driver_acessibilidade and url_gemini:
        _log(f"🚨 Hunter cego em [{etapa}] para '{chave_memoria}'. ACIONANDO UNIDADE MÉDICA...")
        
        try:
            elemento_curado, seletor_curado = pedir_socorro_ao_gemini(
                driver, driver_acessibilidade, url_gemini, descricao_para_ia,
                seletores_tentados=seletores_rapidos, etapa=etapa
            )
        except Exception:
            elemento_curado, seletor_curado = None, None
        
        if elemento_curado:
            _log(f"✅ AUTOCURA BEM SUCEDIDA EM [{etapa}]!")
            if seletor_curado:
                salvar_na_memoria(chave_memoria, seletor_curado, etapa)
            return elemento_curado
    
    return None

# ==========================================
# 🚑 MÓDULO MÉDICO: IA AUTÔNOMA VIA GEMINI
# ==========================================

def _enviar_mensagem_gemini_acessibilidade(driver_acessibilidade, url_gemini, screenshot_path: Path, prompt_texto: str, timeout: int = 60) -> str | None:
    """
    Motor interno do Médico: Usa o browser de acessibilidade para conversar com o Gemini.
    1. Abre novo chat no Gemini
    2. Anexa o screenshot
    3. Envia o prompt
    4. Aguarda e retorna a resposta
    """
    try:
        # 1. Navega para o Gemini
        if url_gemini not in (driver_acessibilidade.current_url or ''):
            driver_acessibilidade.get(url_gemini)
            time.sleep(4)
        
        # 2. Tenta abrir novo chat (para não poluir o anterior)
        try:
            btn_novo = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 
                'side-nav-action-button[data-test-id="new-chat-button"] a, '
                'a.side-nav-action-collapsed-button[href="/app"], '
                'span[data-test-id="new-chat-button"]'
            )
            for b in btn_novo:
                if b.is_displayed():
                    js_click(driver_acessibilidade, b)
                    time.sleep(2)
                    break
        except: pass
        
        # 3. Anexa o screenshot
        try:
            # Abre menu de upload se necessário
            btn_upload = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 
                'button[aria-controls="upload-file-menu"], '
                'button[aria-label*="upload" i], '
                'button[aria-label*="anexar" i], '
                'button[aria-label*="Fazer upload" i]'
            )
            for b in btn_upload:
                if b.is_displayed():
                    js_click(driver_acessibilidade, b)
                    time.sleep(1)
                    break
            
            # Aceita popup de política se aparecer
            try:
                btn_agree = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 'button[data-test-id="upload-image-agree-button"]')
                if btn_agree and btn_agree[0].is_displayed():
                    js_click(driver_acessibilidade, btn_agree[0])
                    time.sleep(1)
            except: pass
            
            # Encontra o input file e injeta o screenshot
            inputs = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if inputs:
                input_file = inputs[-1]
                driver_acessibilidade.execute_script(
                    "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                    input_file
                )
                input_file.send_keys(str(screenshot_path.resolve()))
                _log("📸 Screenshot enviado ao Gemini Médico.")
                salvar_print_debug(driver_acessibilidade, "MEDICO_SCREENSHOT_ENVIADO")
                time.sleep(3)
            
            # Fecha menu de upload
            ActionChains(driver_acessibilidade).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
        except Exception as e:
            _log(f"⚠️ Médico: Falha ao anexar screenshot: {str(e)[:60]}")
        
        # 4. Digita o prompt na caixa de texto
        seletores_textarea = [
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'textarea'
        ]
        textarea = None
        for sel in seletores_textarea:
            els = driver_acessibilidade.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    textarea = el
                    break
            if textarea: break
        
        if not textarea:
            _log("❌ Médico: Caixa de texto do Gemini não encontrada.")
            return None
        
        # Limpa emojis para evitar erros de encoding
        prompt_seguro = re.sub(r'[^\u0000-\uFFFF]', '', prompt_texto)
        
        textarea.click()
        time.sleep(0.3)
        driver_acessibilidade.execute_script(
            "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
            textarea, prompt_seguro
        )
        textarea.send_keys(" ")
        time.sleep(1)
        
        # 5. Clica em enviar
        btn_send = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 
            'button[aria-label="Send message"], '
            '.send-button-container button, '
            'button[data-test-id="send-button"]'
        )
        enviou = False
        for b in btn_send:
            if b.is_displayed() and b.get_attribute('disabled') is None:
                js_click(driver_acessibilidade, b)
                enviou = True
                break
        
        if not enviou:
            textarea.send_keys(Keys.ENTER)
        
        _log("📤 Prompt enviado ao Gemini Médico. Aguardando resposta...")
        salvar_print_debug(driver_acessibilidade, "MEDICO_PROMPT_ENVIADO")
        
        # ⚡ POLL RÁPIDO: Espera Stop aparecer (em vez de sleep(5) cego)
        deadline_stop = time.time() + 5.0
        while time.time() < deadline_stop:
            try:
                stops = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 'button[aria-label*="Stop" i]')
                if any(s.is_displayed() for s in stops):
                    break
            except: pass
            time.sleep(0.3)
        fim_espera = time.time() + timeout
        
        while time.time() < fim_espera:
            stops = driver_acessibilidade.find_elements(By.CSS_SELECTOR, 
                'button.stop, button[aria-label*="Stop" i]'
            )
            if not stops or not any(s.is_displayed() for s in stops):
                # Verifica se mic/send voltou (interface ociosa)
                ociosos = driver_acessibilidade.find_elements(By.CSS_SELECTOR,
                    'button.speech_dictation_mic_button, button[aria-label*="Send" i]'
                )
                if ociosos and any(o.is_displayed() for o in ociosos):
                    break
            time.sleep(1)
        
        time.sleep(2)
        
        # 7. Extrai o texto da resposta
        seletores_resp = [
            'model-response .model-response-text',
            'model-response message-content',
            'model-response'
        ]
        for sel in seletores_resp:
            els = driver_acessibilidade.find_elements(By.CSS_SELECTOR, sel)
            if els:
                txt = driver_acessibilidade.execute_script(
                    "return arguments[0].textContent || arguments[0].innerText || '';",
                    els[-1]
                )
                if txt and len(txt.strip()) > 5:
                    _log(f"✅ Médico respondeu ({len(txt)} chars)")
                    salvar_print_debug(driver_acessibilidade, "MEDICO_RESPOSTA_RECEBIDA")
                    return txt.strip()
        
        _log("❌ Médico: Resposta vazia ou não capturada.")
        return None
        
    except Exception as e:
        _log(f"❌ Médico: Erro fatal na comunicação: {str(e)[:80]}")
        return None


# ==========================================
# 🧠 EXTRAÇÃO DE CONTEXTO DOM INTELIGENTE
# ==========================================

def _extrair_contexto_dom(driver) -> str:
    """Extrai representação comprimida dos elementos interativos visíveis na tela."""
    js_extrator = """
    var sels = 'button, a[href], input, select, [role="button"], [role="menuitem"], [role="tab"], [role="option"], img[alt], [aria-label], i.material-icons, i.google-symbols';
    var els = document.querySelectorAll(sels);
    var result = [];
    for (var i = 0; i < els.length && result.length < 50; i++) {
        var el = els[i];
        try {
            var style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            if (el.offsetParent === null && style.position !== 'fixed' && el.type !== 'file') continue;
            var rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0 && el.type !== 'file') continue;
        } catch(e) { continue; }
        var tag = el.tagName.toLowerCase();
        var parts = [tag];
        var al = ['id','class','aria-label','role','type','data-test-id','data-tile-id','disabled','alt','aria-expanded','data-state'];
        for (var a = 0; a < al.length; a++) {
            var v = el.getAttribute(al[a]);
            if (v && v.length > 0) {
                v = v.length > 60 ? v.substring(0, 60) + '...' : v;
                parts.push(al[a] + '="' + v.replace(/"/g, "'") + '"');
            }
        }
        var text = (el.innerText || '').trim();
        if (text.length > 50) text = text.substring(0, 50) + '...';
        var icon = '';
        try {
            var iTag = el.querySelector('i, mat-icon, .material-icons, .google-symbols');
            if (iTag) icon = '[icon:' + (iTag.textContent || '').trim() + ']';
        } catch(e) {}
        result.push('<' + parts.join(' ') + '>' + icon + text + '</' + tag + '>');
    }
    return result.join('\\n');
    """
    try:
        html = driver.execute_script(js_extrator) or ""
        return html[:4000]
    except Exception as e:
        return f"(erro ao extrair: {str(e)[:50]})"


def _parsear_seletores_medico(resposta: str) -> list:
    """Parseia a resposta do Gemini em lista de seletores testáveis [{tipo, valor}]."""
    seletores = []
    if not resposta:
        return seletores
    
    for linha in resposta.split('\n'):
        linha = linha.strip()
        if not linha or len(linha) < 3:
            continue
        # Remove markdown backticks e numeração
        linha = re.sub(r'^[\d\.\)\-\*\s`]+', '', linha).strip()
        linha = re.sub(r'`+$', '', linha).strip()
        if not linha:
            continue
        
        upper = linha.upper()
        if upper.startswith('CSS:'):
            val = linha[4:].strip().strip('`')
            if val: seletores.append({"tipo": "css", "valor": val})
        elif upper.startswith('XPATH:'):
            val = linha[6:].strip().strip('`')
            if val: seletores.append({"tipo": "xpath", "valor": val})
        elif upper.startswith('JS:'):
            val = linha[3:].strip().strip('`')
            if val: seletores.append({"tipo": "js", "valor": val})
        elif linha.startswith('//') or linha.startswith('(//'):
            seletores.append({"tipo": "xpath", "valor": linha})
        elif linha.startswith('document.'):
            seletores.append({"tipo": "js", "valor": linha})
        elif not linha.startswith('http') and len(linha) > 5 and any(c in linha for c in ['[', '.', '#', '>']):
            seletores.append({"tipo": "css", "valor": linha})
    
    return seletores


def _testar_seletor(driver, sel: dict):
    """Testa um seletor retornado pelo Médico. Retorna o WebElement ou None."""
    tipo = sel.get("tipo", "css")
    valor = sel.get("valor", "")
    if not valor or len(valor) < 3:
        return None
    try:
        if tipo == "css":
            for parte in valor.split(','):
                parte = parte.strip()
                if not parte: continue
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, parte)
                    for el in els:
                        if el.is_displayed() and not _elemento_eh_container_raiz(el):
                            return el
                except: continue
        elif tipo == "xpath":
            els = driver.find_elements(By.XPATH, valor)
            for el in els:
                if el.is_displayed() and not _elemento_eh_container_raiz(el):
                    return el
        elif tipo == "js":
            codigo = valor.strip()
            if not codigo.startswith('return'):
                codigo = f"return {codigo}"
            el = driver.execute_script(codigo)
            if el and hasattr(el, 'is_displayed') and el.is_displayed():
                return el
    except:
        pass
    return None


# ==========================================
# 🚑 MÉDICO ULTRA-INTELIGENTE v2.0
# ==========================================

def pedir_socorro_ao_gemini(driver, driver_acessibilidade, url_gemini, descricao_para_ia,
                            seletores_tentados: list = None, etapa: str = ""):
    """
    🧠 MÉDICO ULTRA-INTELIGENTE v2.0
    
    Envia screenshot + HTML do DOM + contexto completo ao Gemini.
    Pede múltiplos seletores (CSS + XPath + JS), testa cada um.
    Se nenhum funcionar, faz um SEGUNDO ROUND com feedback.
    
    Retorna: (WebElement, seletor_str) ou (None, None)
    """
    _log(f"🚑 Pedindo socorro ao Gemini para: {descricao_para_ia[:60]}...")
    
    if not driver_acessibilidade or not url_gemini:
        _log("⚠️ Driver de acessibilidade não configurado. Socorro indisponível.")
        return None, None
    
    try:
        # 1. Captura screenshot
        screenshot_path = Path(__file__).parent.parent / "logs" / "visao" / "socorro_medico.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screenshot_path))
        salvar_print_debug(driver, "MEDICO_SCREENSHOT_PACIENTE")
        
        # 2. Extrai HTML comprimido dos elementos interativos
        html_dom = _extrair_contexto_dom(driver)
        url_atual = driver.current_url[:100] if driver.current_url else "desconhecida"
        
        # 3. Monta lista de seletores já tentados (para evitar repetição)
        tentativas_txt = ""
        if seletores_tentados:
            tentativas_txt = "SELETORES JA TENTADOS QUE NAO FUNCIONARAM: " + ", ".join(str(s) for s in seletores_tentados[:5]) + ". "
        
        # 4. Prompt cirúrgico COMPLETO (screenshot + HTML + contexto)
        prompt = (
            f"Voce e um engenheiro de automacao Selenium EXPERT. "
            f"CONTEXTO: Estou automatizando o site {url_atual}. "
            f"OBJETIVO: Preciso encontrar e interagir com: {descricao_para_ia}. "
            f"{tentativas_txt}"
            f"SCREENSHOT: Anexado acima (analise visualmente). "
            f"HTML DOS ELEMENTOS INTERATIVOS VISIVEIS: {html_dom[:2500]} "
            f"INSTRUCOES: Analise o screenshot E o HTML acima. "
            f"Me de EXATAMENTE 3 seletores alternativos, um por linha: "
            f"CSS: seletor_css_aqui "
            f"XPATH: seletor_xpath_aqui "
            f"JS: document.querySelector('seletor') "
            f"Se o elemento NAO estiver visivel, diga ELEMENTO_NAO_VISIVEL. "
            f"Responda APENAS com os seletores, sem explicacao."
        )
        
        # 5. ROUND 1: Envia ao Gemini
        _log("📤 [ROUND 1] Enviando screenshot + HTML ao Gemini Médico...")
        resposta = _enviar_mensagem_gemini_acessibilidade(
            driver_acessibilidade, url_gemini, screenshot_path, prompt, timeout=60
        )
        
        if not resposta:
            _log("❌ Médico: Sem resposta no Round 1.")
            return None, None
        
        _log(f"🎯 Médico respondeu ({len(resposta)} chars): {resposta[:120]}...")
        
        # 6. Detecta se o elemento não está visível
        if 'NAO_VISIVEL' in resposta.upper() or 'NOT_VISIBLE' in resposta.upper():
            _log("⚠️ Médico diagnosticou: elemento não está visível na tela atual.")
            return None, None
        
        # 7. Parseia e testa cada seletor do Round 1
        seletores_r1 = _parsear_seletores_medico(resposta)
        _log(f"🔬 Round 1: {len(seletores_r1)} seletor(es) parseados.")
        
        for sel in seletores_r1:
            _log(f"   Testando {sel['tipo'].upper()}: {sel['valor'][:80]}")
            el = _testar_seletor(driver, sel)
            if el:
                _log(f"✅ MÉDICO ACERTOU! Seletor {sel['tipo']}: {sel['valor'][:60]}")
                salvar_print_debug(driver, "MEDICO_SUCESSO")
                return el, sel['valor']
        
        # 8. ROUND 2: Feedback + nova tentativa
        _log("🔄 [ROUND 2] Nenhum seletor funcionou. Enviando feedback ao Gemini...")
        
        # Atualiza screenshot (estado pode ter mudado)
        driver.save_screenshot(str(screenshot_path))
        html_dom_v2 = _extrair_contexto_dom(driver)
        
        seletores_falhos = ", ".join(f"{s['tipo']}:{s['valor'][:40]}" for s in seletores_r1[:5])
        prompt_r2 = (
            f"NENHUM dos seletores anteriores funcionou: {seletores_falhos}. "
            f"O DOM mudou, aqui esta o HTML atualizado dos elementos visiveis: {html_dom_v2[:2500]} "
            f"Tente abordagens DIFERENTES: "
            f"1) Use o texto EXATO visivel no botao/elemento. "
            f"2) Use o atributo innerHTML (ex: //button[contains(.,'texto')]). "
            f"3) Use a hierarquia de pais (ex: //div[@role='dialog']//button). "
            f"De 3 novos seletores no formato CSS:/XPATH:/JS:, um por linha."
        )
        
        resposta_r2 = _enviar_mensagem_gemini_acessibilidade(
            driver_acessibilidade, url_gemini, None, prompt_r2, timeout=60
        )
        
        if resposta_r2:
            _log(f"🎯 Médico Round 2 ({len(resposta_r2)} chars): {resposta_r2[:120]}...")
            seletores_r2 = _parsear_seletores_medico(resposta_r2)
            _log(f"🔬 Round 2: {len(seletores_r2)} seletor(es) parseados.")
            
            for sel in seletores_r2:
                _log(f"   Testando {sel['tipo'].upper()}: {sel['valor'][:80]}")
                el = _testar_seletor(driver, sel)
                if el:
                    _log(f"✅ MÉDICO ACERTOU NO ROUND 2! {sel['tipo']}: {sel['valor'][:60]}")
                    salvar_print_debug(driver, "MEDICO_SUCESSO_R2")
                    return el, sel['valor']
        
        _log("❌ Médico falhou em ambos os rounds.")
        salvar_print_debug(driver, "MEDICO_FALHA_TOTAL")
        return None, None
        
    except Exception as e:
        _log(f"❌ Erro no pedido de socorro: {str(e)[:80]}")
        return None, None


def superar_obstaculo_desconhecido(driver, driver_acessibilidade=None, url_gemini=None, contexto: str = "tela bloqueada") -> bool:
    """
    MEGA INTELIGENTE v2: Screenshot + HTML + multi-seletores para desbloquear tela.
    Retorna True se conseguiu superar, False se não.
    """
    _log(f"🧠 Obstáculo desconhecido detectado ({contexto}). Ativando resolução autônoma...")
    
    if not driver_acessibilidade or not url_gemini:
        _log("⚠️ Driver de acessibilidade não disponível para resolução autônoma.")
        return False
    
    try:
        # 1. Captura screenshot + HTML
        screenshot_path = Path(__file__).parent.parent / "logs" / "visao" / "obstaculo_desconhecido.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screenshot_path))
        salvar_print_debug(driver, f"OBSTACULO_{contexto.replace(' ', '_')}")
        
        html_dom = _extrair_contexto_dom(driver)
        
        # 2. Prompt inteligente com contexto completo
        prompt = (
            f"Voce e um engenheiro de automacao Selenium EXPERT. "
            f"Estou automatizando uma pagina web e apareceu um obstaculo: {contexto}. "
            f"Pode ser modal, popup, onboarding, aviso de privacidade, ou bloqueio. "
            f"SCREENSHOT: Anexado acima. "
            f"HTML DOS ELEMENTOS INTERATIVOS VISIVEIS: {html_dom[:2500]} "
            f"INSTRUCOES: Analise o screenshot E o HTML. "
            f"Identifique o botao que ACEITA/CONCORDA/FECHA/PROSSEGUE. "
            f"Me de 3 seletores alternativos, um por linha: "
            f"CSS: seletor_aqui "
            f"XPATH: seletor_aqui "
            f"JS: document.querySelector('seletor') "
            f"Responda APENAS com os seletores."
        )
        
        resposta = _enviar_mensagem_gemini_acessibilidade(
            driver_acessibilidade, url_gemini, screenshot_path, prompt, timeout=60
        )
        
        if not resposta:
            _log("❌ IA não conseguiu analisar o obstáculo.")
            return False
        
        # 3. Parseia e testa cada seletor
        seletores = _parsear_seletores_medico(resposta)
        _log(f"🎯 IA retornou {len(seletores)} seletor(es) para o obstáculo.")
        
        for sel in seletores:
            _log(f"   Testando {sel['tipo'].upper()}: {sel['valor'][:80]}")
            el = _testar_seletor(driver, sel)
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                js_click(driver, el)
                _log(f"✅ Obstáculo superado! Clicou em: {sel['valor'][:60]}")
                time.sleep(1.5)
                return True
        
        _log("❌ Nenhum seletor da IA conseguiu superar o obstáculo.")
        return False
        
    except Exception as e:
        _log(f"❌ Erro ao superar obstáculo: {str(e)[:60]}")
        return False

# ==========================================
# 👁️ DETECTAR COM HUNTER (MONITORAMENTO RESILIENTE)
# ==========================================
def detectar_com_hunter(
    driver,
    chave_memoria: str,
    descricao_para_ia: str,
    seletores_rapidos: list,
    palavras_semanticas: list = None,
    etapa: str = "global",
    permitir_autocura: bool = False,
    driver_acessibilidade=None,
    url_gemini=None,
) -> list:
    """
    Versão de MONITORAMENTO do Hunter. Não clica, apenas DETECTA elementos.
    Retorna uma lista de WebElements encontrados e visíveis.
    
    Ideal para:
    - Loaders/spinners (verificar se ainda estão na tela)
    - Barras de progresso (%)
    - Mensagens de erro/falha
    - Botões de status (Stop, Send, Mic)
    
    MODO BALA: Usa cache de seletores para busca instantânea.
    Se o cache falhar, tenta os seletores rápidos e semântica.
    """
    palavras_semanticas = palavras_semanticas or []
    resultados = []
    
    # === CAMADA 1: CACHE EM MEMÓRIA ===
    cache = _get_cache()
    chave_cache = f"{etapa}::{chave_memoria}"
    seletores_cacheados = cache.get(chave_cache, [])
    
    for sel in seletores_cacheados:
        if sel.lower() in ['html', 'body', 'head']:
            continue
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            visiveis = [e for e in els if e.is_displayed() and e.tag_name.lower() not in ['html', 'body']]
            if visiveis:
                return visiveis
        except:
            pass
    
    # === CAMADA 2: SELETORES RÁPIDOS ===
    for sel in seletores_rapidos:
        try:
            # Detecta se é XPath ou CSS
            if sel.startswith('//') or sel.startswith('(//'):
                els = driver.find_elements(By.XPATH, sel)
            else:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
            
            visiveis = [e for e in els if e.is_displayed() and e.tag_name.lower() not in ['html', 'body']]
            if visiveis:
                # Aprende o primeiro para cache futuro
                try:
                    _aprender_seletor(visiveis[0], chave_memoria, etapa)
                except:
                    pass
                return visiveis
        except:
            pass
    
    # === CAMADA 3: BUSCA SEMÂNTICA VIA JS (1 round-trip = ~50ms) ===
    if palavras_semanticas:
        try:
            js_script = """
                var keywords = arguments[0];
                var blockedTags = ['html','body','head','script','style','noscript'];
                var blockedIds = ['__next','root','app','__nuxt'];
                var blockedClasses = ['conversation-title','sidebar','nav-drawer','nav-rail','side-panel'];
                var results = [];
                var all = document.querySelectorAll('*');
                
                for (var i = 0; i < all.length && results.length < 10; i++) {
                    var el = all[i];
                    try {
                        if (el.offsetParent === null && el.style.position !== 'fixed') continue;
                        if (blockedTags.indexOf(el.tagName.toLowerCase()) >= 0) continue;
                        if (el.id && blockedIds.indexOf(el.id.toLowerCase()) >= 0) continue;
                        var cls = (el.className || '').toLowerCase();
                        var blocked = false;
                        for (var bc = 0; bc < blockedClasses.length; bc++) {
                            if (cls.indexOf(blockedClasses[bc]) >= 0) { blocked = true; break; }
                        }
                        if (blocked) continue;
                        var rect = el.getBoundingClientRect();
                        if (rect.width > 800 && rect.height > 600) continue;
                        
                        var content = ((el.getAttribute('aria-label') || '') + ' ' + (el.innerText || '')).toLowerCase();
                        for (var k = 0; k < keywords.length; k++) {
                            if (content.indexOf(keywords[k].toLowerCase()) >= 0) {
                                results.push(el);
                                break;
                            }
                        }
                    } catch(e) { continue; }
                }
                return results;
            """
            resultados = driver.execute_script(js_script, palavras_semanticas) or []
            
            if resultados:
                try:
                    _aprender_seletor(resultados[0], chave_memoria, etapa)
                except:
                    pass
                return resultados
        except:
            pass
    
    return resultados

# ==========================================
# 🔫 CLICAR COM HUNTER (WRAPPER INTELIGENTE)
# ==========================================
def clicar_com_hunter(
    driver,
    chave_memoria: str,
    descricao_para_ia: str,
    seletores_rapidos: list,
    palavras_semanticas: list,
    etapa: str = "global",
    permitir_autocura: bool = True,
    driver_acessibilidade=None,
    url_gemini=None,
    timeout_busca: float = 10.0,
    usar_js_click: bool = True,
) -> bool:
    """
    Encontra um elemento via Hunter e clica nele. Retorna True se clicou.
    MODO BALA: Se o cache funcionar, o clique acontece em < 0.1s.
    MODO MÉDICO: Se falhar, aciona a IA para curar e tenta novamente.
    """
    fim = time.time() + timeout_busca
    elemento = None
    
    while time.time() < fim:
        elemento = cacar_elemento_universal(
            driver=driver,
            chave_memoria=chave_memoria,
            descricao_para_ia=descricao_para_ia,
            seletores_rapidos=seletores_rapidos,
            palavras_semanticas=palavras_semanticas,
            permitir_autocura=permitir_autocura,
            driver_acessibilidade=driver_acessibilidade,
            url_gemini=url_gemini,
            etapa=etapa,
        )
        if elemento:
            break
        time.sleep(0.5)
    
    if not elemento:
        _log(f"❌ clicar_com_hunter falhou para '{chave_memoria}' em [{etapa}]")
        return False
    
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
        time.sleep(0.15)
        
        if usar_js_click:
            js_click(driver, elemento)
        else:
            try:
                elemento.click()
            except:
                js_click(driver, elemento)
        
        return True
    except Exception as e:
        _log(f"⚠️ Erro ao clicar em '{chave_memoria}': {str(e)[:80]}")
        limpar_memoria_chave(chave_memoria, etapa)
        return False

# ==========================================
# 🎯 MENU COMPLEXO (DROPDOWNS MULTI-STEP)
# ==========================================
def interagir_com_menu_complexo(
    driver,
    etapa: str,
    passos: list,
    driver_acessibilidade=None,
    url_gemini=None,
) -> bool:
    """
    Navega por menus suspensos de múltiplos passos.
    
    Cada passo é um dict:
    {
        "chave": "flow_btn_download",
        "descricao": "Botão de download na interface do Flow",
        "seletores": ["//button[.//i[text()='download']]"],
        "palavras": ["download", "baixar"],
        "espera_pos_clique": 1.5,
        "usar_action_click": False,
    }
    
    MODO BALA: Usa cache. Se tudo cacheado, menu navega em < 0.5s.
    MODO MÉDICO: Se falhar, limpa cache, tenta IA, recomeça.
    """
    _log(f"🎯 [{etapa}] Menu complexo: {len(passos)} passo(s)")
    
    # ===== FASE 1: MODO BALA (sem IA, timeout curto) =====
    sucesso_bala = True
    for i, passo in enumerate(passos):
        chave = passo["chave"]
        espera = passo.get("espera_pos_clique", 1.0)
        usar_action = passo.get("usar_action_click", False)
        
        elemento = cacar_elemento_universal(
            driver=driver,
            chave_memoria=chave,
            descricao_para_ia=passo.get("descricao", ""),
            seletores_rapidos=passo.get("seletores", []),
            palavras_semanticas=passo.get("palavras", []),
            permitir_autocura=False,
            etapa=etapa,
        )
        
        if not elemento:
            _log(f"⚠️ [{etapa}] Passo {i+1} '{chave}' não encontrado no modo bala.")
            sucesso_bala = False
            break
        
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
            time.sleep(0.1)
            
            if usar_action:
                ActionChains(driver).move_to_element(elemento).click().perform()
            else:
                js_click(driver, elemento)
            
            time.sleep(espera)
        except Exception as e:
            _log(f"⚠️ [{etapa}] Erro no clique bala passo {i+1}: {str(e)[:60]}")
            sucesso_bala = False
            break
    
    if sucesso_bala:
        _log(f"✅ [{etapa}] Menu complexo navegado no MODO BALA!")
        return True
    
    # ===== FASE 2: MODO MÉDICO (limpa cache, tenta com IA) =====
    _log(f"🚑 [{etapa}] Modo Bala falhou. Ativando MODO MÉDICO...")
    
    # Fecha qualquer menu residual
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
    except: pass
    
    # Limpa cache dos passos
    for passo in passos:
        limpar_memoria_chave(passo["chave"], etapa)
    
    # Tenta novamente COM IA
    for i, passo in enumerate(passos):
        chave = passo["chave"]
        espera = passo.get("espera_pos_clique", 1.5)
        usar_action = passo.get("usar_action_click", False)
        
        elemento = None
        fim_busca = time.time() + 15
        
        while time.time() < fim_busca:
            elemento = cacar_elemento_universal(
                driver=driver,
                chave_memoria=chave,
                descricao_para_ia=passo.get("descricao", ""),
                seletores_rapidos=passo.get("seletores", []),
                palavras_semanticas=passo.get("palavras", []),
                permitir_autocura=True,
                driver_acessibilidade=driver_acessibilidade,
                url_gemini=url_gemini,
                etapa=etapa,
            )
            if elemento:
                break
            time.sleep(1.0)
        
        if not elemento:
            _log(f"❌ [{etapa}] MÉDICO falhou no passo {i+1} '{chave}'. Menu abortado.")
            salvar_print_debug(driver, f"MENU_FALHA_{etapa}_{chave}")
            return False
        
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
            time.sleep(0.15)
            
            if usar_action:
                ActionChains(driver).move_to_element(elemento).click().perform()
            else:
                js_click(driver, elemento)
            
            time.sleep(espera)
        except Exception as e:
            _log(f"❌ [{etapa}] Erro no clique médico passo {i+1}: {str(e)[:60]}")
            return False
    
    _log(f"✅ [{etapa}] Menu complexo navegado via MODO MÉDICO!")
    return True
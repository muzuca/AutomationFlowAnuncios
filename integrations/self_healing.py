# arquivo: integrations/self_healing.py
import json
import time
import re
from pathlib import Path
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from integrations.utils import _log as log_base

ARQUIVO_MEMORIA = Path(__file__).parent.parent / "logs" / "memoria_seletores.json"
LOGS_EMITIDOS = set() 

def _log(msg: str):
    log_base(msg, prefixo="HEALER")

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
    if ARQUIVO_MEMORIA.exists():
        try:
            with open(ARQUIVO_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def salvar_na_memoria(chave_elemento: str, seletor_css: str, etapa: str = "global"):
    """Salva o seletor isolando por etapa do script para evitar conflitos."""
    memoria = carregar_memoria()
    
    # Cria a estrutura de etapa se não existir
    if etapa not in memoria:
        memoria[etapa] = {}
    if chave_elemento not in memoria[etapa]:
        memoria[etapa][chave_elemento] = []
    
    # Se o seletor já for o primeiro desta etapa, ignora (performance)
    if memoria[etapa][chave_elemento] and memoria[etapa][chave_elemento][0] == seletor_css:
        return

    # Remove duplicatas dentro da mesma etapa e coloca no topo
    if seletor_css in memoria[etapa][chave_elemento]:
        memoria[etapa][chave_elemento].remove(seletor_css)
    
    memoria[etapa][chave_elemento].insert(0, seletor_css)
    
    # Mantém apenas os 5 melhores seletores por etapa
    memoria[etapa][chave_elemento] = memoria[etapa][chave_elemento][:5]

    with open(ARQUIVO_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4)
    _log(f"💾 [{etapa}] Memória atualizada para '{chave_elemento}': {seletor_css}")

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
    etapa: str = "global" # <--- NOVO PARÂMETRO OBRIGATÓRIO PARA ISOLAMENTO
) -> WebElement | None:
    
    # 1. 🚀 TENTA A MEMÓRIA DA ETAPA (PRIORIDADE ABSOLUTA)
    memoria = carregar_memoria()
    
    # Tenta primeiro na etapa específica, depois na global como fallback
    contextos_de_busca = [etapa, "global"] if etapa != "global" else ["global"]
    
    for ctx in contextos_de_busca:
        lista_seletores = memoria.get(ctx, {}).get(chave_memoria, [])
        for css in lista_seletores:
            try:
                elemento = driver.find_element(By.CSS_SELECTOR, css)
                if elemento.is_displayed() and elemento.is_enabled():
                    return elemento
            except:
                continue

    # 2. ⚡ TENTA OS XPATHS RÁPIDOS
    for xpath in seletores_rapidos:
        try:
            botoes = driver.find_elements(By.XPATH, xpath)
            for b in botoes:
                if b.is_displayed() and b.is_enabled():
                    # APRENDIZAGEM: Gera seletor blindado baseado no sucesso do XPath
                    try:
                        tag = b.tag_name
                        jsname = b.get_attribute("jsname")
                        if jsname:
                            salvar_na_memoria(chave_memoria, f"{tag}[jsname='{jsname}']", etapa)
                    except: pass
                    return b
        except: pass

    # 3. 🧠 TENTA A SEMÂNTICA (APENAS SE O RESTO FALHAR)
    if f"{etapa}_{chave_memoria}" not in LOGS_EMITIDOS:
        _log(f"🔍 [{etapa}] '{chave_memoria}' não encontrado na memória. Buscando semântica...")
        LOGS_EMITIDOS.add(f"{etapa}_{chave_memoria}")

    try:
        for tag_name in ["button", "div[role='button']", "a", "span"]:
            elementos = driver.find_elements(By.TAG_NAME, tag_name.split('[')[0])
            for el in reversed(elementos):
                try:
                    if not el.is_displayed(): continue
                    
                    # Captura texto, label e conteúdo interno
                    conteudo = (el.get_attribute('innerText') or '') + \
                               (el.get_attribute('aria-label') or '') + \
                               (el.get_attribute('innerHTML') or '')
                    
                    if any(keyword.lower() in conteudo.lower() for keyword in palavras_semanticas):
                        # 🔥 GERA SELETOR CSS BLINDADO PARA ESTA ETAPA 🔥
                        jsname = el.get_attribute("jsname")
                        aria = el.get_attribute("aria-label")
                        el_id = el.get_attribute("id")
                        
                        # Prioridade de seletor: jsname > id (se fixo) > aria > class
                        if jsname:
                            novo_css = f"{tag_name.split('[')[0]}[jsname='{jsname}']"
                        elif el_id and not re.search(r'\d', el_id):
                            novo_css = f"{tag_name.split('[')[0]}#{el_id}"
                        elif aria:
                            novo_css = f"{tag_name.split('[')[0]}[aria-label='{aria}']"
                        else:
                            classes = el.get_attribute("class")
                            classe_limpa = ".".join([c for c in classes.split() if c]) if classes else ""
                            novo_css = f"{tag_name.split('[')[0]}.{classe_limpa}" if classe_limpa else tag_name

                        salvar_na_memoria(chave_memoria, novo_css, etapa)
                        return el
                except: continue
    except: pass

    # 4. 🚑 ÚLTIMO RECURSO: AUTOCURA VIA IA
    if permitir_autocura and driver_acessibilidade and url_gemini:
        _log(f"🚨 Hunter cego em [{etapa}] para '{chave_memoria}'. ACIONANDO UNIDADE MÉDICA...")
        
        from integrations.self_healing import pedir_socorro_ao_gemini
        novo_css = pedir_socorro_ao_gemini(driver, driver_acessibilidade, url_gemini, descricao_para_ia)
        
        if novo_css:
            try:
                elemento = driver.find_element(By.CSS_SELECTOR, novo_css)
                if elemento.is_displayed():
                    _log(f"✅ AUTOCURA BEM SUCEDIDA EM [{etapa}]!")
                    salvar_na_memoria(chave_memoria, novo_css, etapa)
                    return elemento
            except:
                _log("❌ O seletor da IA não funcionou no navegador principal.")
    
    return None
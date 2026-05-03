# arquivo: integrations/flow.py
# descricao: Fachada de integracao com o Google Flow (Humble) para gerar videos
# a partir do roteiro de 3 cenas. Blindado com lógica nativa do humble_client.py e Retry Local.

from __future__ import annotations

import os
import re
import sys
import time
import shutil
import pyperclip

from pathlib import Path
from typing import List, Optional, Dict, Any
from integrations.utils import _log as log_base, salvar_print_debug, js_click, scroll_ao_fim, salvar_ultimo_prompt, remover_caracteres_nao_bmp
from integrations.self_healing import cacar_elemento_universal, elemento_esta_realmente_pronto, clicar_com_hunter, interagir_com_menu_complexo, limpar_memoria_chave, superar_obstaculo_desconhecido, detectar_com_hunter

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

def _log(msg: str):
    log_base(msg, prefixo="FLOW-IA")

class GoogleFlowAutomation:
    def __init__(self, driver, url_flow: str, driver_acessibilidade=None, url_gemini_acessibilidade=None):
        self.driver = driver
        self.wait = WebDriverWait(driver, 30, poll_frequency=0.2)
        self.url_flow = url_flow
        
        # Salvamos os "médicos" na classe para usar no Hunter
        self.driver_acessibilidade = driver_acessibilidade
        self.url_gemini_acessibilidade = url_gemini_acessibilidade

        # --- VARIÁVEIS DE ESTADO ---
        self.ultimo_tile_id_gerado = None
        self._projeto_criado = False
        self._modelo_configurado = False
        self._imagem_upada = False
        self.momento_ultimo_submit = 0
        
        # Flags para rastrear se as fotos já estão na mesa no Modo Imagem
        self._modelo_base_upada = False
        self._uploads_apos_modelo = 0

    # --- MÉTODOS NATIVOS DO HUMBLE_CLIENT ORIGINAL BLINDADO ---
    def _wait_click(self, by: By, value: str, timeout: int = 20, descricao: str = "elemento") -> WebElement:
        """Espera um elemento ficar clicável e clica, com blindagem agressiva contra StaleElementReference."""
        fim_espera = time.time() + timeout
        
        while time.time() < fim_espera:
            try:
                el = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((by, value)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                try: 
                    el.click()
                except Exception: 
                    js_click(self.driver, el)
                _log(f"✔ Clicado: {descricao}")
                return el
            except Exception as e:
                msg_erro = str(e).lower()
                if "stale element reference" in msg_erro or "not attached" in msg_erro or "intercepted" in msg_erro:
                    _log(f"Aviso: '{descricao}' piscou/recarregou (Stale). Tentando clicar novamente...")
                    time.sleep(0.5)
                    continue
                if isinstance(e, TimeoutException):
                    if time.time() >= fim_espera:
                        raise TimeoutException(f"Timeout ao tentar clicar em: {descricao}")
                    continue
                raise e
        raise TimeoutException(f"Timeout esgotado para o elemento: {descricao}")

    def _wait_visible(self, by: By, value: str, timeout: int = 20, descricao: str = "elemento") -> WebElement:
        el = WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((by, value))
        )
        _log(f"✔ Visível: {descricao}")
        return el

    # --- PROGRESSO INLINE ---
    def _print_progress_inline(self, msg: str):
        sys.stdout.write("\r" + msg.ljust(120))
        sys.stdout.flush()

    def _finish_progress_inline(self, msg: str = ""):
        if msg:
            sys.stdout.write("\r" + msg.ljust(120) + "\n")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()

    def _fechar_modais_intrusivos(self) -> None:
        fechou_algo = False
        try:
            termos = [
                'concordo', 'agree', 'got it', 'entendi', 'i agree', 'aceitar', 
                'accept', 'enable', 'continuar', 'continue', 'agree and continue', 
                'dismiss', 'close', 'fechar', 'ok', 'comece já'
            ]
            filtro_termos = " or ".join([f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t}')" for t in termos])
            xpath_monstro = f"//button[{filtro_termos}] | //span[{filtro_termos}] | //div[@role='button'][{filtro_termos}]"
            xpath_monstro += " | //div[@role='dialog']//button[.//i[text()='close' or text()='clear']] | //*[text()='Dismiss']"

            botoes = self.driver.find_elements(By.XPATH, xpath_monstro)
            for btn in botoes:
                try:
                    if btn.is_displayed():
                        texto_detectado = (btn.text or "botão").strip().split('\n')[0]
                        if not texto_detectado: texto_detectado = "ícone/fechar"
                        _log(f'Modal detectado ({texto_detectado}). Fechando automaticamente...')
                        js_click(self.driver, btn)
                        time.sleep(1.0)
                        fechou_algo = True
                except:
                    continue
            
            if not fechou_algo:
                overlays = self.driver.find_elements(By.XPATH, "//div[contains(@class,'overlay') or @role='dialog'] | //mat-dialog-container")
                if any(o.is_displayed() for o in overlays):
                    _log("Tela de bloqueio (overlay/dialog) ativa. Forçando ESC duplo.")
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
        except Exception:
            pass
        
        # 🧠 FALLBACK INTELIGENTE: Só pede ajuda à IA se REALMENTE tem um overlay/dialog VISÍVEL
        if not fechou_algo:
            try:
                overlays_reais = self.driver.find_elements(By.XPATH, 
                    "//div[contains(@class,'overlay') or @role='dialog'] | //mat-dialog-container | //div[contains(@class,'modal')]"
                )
                tem_bloqueio_real = any(o.is_displayed() for o in overlays_reais)
            except:
                tem_bloqueio_real = False
            
            if tem_bloqueio_real:
                try:
                    superar_obstaculo_desconhecido(
                        driver=self.driver,
                        driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                        url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                        contexto="modal intrusivo ou popup bloqueando a interface do Google Flow"
                    )
                except: pass

    def acessar_flow(self) -> None:
        _log(f'Acessando a ferramenta Flow: {self.url_flow}')
        if self.url_flow not in self.driver.current_url:
            self.driver.get(self.url_flow)
        
        salvar_print_debug(self.driver,"PAGINA_CARREGADA")

        try:
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass
        
        _log('Analisando a interface para entrar no Workspace...')
        fim_verificacao = time.time() + 15
        
        while time.time() < fim_verificacao:
            bloqueio_regiao = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'not available in your country')]")
            if bloqueio_regiao and any(b.is_displayed() for b in bloqueio_regiao):
                _log("🚨 BLOQUEIO FATAL: O Google Flow bloqueou o seu IP por região.")
                raise Exception("Geo-Block: Ferramenta não disponível neste país. Ligue uma VPN (EUA).")

            botoes_novo = self.driver.find_elements(
                By.XPATH, 
                "//span[contains(text(), 'New project')] | "
                "//button[contains(., 'New')] | "
                "//button[contains(., 'Novo projeto')] | "
                "//button[descendant::i[text()='add_2']]"
            )
            if any(b.is_displayed() for b in botoes_novo):
                _log('Interface do Flow (Workspace) carregada e pronta.')
                return 

            botoes_create = self.driver.find_elements(
                By.XPATH, 
                "//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create with flow')] | "
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create with flow')] | "
                "//span[text()='Create'] | //button[contains(., 'Create')]"
            )
            clicou_create = False
            for btn in botoes_create:
                if btn.is_displayed():
                    _log('Botão "Create with Flow" detectado. Clicando...')
                    js_click(self.driver,btn)
                    clicou_create = True
                    time.sleep(3) 
                    salvar_print_debug(self.driver,"APOS_CLIQUE_CREATE")
                    break
            
            if clicou_create:
                continue 

            self._fechar_modais_intrusivos()
            time.sleep(0.5)

        _log('Aviso: O workspace pode não ter carregado totalmente no tempo limite.')

    def clicar_novo_projeto(self) -> None:
        if self._projeto_criado:
            _log('Reaproveitando projeto atual (pulando criação)...')
            return

        _log('Iniciando um novo projeto/limpando a tela...')
        t0 = time.time()
        self._fechar_modais_intrusivos()
        
        # --- BLOCO DE FUGA: Só sai do projeto se estiver DENTRO de um ---
        try:
            btns_voltar = self.driver.find_elements(By.XPATH, 
                "//button[.//i[contains(text(), 'arrow_back')]] | //button[contains(., 'Voltar')]"
            )
            btn_visivel = next((b for b in btns_voltar if b.is_displayed()), None)
            if btn_visivel:
                _log("Seta Voltar detectada — saindo do projeto atual...")
                js_click(self.driver, btn_visivel)
                time.sleep(2)
        except:
            pass

        try:
            # ⚡ CAMINHO RÁPIDO: Busca direta do botão "Novo Projeto" (< 50ms)
            clicou = False
            xpaths_novo = [
                "//button[descendant::i[text()='add_2']]",
                "//span[contains(text(), 'New project')]/..",
                "//button[contains(., 'Novo projeto')]",
                "//button[contains(., 'New')]",
            ]
            for xp in xpaths_novo:
                try:
                    btns = self.driver.find_elements(By.XPATH, xp)
                    for b in btns:
                        if b.is_displayed():
                            js_click(self.driver, b)
                            clicou = True
                            _log(f"✔ Botão 'Novo Projeto' clicado (direto em {time.time()-t0:.1f}s)")
                            break
                except:
                    pass
                if clicou:
                    break
            
            # 🧠 FALLBACK: Hunter (sem Médico — botão simples, não precisa de IA)
            if not clicou:
                if not clicar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_btn_novo_projeto",
                    descricao_para_ia="Botão de criar novo projeto (New project ou ícone add_2) no Google Flow",
                    seletores_rapidos=xpaths_novo,
                    palavras_semanticas=["new project", "novo projeto", "add_2"],
                    etapa="FLOW_NAVEGACAO",
                    permitir_autocura=False,  # ⚡ Sem Médico (era True, desperdiçava ~30s)
                    timeout_busca=5.0,
                ):
                    raise TimeoutException("Botão Novo Projeto não encontrado")
            
            # ⚡ POLL: Espera o textbox aparecer (em vez de sleep(3) cego)
            deadline_tb = time.time() + 5.0
            while time.time() < deadline_tb:
                try:
                    tb = self.driver.find_elements(By.XPATH, 
                        "//div[@role='textbox' and @contenteditable='true'] | //textarea"
                    )
                    if tb and any(t.is_displayed() for t in tb):
                        break
                except:
                    pass
                time.sleep(0.3)
            
            self._fechar_modais_intrusivos()
            self._projeto_criado = True
            self._modelo_base_upada = False
            self._uploads_apos_modelo = 0
            _log(f"✔ Novo projeto pronto em {time.time()-t0:.1f}s")

        except TimeoutException:
            _log('Botão "Novo projeto" não visível, forçando refresh...')
            self.driver.refresh()
            time.sleep(3)
            self._fechar_modais_intrusivos()
            self._projeto_criado = True
            self._modelo_base_upada = False
            self._uploads_apos_modelo = 0

    def configurar_parametros_video(self) -> bool:
        if self._modelo_configurado:
            _log('Parâmetros de vídeo já configurados neste projeto (pulando)...')
            return True

        _log('Configurando parâmetros (Vídeo > 9:16 > x1 > Veo 3.1 Fast Lower)...')
        self._fechar_modais_intrusivos() 
        
        try:
            salvar_print_debug(self.driver,"CONFIG_PARAM_INICIO")
            
            # =====================================================================
            # PASSO 1: ABRIR O CHIP DO MODELO (_wait_click primário, Hunter fallback)
            # =====================================================================
            chip_encontrado = False
            xpath_chip_video = "//button[@aria-haspopup='menu' and (contains(., 'Veo') or contains(., 'Vídeo') or contains(., 'Video'))]"
            xpath_chip_img = "//button[@aria-haspopup='menu' and (contains(., 'Banana') or contains(., 'Nano'))]"
            
            try:
                self._wait_click(By.XPATH, xpath_chip_video, timeout=5, descricao="chip do Modelo (Vídeo)")
                chip_encontrado = True
            except TimeoutException:
                try:
                    self._wait_click(By.XPATH, xpath_chip_img, timeout=5, descricao="chip do Modelo (Imagem)")
                    chip_encontrado = True
                except TimeoutException:
                    _log("⚠️ _wait_click falhou. Tentando fallback Hunter...")
                    chip_encontrado = clicar_com_hunter(
                        driver=self.driver,
                        chave_memoria="flow_chip_modelo_video",
                        descricao_para_ia="Chip/botão do modelo de vídeo (Veo, Video) com aria-haspopup=menu no Google Flow",
                        seletores_rapidos=[
                            "//button[@aria-haspopup='menu' and (contains(., 'Veo') or contains(., 'Vídeo') or contains(., 'Video'))]",
                            "//button[@aria-haspopup='menu' and (contains(., 'Banana') or contains(., 'Nano'))]",
                            "//button[@aria-haspopup='menu']",
                        ],
                        palavras_semanticas=["veo", "video", "model", "banana", "nano"],
                        etapa="FLOW_CONFIG_VIDEO",
                        permitir_autocura=True,
                        driver_acessibilidade=self.driver_acessibilidade,
                        url_gemini=self.url_gemini_acessibilidade,
                        timeout_busca=8.0,
                    )
                    if not chip_encontrado:
                        # Último fallback genérico
                        botoes_menu = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                        if botoes_menu:
                            js_click(self.driver, botoes_menu[0])
                            chip_encontrado = True

            if chip_encontrado:
                time.sleep(2.0) 

                # =============================================================
                # PASSO 2: NAVEGAR O MENU DROPDOWN (_wait_click primário)
                # =============================================================
                # Aba Vídeo
                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[.//i[text()='videocam'] or contains(., 'Vídeo') or contains(., 'Video')]", 
                        timeout=5, 
                        descricao="Aba Vídeo"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

                # 9:16
                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]", 
                        timeout=5, 
                        descricao="Opção 9:16"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

                # x1
                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[normalize-space()='1x' or normalize-space()='x1']", 
                        timeout=5, 
                        descricao="Opção x1"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

                # Submenu Veo > Veo 3.1 Fast
                try:
                    self._wait_click(
                        By.XPATH,
                        "//div[@role='menu' and @data-state='open']//button[contains(., 'Veo')]",
                        timeout=5,
                        descricao="Dropdown submenu Veo"
                    )
                    time.sleep(1.0) 
                    try:
                        self._wait_click(
                            By.XPATH,
                            "//div[@role='menuitem' and contains(., 'Veo 3.1 - Fast [Lower Priority]')]",
                            timeout=5,
                            descricao="Modelo Veo 3.1 - Fast [Lower Priority]"
                        )
                    except TimeoutException: pass
                except TimeoutException: pass

                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.5)
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()

                # =============================================================
                # PASSO 3: VALIDAÇÃO REAL — o chip mudou para Veo?
                # =============================================================
                time.sleep(0.5)
                try:
                    chips = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                    modelo_atual = ""
                    for c in chips:
                        txt = (c.text or "").strip()
                        if any(k in txt.lower() for k in ["veo", "banana", "nano", "video"]):
                            modelo_atual = txt
                            break
                    
                    if "veo" in modelo_atual.lower():
                        _log(f'✔ Configurações do modelo aplicadas com sucesso: {modelo_atual}')
                    elif "banana" in modelo_atual.lower() or "nano" in modelo_atual.lower():
                        _log(f"⚠️ Modelo ainda é '{modelo_atual}'. Acionando Médico (self-healing)...")
                        salvar_print_debug(self.driver, "CONFIG_VIDEO_ANTES_SELFHEALING")
                        
                        # 🏥 SELF-HEALING: Pede à IA para navegar o menu e selecionar Veo 3.1
                        resolveu = superar_obstaculo_desconhecido(
                            driver=self.driver,
                            driver_acessibilidade=self.driver_acessibilidade,
                            url_gemini=self.url_gemini_acessibilidade,
                            contexto=(
                                "No Google Flow, o modelo de geração está configurado como 'Nano Banana 2' (modo imagem). "
                                "Preciso mudar para modo VÍDEO. O botão do modelo está na barra inferior da tela. "
                                "Clique nele para abrir o menu dropdown, depois selecione a aba 'Vídeo', "
                                "escolha proporção 9:16, quantidade x1, e modelo 'Veo 3.1 - Fast [Lower Priority]'. "
                                "Depois feche o menu com ESC."
                            )
                        )
                        
                        if resolveu:
                            # Re-valida após self-healing
                            time.sleep(1.0)
                            try:
                                chips2 = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                                for c2 in chips2:
                                    txt2 = (c2.text or "").strip()
                                    if "veo" in txt2.lower():
                                        _log(f'✔ Médico resolveu! Modelo agora: {txt2}')
                                        break
                                else:
                                    _log("🚨 Médico tentou mas modelo não mudou. Configuração FALHOU!")
                                    self._modelo_configurado = False
                                    return False
                            except Exception:
                                _log("⚠️ Não foi possível re-validar após self-healing.")
                        else:
                            _log("🚨 Médico não conseguiu resolver. Configuração de vídeo FALHOU!")
                            salvar_print_debug(self.driver, "CONFIG_VIDEO_FALHOU_MODELO_ERRADO")
                            self._modelo_configurado = False
                            return False
                    else:
                        _log(f'Configurações aplicadas (modelo: {modelo_atual or "não identificado"}).')
                except Exception:
                    _log('Configurações do modelo aplicadas com sucesso.')

            else:
                _log("⚠️ Não foi possível abrir o menu. Assumindo que a UI já está configurada por reuso de projeto.")

            salvar_print_debug(self.driver,"CONFIG_PARAM_FIM")
            self._modelo_configurado = True
            return True

        except Exception as e:
            _log(f'🚨 Erro fatal inesperado ao configurar modelo: {e}')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def configurar_parametros_imagem(self) -> bool:
        if self._modelo_configurado: return True
        
        _log('Configurando parâmetros de Imagem (Nano Banana > 9:16)...')
        try:
            salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_INICIO")
            url_antes = self.driver.current_url
            
            # PASSO 1: Clica no chip do modelo (Nano Banana) — _wait_click ESPERA ele ficar clicável
            chip_xpath = "//button[(contains(., 'Banana') or contains(., 'Nano')) and @aria-haspopup='menu']"
            try:
                self._wait_click(By.XPATH, chip_xpath, timeout=10, descricao="chip do Modelo")
            except TimeoutException:
                _log("Aviso: Chip principal não detectado. Tentando menu genérico...")
                botoes_menu = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                if botoes_menu: 
                    js_click(self.driver, botoes_menu[0])
            
            salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_APOS_CHIP_CLICK")
            time.sleep(2.0) 

            # PASSO 2: Seleciona 9:16 — _wait_click ESPERA o menu abrir e o botão ficar clicável
            xpath_916 = "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]"
            try:
                self._wait_click(By.XPATH, xpath_916, timeout=10, descricao="Opção 9:16")
                _log("✔ Proporção 9:16 selecionada!")
                salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_916_OK")
            except TimeoutException:
                _log("⚠️ _wait_click falhou para 9:16. Tentando Hunter + Médico...")
                salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_916_WAIT_FALHOU")
                # FALLBACK: Hunter com Médico (aprende o seletor correto)
                clicar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_menu_ratio_916_img",
                    descricao_para_ia="Opção de proporção 9:16 (vertical) no menu dropdown aberto de configuração do Flow. Ícone crop_9_16 ou texto 9:16.",
                    seletores_rapidos=[
                        "//button[.//i[text()='crop_9_16'] or contains(., '9:16')]",
                        "//button[.//span[contains(text(),'9:16')]]",
                    ],
                    palavras_semanticas=["9:16", "crop_9_16", "vertical", "portrait"],
                    etapa="FLOW_CONFIG_IMG",
                    timeout_busca=5.0,
                    permitir_autocura=True,
                    driver_acessibilidade=self.driver_acessibilidade,
                    url_gemini=self.url_gemini_acessibilidade,
                )
            time.sleep(0.5)

            # PASSO 3: Quantidade x1 (opcional)
            try:
                self._wait_click(
                    By.XPATH, 
                    "//div[@role='menu' and @data-state='open']//button[normalize-space()='1x' or normalize-space()='x1']", 
                    timeout=3, 
                    descricao="Opção x1"
                )
                time.sleep(0.5)
            except TimeoutException:
                pass

            _log('Configurações de IMAGEM aplicadas com sucesso.')
            salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_FIM")
            self._modelo_configurado = True
            
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            
            # VERIFICAÇÃO: Ainda estamos no edit view?
            url_depois = self.driver.current_url
            if '/edit/' not in url_depois and '/edit/' in url_antes:
                _log("🚨 ALERTA: ESC fechou o edit view! Voltando...")
                self.driver.get(url_antes)
                time.sleep(3)
                return False
            
            return True

        except Exception as e:
            _log(f'🚨 Erro fatal ao configurar modelo de imagem: {e}')
            return False

    def _encontrar_input_file(self) -> WebElement:
        # 🛡️ HUNTER: Busca input file via cache
        el = cacar_elemento_universal(
            driver=self.driver,
            chave_memoria="flow_input_file",
            descricao_para_ia="Campo input[type=file] para upload de imagens no Google Flow",
            seletores_rapidos=['input[type="file"]', 'input[accept*="image"]'],
            palavras_semanticas=[],
            permitir_autocura=False,
            etapa="FLOW_UPLOAD",
        )
        if el is not None:
            return el
        
        # Fallback direto
        seletores = ['input[type="file"]', 'input[accept*="image"]']
        for seletor in seletores:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
            if elementos:
                return elementos[-1]
        raise TimeoutException('Nenhum input[type=file] encontrado na interface do Flow.')

    # =================================================================================
    # FUNÇÕES 100% ISOLADAS: OTIMIZADAS PARA O FLUXO DE PRODUTO + MODELO NO MODAL (IMAGE BASE)
    # =================================================================================

    def _upload_produto_isolado(self, caminho: Path) -> bool:
        """Faz o upload cravando a espera até o card cinza de porcentagem sumir."""
        _log(f"Iniciando upload isolado de: {caminho.name}...")
        nome_limpo = caminho.stem 
        
        try:
            salvar_print_debug(self.driver, f"1_ANTES_DO_UPLOAD_{nome_limpo}")
            
            # 1. Injeta o arquivo no input correto
            input_file = self._encontrar_input_file()
            self.driver.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;", input_file)
            input_file.send_keys(str(caminho.resolve()))
            self._fechar_modais_intrusivos()
            _log("Arquivo injetado. Aguardando a interface registrar o card...")
            
            # Respiro pro Flow criar o card cinza de 0%
            time.sleep(3.0) 
            salvar_print_debug(self.driver, f"2_CARD_CINZA_CRIADO_{nome_limpo}")
            
            # =========================================================
            # LÓGICA BLINDADA: Espera Spinners E Textos de "%" (ex: "99%")
            # =========================================================
            _log("Aguardando progresso do upload (0% a 100%)...")
            fim_loader = time.time() + 90 # 1.5 minutos de margem
            while time.time() < fim_loader:
                try:
                    # 🛡️ HUNTER: Detecta spinners, progressbars e textos de %
                    loaders = detectar_com_hunter(
                        driver=self.driver,
                        chave_memoria="flow_upload_loaders",
                        descricao_para_ia="Indicadores de loading (spinners, progressbar, texto com %) durante upload no Google Flow",
                        seletores_rapidos=[
                            "//*[contains(@class, 'spin') or @role='progressbar']",
                            "//*[contains(text(), '%')]",
                        ],
                        palavras_semanticas=["loading", "uploading", "progress", "spin"],
                        etapa="FLOW_UPLOAD",
                    )
                    
                    # Se não tem nada de loading e nada de % na tela, o upload acabou!
                    if not loaders:
                        break
                except: pass
                time.sleep(1)

            # O 100% bateu e sumiu. Dá 3 segundos pro React trocar o fundo cinza pela foto real
            time.sleep(3.0)

            # Checa se o Google cuspiu erro fatal de upload
            try:
                # 🛡️ HUNTER: Detecta erros de upload (SEM busca semântica para evitar falso-positivo do rodapé)
                erros = detectar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_upload_erros",
                    descricao_para_ia="Mensagem de erro/falha no card de upload (Falha, Failed, Error, Violação) no Google Flow",
                    seletores_rapidos=[
                        "//*[@data-tile-id]//div[contains(text(), 'Falha') or contains(text(), 'Failed')]",
                        "//*[@data-tile-id]//*[contains(text(), 'Error') or contains(text(), 'Erro')]",
                        "//*[@data-tile-id]//*[contains(text(), 'Viola') or contains(text(), 'Violat')]",
                        "//*[@data-tile-id]//*[contains(@class, 'error') or contains(@class, 'fail')]",
                    ],
                    palavras_semanticas=[],  # 🛡️ DESATIVADO: O rodapé "O Flow pode cometer erros" causava falso-positivo
                    etapa="FLOW_UPLOAD",
                )
                if erros:
                    _log("❌ Falha crítica: O Google Flow rejeitou a imagem no servidor.")
                    salvar_print_debug(self.driver, f"3_ERRO_SERVIDOR_UPLOAD_{nome_limpo}")
                    return False
            except: pass

            # =========================================================
            # LÓGICA HUNTER: Pega a imagem finalizada
            # =========================================================
            _log(f"Procurando card da imagem finalizada na galeria...")
            fim_busca = time.time() + 30 
            card_upado = None
            
            while time.time() < fim_busca:
                card_upado = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="flow_card_upload",
                    descricao_para_ia="O card de imagem base (original) na galeria do Flow, sem botão de download.",
                    seletores_rapidos=[
                        "//div[@data-tile-id and not(.//button[.//i[text()='download']])]//img",
                        "//img[contains(@src, 'blob:') and ancestor::div[@data-tile-id]]"
                    ],
                    palavras_semanticas=['img', 'image', 'blob', 'upload'],
                    permitir_autocura=False, # Não usa IA, o xpath garante
                    driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                    url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                    etapa="FLOW_UPLOAD"
                )
                
                if card_upado and card_upado.is_displayed():
                    break
                time.sleep(1.5)

            if card_upado:
                _log(f"✔ Upload totalmente concluído e renderizado na tela!")
                salvar_print_debug(self.driver, f"3_UPLOAD_CONCLUIDO_{nome_limpo}")
                return True
            else:
                _log(f"⚠️ Timeout: Imagem não renderizou na galeria após o upload.")
                salvar_print_debug(self.driver, f"3_TIMEOUT_UPLOAD_{nome_limpo}")
                return False

        except Exception as e:
            _log(f"🚨 Erro crítico no upload isolado: {str(e)[:100]}")
            return False
        
    def _clicar_produto_destaque(self, nome_arquivo: str) -> bool:
        """Clica na imagem do produto (que deve ser o Índice 1 após o término do upload)."""
        _log(f"Procurando imagem do produto no índice 1 (Esquerda) para destaque...")
        salvar_print_debug(self.driver, "FLOW_DEST_01_BUSCANDO_GRADE")
        
        # Último respiro de segurança antes de clicar
        time.sleep(2.0)

        try:
            fim_busca = time.time() + 30
            img_destaque = None
            
            while time.time() < fim_busca:
                img_destaque = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="flow_imagem_esquerda",
                    descricao_para_ia="A primeira miniatura de imagem na esquerda da galeria. Retorne o seletor para a tag <img> desse card.",
                    seletores_rapidos=[
                        # Matador: Pega exatamente a primeira imagem da grade que é arquivo local (sem download)
                        "(//div[@data-tile-id and not(.//button[.//i[text()='download']])]//img)[1]",
                        "(//div[@data-tile-id]//img)[1]"
                    ],
                    palavras_semanticas=['first', 'left'],
                    permitir_autocura=False, # Não aciona IA, os xpaths acima dão conta do recado
                    driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                    url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                    etapa="FLOW_DESTAQUE"
                )
                
                if img_destaque and img_destaque.is_displayed():
                    break
                    
                time.sleep(1)

            if not img_destaque:
                _log("❌ Hunter falhou: Não foi possível localizar a imagem na esquerda.")
                return False

            js_click(self.driver, img_destaque) 
            time.sleep(3.0)
            salvar_print_debug(self.driver, "FLOW_DEST_02_MODAL_ABERTO")
            _log("✔ Produto base (identificado na esquerda) aberto com sucesso.")
            return True
            
        except Exception as e:
            _log(f"Erro crítico ao acessar imagem na esquerda: {str(e)[:100]}")
            return False

    def _anexar_modelo_pela_lista(self, nome_modelo: str, url_ancora: str) -> bool:
        """A modelo já foi upada! Abre o +, busca na aba recentes pelo nome e valida o chip."""
        _log(f"Anexando a modelo ({nome_modelo}) pelo botão + da lista de recentes...")
        nome_limpo = Path(nome_modelo).stem
        
        idx_modelo = getattr(self, '_uploads_apos_modelo', 0)
        _log(f"Rastreador: A foto da modelo deve estar na posição {idx_modelo} da galeria de recentes.")

        try:
            # --- 🎯 HUNTER 1: Botão "+" (add_2) ---
            xpath_add = "//button[.//i[text()='add_2']] | //button[contains(., 'Criar')]"
            btn_add = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="flow_botao_add_secundario",
                descricao_para_ia="O botão com ícone de '+' (add_2) usado para anexar mais imagens ao lado do chip principal no Google Flow.",
                seletores_rapidos=[xpath_add],
                palavras_semanticas=['add', 'criar', 'plus'],
                permitir_autocura=True, # Aqui o menu tá fechado, a IA pode agir se precisar
                driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                etapa="FLOW_ANEXO_MODAL"
            )

            if not btn_add:
                btn_add = self._wait_click(By.XPATH, xpath_add, timeout=10, descricao="Botão + (add_2)")
            else:
                js_click(self.driver, btn_add)
                
            time.sleep(2.0)

            if self.driver.current_url != url_ancora:
                _log("⚠️ O Flow perdeu o foco do produto! Restaurando URL...")
                self.driver.get(url_ancora)
                time.sleep(3.0)
                btn_add = self._wait_click(By.XPATH, xpath_add, timeout=10)
                time.sleep(1.5)

            # --- 🛡️ PADRONIZAÇÃO BLOB + NOME (Alinhado com a outra função) ---
            nome_min = nome_modelo.lower()
            limpo_min = nome_limpo.lower()
            cond_alt = f"contains(translate(@alt, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{nome_min}') or contains(translate(@alt, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{limpo_min}')"

            # --- 🎯 HUNTER 2: Foto dentro do Menu Dropdown ---
            foto_modelo = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="flow_foto_modelo_dropdown",
                descricao_para_ia=f"A miniatura da modelo '{nome_limpo}' no menu suspenso de anexos.",
                seletores_rapidos=[
                    # 1. Blindagem Absoluta: Blob (Upload Local) + Nome correto
                    f"//div[@data-state='open' or contains(@role, 'menu')]//img[contains(@src, 'blob:') and ({cond_alt})]",
                    
                    # 2. Fallback de Nome sem o Blob
                    f"//div[@data-state='open' or contains(@role, 'menu')]//img[{cond_alt}]",
                    
                    # 3. Fallback Matemático: Transforma seu index 0-based do Python em 1-based do XPath
                    f"(//div[@data-state='open' or contains(@role, 'menu')]//img[contains(@src, 'blob:')])[{idx_modelo + 1}]"
                ],
                palavras_semanticas=[limpo_min, nome_min, 'blob'],
                permitir_autocura=False, # 🚨 CRÍTICO: Se a IA abrir outra aba, o menu do Flow fecha sozinho!
                driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                etapa="FLOW_ANEXO_MODAL"
            )

            if foto_modelo:
                js_click(self.driver, foto_modelo)
                _log(f"✔ Imagem da modelo ({nome_limpo}) selecionada via Hunter (Proteção Blob Ativa).")
                salvar_print_debug(self.driver, "FLOW_ANEXO_CHIP_OK")
            else:
                _log("⚠️ Hunter falhou. Usando fallback extremo cego...")
                xpath_fallback_extremo = "//div[@data-state='open' or contains(@role, 'menu')]//div[contains(@class, 'grid') or contains(@class, 'list')]//button//img"
                fallbacks_ext = self.driver.find_elements(By.XPATH, xpath_fallback_extremo)
                if fallbacks_ext and fallbacks_ext[0].is_displayed():
                    js_click(self.driver, fallbacks_ext[0])
                    _log("⚠️ Fallback extremo clicado.")
                    salvar_print_debug(self.driver, "FLOW_ANEXO_FALLBACK_EXTREMO")

            time.sleep(1.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1.0)

            # --- VALIDAÇÃO FINAL ---
            xpath_chip = "//button[.//i[text()='cancel']]"
            chips = self.driver.find_elements(By.XPATH, xpath_chip)
            if chips and any(c.is_displayed() for c in chips):
                _log("✔ Confirmação: Modelo anexada perfeitamente no quadradinho (chip)!")
                salvar_print_debug(self.driver, "FLOW_ANEXO_CHIP_CONFIRMADO")
                return True
            
            return False
            
        except Exception as e:
            _log(f"Erro fatal ao selecionar modelo da lista: {str(e).splitlines()[0]}")
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def _enviar_prompt_imagem_isolado(self, prompt: str, timeout_geracao: int = 120) -> bool:
        """Digita o prompt e monitora falhas globais (Unusual Activity) na tela inteira."""
        import os
        import time
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.by import By
        
        def js_click(driver, element):
            driver.execute_script("arguments[0].click();", element)

        _log("Enviando prompt (Fluxo isolado de Imagem)...")

        prompt_linear = remover_caracteres_nao_bmp(" ".join(prompt.replace('\n', ' ').replace('\r', ' ').split()))
        
        # 🛡️ CAMADA 3: Guard de tamanho antes do send_keys
        # Um prompt de imagem do Flow tem ~300-800 chars. Se tem >2000, está corrompido.
        MAX_PROMPT_FLOW = 2000
        if len(prompt_linear) > MAX_PROMPT_FLOW:
            _log(f"🚨 GUARD FLOW: Prompt com {len(prompt_linear)} chars (max {MAX_PROMPT_FLOW}). Prompt corrompido — ABORTANDO envio!")
            _log(f"🚨 Primeiros 200 chars: {prompt_linear[:200]}...")
            return False
        
        try:
            from integrations.utils import salvar_ultimo_prompt
            salvar_ultimo_prompt(f"--- PROMPT ENVIADO AO FLOW (IMAGEM) ---\n{prompt_linear}")
        except: pass

        try:
            xpath_box = "//div[@role='textbox' and @contenteditable='true'] | //textarea"
            # 🛡️ HUNTER: Busca caixa de texto via cache
            box = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="flow_textarea_prompt_img",
                descricao_para_ia="Caixa de texto (textbox contenteditable) para digitar prompt de imagem no Google Flow",
                seletores_rapidos=[xpath_box],
                palavras_semanticas=[],
                permitir_autocura=False,
                etapa="FLOW_SUBMIT_IMG",
            )
            
            if not box:
                caixas = self.driver.find_elements(By.XPATH, xpath_box)
                box = next((c for c in caixas if c.is_displayed()), None)
            
            if not box:
                _log("⚠️ Caixa de texto não encontrada.")
                return False
            
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", box)
            js_click(self.driver, box)
            time.sleep(0.5)
            
            # Limpa e injeta
            box.send_keys(Keys.CONTROL, "a")
            box.send_keys(Keys.BACKSPACE)
            
            is_headless = os.getenv('CHROME_HEADLESS', 'False').lower() == 'true'
            if is_headless:
                box.send_keys(prompt_linear)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
            else:
                import pyperclip
                pyperclip.copy(prompt_linear)
                box.send_keys(Keys.CONTROL, 'v')

            salvar_print_debug(self.driver, "FLOW_DEPOIS_COLAR_PROMPT")                    

            # 📸 PRINT CRÍTICO: Estado da tela ANTES do submit (modelo ainda no chip?)
            salvar_print_debug(self.driver, "FLOW_ANTES_SUBMIT_ESTADO")

            time.sleep(1.5)

            # Tenta clicar o botão de enviar via Hunter
            # --- SUBMIT: Lógica FUNCIONAL do commit (find_elements direto + disabled check) ---
            xpath_submit = "//button[.//i[contains(text(), 'arrow') or contains(text(), 'send') or contains(text(), 'sparkle')]] | //button[contains(@aria-label, 'Gerar')]"
            btns = self.driver.find_elements(By.XPATH, xpath_submit)
            
            if btns and btns[-1].is_displayed():
                btn_send = btns[-1]
                if btn_send.get_attribute("disabled") is not None:
                    box.send_keys(Keys.CONTROL, Keys.ENTER)
                else:
                    try: btn_send.click()
                    except: js_click(self.driver, btn_send)
            else:
                box.send_keys(Keys.CONTROL, Keys.ENTER)

            salvar_print_debug(self.driver, "FLOW_APOS_SUBMIT_PROMPT")
            momento_submit = time.time()
            time.sleep(4) 
            
            # --- MONITORAMENTO COM RADAR DE FALHA GLOBAL ---
            _log(f"Monitorando geração (máx {timeout_geracao}s)...")
            
            _log("[FLOW-IA] Aguardando processamento inicial...")
            time.sleep(15)
            
            # Garante a contagem de tempo
            momento_submit = time.time()
            fim_espera = momento_submit + timeout_geracao

            while time.time() < fim_espera:
                # 🚀 SCRIPT RADAR AVANÇADO
                status = self.driver.execute_script("""
                    var txt = document.body.innerText.toLowerCase();
                    
                    // 1. Verifica falhas críticas
                    if (txt.includes('unusual activity') || txt.includes('policy') || txt.includes('failed') || (txt.includes('falha') && txt.includes('noticed'))) {
                        return 'FALHA';
                    }
                    
                    // 2. Procura ativamente pelo botão de download (por texto ou ícone)
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var b_txt = b.innerText.toLowerCase();
                        if (b_txt.includes('download') || b_txt.includes('baixar') || b.innerHTML.includes('download')) {
                            return 'SUCESSO_BOTAO';
                        }
                    }
                    
                    // 3. Fallback: Se a caixa de texto secou, significa que enviou. 
                    // Se enviou e não tem mais botão de "Stop", é porque gerou.
                    var box = document.querySelector('div[role="textbox"], textarea');
                    if (box && box.innerText.trim() === '') {
                        var is_generating = false;
                        for (var b of btns) {
                            if (b.innerText.toLowerCase().includes('stop') || b.innerHTML.includes('stop')) {
                                is_generating = true;
                            }
                        }
                        if (!is_generating) {
                            return 'SUCESSO_FALLBACK';
                        }
                    }
                    
                    return 'AGUARDANDO';
                """)
                
                if status == 'FALHA':
                    _log("🚨 FALHA DETECTADA NA TELA (Unusual Activity / Policy).")
                    break
                    
                if status in ['SUCESSO_BOTAO', 'SUCESSO_FALLBACK']:
                    # Trava contra falso-positivo (imagens muito rápidas)
                    if (time.time() - momento_submit) < 15:
                        time.sleep(1.5)
                        continue
                        
                    _log("✔ Geração concluída com sucesso!")
                    salvar_print_debug(self.driver, "FLOW_GERACAO_CONCLUIDA")
                    return True
                
                self._print_progress_inline(f"[FLOW-IA] Gerando... {int(time.time() - momento_submit)}s")
                time.sleep(1.5)  # ⚡ Reduzido de 4s para 1.5s (JS radar é instantâneo)
                
            _log("❌ Geração interrompida ou Timeout atingido.")
            return False
            
        except Exception as e:
            _log(f"Erro no monitoramento: {e}")
            return False

    def gerar_imagem_base(self, caminho_referencia: Path, prompt: str, caminho_saida: Path, caminho_modelo: Optional[Path] = None) -> Path:
        """Orquestração corrigida: Modelo primeiro (Direita), Produto depois (Esquerda/Destaque)."""
        _log(f"🎬 [FLOW-IMAGE] Iniciando geração. Saída: {caminho_saida.name}")
        
        sucesso_absoluto = False
        
        # LOOP 1: PROJETOS (Máx 2 Projetos Novos)
        for tentativa_projeto in range(1, 3):
            _log(f"📦 [PROJETO {tentativa_projeto}/2] Iniciando workspace...")
            self.acessar_flow()
            self.clicar_novo_projeto()
            
            try:
                self._fechar_modais_intrusivos()

                # Atributos de rastreamento de estado
                if not hasattr(self, '_modelo_base_upada'): self._modelo_base_upada = False

                # --- 🚨 ESTRATÉGIA DE POSICIONAMENTO 🚨 ---
                
                # 1. FAZ UPLOAD DA MODELO PRIMEIRO
                # Ao subir primeiro, ela será "empurrada" para a direita pelo próximo upload.
                if caminho_modelo and caminho_modelo.exists():
                    if not self._modelo_base_upada:
                        _log("Subindo MODELO primeiro (ficará na direita)...")
                        if not self._upload_produto_isolado(caminho_modelo):
                            raise Exception("Falha no upload da modelo.")
                        self._modelo_base_upada = True
                        time.sleep(2) # Respiro para renderização da grade
                    else:
                        _log("Modelo já presente no Workspace.")

                # 2. FAZ UPLOAD DO PRODUTO POR ÚLTIMO
                # O produto assume a posição 1 (Extrema Esquerda).
                _log("Subindo PRODUTO por último (Garantindo Índice 1 / Esquerda)...")
                if not self._upload_produto_isolado(caminho_referencia):
                    raise Exception("Falha no upload do produto.")
                
                salvar_print_debug(self.driver, f"FLOW_GRADE_PRONTA_{caminho_referencia.stem}") #

                # LOOP 2: TENTATIVAS DE GERAÇÃO (Máx 3 por projeto)
                for tentativa_geracao in range(1, 4):
                    _log(f"⚙️ [GERAÇÃO {tentativa_geracao}/3] Preparando prompt e modelo...")
                    
                    # 3. Clica no Produto para ancorar o destaque (Sempre no Índice 1)
                    if not self._clicar_produto_destaque(caminho_referencia.name):
                        raise Exception("Falha ao abrir o modal do produto em destaque.")

                    url_ancora = self.driver.current_url

                    # 4. Anexar modelo pela lista de recentes
                    if caminho_modelo and caminho_modelo.exists():
                        if not self._anexar_modelo_pela_lista(caminho_modelo.name, url_ancora):
                            raise Exception("A modelo não fixou na interface.")

                    # 5. Configura e Envia
                    self._modelo_configurado = False
                    self.configurar_parametros_imagem()
                    
                    if self._enviar_prompt_imagem_isolado(prompt, timeout_geracao=120):
                        sucesso_absoluto = True
                        break # Sucesso na geração!
                    else:
                        _log(f"⚠️ Tentativa {tentativa_geracao} falhou. Resetando modal...")
                        from selenium.webdriver.common.action_chains import ActionChains
                        from selenium.webdriver.common.keys import Keys
                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                        time.sleep(2)
                        
                if sucesso_absoluto:
                    break # Sucesso no projeto!

            except Exception as e:
                _log(f"Falha no projeto {tentativa_projeto}: {str(e)[:100]}")
                self.driver.refresh()
                self._projeto_criado = False 
                self._modelo_base_upada = False
                time.sleep(4)
                
        if not sucesso_absoluto:
            raise Exception("Falha ao gerar imagem no Flow após 2 projetos.")
            
        return self._baixar_imagem(caminho_saida)
    
    # =================================================================================
    # MÉTODOS DE VÍDEO E DOWNLOADS: COMPLETAMENTE INTOCÁVEIS (SUA LÓGICA ORIGINAL)
    # =================================================================================
    def anexar_imagem(self, caminho: Path, abrir_modal: bool = False) -> bool:
        """
        Sobe a imagem para o projeto e garante a vinculação no slot 'Inicial'.
        Blindado SEM ESC para não resetar a seleção no React.
        """
        nome_arquivo = caminho.name
        self._fechar_modais_intrusivos() 
        
        # 🚨 ADIÇÃO CRÍTICA: Fecha o menu de perfil do Google que está sobrepondo a tela
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
        except: pass
        
        if not self._imagem_upada:
            _log(f'Fazendo upload da imagem de referência: {nome_arquivo}')
            try:
                input_file = self._encontrar_input_file()
                self.driver.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;", input_file)
                input_file.send_keys(str(caminho.resolve()))
                
                _log('Aguardando a conclusão do upload da imagem (sumiço do loader/%)...')
                time.sleep(2.0) 
                
                fim_upload = time.time() + 60
                while time.time() < fim_upload:
                    # 🛡️ HUNTER: Monitora progresso % do upload
                    loaders = detectar_com_hunter(
                        driver=self.driver,
                        chave_memoria="flow_upload_progress_pct",
                        descricao_para_ia="Texto com porcentagem (%) indicando progresso de upload no Google Flow",
                        seletores_rapidos=[
                            "//div[contains(text(), '%')]",
                            "//span[contains(text(), '%')]",
                            "//*[contains(@class, 'spin') or @role='progressbar']",
                        ],
                        palavras_semanticas=["progress", "upload", "%"],
                        etapa="FLOW_UPLOAD",
                    )
                    if not loaders:
                        break 
                    time.sleep(1)

                salvar_print_debug(self.driver, f"FLOW_UPLOAD_SUCESSO_{caminho.stem}")
                time.sleep(3.0) 
                self._imagem_upada = True
            except Exception as e:
                _log(f'🚨 Falha no upload nativo da imagem: {e}')
                return False
        else:
            _log(f'A imagem {nome_arquivo} já foi upada no projeto. Indo para o clique...')

        if abrir_modal:
            _log("Clicando na imagem na tela principal para abrir o modal de prompt...")
            try:
                xpath_miniatura = f"//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')] | //div[@data-tile-id]//img"
                # 🛡️ HUNTER: Busca miniaturas
                miniaturas = detectar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_miniaturas_imagem",
                    descricao_para_ia="Miniatura de imagem na galeria do Google Flow",
                    seletores_rapidos=[xpath_miniatura],
                    palavras_semanticas=["img", "imagem", "blob", "miniatura"],
                    etapa="FLOW_UPLOAD",
                )
                
                if miniaturas:
                    # Rola para o elemento antes de clicar para evitar que fique fora da tela
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", miniaturas[-1])
                    js_click(self.driver, miniaturas[-1])
                    time.sleep(2.0)
                    _log("✔ Imagem clicada! Modal aberto.")
                    salvar_print_debug(self.driver, f"FLOW_MODAL_PROMPT_ABERTO_{caminho.stem}")
                    return True
                    
                _log("⚠️ Imagem não achada. Clicando no último card genérico...")
                imgs = detectar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_imgs_fallback",
                    descricao_para_ia="Qualquer tag img na página do Google Flow",
                    seletores_rapidos=["//img"],
                    etapa="FLOW_UPLOAD",
                )
                if imgs:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", imgs[-1])
                    js_click(self.driver, imgs[-1]) 
                    time.sleep(2.0)
                return True
            except Exception as e:
                _log(f'🚨 Erro ao abrir modal: {e}')
                return True
        else:
            _log("Vinculando a imagem no botão 'Inicial' da interface principal...")
            try:
                xpath_btn_inicial = (
                    "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') "
                    "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))]"
                )
                # 🛡️ HUNTER: Busca botões Initial
                botoes_iniciais = detectar_com_hunter(
                    driver=self.driver,
                    chave_memoria="flow_btn_inicial",
                    descricao_para_ia="Botão 'Inicial' ou 'Initial' para vincular imagem base no Google Flow",
                    seletores_rapidos=[xpath_btn_inicial],
                    palavras_semanticas=["inicial", "initial", "imagem base"],
                    etapa="FLOW_UPLOAD",
                )
                
                if botoes_iniciais:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botoes_iniciais[0])
                    js_click(self.driver, botoes_iniciais[0])
                    _log('Botão "Inicial" clicado. Aguardando galeria...')
                    time.sleep(2.5) 

                    xpath_img_popup = f"//div[@role='dialog']//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')] | //div[@role='dialog']//img"
                    # 🛡️ HUNTER: Busca imagens no popup/dialog
                    imgs_dialog = detectar_com_hunter(
                        driver=self.driver,
                        chave_memoria="flow_imgs_dialog",
                        descricao_para_ia="Imagens dentro do popup/dialog de seleção do Google Flow",
                        seletores_rapidos=[xpath_img_popup],
                        etapa="FLOW_UPLOAD",
                    )
                    if imgs_dialog:
                        js_click(self.driver, imgs_dialog[0])
                        _log('✔ Imagem base selecionada no popup. Aguardando UI processar...')
                        time.sleep(2.5)

                    salvar_print_debug(self.driver, f"FLOW_CONFERENCIA_SLOT_INICIAL_{caminho.stem}")
                    _log('✔ Imagem vinculada e trancada no slot Inicial!')
                else:
                    _log('⚠️ Botão "Inicial" não encontrado na tela.')
                return True
            except Exception as e:
                _log(f'🚨 Erro na vinculação ao botão Inicial: {e}')
                salvar_print_debug(self.driver, "ERRO_VINCULACAO_INICIAL")
                return True

    def _garantir_imagem_anexada(self, caminho_imagem: Path) -> bool:
        _log("Validando visualmente a presença da imagem no Slot Inicial...")
        try:
            # 🛡️ HUNTER: Verifica botão Remove
            btn_remover = detectar_com_hunter(
                driver=self.driver,
                chave_memoria="flow_btn_remover",
                descricao_para_ia="Botão 'Remove' para remover imagem anexada no Google Flow",
                seletores_rapidos=["//button[contains(@aria-label, 'Remove')]"],
                palavras_semanticas=["remove", "remover", "delete"],
                etapa="FLOW_UPLOAD",
            )
            if btn_remover:
                _log("✅ Imagem detectada e garantida no projeto.")
                return True
            
            # 🛡️ HUNTER: Verifica botão Initial image com img
            botoes_initial = detectar_com_hunter(
                driver=self.driver,
                chave_memoria="flow_btn_initial_com_img",
                descricao_para_ia="Botão 'Initial image' contendo uma miniatura de imagem no Google Flow",
                seletores_rapidos=["//button[contains(@aria-label, 'Initial image') and .//img]"],
                palavras_semanticas=["initial", "image", "inicial"],
                etapa="FLOW_UPLOAD",
            )
            if botoes_initial:
                _log("✅ Miniatura de imagem garantida no botão Inicial.")
                return True
            
            _log("⚠️ O slot Inicial está vazio. Tentando re-vincular a imagem do projeto...")
            
            self.driver.refresh()
            time.sleep(5)
            self.acessar_flow()
            
            self._projeto_criado = False
            self._modelo_configurado = False
            self.clicar_novo_projeto()
            self.configurar_parametros_video()
            return self.anexar_imagem(caminho_imagem)
            
        except Exception as e:
            _log(f"Erro na rotina de hard-check da imagem: {e}")
            return False

    def _ler_texto_prompt_box(self, box: WebElement) -> str:
        try:
            return box.get_attribute("textContent") or box.text or ""
        except Exception:
            return ""

    def enviar_prompt_e_aguardar(self, prompt: str, timeout_geracao: int = 420, modo_imagem: bool = False) -> bool:
        import os
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support import expected_conditions as EC
        
        # Helper para clique via JS (se não tiver no seu arquivo, adicione no topo ou use driver.execute_script)
        def js_click(driver, element):
            driver.execute_script("arguments[0].click();", element)

        prompt_linear = remover_caracteres_nao_bmp(" ".join(prompt.split()))
        
        
        # 🛡️ GUARD: Tamanho máximo antes do send_keys (video prompts ~500-800 chars)
        MAX_PROMPT_VIDEO = 3000
        if len(prompt_linear) > MAX_PROMPT_VIDEO:
            _log(f"🚨 GUARD FLOW VIDEO: Prompt com {len(prompt_linear)} chars (max {MAX_PROMPT_VIDEO}). Prompt corrompido — ABORTANDO envio!")
            _log(f"🚨 Primeiros 200 chars: {prompt_linear[:200]}...")
            return False
        
        # Tenta salvar log do prompt se a função existir
        try:
            from integrations.utils import salvar_ultimo_prompt
            salvar_ultimo_prompt(f"--- PROMPT ENVIADO AO FLOW ---\n{prompt_linear}")
        except: pass
                                    
        for tentativa_local in range(1, 4):
            _log(f"[FLOW-IA] Iniciando tentativa local de prompt {tentativa_local}/3...")
            
            try:
                if not modo_imagem:
                    # --- 🛡️ VALIDAÇÃO CRÍTICA DO SLOT INICIAL (CORRIGIDA PARA MODO VÍDEO) ---
                    # No modo vídeo, a imagem vira um "chip" na barra inferior. O XPath antigo não achava.
                    xpath_chip_video = "//div[@role='textbox']/ancestor::div[position()<=3]//img | //button[contains(@aria-label, 'Remove') or contains(@aria-label, 'Close') or contains(@aria-label, 'Delete')]"
                    btn_img_chip = self.driver.find_elements(By.XPATH, xpath_chip_video)
                    
                    if not btn_img_chip:
                        _log("⚠️ O Flow removeu a imagem do slot! Revinculando...")
                        try:
                            xpath_btn_inicial = "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))] | //button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial')]"
                            botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                            
                            if botoes_iniciais and botoes_iniciais[0].is_displayed():
                                js_click(self.driver, botoes_iniciais[0])
                                time.sleep(2.0)
                                imgs_dialog = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//img")
                                if imgs_dialog:
                                    js_click(self.driver, imgs_dialog[0])
                                    _log("✔ Imagem selecionada. Aguardando a interface estabilizar...")
                                    time.sleep(2.5) 
                        except Exception as e:
                            _log(f"🚨 Erro ao revincular: {e}")
                    else:
                        _log("✔ Imagem de referência confirmada no slot (Chip detectado).")

                # --- 2. BUSCA DA CAIXA DE TEXTO (Híbrida para garantir foco) ---
                xpath_box = "//div[@role='dialog']//div[@role='textbox'] | //div[@role='dialog']//textarea | //div[@role='textbox' and @contenteditable='true'] | //textarea"
                caixas = self.driver.find_elements(By.XPATH, xpath_box)
                box = next((c for c in caixas if c.is_displayed()), None)
                
                if not box:
                    box = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_box)))

                # Garante visibilidade e foco sem desmarcar o slot
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
                self.driver.execute_script("arguments[0].focus();", box)
                js_click(self.driver, box) 
                time.sleep(0.5)

                # Limpeza de texto residual
                box.send_keys(Keys.CONTROL, "a")
                box.send_keys(Keys.BACKSPACE)
                time.sleep(0.5)

                _log("📸 Salvando print: ANTES de digitar o prompt.")
                salvar_print_debug(self.driver, f"FLOW_PROMPT_T{tentativa_local}_1_ANTES_DIGITAR")

                # --- 3. ESCRITA RESILIENTE ---
                is_headless = os.getenv('CHROME_HEADLESS', 'False').lower() == 'true'
                
                if is_headless:
                    _log(f"Modo Headless: Injetando prompt via execCommand + DispatchEvent...")
                    box.send_keys(prompt_linear)
                    # Essencial para disparar a validação do React/UI do Google
                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", box)
                else:
                    _log(f"Modo Visível: Colando prompt via Clipboard...")
                    import pyperclip
                    pyperclip.copy(prompt_linear)
                    box.send_keys(Keys.CONTROL, 'v')

                time.sleep(2.0) # Espera a UI processar o texto e habilitar o botão de gerar

                _log("📸 Salvando print: DEPOIS de digitar o prompt.")
                salvar_print_debug(self.driver, f"FLOW_PROMPT_T{tentativa_local}_2_POS_DIGITAR")

                # --- 4. SUBMISSÃO ---
                _log('Buscando botão de submissão (Seta/Send)...')
                xpath_submit = "//div[@role='dialog']//button[.//i[text()='arrow_upward' or text()='send' or text()='arrow_forward']] | //button[.//i[text()='arrow_upward' or text()='send' or text()='arrow_forward']] | //button[@aria-label='Gerar']"
                
                _log("📸 Salvando print: ANTES do clique de submissão.")
                salvar_print_debug(self.driver, f"FLOW_PROMPT_T{tentativa_local}_3_ANTES_SUBMIT")

                try:
                    btn_submit = self.driver.find_element(By.XPATH, xpath_submit)
                    if btn_submit.is_displayed():
                        self.momento_ultimo_submit = time.time()
                        js_click(self.driver, btn_submit)
                        _log("✔ Botão de submissão clicado.")
                    else:
                        raise Exception("Botão oculto")
                except:
                    _log("Botão não clicável, forçando ENTER...")
                    box.send_keys(Keys.ENTER)
                
                time.sleep(3)
                
                # --- 5. MONITORAMENTO DA GERAÇÃO ---
                if modo_imagem:
                    _log(f"Aguardando o botão 'Baixar' habilitar (máx {timeout_geracao}s)...")
                    xpath_btn_baixar = "//button[.//i[text()='download'] and (.//div[text()='Baixar'] or .//span[text()='Baixar'])]"
                    
                    fim_espera = time.time() + timeout_geracao

                    while time.time() < fim_espera:
                        # 🚨 CHECK 1: O Flow cuspiu erro fatal no canto?
                        if getattr(self, 'detectar_erro_fatal_flow', lambda: False)():
                            _log("🚨 [FALHA] Atividade incomum ou erro de política detectado. Abortando conta...")
                            return False # Isso sinaliza para o main.py trocar de conta

                        # Check do botão baixar
                        btns = self.driver.find_elements(By.XPATH, xpath_btn_baixar)
                        if btns and btns[0].is_displayed() and btns[0].get_attribute("disabled") is None:
                            
                            # 🚨 CHECK 2: Trava de 10 segundos (Evita o asset antigo/produto)
                            # Se habilitou rápido demais, ignoramos porque é resíduo da foto original
                            if (time.time() - self.momento_ultimo_submit) < 10:
                                time.sleep(2)
                                continue
                                
                            _log("✔ Geração concluída com sucesso!")
                            return True
                        
                        time.sleep(4)
                else:
                    # Usa seu sistema de tracking de progresso inline (barra de % no terminal)
                    if getattr(self, '_aguardar_geracao_tracking_inline', lambda p, t: False)(prompt_linear, timeout_geracao):
                        return True
                    else:
                        return False # Falhou na geração, aborta a tentativa local para o main.py recriar o projeto.
                
            except Exception as e:
                _log(f'Erro na tentativa local {tentativa_local}: {str(e)[:100]}')
                time.sleep(2)
                
        return False
    
    def _aguardar_geracao_imagem_sem_porcentagem(self, prompt: str, timeout: int = 60) -> bool:
        _log(f"Aguardando o card da nova imagem aparecer no feed central...")
        fim = time.time() + timeout
        ultimo_log = time.time()
        self.ultimo_tile_id_gerado = None
        
        while time.time() < fim:
            if not self.ultimo_tile_id_gerado:
                card = self._encontrar_card_por_prompt(prompt)
                if card:
                    self.ultimo_tile_id_gerado = self._obter_tile_id(card)
                else:
                    xpath_gerando = "//*[@data-tile-id and (.//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'gerando')] or .//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'generating')] or .//*[contains(@class, 'spin')])]"
                    cards_gerando = self.driver.find_elements(By.XPATH, xpath_gerando)
                    if cards_gerando:
                        self.ultimo_tile_id_gerado = self._obter_tile_id(cards_gerando[0])
            
            if not self.ultimo_tile_id_gerado:
                if time.time() - ultimo_log > 5:
                    self._print_progress_inline("[FLOW-IA] Aguardando o Google criar o novo card de imagem...")
                    ultimo_log = time.time()
                time.sleep(2)
                continue

            base_xpath = f"//*[@data-tile-id='{self.ultimo_tile_id_gerado}']"
            try:
                cards = self.driver.find_elements(By.XPATH, base_xpath)
                if cards:
                    card = cards[0]
                    txt = (card.text or "").lower()
                    
                    sucesso = card.find_elements(By.XPATH, ".//button[.//i[text()='download']] | .//img[not(contains(@src, 'blob')) and not(contains(@class, 'avatar'))]")
                    if sucesso:
                        self._finish_progress_inline("[FLOW-IA] ✔ Imagem gerada com sucesso no card correto!")
                        return True
                    
                    if "falha" in txt or "failed" in txt or "erro" in txt:
                        self._finish_progress_inline("[FLOW-IA] ❌ Card em estado de erro detectado.")
                        return False
                    
                    if time.time() - ultimo_log > 5:
                        self._print_progress_inline("[FLOW-IA] Imagem em processamento no feed...")
                        ultimo_log = time.time()
            except Exception:
                pass
            
            time.sleep(2)
            
        self._finish_progress_inline("[FLOW-IA] ❌ Timeout esgotado na geração da imagem.")
        return False

    def _listar_cards(self):
        return self.driver.find_elements(By.XPATH, "//*[@data-tile-id]")

    def _obter_tile_id(self, card):
        try:
            tid = card.get_attribute("data-tile-id")
            if tid: return tid
        except Exception: pass
        try:
            el = card.find_element(By.XPATH, ".//*[@data-tile-id]")
            tid = el.get_attribute("data-tile-id")
            if tid: return tid
        except Exception: pass
        return None

    def _encontrar_card_por_tile_id(self, tile_id: str):
        if not tile_id: return None
        try:
            return self.driver.find_element(By.XPATH, f"//*[@data-tile-id='{tile_id}']")
        except Exception: return None

    def _encontrar_card_por_prompt(self, prompt: str):
        trecho = prompt[:40].strip()
        cards = self._listar_cards()
        for c in cards:
            try:
                txt_bruto = self.driver.execute_script("return arguments[0].textContent;", c)
                if txt_bruto and trecho in txt_bruto: return c
            except Exception: pass
        return None

    def _card_mais_recente(self):
        cards = self._listar_cards()
        return cards[0] if cards else None

    def _aguardar_geracao_tracking_inline(self, prompt: str, timeout: int) -> bool:
        self._print_progress_inline("[FLOW-IA] Aguardando início da geração...")
        fim = time.time() + timeout
        self.ultimo_tile_id_gerado = None
        ultimo_movimento = time.time()
        viu_sinal_de_vida = False
        ultimo_percentual_logado = None
        ultimo_status_inline = None
        linha_progresso_ativa = True

        while time.time() < fim:
            if not self.ultimo_tile_id_gerado:
                card = self._encontrar_card_por_prompt(prompt) or self._card_mais_recente()
                if card: self.ultimo_tile_id_gerado = self._obter_tile_id(card)
                
                if not self.ultimo_tile_id_gerado:
                    self._print_progress_inline("[FLOW-IA] Gerando... aguardando card aparecer")
                    time.sleep(2)
                    continue
                else:
                    if linha_progresso_ativa:
                        self._finish_progress_inline()
                        linha_progresso_ativa = False
                    _log(f"Tile ID rastreado: {self.ultimo_tile_id_gerado}")
                    salvar_print_debug(self.driver, "FLOW_CARD_GERACAO_INICIO")

            base_xpath = f"//*[@data-tile-id='{self.ultimo_tile_id_gerado}']"

            # 🛡️ GRACE PERIOD: Não checa erro nos primeiros 20s (estados transitórios)
            tempo_desde_tile = time.time() - ultimo_movimento
            
            try:
                erros = self.driver.find_elements(By.XPATH, f"{base_xpath}//*[contains(text(), 'Falha') or contains(text(), 'Failed') or contains(text(), 'Erro')]")
                if erros and any(e.is_displayed() for e in erros):
                    # Cross-validação: se tem % de progresso visível, NÃO é erro real
                    txt_card = ""
                    try:
                        els = self.driver.find_elements(By.XPATH, base_xpath)
                        if els:
                            txt_card = self.driver.execute_script("return arguments[0].textContent;", els[0]) or ""
                    except: pass
                    
                    tem_progresso = bool(re.search(r'[1-9]\d?\s*%', txt_card))
                    
                    if tem_progresso:
                        pass  # Falso positivo: vídeo gerando com %, ignora o "erro"
                    elif tempo_desde_tile < 20:
                        pass  # Grace period: muito cedo para declarar erro
                    else:
                        if linha_progresso_ativa: self._finish_progress_inline("[FLOW-IA] Geração falhou.")
                        _log("❌ Card em estado de erro (Falha) detectado na interface.")
                        salvar_print_debug(self.driver,"ERRO_NO_CARD")
                        
                        # 🛡️ Detecta se é POLICY VIOLATION (conteúdo sexual/violação de política)
                        _termos_policy = ['violar', 'sexual', 'policy', 'políticas', 'política', 'violação']
                        if any(t in txt_card.lower() for t in _termos_policy):
                            _log("🚨 POLICY VIOLATION: O prompt foi bloqueado por violação de política do Flow!")
                            return "POLICY_VIOLATION"
                        
                        return False
            except Exception: pass

            try:
                sucesso = self.driver.find_elements(By.XPATH, f"{base_xpath}//video | {base_xpath}//img[contains(@alt, 'Gerado') or contains(@alt, 'Generated')] | {base_xpath}//i[contains(text(), 'play_circle')]")
                if sucesso:
                    if linha_progresso_ativa: self._finish_progress_inline("[FLOW-IA] Gerando... 100% | pronto!")
                    else: _log("✔ Artefato pronto e disponível para download.")
                    salvar_print_debug(self.driver, "FLOW_CARD_GERACAO_PRONTO")
                    return True
            except Exception: pass

            pct_atual = None
            try:
                elementos_card = self.driver.find_elements(By.XPATH, base_xpath)
                for el in elementos_card:
                    txt_bruto = self.driver.execute_script("return arguments[0].textContent;", el)
                    m = re.search(r'(100|[1-9]?\d)\s*%', txt_bruto or "")
                    if m:
                        pct_atual = m.group(0)
                        break
            except Exception: pass

            if pct_atual:
                viu_sinal_de_vida = True
                ultimo_movimento = time.time()
                if pct_atual != ultimo_percentual_logado:
                    self._print_progress_inline(f"[FLOW-IA] Gerando... {pct_atual}")
                    ultimo_percentual_logado = pct_atual
                    ultimo_status_inline = "percentual"
                    linha_progresso_ativa = True
            else:
                try:
                    loaders = self.driver.find_elements(By.XPATH, f"{base_xpath}//*[contains(@class, 'spin') or contains(text(), 'Generating') or contains(text(), 'Gerando')]")
                    if loaders:
                        viu_sinal_de_vida = True
                        ultimo_movimento = time.time()
                        if ultimo_status_inline != "processando":
                            self._print_progress_inline("[FLOW-IA] Gerando... processando")
                            ultimo_status_inline = "processando"
                            linha_progresso_ativa = True
                    else:
                        parado = int(time.time() - ultimo_movimento)
                        msg = f"[FLOW-IA] Gerando... aguardando progresso ({parado}s)"
                        if ultimo_status_inline != msg:
                            self._print_progress_inline(msg)
                            ultimo_status_inline = msg
                            linha_progresso_ativa = True
                        salvar_print_debug(self.driver,"GERANDO_ARTEFATO")   
                except Exception: pass

            if not viu_sinal_de_vida:
                if time.time() - ultimo_movimento > 60:
                    if linha_progresso_ativa: self._finish_progress_inline()
                    _log("❌ Card sem sinal de vida por 60s. Assumindo erro.")
                    return False
            else:
                if time.time() - ultimo_movimento > 60:
                    if linha_progresso_ativa: self._finish_progress_inline()
                    _log("❌ Card estagnado por muito tempo. Assumindo erro.")
                    return False
            time.sleep(2)

        if linha_progresso_ativa: self._finish_progress_inline()
        _log("Timeout esgotado na geração do artefato.")
        return False

    def resolver_permissoes_drive(self) -> None:
        try:
            continue_btn = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Continue')]")
            if continue_btn and continue_btn[0].is_displayed():
                js_click(self.driver, continue_btn[0])
                time.sleep(1.5)
                allow_btn = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Allow')]")
                if allow_btn and allow_btn[0].is_displayed():
                    js_click(self.driver, allow_btn[0])
                    time.sleep(1.5)
        except Exception: pass

    def _snapshot_arquivos(self, diretorio: Path, extensao: str = ".mp4") -> set[str]:
        diretorio.mkdir(parents=True, exist_ok=True)
        return {p.name for p in diretorio.glob(f"*{extensao}")}

    def _esperar_download_arquivo(self, download_dir: Path, antes: set[str], extensao: str = ".mp4", timeout=60) -> Path:
        fim = time.time() + timeout
        ultimo_temp = None
        while time.time() < fim:
            crdownloads = list(download_dir.glob("*.crdownload"))
            novos_arquivos = [p for p in download_dir.glob(f"*{extensao}") if p.name not in antes]
            
            if novos_arquivos and not crdownloads:
                novos_arquivos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                arquivo = novos_arquivos[0]
                _log(f"✔ Download concluído internamente no Windows: {arquivo.name}")
                return arquivo
            
            if crdownloads:
                crdownloads.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                atual = crdownloads[0]
                if ultimo_temp != atual.name:
                    _log(f"ℹ Baixando: {atual.name}")
                    ultimo_temp = atual.name
            time.sleep(1)
            
        raise TimeoutException(f"Timeout aguardando arquivo {extensao} no diretório.")

    def baixar_video_gerado(self, caminho_destino: Path) -> bool:
        """Abre o player, clica em baixar 720p e monitora QUALQUER novo arquivo na pasta local (estratégia faminta)."""
        _log(f'Iniciando download do vídeo para: {caminho_destino.name}')
        caminho_destino = Path(caminho_destino)
        
        # Sincronizado com o browser.py e sua função de imagem
        download_dir = Path("logs/downloads").resolve()
        
        try:
            # 1. 🧹 LIMPEZA PRÉVIA: Mata qualquer lixo antes de começar
            if download_dir.exists():
                for f in download_dir.glob("*"):
                    try: f.unlink()
                    except: pass
            else:
                download_dir.mkdir(parents=True, exist_ok=True)

            _log("Abrindo página do vídeo pronto...")
            card = None
            if self.ultimo_tile_id_gerado: 
                card = self._encontrar_card_por_tile_id(self.ultimo_tile_id_gerado)
            if not card: 
                card = self._card_mais_recente()
            
            if not card:
                _log("ERRO: Não encontrei card do vídeo pronto.")
                return False

            alvo_click = None
            try: alvo_click = card.find_element(By.XPATH, ".//button[contains(@class,'sc-d64366c4-1') and .//video]")
            except: pass
            if not alvo_click:
                try: alvo_click = card.find_element(By.XPATH, ".//video")
                except: pass

            if not alvo_click: return False

            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", alvo_click)
            time.sleep(0.5)
            js_click(self.driver, alvo_click)
            
            # Tempo para o player abrir
            time.sleep(4.0)
            salvar_print_debug(self.driver, f"FLOW_PLAYER_VIDEO_{caminho_destino.stem}")
            
            # =========================================================
            # --- BUSCA DO BOTÃO BAIXAR (XPath direto, sem cache) ---
            # =========================================================
            _log("Procurando botão 'Baixar'...")
            xpath_download = "//button[.//i[text()='download']]"

            btn_baixar = None
            try:
                btn_baixar = WebDriverWait(self.driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_download))
                )
            except TimeoutException:
                _log("ERRO: Botão Baixar não habilitou a tempo na tela do player.")
                salvar_print_debug(self.driver, f"FLOW_SEM_BTN_BAIXAR_{caminho_destino.stem}")
                return False

            try:
                btn_baixar.click()
            except:
                js_click(self.driver, btn_baixar)
            # =========================================================

            time.sleep(1.5) 
            salvar_print_debug(self.driver, f"FLOW_APOS_CLICK_BAIXAR_{caminho_destino.stem}")
            
            _log("Selecionando resolução 720p...")
            xpath_720p = "//button[@role='menuitem'][.//span[contains(.,'720p')]]"
            try:
                btn_720 = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_720p)))
                btn_720.click()
            except TimeoutException:
                options = self.driver.find_elements(By.XPATH, "//button[@role='menuitem']")
                if options: js_click(self.driver, options[0])
                else: return False
            
            self.resolver_permissoes_drive()
            
            _log(f'Monitorando surgimento de vídeo em: {download_dir}')
            
            # 2. 🕵️ MONITORAMENTO FAMINTO (Igual à sua função de imagem)
            arquivo_final = None
            fim_timeout = time.time() + 60 # Vídeos são mais pesados, mantemos 1 min
            
            while time.time() < fim_timeout:
                arquivos_na_pasta = list(download_dir.glob("*"))
                # Filtra fora os temporários
                validos = [f for f in arquivos_na_pasta if not f.name.endswith('.crdownload') and not f.name.endswith('.tmp')]
                
                if validos:
                    # O mais novo é o que acabou de cair
                    validos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    arquivo_final = validos[0]
                    break
                time.sleep(1)

            if not arquivo_final:
                raise TimeoutException("O download do vídeo não foi detectado após o clique.")

            _log(f"✔ Vídeo capturado: {arquivo_final.name}")

            # 3. 📦 FINALIZAÇÃO E RENOMEAÇÃO
            if caminho_destino.exists(): 
                caminho_destino.unlink()
            
            shutil.move(str(arquivo_final), str(caminho_destino))
            _log(f'✅ Vídeo salvo e renomeado: {caminho_destino.name}')
            
            # Limpa UI (Fecha o player)
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            return True

        except Exception as e:
            _log(f'Erro no download do vídeo: {e}')
            salvar_print_debug(self.driver, f"ERRO_FATAL_VIDEO_DOWN_{caminho_destino.stem}")
            return False

    def _baixar_imagem(self, caminho_destino: Path) -> Path:
        """Versão Blindada Radix UI: Força o download 1K usando os seletores reais do menu flutuante."""
        _log(f'Iniciando download da imagem para: {caminho_destino.name}')
        from integrations.utils import salvar_print_debug
        download_dir = Path("logs/downloads").resolve()
        
        try:
            # 1. 🧹 LIMPEZA PRÉVIA
            if download_dir.exists():
                for f in download_dir.glob("*"):
                    try: f.unlink()
                    except: pass
            else:
                download_dir.mkdir(parents=True, exist_ok=True)

            # 📸 Print de diagnóstico ANTES do download (para debug se falhar)
            salvar_print_debug(self.driver, f"FLOW_ANTES_DOWNLOAD_{caminho_destino.stem}")
            
            _log("Abrindo imagem pronta no centro da tela...")
            card = None
            if hasattr(self, 'ultimo_tile_id_gerado') and self.ultimo_tile_id_gerado:
                try: card = self.driver.find_element(By.XPATH, f"//div[@data-tile-id='{self.ultimo_tile_id_gerado}']")
                except: pass
            
            # Fallback se não achar pelo ID: pega o card mais recente (o primeiro da lista)
            if not card: 
                try:
                    cards = self.driver.find_elements(By.XPATH, "//div[@data-tile-id]")
                    if cards: card = cards[0]
                except: pass
                
            if card:
                try: js_click(self.driver, card)
                except: pass
            
            time.sleep(2.5)

            # =========================================================
            # --- BUSCA DO BOTÃO BAIXAR (XPath direto, sem cache) ---
            # =========================================================
            arquivo_final = None
            max_tentativas_download = 2

            for tentativa_dl in range(1, max_tentativas_download + 1):
                _log(f"📥 Tentativa de download {tentativa_dl}/{max_tentativas_download}...")
                
                xpath_download = "//button[.//i[text()='download']]"
                try:
                    btn_baixar = WebDriverWait(self.driver, 30).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_download))
                    )
                    
                    try:
                        btn_baixar.click()
                    except:
                        js_click(self.driver, btn_baixar)
                        
                    time.sleep(1.5)
                    
                    # Clica na opção 1K
                    xpath_1k = "//button[@role='menuitem'][.//span[contains(.,'1K')]]"
                    try:
                        btn_1k = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_1k)))
                        btn_1k.click()
                    except TimeoutException:
                        options = self.driver.find_elements(By.XPATH, "//button[@role='menuitem']")
                        if options: js_click(self.driver, options[0])
                        
                except TimeoutException:
                    _log("ERRO: Botão Baixar não habilitou a tempo na tela da imagem.")
                    continue
                
                time.sleep(2.0)
                self.resolver_permissoes_drive()
                
                # --- 🔍 VERIFICAÇÃO RÁPIDA: O download realmente iniciou? ---
                # Se em 8s não apareceu nenhum arquivo (nem .crdownload), o clique foi em vão.
                download_iniciou = False
                fim_verificacao = time.time() + 8
                while time.time() < fim_verificacao:
                    todos = list(download_dir.glob("*"))
                    if todos:
                        download_iniciou = True
                        break
                    time.sleep(0.5)
                
                if download_iniciou:
                    _log("✔ Download detectado na pasta! Aguardando conclusão...")
                    break  # Sai para o monitoramento completo abaixo
                else:
                    _log(f"⚠️ Nenhum arquivo surgiu após clique (tentativa {tentativa_dl}). Cache pode estar envenenado.")
                    salvar_print_debug(self.driver, f"FLOW_DOWNLOAD_FALHOU_T{tentativa_dl}_{caminho_destino.stem}")
                    
                    if tentativa_dl < max_tentativas_download:
                        # 🧹 PURGA DO CACHE: Limpa seletores envenenados e tenta do zero
                        _log("🧹 Limpando cache envenenado e retentando com seletores frescos...")
                        from integrations.self_healing import limpar_memoria_chave
                        for passo in passos_download:
                            limpar_memoria_chave(passo["chave"], "FLOW_DOWNLOAD_IMG")
                        
                        # Fecha qualquer menu residual antes de retentar
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            from selenium.webdriver.common.keys import Keys
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(1.0)
                        except: pass

            # --- 4. MONITORAMENTO DO DOWNLOAD (espera o arquivo final) ---
            _log(f'Monitorando surgimento de arquivo em: {download_dir}')
            fim_timeout = time.time() + 60 
            while time.time() < fim_timeout:
                validos = [f for f in download_dir.glob("*") if not f.name.endswith(('.crdownload', '.tmp'))]
                if validos:
                    validos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    arquivo_final = validos[0]
                    break
                time.sleep(1)

            if not arquivo_final:
                raise Exception("Arquivo não detectado na pasta após o clique de download.")

            # 5. 📦 FINALIZAÇÃO E LIMPEZA
            if caminho_destino.exists(): caminho_destino.unlink()
            
            import shutil
            shutil.move(str(arquivo_final), str(caminho_destino))
            _log(f'✅ Download concluído e renomeado: {caminho_destino.name}')
            
            # Fecha menu se sobrar aberto (ESC duplo)
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                from selenium.webdriver.common.keys import Keys
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.5)
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except: pass
            
            return caminho_destino

        except Exception as e:
            _log(f'🚨 Erro fatal no download 1K: {e}')
            salvar_print_debug(self.driver, f"ERRO_DOWNLOAD_1K_{caminho_destino.stem}")
            raise

    def _cacar_botao_download_inteligente(self) -> Optional[WebElement]:
        """
        Busca o botão de download/baixar em 3 camadas de inteligência (Heurística).
        """
        # --- CAMADA 1: XPaths robustos e rápidos ---
        seletores_rapidos = [
            "//button[.//i[text()='download']]",
            "//button[.//i[contains(@class, 'google-symbols') and text()='download']]",
            "//button[contains(@aria-label, 'Download') or contains(@aria-label, 'Baixar')]"
        ]
        for xpath in seletores_rapidos:
            try:
                botoes = self.driver.find_elements(By.XPATH, xpath)
                botoes_vis = [b for b in botoes if b.is_displayed() and b.get_attribute("disabled") is None]
                if botoes_vis:
                    return botoes_vis[-1] # Sempre pega o último (útil se tiver cards empilhados)
            except: pass

        _log("⚠️ Hunter: Botão óbvio não achado. Iniciando Varredura Semântica...")

        # --- CAMADA 2: Varredura Semântica (Procura no HTML oculto) ---
        try:
            botoes = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in reversed(botoes): # Ordem reversa para pegar os botões da frente primeiro
                if not btn.is_displayed() or btn.get_attribute("disabled") is not None: 
                    continue
                
                html_interno = (btn.get_attribute('innerHTML') or '').lower()
                aria = (btn.get_attribute('aria-label') or '').lower()
                
                if 'download' in html_interno or 'baixar' in html_interno or 'download' in aria or 'baixar' in aria:
                    _log("🎯 Hunter: Botão encontrado via HTML interno/Semântica!")
                    return btn
        except: pass

        _log("⚠️ Hunter: Varredura Semântica falhou. Iniciando Varredura de Ícones...")

        # --- CAMADA 3: Varredura visual/ícones ---
        try:
            botoes = self.driver.find_elements(By.XPATH, "//button[.//i or .//svg or .//mat-icon]")
            for btn in reversed(botoes):
                if not btn.is_displayed() or btn.get_attribute("disabled") is not None:
                    continue
                
                html_interno = (btn.get_attribute('innerHTML') or '').lower()
                if 'download' in html_interno or 'save_alt' in html_interno:
                    _log("🎯 Hunter: Botão encontrado via nome do ícone da fonte!")
                    return btn
        except: pass

        return None
    
    def detectar_erro_fatal_flow(self):
        """
        Verifica mensagens de bloqueio ou erro fatal na interface do Flow.
        Retorna True se houver erro, forçando a troca de conta no main.py.
        """
        try:
            # Termos chave baseados no comportamento real do Google Labs
            termos_fatais = [
                'unusual activity', 
                'atividade incomum', 
                'policy', 
                'não foi possível gerar',
                'something went wrong',
                'please visit',
                'falha'
            ]
            
            for termo in termos_fatais:
                # XPath Robusto: converte tudo para minúsculo antes de comparar
                xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{termo}')]"
                erros = self.driver.find_elements(By.XPATH, xpath)
                
                for e in erros:
                    if e.is_displayed():
                        _log(f"🚨 BLOQUEIO DETECTADO: Termo '{termo}' encontrado na tela.")
                        return True

            # Check extra por classes de erro CSS ou ícones de alerta
            seletores_extra = ["//div[contains(@class, 'error')]", "//mat-icon[text()='error']"]
            for sel in seletores_extra:
                extras = self.driver.find_elements(By.XPATH, sel)
                if any(ex.is_displayed() for ex in extras):
                    return True

            return False
        except Exception as e:
            _log(f"Erro ao verificar falhas fatais: {e}")
            return False
        
# =====================================================================
#   FUNÇÕES AUXILIARES DE PROCESSAMENTO (TEXTO)
# =====================================================================

def _remover_emojis(texto: str) -> str:
    padrao_emoji = re.compile(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF'
        r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\u2600-\u26FF\u2700-\u27BF\u2B50\u2B55\u23F0-\u23F3\u23F8-\u23FA\uFE0F]'
    )
    return padrao_emoji.sub(r'', texto)


def sanitizar_prompt_policy(prompt: str) -> str:
    """
    Remove ou substitui palavras/frases que ativam o filtro de 'conteúdo sexual'
    do Google Flow. Preserva a intenção criativa usando termos neutros.
    """
    # Substituições case-insensitive (original → neutro)
    _substituicoes = [
        # Cenário
        (r'\bin the bedroom\b', 'in a modern interior'),
        (r'\bbedroom\b', 'interior'),
        (r'\bin bed\b', 'in a cozy setting'),
        # Roupas íntimas / pijama com contexto corporal
        (r'\blingerie\b', 'sleepwear'),
        (r'\bpajama set\b', 'matching lounge outfit'),
        (r'\bpijama\b', 'lounge outfit'),
        (r'\bnightgown\b', 'lounge dress'),
        (r'\brobe\b', 'lounge robe'),
        # Expressões sensuais
        (r'\balluring\b', 'confident'),
        (r'\bseductive\b', 'confident'),
        (r'\bsensual\b', 'elegant'),
        (r'\bsensuality\b', 'elegance'),
        (r'\bsensualidade\b', 'elegância'),
        (r'\bsedoso\b', 'premium'),
        (r'\bsedosa\b', 'premium'),
        (r'\bsexy\b', 'stylish'),
        (r'\bintimate\b', 'personal'),
        (r'\bintimidade\b', 'conforto'),
        (r'\bdesejo\b', 'estilo'),
        (r'\bprovocante\b', 'sofisticada'),
        (r'\bsensorial\b', 'premium'),
        # Corpo
        (r'\bcurves\b', 'silhouette'),
        (r'\bbody-hugging\b', 'well-fitted'),
        (r'\bbody\s*con\b', 'fitted'),
        (r'\bcling(?:s|ing)?\s+to\s+(?:her|the)\s+body\b', 'drapes naturally'),
        (r'\bagainst her body\b', 'on the fabric'),
        (r'\bcleavage\b', 'neckline'),
        (r'\bdecote\b', 'gola'),
        # Autoestima em contexto íntimo
        (r'\bautoestima\b', 'confiança'),
        # V-neck em contexto de pijama pode ser gatilho
        (r'\bdeep V-neck\b', 'V-neckline'),
    ]
    
    resultado = prompt
    for padrao, substituto in _substituicoes:
        resultado = re.sub(padrao, substituto, resultado, flags=re.IGNORECASE)
    
    return resultado

def ler_e_separar_cenas(caminho_txt: Path, num_roteiro: int = 1, qtd_cenas: int = 3, variante: str = "") -> list[str]:
    """Lê do roteiros.txt (ou metadados.txt legado) fatiando pelo marcador do roteiro solicitado."""
    # Define os caminhos possíveis na mesma pasta
    roteiros = caminho_txt.parent / "roteiros.txt"
    metadados = caminho_txt.parent / "metadados.txt"
    
    # Prioridade: roteiros.txt > metadados.txt (legado) > arquivo individual (antigo)
    if roteiros.exists():
        arquivo_alvo = roteiros
    elif metadados.exists():
        arquivo_alvo = metadados
    else:
        arquivo_alvo = caminho_txt
    
    if not arquivo_alvo.exists():
        _log(f"⚠️ Arquivo não encontrado: {arquivo_alvo}")
        return []

    conteudo = arquivo_alvo.read_text(encoding='utf-8')
    
    # --- LÓGICA DE FATIAMENTO DO ARQUIVO UNIFICADO ---
    # 🛡️ CORREÇÃO: Verifica se o CONTEÚDO tem o marcador, não se roteiros.txt existe.
    # O metadados.txt TAMBÉM contém os blocos === ROTEIRO X_VARIANTE_Y ===
    if variante:
        tag_atual = f"=== ROTEIRO {num_roteiro}_{variante} ==="
    else:
        tag_atual = f"=== ROTEIRO {num_roteiro} ==="
        
    if tag_atual in conteudo:
        # Pega o texto que começa após a tag do roteiro solicitado
        bloco = conteudo.split(tag_atual)[1]
        
        # Corta antes do próximo === para não pegar outras coisas
        if "\n===" in bloco:
            bloco = bloco.split("\n===")[0]
    else:
        bloco = conteudo
        
    # --- LIMPEZA GERAL ---
    bloco = re.sub(r'<thinking>.*?</thinking>', '', bloco, flags=re.DOTALL)
    bloco = bloco.replace("Show thinking", "").replace("Gemini said", "").strip()
    
    # 🛡️ CORREÇÃO: Remove qualquer marcador === que tenha vazado para dentro do bloco
    bloco = re.sub(r'===\s*VARIANTE\s*\d+\s*===', '', bloco)
    bloco = re.sub(r'===\s*ROTEIRO\s*\d+[^=]*===', '', bloco)
    
    # Remove a parte da legenda do bloco para focar só nas cenas
    bloco = re.split(r'\[(?i:legenda).*?\]', bloco)[0].strip()
    
    partes = re.split(r'\[(?i:cena\s*\d+).*?\]', bloco)
    
    cenas_extraidas = []
    for i, texto_parcial in enumerate(partes):
        # Filtro de segurança para ignorar introduções da IA
        if i == 0 and "transform the input" not in texto_parcial.lower() and "câmera" not in texto_parcial.lower():
            continue 
            
        texto_limpo = texto_parcial.strip()
        if texto_limpo:
            cenas_extraidas.append(texto_limpo)
            
    _log(f"Análise de {arquivo_alvo.name} (Roteiro {num_roteiro}): {len(cenas_extraidas)} cenas extraídas.")
    
    if len(cenas_extraidas) < qtd_cenas:
        _log(f"⚠️ Aviso: O arquivo tem menos cenas que o esperado. Extraídas: {len(cenas_extraidas)}")
        
    return cenas_extraidas[:qtd_cenas]
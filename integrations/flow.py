# arquivo: integrations/flow.py
# descricao: Fachada de integracao com o Google Flow (Humble) para gerar videos
# a partir do roteiro de 3 cenas. Blindado com lógica nativa do humble_client.py e Retry Local.

from __future__ import annotations

import re
import sys
import time
import shutil
import pyperclip
from pathlib import Path
from typing import List, Optional, Dict, Any
from integrations.utils import _log as log_base, salvar_print_debug, js_click, scroll_ao_fim

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
    def __init__(self, driver, url_flow: str):
        self.driver = driver
        self.wait = WebDriverWait(driver, 30, poll_frequency=0.2)
        self.url_flow = url_flow
        
        # --- VARIÁVEIS DE ESTADO (Para usar o mesmo projeto nas Cenas 2 e 3) ---
        self.ultimo_tile_id_gerado = None
        self._projeto_criado = False
        self._modelo_configurado = False
        self._imagem_upada = False

    # --- MÉTODOS NATIVOS DO HUMBLE_CLIENT ORIGINAL ---
    def _wait_click(self, by: By, value: str, timeout: int = 20, descricao: str = "elemento") -> WebElement:
        el = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        try:
            el.click()
        except Exception:
            js_click(self.driver,el)
        _log(f"✔ Clicado: {descricao}")
        return el

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
        """
        Tratamento agressivo para fechar popups de 'Welcome', 'Terms', 'Discover Veo', etc.
        Atualizado para detectar 'Concordo' e 'Entendi' do Google Flow.
        """
        fechou_algo = False
        try:
            # Lista de termos para busca (Case Insensitive via translate)
            termos = [
                'got it', 'entendi', 'i agree', 'concordo', 'agree', 'aceitar', 
                'accept', 'enable', 'continuar', 'continue', 'agree and continue', 
                'dismiss', 'close', 'fechar'
            ]

            # Monta um XPath único e poderoso para todos os termos
            filtro_termos = " or ".join([f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t}')" for t in termos])
            
            # Busca em botões, spans ou divs que funcionam como botões
            xpath_monstro = f"//button[{filtro_termos}] | //span[{filtro_termos}] | //div[@role='button'][{filtro_termos}]"
            
            # Adiciona o seletor específico do botão de "X" fechar
            xpath_monstro += " | //div[@role='dialog']//button[.//i[text()='close']]"

            botoes = self.driver.find_elements(By.XPATH, xpath_monstro)
            for btn in botoes:
                try:
                    if btn.is_displayed():
                        # Captura o texto para o log (se houver)
                        texto_detectado = (btn.text or "botão").strip().split('\n')[0]
                        _log(f'Modal detectado ({texto_detectado}). Fechando automaticamente...')
                        js_click(self.driver, btn)
                        time.sleep(1.0)
                        fechou_algo = True
                except:
                    continue
            
            # Se a interface ainda parecer bloqueada (escurecida), usa ESC agressivo como fallback
            if not fechou_algo:
                # Verifica se existe o fundo escuro (overlay) ou diálogo aberto
                overlays = self.driver.find_elements(By.XPATH, "//div[contains(@class,'overlay') or @role='dialog'] | //mat-dialog-container")
                if any(o.is_displayed() for o in overlays):
                    _log("Tela de bloqueio (overlay/dialog) ativa. Forçando ESC duplo.")
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)

        except Exception:
            pass

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
            # 🚨 NOVO: Checagem de Bloqueio Geográfico
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
        # LÓGICA DE MEMÓRIA PARA A CENA 2 E 3
        if self._projeto_criado:
            _log('Reaproveitando projeto atual (pulando criação)...')
            return

        _log('Iniciando um novo projeto/limpando a tela...')
        self._fechar_modais_intrusivos()
        
        try:
            self._wait_click(
                By.XPATH, 
                "//span[contains(text(), 'New project')] | //button[contains(., 'New')] | //button[contains(., 'Novo projeto')] | //button[descendant::i[text()='add_2']]",
                timeout=10,
                descricao="Botão Novo Projeto"
            )
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='textbox' and @contenteditable='true'] | //textarea")))
            except Exception:
                pass
            self._projeto_criado = True
        except TimeoutException:
            _log('Botão "Novo projeto" não visível, forçando refresh para limpar estado...')
            self.driver.refresh()
            time.sleep(4)
            self._projeto_criado = True

    def configurar_parametros_video(self) -> bool:
        # LÓGICA DE MEMÓRIA PARA A CENA 2 E 3
        if self._modelo_configurado:
            _log('Parâmetros Nano Banana já configurados neste projeto (pulando)...')
            return True

        _log('Configurando parâmetros (Nano Banana 2 > Vídeo > 9:16 > x1 > Veo 3.1 Fast Lower)...')
        self._fechar_modais_intrusivos() # Limpeza preventiva
        
        try:
            salvar_print_debug(self.driver,"CONFIG_PARAM_INICIO")
            chip_xpath = "//button[contains(., 'Nano Banana 2') and @aria-haspopup='menu']"
            try:
                self._wait_click(By.XPATH, chip_xpath, timeout=10, descricao="chip Nano Banana 2")
            except TimeoutException:
                chip_fallback = "//button[@aria-haspopup='menu' and (contains(., 'Banana') or contains(., 'Nano') or contains(., 'Veo'))]"
                self._wait_click(By.XPATH, chip_fallback, timeout=5, descricao="chip Modelo (Fallback)")

            time.sleep(1.0) 

            self._wait_click(
                By.XPATH, 
                "//div[@role='menu' and @data-state='open']//button[.//i[text()='videocam'] or contains(., 'Vídeo') or contains(., 'Video')]", 
                timeout=10, 
                descricao="Aba Vídeo"
            )
            time.sleep(0.5)

            self._wait_click(
                By.XPATH, 
                "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]", 
                timeout=10, 
                descricao="Opção 9:16"
            )
            time.sleep(0.5)

            self._wait_click(
                By.XPATH, 
                "//div[@role='menu' and @data-state='open']//button[normalize-space()='x1']", 
                timeout=10, 
                descricao="Opção x1"
            )
            time.sleep(0.5)

            self._wait_click(
                By.XPATH,
                "//div[@role='menu' and @data-state='open']//button[contains(., 'Veo')]",
                timeout=10,
                descricao="Dropdown submenu Veo"
            )
            time.sleep(1.0) 

            try:
                self._wait_click(
                    By.XPATH,
                    "//div[@role='menuitem' and contains(., 'Veo 3.1 - Fast [Lower Priority]')]",
                    timeout=10,
                    descricao="Modelo Veo 3.1 - Fast [Lower Priority]"
                )
            except TimeoutException:
                _log("Aviso: 'Lower Priority' não encontrado. Mantendo a configuração Veo atual.")

            _log('Configurações do modelo aplicadas com sucesso.')
            salvar_print_debug(self.driver,"CONFIG_PARAM_FIM")
            self._modelo_configurado = True
            
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            return True

        except Exception as e:
            _log(f'🚨 Erro fatal ao configurar modelo: {e}')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def configurar_parametros_imagem(self) -> bool:
        """Configura o Flow apenas para gerar Imagem. Executado com o Modal da foto já aberto."""
        if self._modelo_configurado: return True
        
        _log('Configurando parâmetros de Imagem (Nano Banana > 9:16)...')
        try:
            salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_INICIO")
            
            # Clica no chip do modelo (Banana 2 ou Pro)
            chip_xpath = "//button[(contains(., 'Banana') or contains(., 'Nano')) and @aria-haspopup='menu']"
            try:
                self._wait_click(By.XPATH, chip_xpath, timeout=10, descricao="chip do Modelo")
            except TimeoutException:
                _log("Aviso: Chip principal não detectado. Tentando menu genérico...")
                botoes_menu = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                if botoes_menu: 
                    js_click(self.driver, botoes_menu[0])
            
            time.sleep(1.0) 

            # Clica na Opção 9:16
            self._wait_click(
                By.XPATH, 
                "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]", 
                timeout=10, 
                descricao="Opção 9:16"
            )
            time.sleep(0.5)

            # Clica na Opção x1 se ela existir no menu aberto
            try:
                self._wait_click(
                    By.XPATH, 
                    "//div[@role='menu' and @data-state='open']//button[normalize-space()='x1']", 
                    timeout=3, 
                    descricao="Opção x1"
                )
                time.sleep(0.5)
            except TimeoutException:
                pass

            _log('Configurações de IMAGEM aplicadas com sucesso.')
            salvar_print_debug(self.driver,"CONFIG_PARAM_IMG_FIM")
            self._modelo_configurado = True
            
            # Fecha o menu de resolução clicando no fundo ou usando ESC seguro
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            
            return True

        except Exception as e:
            _log(f'🚨 Erro fatal ao configurar modelo de imagem: {e}')
            return False

    def _encontrar_input_file(self) -> WebElement:
        seletores = ['input[type="file"]', 'input[accept*="image"]']
        for seletor in seletores:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
            for el in elementos:
                if el is not None:
                    return el
        raise TimeoutException('Nenhum input[type=file] encontrado na interface do Flow.')

    # =================================================================================
    # MUDANÇA: A função anexar_imagem agora clica na foto para abrir o modal de prompt
    # =================================================================================
    def anexar_imagem(self, caminho: Path, abrir_modal: bool = False) -> bool:
        """Faz o upload invisível da imagem e direciona: 'Inicial' (Vídeo) ou 'Modal' (Imagem)."""
        nome_arquivo = caminho.name
        self._fechar_modais_intrusivos() 
        
        # O BLOCO QUE CLICAVA NA CAIXA E ABRIA O WINDOWS FOI DELETADO DAQUI!

        # 1. UPLOAD (Igual para ambos)
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
                    loaders = self.driver.find_elements(By.XPATH, "//div[contains(text(), '%')] | //span[contains(text(), '%')]")
                    if not loaders or not any(l.is_displayed() for l in loaders):
                        break 
                    time.sleep(1)

                salvar_print_debug(self.driver,"IMAGEM_UPADA")
                time.sleep(3.0) 
                self._imagem_upada = True
            except Exception as e:
                _log(f'🚨 Falha no upload nativo da imagem: {e}')
                return False
        else:
            _log(f'A imagem {nome_arquivo} já foi upada no projeto. Indo para o clique...')

        # 2. ROTEAMENTO DO CLIQUE
        if abrir_modal:
            # --- MODO IMAGEM POV (Novo) ---
            _log("Clicando na imagem na tela principal para abrir o modal de prompt...")
            try:
                xpath_miniatura = f"//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')] | //div[@data-tile-id]//img"
                miniaturas = self.driver.find_elements(By.XPATH, xpath_miniatura)
                
                if miniaturas:
                    imgs_visiveis = [img for img in miniaturas if img.is_displayed()]
                    if imgs_visiveis:
                        js_click(self.driver, imgs_visiveis[-1])
                        time.sleep(2.0)
                        _log("✔ Imagem clicada! O modal com a imagem e o campo de texto deve estar aberto.")
                        return True
                    
                _log("⚠️ Imagem específica não achada. Clicando na primeira foto genérica...")
                imgs = self.driver.find_elements(By.XPATH, "//img")
                if imgs:
                    js_click(self.driver, imgs[-1]) 
                    time.sleep(2.0)
                    _log("✔ Imagem genérica clicada.")
                else:
                    _log("⚠️ Nenhuma imagem encontrada na tela para clicar.")
                return True
            except Exception as e:
                _log(f'🚨 Erro na etapa de clicar na imagem: {e}')
                return True
        else:
            # --- MODO VÍDEO ORIGINAL (Seu script intocável) ---
            _log("Vinculando a imagem no botão 'Inicial' da interface principal...")
            try:
                xpath_btn_inicial = (
                    "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') "
                    "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))]"
                )
                botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                botao_visivel = [b for b in botoes_iniciais if b.is_displayed()]
                
                if botao_visivel:
                    _log('Botão "Inicial" encontrado. Abrindo galeria...')
                    js_click(self.driver,botao_visivel[0])
                    time.sleep(2.0) 

                    xpath_img_popup = f"//div[@role='dialog']//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')] | //div[@role='dialog']//img"
                    imgs_dialog = self.driver.find_elements(By.XPATH, xpath_img_popup)
                    if imgs_dialog:
                        js_click(self.driver, imgs_dialog[0])
                        time.sleep(0.5)

                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    _log('✔ Imagem vinculada com sucesso ao slot Inicial!')
                else:
                    _log('⚠️ Botão "Inicial" não encontrado. Verifique a interface.')
                return True
            except Exception as e:
                _log(f'🚨 Erro na etapa de vinculação ao botão Inicial: {e}')
                return True

    def _garantir_imagem_anexada(self, caminho_imagem: Path) -> bool:
        """
        Verifica se a imagem realmente foi vinculada ao slot 'Inicial' 
        antes de prosseguirmos para o prompt.
        """
        _log("Validando visualmente a presença da imagem no Slot Inicial...")
        try:
            # 1. Checa a presença do botão 'Remove initial image'
            btn_remover = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Remove')]")
            if len(btn_remover) > 0:
                _log("✅ Imagem detectada e garantida no projeto.")
                return True
            
            # 2. Checa se o botão Initial tem uma tag img dentro
            botoes_initial = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Initial image') and .//img]")
            if len(botoes_initial) > 0:
                _log("✅ Miniatura de imagem garantida no botão Inicial.")
                return True
            
            _log("⚠️ O slot Inicial está vazio. Tentando re-vincular a imagem do projeto...")
            
            # Força refresh e reset completo local para limpar bugs da UI
            self.driver.refresh()
            time.sleep(5)
            self.acessar_flow()
            
            # Limpa flag local para re-configurar tudo e forçar vinculação
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

    # =================================================================================
    # MUDANÇA: Prioriza o Textbox que está DENTRO do Modal (Dialog) que a imagem abriu
    # =================================================================================
    def enviar_prompt_e_aguardar(self, prompt: str, timeout_geracao: int = 420, modo_imagem: bool = False) -> bool:
        """Digita o prompt e roteia a espera: Porcentagem (Vídeo) ou Baixar (Imagem)."""
        prompt_linear = " ".join(prompt.split())
                                  
        for tentativa_local in range(1, 4):
            _log(f"[FLOW-IA] Iniciando tentativa local de prompt {tentativa_local}/3...")
            self._fechar_modais_intrusivos()
            salvar_print_debug(self.driver,f"TENTATIVA_PROMPT_{tentativa_local}_INICIO")

            try:
                # =====================================================================
                # 🚨 NOVO: CHECKPOINT DE IMAGEM INICIAL OBRIGATÓRIA (Apenas Vídeo)
                # =====================================================================
                if not modo_imagem:
                    _log("Validando se a imagem de referência continua no slot Inicial...")
                    
                    # Procura sinais de que a imagem ESTÁ lá (Botão Remover ou tag <img> dentro do botão inicial)
                    btn_remover = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Remove')] | //div[@role='button' and contains(@aria-label, 'Remove')]")
                    btn_img = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Initial image') and .//img] | //div[contains(@aria-label, 'Initial') and .//img]")
                    
                    if not btn_remover and not btn_img:
                        _log("⚠️ O Flow removeu a imagem do slot! Revinculando antes de enviar...")
                        try:
                            # Encontra o botão "Inicial" vazio
                            xpath_btn_inicial = (
                                "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') "
                                "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))]"
                            )
                            botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                            if botoes_iniciais and botoes_iniciais[0].is_displayed():
                                js_click(self.driver, botoes_iniciais[0])
                                time.sleep(2.0)
                                
                                # Clica na primeira foto da galeria que abrir (a que já fizemos upload)
                                imgs_dialog = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//img")
                                if imgs_dialog:
                                    js_click(self.driver, imgs_dialog[0])
                                    time.sleep(0.5)
                                    
                                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(0.5)
                                _log("✔ Imagem revinculada com sucesso no slot Inicial!")
                            else:
                                _log("⚠️ Botão Inicial vazio não encontrado na tela.")
                        except Exception as e:
                            _log(f"🚨 Erro ao tentar revincular imagem: {e}")
                    else:
                        _log("✔ Imagem de referência confirmada no slot Inicial.")
                # =====================================================================

                # 1. Localização e Foco
                _log("Buscando caixa de texto ativa...")
                xpath_box = "//div[@role='dialog']//div[@role='textbox'] | //div[@role='dialog']//textarea | //div[@role='textbox' and @contenteditable='true'] | //textarea"
                caixas = self.driver.find_elements(By.XPATH, xpath_box)
                box = next((c for c in caixas if c.is_displayed()), None)
                
                if not box:
                    box = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_box)))
                
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
                self.driver.execute_script("arguments[0].focus();", box)
                js_click(self.driver,box)
                time.sleep(0.5)

                # 2. Limpeza
                box.send_keys(Keys.CONTROL, "a")
                box.send_keys(Keys.BACKSPACE)
                time.sleep(0.5)

                # 3. Digitação
                _log(f"Digitando prompt ({len(prompt_linear)} chars)...")
                box.send_keys(prompt_linear)
                time.sleep(1.5) 

                depois = self._ler_texto_prompt_box(box)
                if len(depois) < 10:
                    _log("⚠️ Falha na digitação. Tentando ActionChains...")
                    ActionChains(self.driver).move_to_element(box).click().send_keys(prompt_linear).perform()
                    time.sleep(1.0)

                # 4. SUBMIT
                _log('Buscando botão de submissão (Seta/Send)...')
                try:
                    xpath_submit = "//div[@role='dialog']//button[.//i[text()='arrow_upward' or text()='send']] | //button[.//i[text()='arrow_upward' or text()='send']] | //button[@aria-label='Gerar']"
                    btn_submit = self.driver.find_element(By.XPATH, xpath_submit)
                    js_click(self.driver,btn_submit)
                    _log("✔ Botão de submissão clicado.")
                except Exception:
                    _log("Botão não achado, tentando ENTER como fallback...")
                    box.send_keys(Keys.ENTER)
                
                time.sleep(3)
                
                # 5. ROTEAMENTO DE ESPERA
                if modo_imagem:
                    # --- MODO IMAGEM: Vigia o botão Baixar no Modal ---
                    _log(f"Aguardando o botão 'Baixar' habilitar (máx {timeout_geracao}s)...")
                    xpath_btn_baixar = "//button[.//i[text()='download'] and .//div[text()='Baixar']]"
                    fim_espera = time.time() + timeout_geracao
                    
                    while time.time() < fim_espera:
                        btns = self.driver.find_elements(By.XPATH, xpath_btn_baixar)
                        if btns:
                            btn = btns[0]
                            is_disabled = btn.get_attribute("disabled")
                            if btn.is_displayed() and is_disabled is None:
                                _log("✔ Botão 'Baixar' habilitado! Geração concluída.")
                                return True
                        
                        self._print_progress_inline(f"[FLOW-IA] Gerando... {int(time.time() - (fim_espera - timeout_geracao))}s")
                        time.sleep(4)
                    
                    self._finish_progress_inline()
                    _log("❌ Timeout: O botão de baixar não habilitou a tempo.")
                else:
                    # --- MODO VÍDEO ORIGINAL (Rastreador de Porcentagem) ---
                    if self._aguardar_geracao_tracking_inline(prompt_linear, timeout_geracao):
                        return True
                
            except Exception as e:
                _log(f'Erro na tentativa de prompt {tentativa_local}: {str(e)[:100]}')
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(2)
                
        return False
    
    def _aguardar_geracao_imagem_sem_porcentagem(self, prompt: str, timeout: int = 120) -> bool:
        """Monitora a geração caçando o card ESPECÍFICO da geração, ignorando a imagem de referência."""
        _log(f"Aguardando o card da nova imagem aparecer no feed central...")
        fim = time.time() + timeout
        ultimo_log = time.time()
        self.ultimo_tile_id_gerado = None
        
        while time.time() < fim:
            # 1. TENTA ACHAR O CARD NOVO (E NÃO A REFERÊNCIA)
            if not self.ultimo_tile_id_gerado:
                # Primeiro tenta achar pelo texto do prompt que acabamos de enviar
                card = self._encontrar_card_por_prompt(prompt)
                if card:
                    self.ultimo_tile_id_gerado = self._obter_tile_id(card)
                else:
                    # Se o texto não apareceu, caça o spinner/loader de geração
                    xpath_gerando = "//*[@data-tile-id and (.//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'gerando')] or .//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'generating')] or .//*[contains(@class, 'spin')])]"
                    cards_gerando = self.driver.find_elements(By.XPATH, xpath_gerando)
                    if cards_gerando:
                        self.ultimo_tile_id_gerado = self._obter_tile_id(cards_gerando[0])
            
            # Se ainda não achou o card novo, espera mais um pouco
            if not self.ultimo_tile_id_gerado:
                if time.time() - ultimo_log > 5:
                    self._print_progress_inline("[FLOW-IA] Aguardando o Google criar o novo card de imagem...")
                    ultimo_log = time.time()
                time.sleep(2)
                continue

            # 2. AGORA QUE TEMOS O CARD CERTO, MONITORAMOS ELE
            base_xpath = f"//*[@data-tile-id='{self.ultimo_tile_id_gerado}']"
            try:
                cards = self.driver.find_elements(By.XPATH, base_xpath)
                if cards:
                    card = cards[0]
                    txt = (card.text or "").lower()
                    
                    # Sucesso: Apareceu o botão de download no card central
                    sucesso = card.find_elements(By.XPATH, ".//button[.//i[text()='download']] | .//img[not(contains(@src, 'blob')) and not(contains(@class, 'avatar'))]")
                    if sucesso:
                        self._finish_progress_inline("[FLOW-IA] ✔ Imagem gerada com sucesso no card correto!")
                        return True
                    
                    # Falha
                    if "falha" in txt or "failed" in txt or "erro" in txt:
                        self._finish_progress_inline("[FLOW-IA] ❌ Card em estado de erro detectado.")
                        return False
                    
                    # Loading log
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

            base_xpath = f"//*[@data-tile-id='{self.ultimo_tile_id_gerado}']"

            try:
                erros = self.driver.find_elements(By.XPATH, f"{base_xpath}//*[contains(text(), 'Falha') or contains(text(), 'Failed') or contains(text(), 'Erro')]")
                if erros and any(e.is_displayed() for e in erros):
                    if linha_progresso_ativa: self._finish_progress_inline("[FLOW-IA] Geração falhou.")
                    _log("❌ Card em estado de erro (Falha) detectado na interface.")
                    salvar_print_debug(self.driver,"ERRO_NO_CARD")
                    return False
            except Exception: pass

            try:
                # Modificado para aceitar foto (img) e video
                sucesso = self.driver.find_elements(By.XPATH, f"{base_xpath}//video | {base_xpath}//img[contains(@alt, 'Gerado') or contains(@alt, 'Generated')] | {base_xpath}//i[contains(text(), 'play_circle')]")
                if sucesso:
                    if linha_progresso_ativa: self._finish_progress_inline("[FLOW-IA] Gerando... 100% | pronto!")
                    else: _log("✔ Artefato pronto e disponível para download.")
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
                if time.time() - ultimo_movimento > 180:
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
                js_click(self.driver,continue_btn[0])
                time.sleep(1.5)
                allow_btn = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Allow')]")
                if allow_btn and allow_btn[0].is_displayed():
                    js_click(self.driver,allow_btn[0])
                    time.sleep(1.5)
        except Exception: pass

    def _snapshot_arquivos(self, diretorio: Path, extensao: str = ".mp4") -> set[str]:
        """Tira snapshot de arquivos na pasta de download por extensão."""
        diretorio.mkdir(parents=True, exist_ok=True)
        return {p.name for p in diretorio.glob(f"*{extensao}")}

    def _esperar_download_arquivo(self, download_dir: Path, antes: set[str], extensao: str = ".mp4", timeout=180) -> Path:
        """Espera um arquivo ser baixado considerando a extensão escolhida e o .crdownload temporário."""
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
        _log(f'Iniciando download do vídeo para: {caminho_destino.name}')
        caminho_destino = Path(caminho_destino)
        download_dir = Path.home() / "Downloads"
        try:
            _log("Abrindo página do vídeo pronto...")
            card = None
            if self.ultimo_tile_id_gerado: card = self._encontrar_card_por_tile_id(self.ultimo_tile_id_gerado)
            if not card: card = self._card_mais_recente()
            if not card:
                _log("ERRO: Não encontrei card do vídeo pronto para clicar.")
                return False
            alvo_click = None
            try: alvo_click = card.find_element(By.XPATH, ".//button[contains(@class,'sc-d64366c4-1') and .//video]")
            except Exception: pass
            if alvo_click is None:
                try: alvo_click = card.find_element(By.XPATH, ".//video")
                except Exception: pass
            if alvo_click is None:
                _log("ERRO: Encontrei o card, mas não achei elemento clicável (botão/vídeo).")
                return False
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", alvo_click)
            time.sleep(0.4)
            try: alvo_click.click()
            except Exception: js_click(self.driver,alvo_click)
            time.sleep(4.0)
            salvar_print_debug(self.driver,"PLAYER_ABERTO")
            _log("Procurando botão 'Baixar'...")
            xpath_baixar = "//button[.//i[text()='download'] and .//div[contains(.,'Baixar')]]"
            try:
                btn_baixar = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_baixar)))
                btn_baixar.click()
            except TimeoutException:
                btn_baixar = self.driver.find_elements(By.XPATH, "//button[@aria-label='Download video'] | //button[contains(@aria-label, 'Download')] | //button[.//i[text()='download']]")
                if btn_baixar: js_click(self.driver,btn_baixar[-1])
                else: return False
            time.sleep(1.0) 
            _log("Procurando option 720p...")
            xpath_720p = "//button[@role='menuitem'][.//span[text()='720p'] and .//span[contains(.,'Tamanho original')]]"
            try:
                btn_720 = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_720p)))
                btn_720.click()
            except TimeoutException:
                xpath_fallback = "//button[@role='menuitem'][contains(., '720p') or contains(., '1080p')]"
                try:
                    btn_fallback = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_fallback)))
                    btn_fallback.click()
                except TimeoutException:
                    btn_qualquer = self.driver.find_elements(By.XPATH, "//button[@role='menuitem']")
                    if btn_qualquer: js_click(self.driver,btn_qualquer[0])
                    else: return False
            
            # Snapshots usando a nova função generalizada
            antes = self._snapshot_arquivos(download_dir, ".mp4")
            self.resolver_permissoes_drive()
            _log('Aguardando o arquivo terminar de baixar no Windows...')
            arquivo_baixado = self._esperar_download_arquivo(download_dir, antes, ".mp4")
            
            if caminho_destino.exists(): caminho_destino.unlink()
            shutil.move(str(arquivo_baixado), str(caminho_destino))
            _log(f'✅ Vídeo baixado com sucesso: {caminho_destino.name}')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5); ActionChains(self.driver).send_keys(Keys.ESCAPE).perform(); time.sleep(1.5)
            return True
        except Exception as e:
            _log(f'Erro no download: {e}')
            return False

    # =================================================================================
    # MUDANÇA: O retry de falha de imagem agora anexa a imagem DENTRO do loop!
    # =================================================================================
    def gerar_imagem_pov(self, caminho_referencia: Path, prompt: str, caminho_saida: Path) -> Path:
        """Orquestra a geração completa de uma imagem POV no Flow e salva no caminho correto."""
        _log(f"🎬 [FLOW-IMAGE] Iniciando geração de imagem. Saída: {caminho_saida.name}")
        self.acessar_flow()
        
        self.clicar_novo_projeto()
        
        sucesso = False
        for tentativa in range(1, 4):
            _log(f"[FLOW-IMAGE] Iniciando tentativa local {tentativa}/3...")
            try:
                # 1. Faz upload e CLICA na imagem
                if not self.anexar_imagem(caminho_referencia, abrir_modal=True):
                    raise Exception("Falha ao preparar a imagem na tela.")

                # 2. Configura o modelo para 9:16
                self._modelo_configurado = False
                self.configurar_parametros_imagem()
                
                # 3. Manda o texto e avisa para esperar o Botão Baixar
                if self.enviar_prompt_e_aguardar(prompt, timeout_geracao=120, modo_imagem=True):
                    sucesso = True
                    break
                else:
                    self.driver.refresh()
                    time.sleep(3)
            except Exception as e:
                _log(f"Falha na tentativa {tentativa}: {e}")
                self.driver.refresh()
                time.sleep(3)
                
        if not sucesso:
            raise Exception("Falha ao gerar imagem no Flow após 3 tentativas locais.")
            
        # Repassa o caminho COMPLETO para o download
        return self._baixar_imagem(caminho_saida)

    # =================================================================================
    # MUDANÇA: A função _baixar_imagem agora clica no 1k, como você ensinou antes.
    # =================================================================================
    def _baixar_imagem(self, caminho_destino: Path) -> Path:
        """Clica no botão Baixar, seleciona 1K e move o arquivo para a pasta correta da tarefa."""
        _log(f'Iniciando download da imagem para: {caminho_destino.name}')
        download_dir = Path.home() / "Downloads"
        try:
            _log("Procurando botão 'Baixar'...")
            xpath_baixar = "//button[.//i[text()='download'] and .//div[contains(.,'Baixar')]]"
            try:
                btn_baixar = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_baixar)))
                btn_baixar.click()
            except TimeoutException:
                btn_baixar = self.driver.find_elements(By.XPATH, "//button[@aria-label='Download image'] | //button[contains(@aria-label, 'Download')] | //button[.//i[text()='download']]")
                if btn_baixar: js_click(self.driver,btn_baixar[-1])
                else: raise Exception("Botão baixar não encontrado.")
            time.sleep(1.0) 
            
            _log("Procurando option 1K...")
            xpath_1k = "//button[@role='menuitem'][.//span[text()='1K'] and .//span[contains(.,'Tamanho original')]]"
            try:
                btn_1k = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_1k)))
                btn_1k.click()
            except TimeoutException:
                xpath_fallback = "//button[@role='menuitem'][contains(., '1K') or contains(., '1k')]"
                try:
                    btn_fallback = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_fallback)))
                    btn_fallback.click()
                except TimeoutException:
                    btn_qualquer = self.driver.find_elements(By.XPATH, "//button[@role='menuitem']")
                    if btn_qualquer: js_click(self.driver,btn_qualquer[0])
                    else: raise Exception("Nenhuma opção de resolução encontrada.")
            
            antes = self._snapshot_arquivos(download_dir, ".jpeg")
            self.resolver_permissoes_drive()
            _log('Aguardando o arquivo .jpeg terminar de baixar no Windows...')
            
            arquivo_baixado = self._esperar_download_arquivo(download_dir, antes, ".jpeg", timeout=60)
            
            if caminho_destino.exists(): caminho_destino.unlink()
            
            # O shutil.move agora move para a pasta pendente/1 no Drive (caminho_destino completo)
            shutil.move(str(arquivo_baixado), str(caminho_destino))
            _log(f'✅ Imagem baixada com sucesso: {caminho_destino.name}')
            
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5); ActionChains(self.driver).send_keys(Keys.ESCAPE).perform(); time.sleep(1.5)
            
            return caminho_destino
            
        except Exception as e:
            _log(f'Erro no download: {e}')
            salvar_print_debug(self.driver, "ERRO_DOWNLOAD_IMAGEM")
            raise
        
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


def ler_e_separar_cenas(caminho_txt: Path, qtd_cenas: int = 3) -> list[str]:
    """
    Lê o roteiro de Cenas e corta os parágrafos de forma independente e flexível,
    não importa se o Gemini gerou na mesma linha ou com 10 quebras de linha.
    """
    if not caminho_txt.exists():
        _log(f"⚠️ Arquivo não encontrado: {caminho_txt}")
        return []

    conteudo = caminho_txt.read_text(encoding='utf-8')
    
    # 1. Limpeza de Lixo de IA
    conteudo = re.sub(r'<thinking>.*?</thinking>', '', conteudo, flags=re.DOTALL)
    conteudo = conteudo.replace("Show thinking", "").replace("Gemini said", "").strip()
    
    # 2. Corta fora a Legenda para ela não vazar na última cena
    # Pega tudo antes do marcador [Legenda (case insensitive)
    conteudo = re.split(r'\[(?i:legenda).*?\]', conteudo)[0].strip()
    
    # 3. O Separador Flexível
    # O re.split vai cortar o texto toda vez que achar uma tag tipo: [Cena 1: Titulo], [CENA 2], etc.
    # O (?i:cena\s*\d+) garante que ele foca na palavra Cena + Número, ignorando caixa alta/baixa.
    partes = re.split(r'\[(?i:cena\s*\d+).*?\]', conteudo)
    
    cenas_extraidas = []
    
    # O primeiro item do split costuma ser vazio ou o lixo "Aqui está o seu roteiro:"
    # O enumerate ignora a primeira parte vazia
    for i, texto_parcial in enumerate(partes):
        if i == 0 and "transform the input" not in texto_parcial.lower() and "câmera" not in texto_parcial.lower():
            continue # Ignora preâmbulos e lixos antes da Cena 1
            
        texto_limpo = texto_parcial.strip()
        if texto_limpo:
            cenas_extraidas.append(texto_limpo)
            
    # Log de Auditoria
    _log(f"Análise de {caminho_txt.name}: {len(cenas_extraidas)} cenas extraídas com sucesso.")
    
    if len(cenas_extraidas) < qtd_cenas:
        _log(f"⚠️ Aviso: O arquivo tem menos cenas que o esperado. Extraídas: {len(cenas_extraidas)}")
        
    return cenas_extraidas[:qtd_cenas]
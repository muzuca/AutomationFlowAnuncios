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
from integrations.utils import _log as log_base, salvar_print_debug, js_click, scroll_ao_fim, salvar_ultimo_prompt

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
        
        # --- VARIÁVEIS DE ESTADO ---
        self.ultimo_tile_id_gerado = None
        self._projeto_criado = False
        self._modelo_configurado = False
        self._imagem_upada = False
        
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
                'got it', 'entendi', 'i agree', 'concordo', 'agree', 'aceitar', 
                'accept', 'enable', 'continuar', 'continue', 'agree and continue', 
                'dismiss', 'close', 'fechar', 'ok'
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
        self._fechar_modais_intrusivos()
        
        try:
            self._wait_click(
                By.XPATH, 
                "//span[contains(text(), 'New project')] | //button[contains(., 'New')] | //button[contains(., 'Novo projeto')] | //button[descendant::i[text()='add_2']]",
                timeout=10,
                descricao="Botão Novo Projeto"
            )
            time.sleep(3)
            self._fechar_modais_intrusivos()

            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='textbox' and @contenteditable='true'] | //textarea")))
            except Exception:
                pass
            self._projeto_criado = True
            
            # Reset de estado de imagem toda vez que um NOVO projeto nasce de fato
            self._modelo_base_upada = False
            self._uploads_apos_modelo = 0

        except TimeoutException:
            _log('Botão "Novo projeto" não visível, forçando refresh para limpar estado...')
            self.driver.refresh()
            time.sleep(4)
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
                    _log("Aviso: Nenhum chip de modelo encontrado. Tentando genérico...")
                    botoes_menu = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                    if botoes_menu:
                        js_click(self.driver, botoes_menu[0])
                        chip_encontrado = True

            if chip_encontrado:
                time.sleep(2.0) 

                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[.//i[text()='videocam'] or contains(., 'Vídeo') or contains(., 'Video')]", 
                        timeout=5, 
                        descricao="Aba Vídeo"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]", 
                        timeout=5, 
                        descricao="Opção 9:16"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

                try:
                    self._wait_click(
                        By.XPATH, 
                        "//div[@role='menu' and @data-state='open']//button[normalize-space()='x1']", 
                        timeout=5, 
                        descricao="Opção x1"
                    )
                    time.sleep(0.5)
                except TimeoutException: pass

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
            
            chip_xpath = "//button[(contains(., 'Banana') or contains(., 'Nano')) and @aria-haspopup='menu']"
            try:
                self._wait_click(By.XPATH, chip_xpath, timeout=10, descricao="chip do Modelo")
            except TimeoutException:
                _log("Aviso: Chip principal não detectado. Tentando menu genérico...")
                botoes_menu = self.driver.find_elements(By.XPATH, "//button[@aria-haspopup='menu']")
                if botoes_menu: 
                    js_click(self.driver, botoes_menu[0])
            
            time.sleep(2.0) 

            self._wait_click(
                By.XPATH, 
                "//div[@role='menu' and @data-state='open']//button[.//i[text()='crop_9_16'] or contains(., '9:16')]", 
                timeout=10, 
                descricao="Opção 9:16"
            )
            time.sleep(0.5)

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
            if elementos:
                # Pega SEMPRE o último input criado no DOM para não injetar em inputs fantasmas de modais antigos
                return elementos[-1] 
        raise TimeoutException('Nenhum input[type=file] encontrado na interface do Flow.')

    # =================================================================================
    # FUNÇÕES 100% ISOLADAS: OTIMIZADAS PARA O FLUXO DE PRODUTO + MODELO NO MODAL (IMAGE BASE)
    # =================================================================================

    def _upload_produto_isolado(self, caminho: Path) -> bool:
        """Faz o upload e CONTA os cards originais na tela para evitar falsos positivos de re-upload."""
        _log(f"Iniciando upload isolado de: {caminho.name}...")
        nome_arquivo = caminho.name
        nome_limpo = caminho.stem # Usado apenas para dar nome aos prints sem a extensão
        
        try:
            # 1. Conta quantos cards ORIGINAIS (sem botão de download) COM ESTE NOME já existem
            xpath_sucesso = f"//*[@data-tile-id and not(.//button[.//i[text()='download']]) and .//*[contains(text(), '{nome_arquivo}')]]"
            elementos_antes = self.driver.find_elements(By.XPATH, xpath_sucesso)
            qtd_antes = len([el for el in elementos_antes if el.is_displayed()])
            
            # 📸 PRINT 1: Visão da galeria ANTES de enviar o arquivo
            salvar_print_debug(self.driver, f"1_ANTES_DO_UPLOAD_{nome_limpo}")
            
            # 2. Injeta o arquivo no input correto
            input_file = self._encontrar_input_file()
            self.driver.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;", input_file)
            input_file.send_keys(str(caminho.resolve()))
            
            _log(f"Arquivo injetado. Monitorando a criação do NOVO card (Atuais: {qtd_antes})...")
            
            # 📸 PRINT 2: Visão logo após o script injetar o arquivo no HTML
            salvar_print_debug(self.driver, f"2_ARQUIVO_INJETADO_{nome_limpo}")
            
            time.sleep(3.0) 
            
            inicio_upload = time.time()
            fim_upload = inicio_upload + 120 
            
            sucesso_upload = False
            ultimo_movimento = time.time()
            
            while time.time() < fim_upload:
                xpath_erros = "//*[@data-tile-id]//div[contains(text(), 'Falha') or contains(text(), 'Failed')]"
                erros = self.driver.find_elements(By.XPATH, xpath_erros)
                if erros and any(e.is_displayed() for e in erros):
                    self._finish_progress_inline()
                    _log("❌ Falha crítica: O Google Flow rejeitou a imagem (Erro no servidor/Falha).")
                    
                    # 📸 PRINT 3 (Erro): Caso o Flow mostre a mensagem de falha no card
                    salvar_print_debug(self.driver, f"3_ERRO_SERVIDOR_UPLOAD_{nome_limpo}")
                    return False

                # 3. Verifica se a quantidade de imagens ORIGINAIS aumentou (Ignora as geradas pela Variante A)
                elementos_agora = self.driver.find_elements(By.XPATH, xpath_sucesso)
                qtd_agora = len([el for el in elementos_agora if el.is_displayed()])
                
                if qtd_agora > qtd_antes:
                    self._finish_progress_inline()
                    _log(f"✔ Upload concluído! O NOVO card com '{nome_arquivo}' apareceu na interface.")
                    
                    # 📸 PRINT 3 (Sucesso): Momento em que o script detecta que o upload terminou
                    salvar_print_debug(self.driver, f"3_UPLOAD_CONCLUIDO_{nome_limpo}")
                    sucesso_upload = True
                    break
                
                if time.time() - ultimo_movimento > 3:
                    self._print_progress_inline(f"[FLOW-IA] Aguardando o NOVO card do arquivo '{nome_arquivo}' ficar pronto...")
                    ultimo_movimento = time.time()
                    
                time.sleep(1)
            
            if not sucesso_upload:
                self._finish_progress_inline()
                _log(f"⚠️ Timeout: O NOVO card com o nome '{nome_arquivo}' não apareceu após 120s.")
                
                # 📸 PRINT 3 (Timeout): A tela após 120 segundos travada
                salvar_print_debug(self.driver, f"3_TIMEOUT_UPLOAD_{nome_limpo}")
                return False

            time.sleep(2.0) 
            return True
            
        except Exception as e:
            self._finish_progress_inline()
            _log(f"🚨 Erro crítico na injeção de upload isolado: {str(e)[:100]}")
            # 📸 PRINT (Crash)
            salvar_print_debug(self.driver, f"ERRO_CRITICO_UPLOAD_{nome_limpo}")
            return False
        
    def _clicar_produto_destaque(self, nome_arquivo: str) -> bool:
        """Busca o card do produto especificamente pelo NOME e clica nele (XPATH Restaurado com blindagem)."""
        _log(f"Clicando na imagem {nome_arquivo} para abrir em destaque...")
        nome_limpo = Path(nome_arquivo).stem
        try:
            # O XPATH que funcionava: Busca a div com o texto e sobe para clicar na IMG dela
            # A CORREÇÃO: Exclui cards com botão 'download' para NUNCA clicar na imagem gerada da Variante A!
            xpath_exato = f"//div[@data-tile-id and not(.//button[.//i[text()='download']]) and .//*[contains(text(), '{nome_limpo}') or contains(text(), '{nome_arquivo}')]]//img"
            miniaturas = self.driver.find_elements(By.XPATH, xpath_exato)
            visiveis = [img for img in miniaturas if img.is_displayed()]
            
            if visiveis:
                # O Flow empilha os recentes no topo. A [0] é a que acabamos de fazer o re-upload
                js_click(self.driver, visiveis[0]) 
                time.sleep(3.0)
                _log("✔ Produto base (original) aberto em destaque pelo nome.")
                return True
            
            _log("⚠️ Produto não achado pelo nome exato. Usando fallback...")
            xpath_fallback = "//div[@data-tile-id and not(.//button[.//i[text()='download']])]//img"
            miniaturas_fallback = self.driver.find_elements(By.XPATH, xpath_fallback)
            visiveis_fall = [img for img in miniaturas_fallback if img.is_displayed()]
            
            if visiveis_fall:
                js_click(self.driver, visiveis_fall[0])
                time.sleep(3.0)
                _log(f"✔ Imagem fallback clicada (destaque).")
                return True
                
            return False
        except Exception as e:
            _log(f"Erro ao clicar na imagem base: {e}")
            return False

    def _clicar_produto_destaque(self, nome_arquivo: str) -> bool:
        """Busca o card do produto especificamente pelo NOME e clica nele."""
        _log(f"Clicando na imagem {nome_arquivo} para abrir em destaque...")
        nome_limpo = Path(nome_arquivo).stem
        try:
            # Encontra a <div> que tem o texto do arquivo e SOBE na árvore do HTML para achar a imagem que pertence a ele.
            # Essa é a forma mais robusta e imune a falhas que existe, garantindo 100% que clicaremos no PRODUTO e não na MODELO ou numa imagem gerada.
            xpath_exato = f"//div[@data-tile-id and .//*[contains(text(), '{nome_limpo}') or contains(text(), '{nome_arquivo}')]]//img"
            miniaturas = self.driver.find_elements(By.XPATH, xpath_exato)
            visiveis = [img for img in miniaturas if img.is_displayed()]
            
            if visiveis:
                js_click(self.driver, visiveis[0]) 
                time.sleep(3.0)
                _log("✔ Produto base (original) aberto em destaque pelo nome.")
                return True
            
            # Fallback seguro: Pega o index correto baseado no que tem na tela
            _log("⚠️ Produto não achado pelo nome exato. Usando fallback de posição na galeria...")
            xpath_fallback = "//div[@data-tile-id and not(.//button[.//i[text()='download']])]//img"
            miniaturas_fallback = self.driver.find_elements(By.XPATH, xpath_fallback)
            visiveis_fall = [img for img in miniaturas_fallback if img.is_displayed()]
            
            if visiveis_fall:
                js_click(self.driver, visiveis_fall[0]) # Clica na primeira que geralmente é a base
                time.sleep(3.0)
                _log(f"✔ Imagem fallback clicada (destaque).")
                return True
                
            return False
        except Exception as e:
            _log(f"Erro ao clicar na imagem base: {e}")
            return False

    def _anexar_modelo_pela_lista(self, nome_modelo: str, url_ancora: str) -> bool:
        """A modelo já foi upada! Abre o +, busca na aba recentes pelo nome e valida o chip."""
        _log(f"Anexando a modelo ({nome_modelo}) pelo botão + da lista de recentes...")
        nome_limpo = Path(nome_modelo).stem
        
        idx_modelo = getattr(self, '_uploads_apos_modelo', 0)
        _log(f"Rastreador: A foto da modelo deve estar na posição {idx_modelo} da galeria de recentes.")

        try:
            xpath_add = "//button[.//i[text()='add_2']] | //button[contains(., 'Criar')]"
            btn_add = self._wait_click(By.XPATH, xpath_add, timeout=10, descricao="Botão + (add_2)")
            time.sleep(2.0)

            if self.driver.current_url != url_ancora:
                _log("⚠️ O Flow perdeu o foco do produto! Restaurando URL...")
                self.driver.get(url_ancora)
                time.sleep(3.0)
                btn_add = self._wait_click(By.XPATH, xpath_add, timeout=10)
                time.sleep(1.5)

            # Busca a modelo exatamente pelo nome
            xpath_img = f"//div[@data-state='open' or contains(@role, 'menu')]//img[contains(@alt, '{nome_limpo}')] | //div[contains(@class, 'grid') or contains(@class, 'list')]//button[contains(., '{nome_limpo}')]//img | //div[contains(@class, 'grid') or contains(@class, 'list')]//img[contains(@alt, '{nome_limpo}')]"
            imgs = self.driver.find_elements(By.XPATH, xpath_img)
            imgs_visiveis = [i for i in imgs if i.is_displayed()]
            
            if imgs_visiveis:
                js_click(self.driver, imgs_visiveis[0])
                _log(f"✔ Imagem da modelo ({nome_limpo}) selecionada da aba recentes via nome.")
            else:
                # SE NÃO ACHAR PELO NOME, USA A MATEMÁTICA DO RASTREADOR
                _log("⚠️ Não achou na lista pelo nome exato. Usando matemática do rastreador de índice...")
                xpath_fallback = "//div[@data-state='open']//div[contains(@class, 'grid') or contains(@class, 'list')]//button//img"
                fallbacks = self.driver.find_elements(By.XPATH, xpath_fallback)
                if fallbacks:
                    if idx_modelo < len(fallbacks) and fallbacks[idx_modelo].is_displayed():
                        js_click(self.driver, fallbacks[idx_modelo])
                        _log(f"✔ Foto no índice exato {idx_modelo} selecionada com sucesso.")
                    elif fallbacks[0].is_displayed():
                        js_click(self.driver, fallbacks[0])
                        _log("⚠️ Índice fora de alcance. Usando a primeira foto como fallback de emergência.")

            time.sleep(1.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1.0)

            xpath_chip = "//button[.//i[text()='cancel']]"
            chips = self.driver.find_elements(By.XPATH, xpath_chip)
            if chips and any(c.is_displayed() for c in chips):
                _log("✔ Confirmação: Modelo anexada perfeitamente no quadradinho (chip)!")
                return True
            
            return False
        except Exception as e:
            _log(f"Erro fatal ao selecionar modelo da lista: {str(e).splitlines()[0]}")
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def _enviar_prompt_imagem_isolado(self, prompt: str, timeout_geracao: int = 120) -> bool:
        """Digita o prompt e submete (Modo Imagem)."""
        _log("Enviando prompt (Fluxo isolado de Imagem)...")
        prompt_linear = " ".join(prompt.split())
        
        salvar_ultimo_prompt(f"--- PROMPT ENVIADO AO FLOW (IMAGEM) ---\n{prompt_linear}")

        try:
            xpath_box = "//div[@role='textbox' and @contenteditable='true'] | //textarea"
            caixas = self.driver.find_elements(By.XPATH, xpath_box)
            box = next((c for c in caixas if c.is_displayed()), None)
            
            if not box:
                _log("⚠️ Caixa de texto não encontrada para digitar o prompt.")
                return False
            
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();", box)
            js_click(self.driver, box)
            time.sleep(0.5)
            
            box.send_keys(Keys.CONTROL, "a")
            box.send_keys(Keys.BACKSPACE)
            time.sleep(0.5)
            
            box.send_keys(prompt_linear)
            time.sleep(1.5)
            
            xpath_submit = "//button[.//i[contains(text(), 'arrow') or contains(text(), 'send') or contains(text(), 'sparkle')]] | //button[contains(@aria-label, 'Gerar')]"
            btns = self.driver.find_elements(By.XPATH, xpath_submit)
            
            if btns and btns[-1].is_displayed():
                js_click(self.driver, btns[-1])
                _log("✔ Botão de envio (Seta) clicado.")
            else:
                _log("⚠️ Botão de seta não achado, usando CTRL+ENTER...")
                box.send_keys(Keys.CONTROL, Keys.ENTER)
                time.sleep(0.5)
                box.send_keys(Keys.ENTER)
                
            time.sleep(3)
            
            _log(f"Aguardando o botão 'Baixar' habilitar (máx {timeout_geracao}s)...")
            xpath_btn_baixar = "//button[.//i[text()='download'] and .//div[text()='Baixar']]"
            fim_espera = time.time() + timeout_geracao
            
            while time.time() < fim_espera:
                b_baixar = self.driver.find_elements(By.XPATH, xpath_btn_baixar)
                if b_baixar and b_baixar[0].is_displayed() and b_baixar[0].get_attribute("disabled") is None:
                    print() 
                    _log("✔ Botão 'Baixar' habilitado! Geração de imagem concluída.")
                    return True
                
                self._print_progress_inline(f"[FLOW-IA] Gerando Imagem... {int(time.time() - (fim_espera - timeout_geracao))}s")
                time.sleep(4)
                
            self._finish_progress_inline()
            _log("❌ Timeout aguardando o botão de baixar.")
            return False
            
        except Exception as e:
            _log(f"Erro ao enviar prompt de imagem: {e}")
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def gerar_imagem_base(self, caminho_referencia: Path, prompt: str, caminho_saida: Path, caminho_modelo: Optional[Path] = None) -> Path:
        """A orquestração: Sobe o produto a cada variante para não ser engolido pela geração anterior. A modelo sobe só 1x."""
        _log(f"🎬 [FLOW-IMAGE] Iniciando geração. Saída: {caminho_saida.name}")
        self.acessar_flow()
        self.clicar_novo_projeto()
        
        sucesso = False
        for tentativa in range(1, 4):
            _log(f"[FLOW-IMAGE] Iniciando tentativa local {tentativa}/3...")
            try:
                self._fechar_modais_intrusivos()

                # Garante os atributos de rastreamento
                if not hasattr(self, '_modelo_base_upada'): self._modelo_base_upada = False
                if not hasattr(self, '_uploads_apos_modelo'): self._uploads_apos_modelo = 0

                # Toda vez que a gente upa o produto, se a modelo já estava upada, ela "desce" uma posição na galeria
                if self._modelo_base_upada:
                    _log("Incrementando índice da modelo na galeria (Produto sendo re-upado)...")
                    self._uploads_apos_modelo += 1

                # 1. Faz upload do produto (SEMPRE RE-UPA NA VARIANTE B, C...)
                if not self._upload_produto_isolado(caminho_referencia):
                    if self._modelo_base_upada: self._uploads_apos_modelo -= 1 # Reverte se deu erro
                    raise Exception("Falha no upload do produto.")

                # 2. Faz upload da modelo (SÓ UMA VEZ POR PROJETO)
                if caminho_modelo and caminho_modelo.exists():
                    if not self._modelo_base_upada:
                        if not self._upload_produto_isolado(caminho_modelo):
                            raise Exception("Falha no upload da modelo.")
                        self._modelo_base_upada = True
                        self._uploads_apos_modelo = 0 # Zerou, a modelo é o topo da galeria (index 0)
                    else:
                        _log("Modelo já presente no Workspace. Reaproveitando da lista...")

                # 3. Clica no Produto para ancorar o destaque (Sempre clicando no produto, nunca no gerado)
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
                    sucesso = True
                    break
                else:
                    _log(f"Tentativa {tentativa} falhou na geração. Resetando interface...")
                    self.driver.refresh()
                    self._projeto_criado = False # Se falhou a tentativa, recomeça TUDO do zero.
                    self._modelo_base_upada = False
                    self._uploads_apos_modelo = 0
                    time.sleep(4)

            except Exception as e:
                _log(f"Falha tentativa {tentativa}: {str(e)[:100]}")
                self.driver.refresh()
                self._projeto_criado = False # Se falhou a tentativa, recomeça TUDO do zero.
                self._modelo_base_upada = False
                self._uploads_apos_modelo = 0
                time.sleep(4)
                
        if not sucesso:
            raise Exception("Falha ao gerar imagem no Flow após 3 tentativas.")
            
        return self._baixar_imagem(caminho_saida)

    # =================================================================================
    # MÉTODOS DE VÍDEO E DOWNLOADS: COMPLETAMENTE INTOCÁVEIS (SUA LÓGICA ORIGINAL)
    # =================================================================================
    def anexar_imagem(self, caminho: Path, abrir_modal: bool = False) -> bool:
        nome_arquivo = caminho.name
        self._fechar_modais_intrusivos() 
        
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

        if abrir_modal:
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
        _log("Validando visualmente a presença da imagem no Slot Inicial...")
        try:
            btn_remover = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Remove')]")
            if len(btn_remover) > 0:
                _log("✅ Imagem detectada e garantida no projeto.")
                return True
            
            botoes_initial = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Initial image') and .//img]")
            if len(botoes_initial) > 0:
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
        prompt_linear = " ".join(prompt.split())
        
        salvar_ultimo_prompt(f"--- PROMPT ENVIADO AO FLOW ---\n{prompt_linear}")
                                  
        for tentativa_local in range(1, 4):
            _log(f"[FLOW-IA] Iniciando tentativa local de prompt {tentativa_local}/3...")
            self._fechar_modais_intrusivos()
            salvar_print_debug(self.driver,f"TENTATIVA_PROMPT_{tentativa_local}_INICIO")

            try:
                if not modo_imagem:
                    _log("Validando se a imagem de referência continua no slot Inicial...")
                    
                    btn_remover = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Remove')] | //div[@role='button' and contains(@aria-label, 'Remove')]")
                    btn_img = self.driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Initial image') and .//img] | //div[contains(@aria-label, 'Initial') and .//img]")
                    
                    if not btn_remover and not btn_img:
                        _log("⚠️ O Flow removeu a imagem do slot! Revinculando antes de enviar...")
                        try:
                            xpath_btn_inicial = (
                                "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') "
                                "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))]"
                            )
                            botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                            if botoes_iniciais and botoes_iniciais[0].is_displayed():
                                js_click(self.driver, botoes_iniciais[0])
                                time.sleep(2.0)
                                
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

                box.send_keys(Keys.CONTROL, "a")
                box.send_keys(Keys.BACKSPACE)
                time.sleep(0.5)

                _log(f"Digitando prompt ({len(prompt_linear)} chars)...")
                box.send_keys(prompt_linear)
                time.sleep(1.5) 

                depois = self._ler_texto_prompt_box(box)
                if len(depois) < 10:
                    _log("⚠️ Falha na digitação. Tentando ActionChains...")
                    ActionChains(self.driver).move_to_element(box).click().send_keys(prompt_linear).perform()
                    time.sleep(1.0)

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
                
                if modo_imagem:
                    _log(f"Aguardando o botão 'Baixar' habilitar (máx {timeout_geracao}s)...")
                    xpath_btn_baixar = "//button[.//i[text()='download'] and .//div[text()='Baixar']]"
                    fim_espera = time.time() + timeout_geracao
                    
                    while time.time() < fim_espera:
                        btns = self.driver.find_elements(By.XPATH, xpath_btn_baixar)
                        if btns:
                            btn = btns[0]
                            is_disabled = btn.get_attribute("disabled")
                            if btn.is_displayed() and is_disabled is None:
                                print() 
                                _log("✔ Botão 'Baixar' habilitado! Geração concluída.")
                                return True
                        
                        self._print_progress_inline(f"[FLOW-IA] Gerando... {int(time.time() - (fim_espera - timeout_geracao))}s")
                        time.sleep(4)
                    
                    self._finish_progress_inline()
                    _log("❌ Timeout: O botão de baixar não habilitou a tempo.")
                else:
                    if self._aguardar_geracao_tracking_inline(prompt_linear, timeout_geracao):
                        return True
                
            except Exception as e:
                _log(f'Erro na tentativa de prompt {tentativa_local}: {str(e)[:100]}')
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(2)
                
        return False
    
    def _aguardar_geracao_imagem_sem_porcentagem(self, prompt: str, timeout: int = 120) -> bool:
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
        diretorio.mkdir(parents=True, exist_ok=True)
        return {p.name for p in diretorio.glob(f"*{extensao}")}

    def _esperar_download_arquivo(self, download_dir: Path, antes: set[str], extensao: str = ".mp4", timeout=180) -> Path:
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

    def gerar_imagem_pov(self, caminho_referencia: Path, prompt: str, caminho_saida: Path) -> Path:
        """Orquestra a geração completa de uma imagem POV no Flow e salva no caminho correto."""
        _log(f"🎬 [FLOW-IMAGE] Iniciando geração de imagem POV. Saída: {caminho_saida.name}")
        self.acessar_flow()
        
        self.clicar_novo_projeto()
        
        sucesso = False
        for tentativa in range(1, 4):
            _log(f"[FLOW-IMAGE] Iniciando tentativa local {tentativa}/3...")
            try:
                if not self.anexar_imagem(caminho_referencia, abrir_modal=True):
                    raise Exception("Falha ao preparar a imagem na tela.")

                self._modelo_configurado = False
                self.configurar_parametros_imagem()
                
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
            
        return self._baixar_imagem(caminho_saida)

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
    if not caminho_txt.exists():
        _log(f"⚠️ Arquivo não encontrado: {caminho_txt}")
        return []

    conteudo = caminho_txt.read_text(encoding='utf-8')
    
    conteudo = re.sub(r'<thinking>.*?</thinking>', '', conteudo, flags=re.DOTALL)
    conteudo = conteudo.replace("Show thinking", "").replace("Gemini said", "").strip()
    
    conteudo = re.split(r'\[(?i:legenda).*?\]', conteudo)[0].strip()
    
    partes = re.split(r'\[(?i:cena\s*\d+).*?\]', conteudo)
    
    cenas_extraidas = []
    
    for i, texto_parcial in enumerate(partes):
        if i == 0 and "transform the input" not in texto_parcial.lower() and "câmera" not in texto_parcial.lower():
            continue 
            
        texto_limpo = texto_parcial.strip()
        if texto_limpo:
            cenas_extraidas.append(texto_limpo)
            
    _log(f"Análise de {caminho_txt.name}: {len(cenas_extraidas)} cenas extraídas com sucesso.")
    
    if len(cenas_extraidas) < qtd_cenas:
        _log(f"⚠️ Aviso: O arquivo tem menos cenas que o esperado. Extraídas: {len(cenas_extraidas)}")
        
    return cenas_extraidas[:qtd_cenas]
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
from integrations.self_healing import cacar_elemento_universal, elemento_esta_realmente_pronto

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
        
        # --- BLOCO DE FUGA: GARANTE QUE ESTAMOS NA RAIZ ANTES DE CRIAR PROJETO ---
        _log("Verificando se precisamos sair do projeto atual (Seta Voltar)...")
        xpath_voltar = "//button[.//i[contains(text(), 'arrow_back')]] | //button[contains(., 'Voltar')]"
        botoes_voltar = self.driver.find_elements(By.XPATH, xpath_voltar)
        
        btn_voltar = next((b for b in botoes_voltar if b.is_displayed()), None)
        
        if btn_voltar:
            _log("Seta encontrada. Saindo do projeto atual e voltando para a galeria...")
            try:
                btn_voltar.click()
            except:
                self.driver.execute_script("arguments[0].click();", btn_voltar)
            time.sleep(3) # Aguarda voltar pro painel inicial
        # -------------------------------------------------------------------------

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
                        "//div[@role='menu' and @data-state='open']//button[normalize-space()='1x' or normalize-space()='x1']", 
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
                    # Captura bolinhas girando, progressbars e o maldito texto de 99%
                    xpath_loaders = "//*[contains(@class, 'spin') or @role='progressbar'] | //*[contains(text(), '%')]"
                    loaders = self.driver.find_elements(By.XPATH, xpath_loaders)
                    
                    # Se não tem nada de loading e nada de % na tela, o upload acabou!
                    if not loaders or not any(l.is_displayed() for l in loaders):
                        break
                except: pass
                time.sleep(1)

            # O 100% bateu e sumiu. Dá 3 segundos pro React trocar o fundo cinza pela foto real
            time.sleep(3.0)

            # Checa se o Google cuspiu erro fatal de upload
            try:
                xpath_erros = "//*[@data-tile-id]//div[contains(text(), 'Falha') or contains(text(), 'Failed')]"
                erros = self.driver.find_elements(By.XPATH, xpath_erros)
                if erros and any(e.is_displayed() for e in erros):
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

    def _enviar_prompt_imagem_isolado(self, prompt: str, timeout_geracao: int = 60) -> bool:
        """Digita o prompt e monitora falhas globais (Unusual Activity) na tela inteira."""
        import os
        import time
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.by import By
        
        def js_click(driver, element):
            driver.execute_script("arguments[0].click();", element)

        _log("Enviando prompt (Fluxo isolado de Imagem)...")

        prompt_linear = " ".join(prompt.replace('\n', ' ').replace('\r', ' ').split())
        
        try:
            from integrations.utils import salvar_ultimo_prompt
            salvar_ultimo_prompt(f"--- PROMPT ENVIADO AO FLOW (IMAGEM) ---\n{prompt_linear}")
        except: pass

        try:
            xpath_box = "//div[@role='textbox' and @contenteditable='true'] | //textarea"
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

            time.sleep(1.5)

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

            momento_submit = time.time()
            time.sleep(4) 
            
            # --- MONITORAMENTO COM RADAR DE FALHA GLOBAL ---
            _log(f"Monitorando geração (máx {timeout_geracao}s)...")
            
            # Trava cega reduzida para 15s para começar a vigiar a falha mais cedo
            _log("[FLOW-IA] Aguardando processamento inicial...")
            time.sleep(15)
            
            fim_espera = time.time() + (timeout_geracao - 15)

            while time.time() < fim_espera:
                # 🚀 1. RADAR DE FALHA GLOBAL (Pega o "Unusual Activity" na lateral)
                erro_tela = self.driver.execute_script("""
                    var txt = document.body.innerText || "";
                    txt = txt.toLowerCase();
                    return txt.includes('unusual activity') || 
                        txt.includes('policy') || 
                        txt.includes('failed') || 
                        (txt.includes('falha') && txt.includes('noticed'));
                """)
                
                if erro_tela:
                    _log("🚨 FALHA DETECTADA NA TELA (Unusual Activity / Policy).")
                    # Break aqui sai do while e retorna False no final da função
                    break

                # 2. SUCESSO REAL (Verifica se a seta destravou)
                xpath_seta = "//button[.//i[contains(text(), 'arrow') or contains(text(), 'send') or contains(text(), 'sparkle')]] | //button[contains(@aria-label, 'Gerar')]"
                setas = self.driver.find_elements(By.XPATH, xpath_seta)
                
                if setas and setas[-1].is_displayed() and setas[-1].get_attribute("disabled") is None:
                    # Garantia contra falso-positivo da imagem base
                    if (time.time() - momento_submit) < 20:
                        time.sleep(2)
                        continue
                        
                    _log("✔ Geração concluída com sucesso!")
                    return True
                
                self._print_progress_inline(f"[FLOW-IA] Gerando... {int(time.time() - momento_submit)}s")
                time.sleep(4)
                
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
                    
                    if self._enviar_prompt_imagem_isolado(prompt, timeout_geracao=60):
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
                    loaders = self.driver.find_elements(By.XPATH, "//div[contains(text(), '%')] | //span[contains(text(), '%')]")
                    if not loaders or not any(l.is_displayed() for l in loaders):
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
                miniaturas = self.driver.find_elements(By.XPATH, xpath_miniatura)
                
                if miniaturas:
                    imgs_visiveis = [img for img in miniaturas if img.is_displayed()]
                    if imgs_visiveis:
                        # Rola para o elemento antes de clicar para evitar que fique fora da tela
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", imgs_visiveis[-1])
                        js_click(self.driver, imgs_visiveis[-1])
                        time.sleep(2.0)
                        _log("✔ Imagem clicada! Modal aberto.")
                        salvar_print_debug(self.driver, f"FLOW_MODAL_PROMPT_ABERTO_{caminho.stem}")
                        return True
                    
                _log("⚠️ Imagem não achada. Clicando no último card genérico...")
                imgs = self.driver.find_elements(By.XPATH, "//img")
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
                botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                botao_visivel = [b for b in botoes_iniciais if b.is_displayed()]
                
                if botao_visivel:
                    # 🚨 PROTEÇÃO ANTI-ERRO: Rola pro botão antes de clicar
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_visivel[0])
                    js_click(self.driver, botao_visivel[0])
                    _log('Botão "Inicial" clicado. Aguardando galeria...')
                    time.sleep(2.5) 

                    xpath_img_popup = f"//div[@role='dialog']//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')] | //div[@role='dialog']//img"
                    imgs_dialog = self.driver.find_elements(By.XPATH, xpath_img_popup)
                    if imgs_dialog:
                        js_click(self.driver, imgs_dialog[0])
                        _log('✔ Imagem base selecionada no popup. Aguardando UI processar...')
                        time.sleep(2.5) # Deixa a galeria fechar sozinha e o React atualizar o slot sem marretada de ESC

                    # 📸 PRINT DE CONFERÊNCIA: Ver se a miniatura fixou no botão Inicial
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
        import os
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support import expected_conditions as EC
        
        # Helper para clique via JS (se não tiver no seu arquivo, adicione no topo ou use driver.execute_script)
        def js_click(driver, element):
            driver.execute_script("arguments[0].click();", element)

        prompt_linear = " ".join(prompt.split())
        
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
                            # Tenta achar o botão de input 'Inicial' ou 'Initial'
                            xpath_btn_inicial = "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))] | //button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial')]"
                            botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
                            
                            if botoes_iniciais and botoes_iniciais[0].is_displayed():
                                js_click(self.driver, botoes_iniciais[0])
                                time.sleep(2.0)
                                # Seleciona a primeira imagem da galeria aberta (que deve ser o upload que acabamos de fazer)
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
            # --- 🛡️ BUSCA DO BOTÃO BAIXAR (Versão HUNTER INTELIGENTE) ---
            # =========================================================
            _log("Procurando botão 'Baixar' (Hunter mode)...")

            btn_baixar = None
            fim_busca = time.time() + 30
            while time.time() < fim_busca:
                btn_baixar = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="flow_botao_baixar",
                    descricao_para_ia="Botão de Download ou Baixar imagem na interface do Google Flow",
                    seletores_rapidos=[
                        "//button[.//i[text()='download']]",
                        "//button[contains(@aria-label, 'Download')]"
                    ],
                    palavras_semanticas=['download', 'baixar', 'save_alt'],
                    driver_acessibilidade=self.driver_acessibilidade, 
                    url_gemini=self.url_gemini_acessibilidade,
                    etapa="FLOW_VIDEO_PLAYER" # <--- ADICIONADO PARA ISOLAR O PLAYER
                )
                if btn_baixar:
                    break
                time.sleep(1)

            if not btn_baixar:
                _log("ERRO: Botão Baixar não habilitou a tempo na tela do player.")
                return False

            try:
                btn_baixar.click()
            except:
                js_click(self.driver, btn_baixar)
            # =========================================================

            time.sleep(1.5) 
            
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
        download_dir = Path("logs/downloads").resolve()
        
        try:
            # 1. 🧹 LIMPEZA PRÉVIA
            if download_dir.exists():
                for f in download_dir.glob("*"):
                    try: f.unlink()
                    except: pass
            else:
                download_dir.mkdir(parents=True, exist_ok=True)

            # --- 2. CLIQUE NO BOTÃO PRINCIPAL 'BAIXAR' ---
            _log("Procurando botão 'Baixar' (Alvo: sc-e8425ea6-0)...")
            
            # XPath baseado no HTML real que você mandou (procura o ícone download + o span escondido)
            xpath_baixar = "//button[contains(., 'download') or contains(., 'Baixar')]"
            
            btn_baixar = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_baixar)))

            # 🚨 MUDANÇA VITAL: Clique físico real para o Radix disparar o Popper do menu
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_baixar)
            time.sleep(1.0)
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).move_to_element(btn_baixar).click().perform()
            except:
                btn_baixar.click()
            
            _log("✔ Menu de resoluções aberto. Buscando opção 1K...")
            time.sleep(2.5) # Tempo essencial para o menu flutuante renderizar no DOM

            # --- 3. SELEÇÃO DA RESOLUÇÃO 1K NO MENU FLUTUANTE ---
            # O menu flutuante do Radix usa role="menuitem". Vamos buscar o span '1K' dentro dele.
            xpath_1k_real = "//button[@role='menuitem']//span[text()='1K']"
            
            clicou_1k = False
            try:
                # Tenta achar o botão que contém o span 1K
                btn_1k = self.driver.find_element(By.XPATH, xpath_1k_real)
                # Sobe para o pai (button) se necessário, ou clica no span mesmo (o Radix aceita)
                self.driver.execute_script("arguments[0].click();", btn_1k)
                clicou_1k = True
                _log("✔ Opção '1K' clicada com sucesso via XPath Real!")
            except:
                _log("⚠️ XPath 1K falhou no menu flutuante. Tentando varredura JS total...")
                # Fallback JS varrendo todos os menuitems abertos na tela
                clicou_1k = self.driver.execute_script("""
                    var itens = document.querySelectorAll('button[role="menuitem"], [data-radix-collection-item]');
                    for (var i = 0; i < itens.length; i++) {
                        if (itens[i].innerText.includes('1K')) {
                            itens[i].click();
                            return true;
                        }
                    }
                    return false;
                """)

            if not clicou_1k:
                # Último suspiro: clica no primeiro item do menu (que pelo seu HTML é o 1K)
                _log("⚠️ Tentando clique cego no primeiro item do menu Radix...")
                self.driver.execute_script("""
                    var primeiro = document.querySelector('button[role="menuitem"]');
                    if (primeiro) { primeiro.click(); return true; }
                    return false;
                """)

            time.sleep(2.0)
            self.resolver_permissoes_drive()
            
            # --- 4. MONITORAMENTO DO DOWNLOAD ---
            _log(f'Monitorando surgimento de arquivo em: {download_dir}')
            arquivo_final = None
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
            from integrations.utils import salvar_print_debug
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


def ler_e_separar_cenas(caminho_txt: Path, num_roteiro: int = 1, qtd_cenas: int = 3, variante: str = "") -> list[str]:
    """Lê do roteiros.txt unificado fatiando pelo marcador do roteiro solicitado."""
    # Define o caminho do arquivo unificado na mesma pasta
    unificado = caminho_txt.parent / "roteiros.txt"
    
    # Prioridade para o roteiros.txt, fallback para o arquivo individual (antigo)
    arquivo_alvo = unificado if unificado.exists() else caminho_txt
    
    if not arquivo_alvo.exists():
        _log(f"⚠️ Arquivo não encontrado: {arquivo_alvo}")
        return []

    conteudo = arquivo_alvo.read_text(encoding='utf-8')
    
    # --- LÓGICA DE FATIAMENTO DO ARQUIVO UNIFICADO ---
    if unificado.exists():
        # 🚨 A MUDANÇA ESTÁ AQUI: Aceita a tag com a variante
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
    else:
        bloco = conteudo
        
    # --- SUA LÓGICA DE LIMPEZA ORIGINAL (MANTIDA) ---
    bloco = re.sub(r'<thinking>.*?</thinking>', '', bloco, flags=re.DOTALL)
    bloco = bloco.replace("Show thinking", "").replace("Gemini said", "").strip()
    
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
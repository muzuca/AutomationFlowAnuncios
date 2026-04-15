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

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] [FLOW-IA] {msg}')


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

    def _js_click(self, element: WebElement) -> None:
        self.driver.execute_script('arguments[0].click();', element)

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
            self._js_click(el)
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
        Comum ao logar com contas novas no Humble.
        """
        fechou_algo = False
        try:
            seletores_modais = [
                "//span[contains(text(), 'Got it')] | //button[contains(., 'Got it')] | "
                "//span[contains(text(), 'I agree')] | //button[contains(., 'Agree')] | "
                "//span[contains(text(), 'Enable')] | //button[contains(., 'Enable')] | "
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree and continue')] | "
                "//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree and continue')] | "
                "//button[contains(., 'Dismiss')] | //button[contains(., 'Close')] | "
                "//div[@role='dialog']//button[.//i[text()='close']]" # Botão de "X" (close) genérico em diálogos
            ]
            for seletor in seletores_modais:
                botoes = self.driver.find_elements(By.XPATH, seletor)
                for btn in botoes:
                    if btn.is_displayed():
                        _log('Modal detectado (Terms/Promo/Workspace). Fechando automaticamente...')
                        self._js_click(btn)
                        time.sleep(1.0)
                        fechou_algo = True
            
            # Se a interface ainda parecer bloqueada, usa ESC agressivo como fallback
            if not fechou_algo:
                overlays = self.driver.find_elements(By.XPATH, "//div[contains(@class,'overlay') or @role='dialog']")
                visiveis = [o for o in overlays if o.is_displayed()]
                if visiveis:
                    _log("Overlay ativo detectado. Forçando ESC duplo para limpar a tela.")
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
        
        try:
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass
        
        _log('Analisando a interface para entrar no Workspace...')
        fim_verificacao = time.time() + 15
        
        while time.time() < fim_verificacao:
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
                    self._js_click(btn)
                    clicou_create = True
                    time.sleep(3) 
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
            self._modelo_configurado = True
            
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            return True

        except Exception as e:
            _log(f'🚨 Erro fatal ao configurar modelo: {e}')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            return False

    def _encontrar_input_file(self) -> WebElement:
        seletores = ['input[type="file"]', 'input[accept*="image"]']
        for seletor in seletores:
            elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
            for el in elementos:
                if el is not None:
                    return el
        raise TimeoutException('Nenhum input[type=file] encontrado na interface do Flow.')

    def anexar_imagem(self, caminho: Path) -> bool:
        nome_arquivo = caminho.name
        self._fechar_modais_intrusivos() # Limpeza antes de mexer na imagem
        
        # Focar a caixa de prompt garante que os botões inferiores fiquem visíveis
        try:
            box = self.driver.find_element(By.XPATH, "//div[@role='textbox' and @contenteditable='true']")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", box)
            self._js_click(box)
            time.sleep(0.5)
        except Exception:
            pass

        # LÓGICA DE MEMÓRIA DE UPLOAD
        if not self._imagem_upada:
            _log(f'Fazendo upload da imagem de referência: {nome_arquivo}')
            try:
                input_file = self._encontrar_input_file()
                self.driver.execute_script(
                    "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                    input_file,
                )
                input_file.send_keys(str(caminho.resolve()))
                
                _log('Aguardando a conclusão do upload da imagem (sumiço do loader/%)...')
                time.sleep(2.0) 
                
                fim_upload = time.time() + 60
                while time.time() < fim_upload:
                    loaders = self.driver.find_elements(By.XPATH, "//div[contains(text(), '%')] | //span[contains(text(), '%')]")
                    if not loaders or not any(l.is_displayed() for l in loaders):
                        break 
                    time.sleep(1)
                
                _log('Aguardando a miniatura da imagem ficar disponível...')
                try:
                    self._wait_visible(
                        By.XPATH, 
                        f"//img[contains(@alt, '{nome_arquivo}') or contains(@src, 'blob:')]", 
                        timeout=15, 
                        descricao=f"Miniatura da imagem {nome_arquivo}"
                    )
                except TimeoutException:
                    _log('Aviso: Miniatura não foi visualizada claramente, mas prosseguindo por segurança.')

                time.sleep(1.5) 
                self._imagem_upada = True
            except Exception as e:
                _log(f'🚨 Falha no upload nativo da imagem: {e}')
                return False
        else:
            _log(f'A imagem {nome_arquivo} já foi feito upload no projeto. Verificando vínculo...')

        # LÓGICA DE VINCULAÇÃO INTELIGENTE
        try:
            xpath_btn_inicial = (
                "//div[@type='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'inicial') "
                "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'initial'))]"
            )
            
            botoes_iniciais = self.driver.find_elements(By.XPATH, xpath_btn_inicial)
            botao_visivel = [b for b in botoes_iniciais if b.is_displayed()]
            
            if botao_visivel:
                _log('Botão "Inicial" está livre. Vinculando a imagem...')
                self._js_click(botao_visivel[0])
                time.sleep(2.0) 

                xpath_img_popup = f"//div[@data-state='open' or @role='dialog']//div[contains(text(), '{nome_arquivo}')] | //img[@alt='{nome_arquivo}']"
                self._wait_click(By.XPATH, xpath_img_popup, timeout=15, descricao=f"Imagem '{nome_arquivo}' no popup")
                time.sleep(0.5)

                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.5)
                _log('Imagem anexada e vinculada com sucesso!')
            else:
                _log('Botão "Inicial" vazio não encontrado.')
                # Se não tem botão Inicial, verifica se o nome da imagem já está presente na UI
                img_ja_vinculada = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{nome_arquivo}')]")
                if img_ja_vinculada and any(el.is_displayed() for el in img_ja_vinculada):
                    _log(f'✔ A imagem {nome_arquivo} já está selecionada/vinculada na interface! (Reaproveitada)')
                else:
                    _log(f'Aviso: Assumindo que {nome_arquivo} continua vinculada da cena anterior.')

            return True

        except Exception as e:
            _log(f'🚨 Erro na etapa de vinculação (imagem provavelmtente já vinculada): {e}')
            # Não falha imediatamente, permite o script tentar preencher o prompt
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
            self._aguardar_carregamento_inicial()
            
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

    def enviar_prompt_e_aguardar(self, prompt: str, caminho_imagem: Path = None, timeout_geracao: int = 420) -> bool:
        """
        Versão RESILIENTE: Tenta gerar o vídeo até 3 vezes no mesmo login se o card falhar.
        Garante que a imagem está upada e vinculada antes de enviar o ENTER.
        Na retentativa, NÃO recarrega o projeto (evita erro de sessão); apenas fecha modais, 
        limpa o texto anterior e reenvia.
        """
        for tentativa_local in range(1, 4):
            _log(f"[FLOW-IA] Iniciando tentativa local {tentativa_local}/3 para gerar esta cena...")
            self._fechar_modais_intrusivos()

            try:
                # Se for retentativa, NÃO cria projeto novo. Apenas dá ESC para fechar possíveis mensagens de erro
                if tentativa_local > 1:
                    _log("🔄 Retentando cirurgicamente: Fechando alertas e reaproveitando a mesma aba...")
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(2)

                # 1. HARD CHECK DA IMAGEM: OBRIGATÓRIO (Evita Vídeo Aleatório sem seu Produto)
                if caminho_imagem:
                    if not self._garantir_imagem_anexada(caminho_imagem):
                        _log("❌ Falha crítica: Não foi possível garantir a imagem no slot Inicial.")
                        return False

                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                # O TEMPO CRUCIAL DE ESPERA PARA O ELEMENT NOT INTERACTABLE
                time.sleep(2) 
                
                prompt_linear = " ".join(prompt.split())
                
                # Foca explicitamente no input clicável
                box = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='textbox' and @contenteditable='true'] | //textarea")))

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", box)
                time.sleep(0.3)

                try:
                    self.driver.execute_script("arguments[0].focus();", box)
                    self.driver.execute_script("arguments[0].click();", box)
                except Exception:
                    # Se falhar o foco, tenta remoção forçada de overlays
                    try:
                        overlays = self.driver.find_elements(By.XPATH, "//div[contains(@class,'overlay') or @role='dialog']")
                        for o in overlays: self.driver.execute_script("arguments[0].remove();", o)
                        time.sleep(0.3)
                        self.driver.execute_script("arguments[0].focus(); arguments[0].click();", box)
                    except Exception: pass

                time.sleep(0.4)

                try:
                    box.send_keys(Keys.CONTROL, "a")
                    time.sleep(0.5)
                    box.send_keys(Keys.BACKSPACE)
                    time.sleep(0.2)
                except Exception: pass

                import pyperclip
                pyperclip.copy(prompt_linear)
                box.send_keys(Keys.CONTROL, "v")
                time.sleep(1.2)

                depois = self._ler_texto_prompt_box(box)
                _log(f"Tamanho esperado={len(prompt_linear)} | colado={len(depois)}")
                
                _log('Pressionando ENTER para submeter...')
                box.send_keys(Keys.ENTER)
                time.sleep(2)
                
                # Aguarda o processo real do card
                sucesso = self._aguardar_geracao_tracking_inline(prompt_linear, timeout_geracao)
                
                if sucesso:
                    return True
                else:
                    _log(f"⚠️ Card indicou erro na tentativa {tentativa_local}. O Google Flow falhou ao gerar o vídeo.")
                    time.sleep(2)
                    continue # Volta para o topo do FOR e tenta colar de novo na mesma tela

            except Exception as e:
                _log(f'Erro na tentativa local {tentativa_local}: {str(e)[:100]}')
                if tentativa_local == 3: return False
                time.sleep(2)
                
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
                    self._print_progress_inline("[FLOW-IA] Gerando vídeo... aguardando card aparecer")
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
                    return False
            except Exception: pass

            try:
                sucesso = self.driver.find_elements(By.XPATH, f"{base_xpath}//video | {base_xpath}//i[contains(text(), 'play_circle')]")
                if sucesso:
                    if linha_progresso_ativa: self._finish_progress_inline("[FLOW-IA] Gerando vídeo... 100% | pronto!")
                    else: _log("✔ Vídeo pronto e disponível para download.")
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
                    self._print_progress_inline(f"[FLOW-IA] Gerando vídeo... {pct_atual}")
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
                            self._print_progress_inline("[FLOW-IA] Gerando vídeo... processando")
                            ultimo_status_inline = "processando"
                            linha_progresso_ativa = True
                    else:
                        parado = int(time.time() - ultimo_movimento)
                        msg = f"[FLOW-IA] Gerando vídeo... aguardando progresso ({parado}s)"
                        if ultimo_status_inline != msg:
                            self._print_progress_inline(msg)
                            ultimo_status_inline = msg
                            linha_progresso_ativa = True
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
        _log("Timeout esgotado na geração do vídeo.")
        return False

    def resolver_permissoes_drive(self) -> None:
        try:
            continue_btn = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Continue')]")
            if continue_btn and continue_btn[0].is_displayed():
                self._js_click(continue_btn[0])
                time.sleep(1.5)
                allow_btn = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Allow')]")
                if allow_btn and allow_btn[0].is_displayed():
                    self._js_click(allow_btn[0])
                    time.sleep(1.5)
        except Exception: pass

    def _snapshot_mp4s(self, diretorio: Path) -> set[str]:
        diretorio.mkdir(parents=True, exist_ok=True)
        return {p.name for p in diretorio.glob("*.mp4")}

    def _esperar_download_mp4(self, download_dir: Path, antes: set[str], timeout=180) -> Path:
        fim = time.time() + timeout
        ultimo_temp = None
        while time.time() < fim:
            crdownloads = list(download_dir.glob("*.crdownload"))
            novos_mp4 = [p for p in download_dir.glob("*.mp4") if p.name not in antes]
            if novos_mp4 and not crdownloads:
                novos_mp4.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                arquivo = novos_mp4[0]
                _log(f"✔ Download concluído internamente no Windows: {arquivo.name}")
                return arquivo
            if crdownloads:
                crdownloads.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                atual = crdownloads[0]
                if ultimo_temp != atual.name:
                    _log(f"ℹ Baixando: {atual.name}")
                    ultimo_temp = atual.name
            time.sleep(1)
        raise TimeoutException("Timeout aguardando arquivo .mp4 no diretório.")

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
            except Exception: self._js_click(alvo_click)
            time.sleep(4.0)
            _log("Procurando botão 'Baixar'...")
            xpath_baixar = "//button[.//i[text()='download'] and .//div[contains(.,'Baixar')]]"
            try:
                btn_baixar = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_baixar)))
                btn_baixar.click()
            except TimeoutException:
                btn_baixar = self.driver.find_elements(By.XPATH, "//button[@aria-label='Download video'] | //button[contains(@aria-label, 'Download')] | //button[.//i[text()='download']]")
                if btn_baixar: self._js_click(btn_baixar[-1])
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
                    if btn_qualquer: self._js_click(btn_qualquer[0])
                    else: return False
            antes = self._snapshot_mp4s(download_dir)
            self.resolver_permissoes_drive()
            _log('Aguardando o arquivo terminar de baixar no Windows...')
            arquivo_baixado = self._esperar_download_mp4(download_dir, antes)
            if caminho_destino.exists(): caminho_destino.unlink()
            shutil.move(str(arquivo_baixado), str(caminho_destino))
            _log(f'✅ Vídeo baixado com sucesso: {caminho_destino.name}')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5); ActionChains(self.driver).send_keys(Keys.ESCAPE).perform(); time.sleep(1.5)
            return True
        except Exception as e:
            _log(f'Erro no download: {e}')
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


def ler_e_separar_cenas(caminho_txt: Path, qtd_cenas: int = 3) -> List[str]:
    """
    Lê o arquivo de roteiro e separa o conteúdo de cada cena baseado nas tags [Cena X].
    Suporta formatos [CENA 1], [Cena 1] ou [Cena 1: Título].
    """
    if not caminho_txt.exists():
        return []

    conteudo = caminho_txt.read_text(encoding='utf-8')
    
    # Remove lixos comuns da interface do Gemini que podem vir no início do arquivo
    conteudo = conteudo.replace("Show thinking", "").replace("Gemini said", "").strip()
    
    cenas_encontradas = []
    
    for i in range(1, qtd_cenas + 1):
        # Regex que busca por "[Cena i" ou "[CENA i" (ignora maiúsculas/minúsculas e aceita texto depois do número)
        padrao_inicio = rf"\[[Cc][Ee][Nn][Aa]\s*{i}.*?\]"
        padrao_proxima = rf"\[[Cc][Ee][Nn][Aa]\s*{i+1}.*?\]"
        
        # Se for a última cena, tentamos achar o marcador de Legenda como fim
        if i == qtd_cenas:
            padrao_proxima = r"\[[Ll]egenda.*?\]"

        # Localiza o início da cena atual
        match_inicio = re.search(padrao_inicio, conteudo)
        
        if match_inicio:
            inicio_pos = match_inicio.end()
            # Busca onde começa a próxima cena (ou a legenda) para saber onde parar
            match_fim = re.search(padrao_proxima, conteudo[inicio_pos:])
            
            if match_fim:
                texto_cena = conteudo[inicio_pos : inicio_pos + match_fim.start()]
            else:
                # Se não achou a próxima tag, pega até o fim do arquivo
                texto_cena = conteudo[inicio_pos:]
            
            cenas_encontradas.append(texto_cena.strip())

    return cenas_encontradas
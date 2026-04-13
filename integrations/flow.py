# arquivo: integrations/flow.py
# descricao: Fachada de integracao com o Google Flow (Humble) para gerar videos
# a partir do roteiro de 3 cenas. Blindado com lógica nativa do humble_client.py.

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
        try:
            seletores_modais = [
                "//span[contains(text(), 'Got it')] | //button[contains(., 'Got it')] | "
                "//span[contains(text(), 'I agree')] | //button[contains(., 'Agree')] | "
                "//span[contains(text(), 'Enable')] | //button[contains(., 'Enable')] | "
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree and continue')] | "
                "//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree and continue')]"
            ]
            for seletor in seletores_modais:
                botoes = self.driver.find_elements(By.XPATH, seletor)
                for btn in botoes:
                    if btn.is_displayed():
                        _log('Modal detectado (Terms/Workspace). Fechando automaticamente...')
                        self._js_click(btn)
                        time.sleep(1.5)
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
        
        # Focar a caixa de prompt garante que os botões inferiores da interface apareçam
        try:
            box = self.driver.find_element(By.XPATH, "//div[@role='textbox' and @contenteditable='true']")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", box)
            self._js_click(box)
            time.sleep(0.5)
        except Exception:
            pass

        # LÓGICA DE MEMÓRIA DE UPLOAD (A imagem só é upada 1x no projeto)
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

        # LÓGICA DE VINCULAÇÃO INTELIGENTE (Trata a Cena 2 e 3 de forma limpa)
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
                # Se o botão inicial não está lá, ou a imagem já está preenchendo ele, ou a UI mudou
                # Verificamos se o nome do arquivo já está na tela
                img_ja_vinculada = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{nome_arquivo}')]")
                if img_ja_vinculada and any(el.is_displayed() for el in img_ja_vinculada):
                    _log(f'✔ A imagem {nome_arquivo} já está selecionada/vinculada na interface! (Reaproveitada)')
                else:
                    _log(f'Aviso: Não consegui confirmar 100% visualmente, mas assumindo que {nome_arquivo} continua vinculada da cena anterior.')

            return True

        except Exception as e:
            _log(f'🚨 Falha ao tratar anexo de imagem: {e}')
            return False

    def _ler_texto_prompt_box(self, box: WebElement) -> str:
        try:
            return box.get_attribute("textContent") or box.text or ""
        except Exception:
            return ""

    def enviar_prompt_e_aguardar(self, prompt: str, timeout_geracao: int = 420) -> bool:
        _log("[FLOW-IA] Preenchendo prompt (Colando com Pyperclip)...")
        try:
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.2)
            
            prompt_linear = " ".join(prompt.split())
            
            box = self._wait_visible(
                By.XPATH,
                "//div[@role='textbox' and @contenteditable='true']",
                timeout=20,
                descricao="campo prompt (Slate.js)",
            )

            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", box)
            time.sleep(0.3)

            try:
                self.driver.execute_script("arguments[0].focus();", box)
                self.driver.execute_script("arguments[0].click();", box)
            except Exception:
                try:
                    overlays = self.driver.find_elements(
                        By.XPATH,
                        "//div[contains(@class,'sc-d23b167b-0') or contains(@class,'overlay') or contains(@class,'hTyrgE')]"
                    )
                    for o in overlays:
                        self.driver.execute_script("arguments[0].remove();", o)
                    time.sleep(0.3)
                    self.driver.execute_script("arguments[0].focus();", box)
                    self.driver.execute_script("arguments[0].click();", box)
                except Exception:
                    pass

            time.sleep(0.4)

            try:
                box.send_keys(Keys.CONTROL, "a")
                time.sleep(0.2)
            except Exception:
                pass

            pyperclip.copy(prompt_linear)
            box.send_keys(Keys.CONTROL, "v")
            time.sleep(1.2)

            depois = self._ler_texto_prompt_box(box)
            _log(f"Tamanho esperado={len(prompt_linear)} | colado={len(depois)}")
            
            trecho_ref = prompt_linear[:50].strip()
            if trecho_ref and trecho_ref not in depois:
                _log("AVISO: trecho inicial do prompt não confirmado na leitura, seguindo mesmo assim.")

            _log('Pressionando ENTER para submeter...')
            box.send_keys(Keys.ENTER)
            time.sleep(2)
            
            return self._aguardar_geracao_tracking_inline(prompt_linear, timeout_geracao)

        except Exception as e:
            _log(f'Erro durante a geração do vídeo/envio de prompt: {e}')
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
        except Exception:
            return None

    def _encontrar_card_por_prompt(self, prompt: str):
        trecho = prompt[:40].strip()
        cards = self._listar_cards()
        for c in cards:
            try:
                txt_bruto = self.driver.execute_script("return arguments[0].textContent;", c)
                if txt_bruto and trecho in txt_bruto:
                    return c
            except Exception:
                pass
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
                if card:
                    self.ultimo_tile_id_gerado = self._obter_tile_id(card)
                
                if not self.ultimo_tile_id_gerado:
                    self._print_progress_inline("[FLOW-IA] Gerando vídeo... aguardando card aparecer")
                    time.sleep(2)
                    continue
                else:
                    if linha_progresso_ativa:
                        self._finish_progress_inline()
                        linha_progresso_ativa = False
                    _log(f"[FLOW-IA] Tile ID rastreado: {self.ultimo_tile_id_gerado}")

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
                    if linha_progresso_ativa:
                        self._finish_progress_inline("[FLOW-IA] Gerando vídeo... 100% | pronto!")
                    else:
                        _log("✔ Vídeo pronto e disponível para download.")
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

        if linha_progresso_ativa:
            self._finish_progress_inline()
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
        except Exception:
            pass

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
            if self.ultimo_tile_id_gerado:
                card = self._encontrar_card_por_tile_id(self.ultimo_tile_id_gerado)
                
            if not card:
                card = self._card_mais_recente()
                
            if not card:
                _log("ERRO: Não encontrei card do vídeo pronto para clicar.")
                return False

            alvo_click = None
            try:
                alvo_click = card.find_element(By.XPATH, ".//button[contains(@class,'sc-d64366c4-1') and .//video]")
                _log("Botão contendo <video> encontrado para clique.")
            except Exception: pass

            if alvo_click is None:
                try:
                    alvo_click = card.find_element(By.XPATH, ".//video")
                    _log("<video> encontrado para clique direto.")
                except Exception: pass
                
            if alvo_click is None:
                _log("ERRO: Encontrei o card, mas não achei elemento clicável (botão/vídeo).")
                return False

            self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", alvo_click)
            time.sleep(0.4)
            try:
                alvo_click.click()
                _log("✔ Clique normal no card/vídeo disparado.")
            except Exception:
                _log("ℹ Clique normal falhou, tentando clique via JS...")
                self._js_click(alvo_click)
                _log("✔ Clique via JS no card/vídeo disparado.")
            
            time.sleep(4.0)

            _log("Procurando botão 'Baixar'...")
            xpath_baixar = "//button[.//i[text()='download'] and .//div[contains(.,'Baixar')]]"
            try:
                btn_baixar = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_baixar)))
                btn_baixar.click()
            except TimeoutException:
                btn_baixar = self.driver.find_elements(By.XPATH, "//button[@aria-label='Download video'] | //button[contains(@aria-label, 'Download')] | //button[.//i[text()='download']]")
                if btn_baixar:
                    self._js_click(btn_baixar[-1])
                else:
                    _log("ERRO: Botão de baixar não encontrado.")
                    return False
            
            time.sleep(1.0) 

            _log("Procurando opção 720p...")
            xpath_720p = "//button[@role='menuitem'][.//span[text()='720p'] and .//span[contains(.,'Tamanho original')]]"
            try:
                btn_720 = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_720p)))
                btn_720.click()
            except TimeoutException:
                _log("Aviso: '720p' com Tamanho original não encontrado. Tentando fallback...")
                xpath_fallback = "//button[@role='menuitem'][contains(., '720p') or contains(., '1080p')]"
                try:
                    btn_fallback = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_fallback)))
                    btn_fallback.click()
                except TimeoutException:
                    _log("Aviso: Falha ao encontrar menuitem de resolução. Clicando na primeira opção disponível.")
                    btn_qualquer = self.driver.find_elements(By.XPATH, "//button[@role='menuitem']")
                    if btn_qualquer:
                        self._js_click(btn_qualquer[0])
                    else:
                        _log("ERRO: Nenhuma opção de resolução encontrada no menu.")
                        return False

            antes = self._snapshot_mp4s(download_dir)
            self.resolver_permissoes_drive()
            
            _log('Aguardando o arquivo terminar de baixar no Windows...')
            arquivo_baixado = self._esperar_download_mp4(download_dir, antes)
            
            if caminho_destino.exists():
                caminho_destino.unlink()
                
            shutil.move(str(arquivo_baixado), str(caminho_destino))
            _log(f'✅ Vídeo baixado com sucesso: {caminho_destino.name}')
            
            _log("Voltando para a tela de prompts (mantendo o projeto aberto)...")
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1.5)

            return True

        except Exception as e:
            _log(f'Erro no download nativo do Flow: {e}')
            return False


# =====================================================================
#   REMOÇÃO DE EMOJIS (LIMPEZA DO PROMPT ANTES DE ENVIAR)
# =====================================================================
def _remover_emojis(texto: str) -> str:
    """Remove símbolos e emojis do texto para evitar erros de renderização no Flow."""
    padrao_emoji = re.compile(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF'
        r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\u2600-\u26FF\u2700-\u27BF\u2B50\u2B55\u23F0-\u23F3\u23F8-\u23FA\uFE0F]'
    )
    return padrao_emoji.sub(r'', texto)


def ler_e_separar_cenas(caminho_roteiro: Path) -> List[str]:
    if not caminho_roteiro.exists():
        raise FileNotFoundError(f"Arquivo de roteiro não encontrado: {caminho_roteiro}")
        
    conteudo = caminho_roteiro.read_text(encoding="utf-8")
    
    padrao = re.compile(r"\[CENA \d\](.*?)(?=\[CENA \d\]|$)", re.DOTALL | re.IGNORECASE)
    matches = padrao.findall(conteudo)
    
    cenas = []
    for m in matches:
        cena_limpa = m.strip()
        if cena_limpa:
            # SANITIZAÇÃO: Remove todos os emojis do texto da cena!
            cena_sem_emoji = _remover_emojis(cena_limpa)
            # Remove espaços duplos criados pela ausência dos emojis
            cena_sem_emoji = " ".join(cena_sem_emoji.split())
            cenas.append(cena_sem_emoji)
            
    return cenas
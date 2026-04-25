# arquivo: integrations/gemini.py
# descricao: fachada GeminiAnunciosViaFlow blindada para validacao de imagem,
# geracao POV e criacao de roteiro dinâmico com suporte a Testes A/B (múltiplos roteiros).
# Otimizado para VELOCIDADE EXTREMA, DOWNLOAD NATIVO (60s) e AUTO-F5 EM ERROS DA UI.
# Adicionado suporte para avaliar múltiplas variantes de vídeo e eleger a melhor via interface Web.

from __future__ import annotations

import re
import time
import shutil
import pyperclip
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from integrations.utils import _log as log_base, salvar_print_debug, js_click, scroll_ao_fim, _get_logs_dir, salvar_ultimo_prompt, limpar_diretorio_visao, forcar_fechamento_janela_windows

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from anuncios.prompts import (
    PROMPT_CLASSIFICACAO_ARQUIVOS,
    PROMPT_VALIDACAO_PRODUTO,
    PROMPT_GERACAO_IMAGEM_POV,
    PROMPT_GERACAO_IMAGEM_FRONTAL,
    PROMPT_GERACAO_IMAGEM_CAMINHANDO,
    PROMPT_GERACAO_IMAGEM_FLAT,
    PROMPT_GERACAO_IMAGEM_PES,  
    PROMPT_JURI_CANDIDATOS_IMAGEM_BASE,
    PROMPT_JURI_TESTE_AB_IMAGEM_BASE,
    PROMPT_MESTRE_ROTEIRO,
    PROMPT_EXECUCAO_ROTEIRO,
    PROMPT_JURI_VIDEO
)

EXTENSOES_IMAGEM = ('.jpg', '.jpeg', '.png', '.webp')

# Atalho para manter o prefixo [GEMINI-IA] automaticamente neste arquivo
def _log(msg: str):
    log_base(msg, prefixo="GEMINI-IA")


class GeminiAnunciosViaFlow:
    def __init__(self, driver: Any, url_gemini: str, timeout: int = 30):
        self.driver = driver
        self.url_gemini = url_gemini
        self.wait = WebDriverWait(driver, timeout, poll_frequency=0.1)
        self.timeout = timeout
        
        # --- ZERANDO DIRETÓRIO DE LOGS A CADA CICLO ---
        limpar_diretorio_visao()
        self.pasta_logs_visao = _get_logs_dir() / "visao"

    def abrir_gemini(self) -> None:
        _log('Abrindo Gemini e validando estado da tela...')
        self.driver.get(self.url_gemini) 
        time.sleep(4.0) # Aumentado para 4s para estabilizar o Angular

        tela_liberada = False
        
        self._superar_bloqueios_e_onboarding()

        try:
            # Selecionamos o alvo principal (Microfone ou Caixa de Texto)
            alvo = self.driver.find_element(By.CSS_SELECTOR, 'button.speech_dictation_mic_button, rich-textarea div[contenteditable="true"]')
            
            if alvo.is_displayed():
                # --- A PROVA REAL (RAIO-X) ---
                # Verificamos se o elemento no topo dessa coordenada é o próprio alvo.
                # Se houver uma landing page na frente, o 'elementFromPoint' retornará a landing page, não o chat.
                is_obstruido = self.driver.execute_script("""
                    var el = arguments[0];
                    var rect = el.getBoundingClientRect();
                    var cx = rect.left + rect.width / 2;
                    var cy = rect.top + rect.height / 2;
                    var elAtPoint = document.elementFromPoint(cx, cy);
                    return !el.contains(elAtPoint);
                """, alvo)
                
                if not is_obstruido:
                    tela_liberada = True
        except:
            pass

        # Se a tela está obstruída ou os elementos não existem, CHAMA O TRATOR
        if not tela_liberada:
            _log('⚠️ Interface obstruída ou não detectada. Acionando o trator...')
            salvar_print_debug(self.driver, "BLOQUEIO_DETECTADO")
            
            if not self._superar_bloqueios_e_onboarding():
                _log("⚠️ Trator falhou. Tentando Refresh de emergência...")
                self.driver.refresh()
                time.sleep(5)
                # Check final pós-refresh
                if not self.driver.find_elements(By.CSS_SELECTOR, 'button.speech_dictation_mic_button'):
                    raise Exception("Interface bloqueada. Rotacionando conta.")
            
            _log("✅ Interface liberada.")

    def _superar_bloqueios_e_onboarding(self) -> bool:
        """
        Função MEGA GENÉRICA estilo 'Trator'.
        Lida com Privacy Hub, Termos de Uso e Onboarding de contas novas.
        """
        salvar_print_debug(self.driver,"VERIFICANDO_BLOQUEIOS_UI")
        _log("🔥 ENTROU EM _superar_bloqueios_e_onboarding")
        
        # 🚨 ACELERAÇÃO MÁXIMA: Desliga a espera automática do Selenium
        self.driver.implicitly_wait(0)
        
        try:
            palavras_chave = [
                'chat with gemini', 'conversar com', 'i agree', 'concordo', 'aceito',
                'continue', 'continuar', 'next', 'próximo', 'got it', 'entendi',
                'try gemini', 'experimentar', 'ok', 'aceitar', 'accept', 'use gemini',
                'more', 'mais', 'done', 'concluir', 'finalizar', 'agree', 'no, thanks', 'não, obrigado'
            ]
            
            for rodada in range(6):
                try:
                    self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    #time.sleep(0.1)
                except: pass
                    
                clicou_algo = False
                
                seletores_prioridade = [
                    "button[data-test-id='upload-image-agree-button']", 
                    "button.agree-button",                              
                    "button[jslog*='173921']",                          
                    ".mat-mdc-dialog-actions button",                   
                    "button.mat-mdc-unelevated-button"                  
                ]
                
                xpath_condicoes = " or ".join([f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{p}')" for p in palavras_chave])
                
                # --- 🛡️ BLINDAGEM V3: BLOQUEIO DE COMPONENTES CUSTOMIZADOS ---
                # Adicionamos not(ancestor::bard-sidenav) para matar o clique no histórico.
                # Também mantemos o not(ancestor::nav) por segurança para outras telas.
                xpath_exclusao = "not(ancestor::nav) and not(ancestor::bard-sidenav)"
                
                xpath_monstro = (
                    f"//button[{xpath_exclusao}][{xpath_condicoes}] | "
                    f"//a[{xpath_exclusao}][{xpath_condicoes}] | "
                    f"//span[{xpath_exclusao}][{xpath_condicoes}]/ancestor::button"
                )
                
                # 1. Monta lista de candidatos priorizando o MODAL
                candidatos = []
                for sel in seletores_prioridade:
                    try: 
                        els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        # Filtro extra para seletores CSS: ignora se estiver dentro do sidenav
                        for el in els:
                            if not self.driver.execute_script("return arguments[0].closest('bard-sidenav')", el):
                                candidatos.append(el)
                    except: pass
                
                try: candidatos.extend(self.driver.find_elements(By.XPATH, xpath_monstro))
                except: pass
                
                try: 
                    fab = self.driver.find_element(By.CSS_SELECTOR, "button.mat-mdc-extended-fab")
                    if not self.driver.execute_script("return arguments[0].closest('bard-sidenav')", fab):
                        candidatos.append(fab)
                except: pass

                # 2. Executa o clique de alta pressão
                for btn in candidatos:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            texto_btn = (btn.text or btn.get_attribute('aria-label') or '').strip().replace('\n', ' ')
                            _log(f"🎯 Trator encontrou: '{texto_btn[:30]}'. Executando clique de alta pressão...")
                            
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                            self.driver.execute_script("arguments[0].focus();", btn)
                            
                            self.driver.execute_script("""
                                var btn = arguments[0];
                                btn.style.pointerEvents = 'auto'; 
                                btn.style.visibility = 'visible';
                                var label = btn.querySelector('.mdc-button__label') || btn;
                                var mousedown = new MouseEvent('mousedown', { 'bubbles': true, 'cancelable': true, 'view': window });
                                var click = new MouseEvent('click', { 'bubbles': true, 'cancelable': true, 'view': window });
                                var mouseup = new MouseEvent('mouseup', { 'bubbles': true, 'cancelable': true, 'view': window });
                                label.dispatchEvent(mousedown);
                                label.dispatchEvent(click);
                                label.dispatchEvent(mouseup);
                            """, btn)
                            
                            try:
                                ActionChains(self.driver).move_to_element(btn).click().perform()
                                btn.send_keys(Keys.ENTER)
                                btn.send_keys(Keys.SPACE)
                            except: pass
                                
                            clicou_algo = True
                            _log("⏳ Clique disparado. Validando transição...")
                            salvar_print_debug(self.driver,"VERIFICANDO SE CLICOU NO BOTAO DE BLOQUEIO")
                            time.sleep(0.1) 
                            break 
                    except: continue
                
                # 3. Verificação de Sucesso
                try:
                    textarea = self.driver.find_elements(By.CSS_SELECTOR, 'rich-textarea div[contenteditable="true"]')
                    if textarea and textarea[0].is_displayed():
                        _log("✅ Interface de chat liberada!")
                        return True
                except: pass

                if not clicou_algo: break
                    
            return False
            
        finally:
            # 🚨 RELIGA O FREIO DE MÃO (Timeout original de 5s estipulado no .env)
            self.driver.implicitly_wait(5)

    def _forcar_modelo_pro(self) -> None:
        _log('Verificando/Forçando modelo Pro...')
        
        time.sleep(1.0) 
        
        for tentativa in range(1, 4):
            try:
                menu_btn_elements = self.driver.find_elements(By.CSS_SELECTOR, 'button[data-test-id="bard-mode-menu-button"], button[aria-label="Open mode picker"]')
                if not menu_btn_elements or not menu_btn_elements[0].is_displayed():
                    _log(f'Botão de modelo ainda não apareceu ou está coberto (Tentativa {tentativa}/3)...')
                    
                    # Tenta dar mais um ESC para garantir que menus ocultos sumam
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1.5)
                    continue 

                menu_btn = menu_btn_elements[0]
                texto_atual = (menu_btn.text or '').strip().lower()
                
                if 'pro' in texto_atual and 'thinking' not in texto_atual and 'pensamento' not in texto_atual:
                    _log('✅ Modelo Pro já está ativo.')
                    return 
                    
                _log(f'Modelo atual é "{texto_atual}". Abrindo menu de seleção (Tentativa {tentativa}/3)...')
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", menu_btn)
                time.sleep(0.5)
                js_click(self.driver,menu_btn)
                time.sleep(1.5) 
                
                seletores_pro = [
                    'button[data-mode-id="e6fa609c3fa255c0"]',
                    'button[data-test-id="bard-mode-option-pro"]'
                ]
                
                clicou_pro = False
                for seletor in seletores_pro:
                    opcoes_pro = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for opcao in opcoes_pro:
                        texto_opcao = (opcao.text or '').strip().lower()
                        if 'thinking' not in texto_opcao and 'pensamento' not in texto_opcao and 'fast' not in texto_opcao:
                            if opcao.is_displayed():
                                js_click(self.driver,opcao)
                                clicou_pro = True
                                break
                    if clicou_pro:
                        break

                if clicou_pro:
                    time.sleep(1.5) 
                    _log('✅ Modelo Pro selecionado com sucesso.')
                    salvar_print_debug(self.driver,"PRO_SELECIONADO_SUCESSO")
                    return 
                else:
                    _log('⚠️ Opção Pro não encontrada no DOM. Fechando menu e recomeçando...')
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1.0)
                    
            except Exception as e:
                _log(f'⚠️ Erro na interface ao tentar mudar pro Pro ({e}). Tentando novamente...')
                time.sleep(1.0)
                
        _log('🚨 Aviso: Esgotaram as tentativas de forçar o modelo Pro. Seguindo em frente...')

    def abrir_novo_chat_limpo(self) -> None:
        """
        Versão corrigida: Se já estamos no Gemini, não damos refresh nem reabrimos a URL.
        Apenas clicamos no botão de Novo Chat.
        """
        scroll_ao_fim(self.driver)
        _log('Limpando interface para novo chat...')
            
        try:
            seletores_botao = [
                'side-nav-action-button[data-test-id="new-chat-button"] a',
                'a.side-nav-action-collapsed-button[href="/app"]',
                'span[data-test-id="new-chat-button"]',
                'div[aria-label*="Novo chat"]',
                'div[aria-label*="New chat"]'
            ]
            
            clicou = False
            for seletor in seletores_botao:
                botoes = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for btn in botoes:
                    if btn.is_displayed():
                        js_click(self.driver, btn)
                        _log('Botão "Novo Chat" acionado.')
                        clicou = True
                        break
                if clicou: break
            
            # Se não conseguiu clicar, não damos refresh. Apenas tentamos seguir ou validar a caixa.
            if not clicou:
                _log('Aviso: Botão de Novo Chat não visível. Verificando se a caixa de texto já está limpa...')
            
            # Validação curta da caixa de texto
            self._obter_textarea_prompt()
            _log('Pronto para novos comandos.')
            
            # Garante o modelo Pro
            self._forcar_modelo_pro()
            
        except Exception as e:
            _log(f'Erro ao limpar chat: {e}')
            raise

    def fechar_popup_tardio_chrome_no_gemini(self) -> None:
        seletores = [
            'button[aria-label*="Continuar como"]',
            'button[aria-label*="Chrome sem uma conta"]',
            'button[jsname]',
        ]
        textos_alvo = ['Continuar como', 'Usar o Chrome sem uma conta']
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    if not el.is_displayed():
                        continue
                    texto = (el.text or el.get_attribute('aria-label') or '').strip()
                    if any(t in texto for t in textos_alvo):
                        js_click(self.driver,el)
                        _log(f'Popup tardio do Chrome tratado: {texto}')
                        salvar_print_debug(self.driver,"POPUP_TARDIO_FECHADO")
                        return
            except Exception:
                pass

    def _encontrar_input_file_visivel_ou_oculto(self, timeout: int = 10) -> WebElement:
        fim = time.time() + timeout
        ultimo_erro = None
        seletores = ['input[type="file"]', 'input[type="file"][multiple]', 'input[accept*="image"]']
        while time.time() < fim:
            try:
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                for seletor in seletores:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in elementos:
                        if el is not None:
                            return el
            except Exception as e:
                ultimo_erro = e
            time.sleep(0.1) 
        if ultimo_erro:
            raise ultimo_erro
        raise TimeoutException('Nenhum input[type=file] encontrado no DOM.')

    def _obter_textarea_prompt(self) -> WebElement:
        seletores = [
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"][role="textbox"]',
            '.initial-input-area-container textarea',
            'textarea[placeholder="Ask Gemini"]',
            'div[aria-label*="Message"]',
            'div.editor-container div[contenteditable="true"]'
        ]
        
        fim = time.time() + 8
        while time.time() < fim:
            for seletor in seletores:
                try:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in elementos:
                        if el.is_displayed() and el.is_enabled():
                            return el
                except Exception:
                    pass
            time.sleep(0.5)
            
        # Se chegou aqui, passou 8 segundos e a caixa não apareceu.
        _log("⚠️ Caixa de digitação sumiu! Chamando trator para tentar recuperar a tela...")
        if self._superar_bloqueios_e_onboarding():
            # Trator rodou, vamos tentar achar a caixa uma última vez
            for seletor in seletores:
                try:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in elementos:
                        if el.is_displayed() and el.is_enabled():
                            return el
                except Exception:
                    pass
                    
        salvar_print_debug(self.driver,"ERRO_TEXTAREA_MORTA")
        raise TimeoutException('Falha irrecuperável: A caixa de digitação não existe na tela atual.')

    def _obter_botao_enviar(self) -> Optional[WebElement]:
        seletores = ['button[aria-label="Send message"]', '.send-button-container button', '.initial-input-area-container .send-icon']
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    if not el.is_displayed():
                        continue
                    aria_disabled = (el.get_attribute('aria-disabled') or '').strip().lower()
                    disabled = el.get_attribute('disabled')
                    if aria_disabled == 'false' and disabled is None:
                        return el
            except Exception:
                pass
        return None

    def _aguardar_upload_estabilizar(self, timeout: int = 20, is_video: bool = False) -> None:
        fim = time.time() + timeout
        
        salvar_print_debug(self.driver,f"UPLOAD_AGUARDANDO_INICIO_isvideo_{is_video}")
        
        if is_video:
            _log(f'Aguardando estabilização do upload de VÍDEO (max {timeout}s)...')
            while time.time() < fim:
                try:
                    scroll_ao_fim(self.driver)
                    carregando = False
                    try:
                        loaders = self.driver.find_elements(By.CSS_SELECTOR, 'mat-progress-bar, .uploading, [role="progressbar"], mat-spinner, .loading-spinner, [aria-label*="loading"], [aria-label*="uploading"]')
                        if loaders and any(l.is_displayed() for l in loaders):
                            carregando = True
                    except Exception:
                        pass
                    
                    if not carregando:
                        btn = self._obter_botao_enviar()
                        if btn is not None:
                            time.sleep(2.0)
                            _log('Upload de vídeo estabilizado e botão de envio habilitado.')
                            salvar_print_debug(self.driver,"UPLOAD_VIDEO_OK")
                            return
                except Exception:
                    pass
                time.sleep(1.0)
        else:
            while time.time() < fim:
                try:
                    scroll_ao_fim(self.driver)
                    btn = self._obter_botao_enviar()
                    if btn is not None:
                        _log('Botão de envio habilitado apos upload.')
                        return
                except Exception:
                    pass
                time.sleep(0.1)
                
        _log('Aviso: upload nao confirmou estado pronto dentro do tempo esperado.')
        salvar_print_debug(self.driver,"UPLOAD_TIMEOUT_AVISO")

    def _texto_limpo(self, txt: str) -> str:
        txt = (txt or '').replace('\r', '\n')
        txt = re.sub(r'\n+', '\n', txt).strip()
        return txt

    def _parece_texto_inutil_ui(self, txt: str) -> bool:
        if not txt:
            return True
        upper = self._texto_limpo(txt).upper()
        lixos_exatos = {
            'ANÁLISE', 'ANALISE', 'GEMINI SAID',
            'ANÁLISE\nGEMINI SAID', 'ANALISE\nGEMINI SAID',
            'GEMINI SAID\nANÁLISE', 'GEMINI SAID\nANALISE',
            'SHOW THINKING',
        }
        if upper in lixos_exatos:
            return True
        linhas = [x.strip() for x in upper.split('\n') if x.strip()]
        if linhas and all(l in {'ANÁLISE', 'ANALISE', 'GEMINI SAID', 'SHOW THINKING'} for l in linhas):
            return True
        return False

    def _gemini_esta_processando(self) -> bool:
        try:
            mics = self.driver.find_elements(By.CSS_SELECTOR, 'button.speech_dictation_mic_button, button[aria-label="Microphone"]')
            if not mics:
                return True
            for mic in mics:
                if mic.is_displayed():
                    return False
            return True
        except StaleElementReferenceException:
            return True
        except Exception:
            return False

    def _extrair_texto_resposta_recente(self) -> str:
        """Nova Lógica (Blindada Suprema): Busca o texto em múltiplos níveis do DOM e ignora erros de stale element."""
        salvar_print_debug(self.driver,"EXTRAINDO_TEXTO_PROCURANDO")
        
        # Seletores atualizados: pega do mais específico pro mais genérico
        seletores = [
            'model-response .model-response-text',
            'model-response message-content',
            'model-response',
            # Fallbacks caso o Gemini esconda o componente principal num Shadow DOM
            '.message-content',
            'div[data-test-id="model-response"]'
        ]
        
        for seletor in seletores:
            try:
                time.sleep(0.5) # Dá tempo pro Angular processar
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                if not elementos: 
                    continue
                
                el = elementos[-1]
                
                # Tenta pegar o texto por 3 caminhos diferentes direto na engine do Chrome
                script = """
                    return arguments[0].textContent || 
                           arguments[0].innerText || 
                           arguments[0].value || '';
                """
                txt_bruto = self.driver.execute_script(script, el)
                txt = self._texto_limpo(txt_bruto).strip()
                
                if not txt:
                    continue
                    
                # Ignora as mensagens de carregamento da interface em PT e EN
                lixos_carregamento = [
                    "show thinking", "gemini said", "carregando", 
                    "is thinking", "pensando", "analisando"
                ]
                if any(lixo in txt.lower() for lixo in lixos_carregamento):
                    continue
                
                salvar_print_debug(self.driver,"EXTRAINDO_TEXTO_SUCESSO")
                return txt
            except Exception as e:
                # Silenciamos o erro mas seguimos tentando os próximos seletores
                pass
                
        salvar_print_debug(self.driver,"EXTRAINDO_TEXTO_FALHA_DOM")
        return ''

    def _interpretar_resposta_binaria(self, texto: str) -> Optional[bool]:
        if not texto:
            return None
        up = self._texto_limpo(texto).upper()
        up_clean = re.sub(r'[*_.\-",:;]', ' ', up)
        
        sim_matches = list(re.finditer(r'\bSIM\b', up_clean))
        nao_matches = list(re.finditer(r'\b(NAO|NÃO)\b', up_clean))
        
        last_sim = sim_matches[-1].start() if sim_matches else -1
        last_nao = nao_matches[-1].start() if nao_matches else -1
        
        if last_sim > last_nao:
            return True
        elif last_nao > last_sim:
            return False
            
        return None

    def _aguardar_fim_analise(self, timeout: int = 60) -> bool:
        """
        Lógica baseada puramente no estado dos botões (Stop vs Mic/Send).
        Identifica quando o processamento terminou validando o sumiço do Stop
        e o reaparecimento do Microfone ou Seta de Envio.
        """
        _log(f'Gemini processando... Monitorando botões (Timeout: {timeout}s).')
        salvar_print_debug(self.driver,"AGUARDANDO_ANALISE_INICIO")
        fim = time.time() + timeout
        
        # Pausa obrigatória para o Angular processar o clique e renderizar o botão Stop
        time.sleep(5.0)
        salvar_print_debug(self.driver,"AGUARDANDO_ANALISE_POS_5SEG")
        
        while time.time() < fim:
            try:
                # 1. Procura ativamente pelo botão de STOP na tela
                botoes_stop = self.driver.find_elements(By.CSS_SELECTOR, 'button.stop, button[aria-label="Stop response"], button[aria-label*="Stop"]')
                
                if botoes_stop and any(b.is_displayed() for b in botoes_stop):
                    # IA ainda gerando...
                    pass
                else:
                    # 2. O Stop SUMIU. Precisamos confirmar se a interface voltou ao estado ocioso
                    botoes_ociosos = self.driver.find_elements(
                        By.CSS_SELECTOR, 
                        'button.speech_dictation_mic_button, button[aria-label*="microphone" i], button[aria-label*="Microfone" i], button.send-button, button[aria-label*="Send" i]'
                    )
                    
                    if botoes_ociosos and any(b.is_displayed() for b in botoes_ociosos):
                        # Confirmação dupla: garante que spinners globais de página também não estão rodando
                        loaders = self.driver.find_elements(By.CSS_SELECTOR, 'mat-progress-bar, .uploading, [role="progressbar"]')
                        if not any(l.is_displayed() for l in loaders):
                            _log("Gatilho detectado: Botão Stop sumiu e interface voltou a ficar ociosa. Geração concluída!")
                            time.sleep(1.0)
                            salvar_print_debug(self.driver,"AGUARDANDO_ANALISE_SUCESSO")
                            return True
                            
            except StaleElementReferenceException:
                pass
            except Exception:
                pass
                
            time.sleep(0.5)
            
        # --- 📸 O PONTO CHAVE: PRINT ANTES DE MORRER ---
        _log(f'Aviso: Timeout de {timeout}s atingido aguardando mudança nos botões.')
        
        # Tira o print no último segundo possível para vermos se o Stop ainda estava lá
        salvar_print_debug(self.driver, "DETALHE_ESTADO_TELA_NA_FALHA")
        
        return False
    
    def _aguardar_resposta_textual(self, timeout: int = 60) -> str:
        finalizou = self._aguardar_fim_analise(timeout=timeout)
        
        if not finalizou:
            # 📸 PRINT DE SEGURANÇA ANTES DO REFRESH
            salvar_print_debug(self.driver, "ESTADO_TELA_PRE_RECOVERY")

            _log('⚠️ Timeout na UI detectado. Forçando F5 Recovery e reinício da etapa...')
            self.driver.refresh()
            time.sleep(3.0) # Tempo para o Chrome estabilizar pós-refresh
            self._superar_bloqueios_e_onboarding()
            
            # Em vez de tentar ler um texto que sumiu, retornamos um sinal de RESET
            return 'RECOVERY_TRIGGERED'
        
        time.sleep(2.0) # Pausa para o Angular renderizar o texto final
        
        # --- POLLING INTELIGENTE ---
        _log("Iniciando captura dinâmica de texto (Polling)...")
        fim = time.time() + 10.0 
        
        while time.time() < fim:
            try:
                scroll_ao_fim(self.driver)
                texto = self._extrair_texto_resposta_recente()
                if texto and not self._parece_texto_inutil_ui(texto):
                    _log(f"✅ Texto capturado com sucesso.")
                    return texto
            except Exception:
                pass
            time.sleep(1.5)
            
        return 'SEM_RESPOSTA_UTIL'
    
    def anexar_arquivo_local(self, caminho: Path) -> None:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f'Arquivo nao encontrado: {caminho}')
        _log(f'Anexando arquivo: {caminho.name}')
        
        # 1. Chamar apenas se NÃO for headless (otimização de 0.5s)
        # O Chrome Headless não dispara janelas do Windows, então podemos pular isso.
        is_headless = self.driver.capabilities.get('moz:headless') or 'headless' in str(self.driver.capabilities).lower()
        if not is_headless:
            from integrations.utils import forcar_fechamento_janela_windows
            forcar_fechamento_janela_windows()

        try:
            scroll_ao_fim(self.driver)
            
            # --- TENTATIVA DE INPUT DIRETO ---
            input_file = None
            try:
                # Busca relâmpago: se já estiver no DOM, economiza todo o processo de clique
                input_file = self.driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
            except:
                pass

            if not input_file:
                # --- FALLBACK 1: BOTÃO PRINCIPAL ---
                seletores_mais = [
                    'button[jslog*="188890"]', # JSLog é o mais rápido e estável (identificação interna)
                    'button[aria-label*="envio de arquivo"]', 
                    'button[aria-label*="upload file menu"]'
                ]
                
                for seletor in seletores_mais:
                    try:
                        btn = self.driver.find_element(By.CSS_SELECTOR, seletor)
                        if btn.is_displayed():
                            js_click(self.driver, btn)
                            break
                    except: continue

                # --- FALLBACK 2: BOTÃO DENTRO DO MODAL ---
                try:
                    # Reduzi o timeout do modal de 10s para 4s (ele abre rápido ou não abre)
                    btn_enviar = WebDriverWait(self.driver, 4).until(EC.element_to_be_clickable((
                        By.CSS_SELECTOR, 'button[data-test-id="local-images-files-uploader-button"]'
                    )))
                    js_click(self.driver, btn_enviar)
                except:
                    pass 

            # --- VALIDAÇÃO E INJEÇÃO ---
            # Aqui é onde injetamos o caminho. Mantive os 10s para garantir que não dê erro de "não encontrado"
            input_file = self._encontrar_input_file_visivel_ou_oculto(timeout=10)
            
            self.driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1; arguments[0].style.height='1px'; arguments[0].style.width='1px';",
                input_file,
            )

            input_file.send_keys(str(caminho.resolve()))         
            _log(f'Upload iniciado: {caminho.name}')

            # Limpeza rápida de menus abertos
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            is_video = caminho.suffix.lower() in ['.mov', '.mp4', '.avi', '.mkv', '.webm']
            
            # 2. Otimização do tempo de guarda:
            # Imagem não precisa de 20s de estabilização. 10s é o suficiente após o arquivo entrar.
            timeout_upload = 60 if is_video else 10 
            self._aguardar_upload_estabilizar(timeout=timeout_upload, is_video=is_video)
            
        except Exception as e:
            _log(f'🛡️ Falha Crítica no Fluxo de Anexo: {str(e).splitlines()[0]}')
            salvar_print_debug(self.driver, f"ERRO_ANEXO_{caminho.stem}")
            raise Exception(f"Timeout ou falha de UI ao anexar {caminho.name}.")
        
    def enviar_prompt(
        self,
        prompt: str,
        timeout: int = 60,
        aguardar_resposta: bool = True,
    ) -> str:
        _log(f'Enviando prompt ({len(prompt)} chars)...')

        # --- NOVO: COOLDOWN CONTRA ERRO 13 ---
        time.sleep(2.5) # Espera o Gemini "respirar" antes de cada envio
        # -------------------------------------

        salvar_print_debug(self.driver,"PROMPT_PREPARACAO")
        
        try:
            scroll_ao_fim(self.driver)
            textarea = self._obter_textarea_prompt()
            
            textarea.click()
            time.sleep(0.5)
            
            # === SOLUÇÃO DEFINITIVA HEADLESS: Digitação Real Fragmentada ===
            # Sem Pyperclip, sem TrustedHTML. Remove emojis nativamente 
            # e escreve o texto diretamente no input buffer.
            prompt_seguro = re.sub(r'[^\u0000-\uFFFF]', '', prompt)

            salvar_ultimo_prompt(prompt_seguro)
                        
            try:
                # Método blindado Selenium: Aciona a API nativa de eventos do Chrome
                self.driver.execute_script(
                    "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                    textarea, prompt_seguro
                )
                time.sleep(0.5)
                # Dá um espaço final para despertar os gatilhos do Angular
                textarea.send_keys(" ")
            except Exception as e:
                _log(f'Fallback de fallback ativado para digitação: {e}')
                textarea.send_keys(prompt_seguro)
                
            _log('Prompt digitado')
            salvar_print_debug(self.driver,"PROMPT_DIGITADO")
            
            scroll_ao_fim(self.driver)
            
            botao_submit = None
            fim = time.time() + 5
            while time.time() < fim:
                scroll_ao_fim(self.driver)
                botao = self._obter_botao_enviar()
                if botao is not None:
                    botao_submit = botao
                    break
                time.sleep(0.1)

            if botao_submit is None:
                raise TimeoutException('Botao de envio nao ficou disponivel.')
            
            # === BLOQUEIO DE CONFIRMAÇÃO DE ENVIO ===
            # Clica no botão e espera até a caixa de texto ESVAZIAR
            tentativas_click = 0
            enviou = False
            
            while tentativas_click < 4 and not enviou:
                try:
                    js_click(self.driver,botao_submit)
                except Exception:
                    botao_submit.click()
                
                # Aguarda até 3 segundos para a caixa esvaziar após o clique
                fim_esvaziamento = time.time() + 3
                while time.time() < fim_esvaziamento:
                    try:
                        # Se não conseguir achar a caixa, ou ela estiver vazia, significa que a tela mudou e o envio funcionou!
                        ta = self._obter_textarea_prompt()
                        texto_caixa = self.driver.execute_script("return arguments[0].textContent;", ta) or ""
                        if len(texto_caixa.strip()) < 10:
                            enviou = True
                            break
                    except Exception:
                        enviou = True
                        break
                    time.sleep(0.5)
                
                tentativas_click += 1
            
            if not enviou:
                salvar_print_debug(self.driver,"ERRO_PROMPT_NAO_ENVIADO")
                raise Exception("O botão Submit foi clicado, mas o Gemini ignorou a ação.")
                
            _log('Prompt submetido e processamento iniciado.')
            salvar_print_debug(self.driver,"PROMPT_SUBMETIDO_CLICK")
            
            # --- CHECAGEM PÓS ENVIO ---
            fim_erro = time.time() + 4
            while time.time() < fim_erro:
                try:
                    retry_btns = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Retry') or contains(text(), 'Tentar novamente')]/ancestor::button")
                    if retry_btns and retry_btns[0].is_displayed():
                        _log("⚠️ Erro de servidor detectado. Clicando em Retry...")
                        js_click(self.driver,retry_btns[0])
                        salvar_print_debug(self.driver,"PROMPT_ERRO_RETRY_APERTADO")
                        break
                    
                    toasts = self.driver.find_elements(By.CSS_SELECTOR, "simple-snack-bar, snack-bar-container, div[class*='snackbar'], div[class*='toast'], [role='alert']")
                    if toasts:
                        for toast in toasts:
                            if toast.is_displayed():
                                t_text = toast.text.lower()
                                if "wrong" in t_text or "errado" in t_text or "error" in t_text or "tente" in t_text or "try again" in t_text:
                                    _log(f"⚠️ Erro na UI detectado ('{t_text[:30]}...'). Dando F5 e abortando...")
                                    salvar_print_debug(self.driver,"PROMPT_ERRO_SNACKBAR_F5")
                                    self.driver.refresh()
                                    time.sleep(3)
                                    return 'ERRO_F5'

                    if self._obter_botao_enviar() is None:
                        break 
                except Exception:
                    pass
                time.sleep(0.2)
            
            scroll_ao_fim(self.driver)
            
            if aguardar_resposta:
                return self._aguardar_resposta_textual(timeout=timeout)
            return 'ENVIADO'
            
        except TimeoutException:
            _log('ERRO: Timeout ao enviar prompt. A caixa de texto travou.')
            salvar_print_debug(self.driver,"PROMPT_ERRO_TIMEOUT")
            return 'TIMEOUT'
            
        except Exception as e:
            msg_limpa = str(e).split('\n')[0] # Mata o stacktrace
            _log(f'ERRO ao enviar prompt: {msg_limpa}')
            salvar_print_debug(self.driver,"PROMPT_ERRO_CRITICO")
            return f'ERRO: {msg_limpa}'

    def avaliar_melhor_imagem_base(self, img_a: Path, img_b: Path, nome_produto: str, estilo_filmagem: str) -> Path:
        """Pede ao Gemini para avaliar duas variações de Imagem Base e escolher a melhor."""
        _log(f"Iniciando Teste A/B de Imagens: {img_a.name} vs {img_b.name}...")
        
        if "frontal" in estilo_filmagem.lower():
            criterios = "Anatomia e rosto da modelo (rejeite imagens com rostos deformados, olhos tortos ou mãos derretidas segurando o produto)."
        else:
            criterios = "Anatomia das mãos (rejeite imagens com dedos extras, posições impossíveis, rostos, cabeças ou corpos visíveis)."

        for tentativa in range(1, 4):
            try:
                self.abrir_novo_chat_limpo()
                _log("Fazendo upload das duas candidatas...")
                self.anexar_arquivo_local(img_a)
                self.anexar_arquivo_local(img_b)
                
                prompt = PROMPT_JURI_TESTE_AB_IMAGEM_BASE.format(
                    nome_produto=nome_produto,
                    criterios_avaliacao=criterios
                )
                resposta = self.enviar_prompt(prompt, timeout=60, aguardar_resposta=True)
                
                if resposta == 'RECOVERY_TRIGGERED' or not resposta:
                    _log("⚠️ Falha ao avaliar imagens, tentando novamente...")
                    continue
                
                resposta_limpa = str(resposta).strip().upper()
                if 'B' in resposta_limpa:
                    _log(f"🏆 Gemini escolheu a Variante B ({img_b.name})!")
                    return img_b
                else:
                    _log(f"🏆 Gemini escolheu a Variante A ({img_a.name})!")
                    return img_a

            except Exception as e:
                _log(f"Erro na tentativa {tentativa} de avaliar Imagens: {e}")
                time.sleep(2)
                
        _log("⚠️ Fallback: Escolhendo Variante A devido a falhas contínuas.")
        return img_a

    def contar_imagens_geradas(self) -> int:
        script_js = """
        const seletores = [
            'model-response:last-of-type img[data-test-id*="generated"]',
            'model-response:last-of-type img[src^="blob:"]',
            'model-response:last-of-type img[alt*="Generated"]',
            'model-response:last-of-type img'
        ];
        let imagensVistas = new Set();
        
        seletores.forEach(seletor => {
            document.querySelectorAll(seletor).forEach(el => {
                const src = (el.src || '').toLowerCase();
                if (src.includes('profile/picture') || src.includes('avatar') || src.includes('logo')) {
                    return;
                }
                if (el.getBoundingClientRect().width > 0) {
                    imagensVistas.add(src);
                }
            });
        });
        
        return imagensVistas.size;
        """
        try:
            total = self.driver.execute_script(script_js)
            return int(total) if total else 0
        except Exception as e:
            return 0

    def aguardar_nova_imagem(self, total_antes: int, timeout: int = 60) -> bool:
        fim = time.time() + timeout
        while time.time() < fim:
            scroll_ao_fim(self.driver)
            total_agora = self.contar_imagens_geradas()
            if total_agora > total_antes:
                _log(f'Nova imagem detectada: {total_agora} > {total_antes}')
                return True
            time.sleep(0.5) 
        _log('Timeout aguardando nova imagem.')
        salvar_print_debug(self.driver,"ERRO_GERACAO_IMAGEM_TIMEOUT")
        return False

    def baixar_ultima_imagem(self, destino: Path) -> bool:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            scroll_ao_fim(self.driver)
            salvar_print_debug(self.driver,"BAIXAR_IMG_INICIO")
            
            candidatos = [
                'model-response:last-of-type img[data-test-id*="generated"]',
                'model-response:last-of-type img[src^="blob:"]',
                'model-response:last-of-type img[alt*="Generated"]',
                'model-response:last-of-type img',
            ]
            
            imgs = []
            for seletor in candidatos:
                try:
                    imgs.extend(self.driver.find_elements(By.CSS_SELECTOR, seletor))
                except Exception:
                    pass
                    
            imgs_validas = []
            for img in imgs:
                if not img.is_displayed(): 
                    continue
                src = img.get_attribute('src') or ''
                if 'profile/picture' in src or 'avatar' in src.lower() or 'logo' in src.lower():
                    continue
                imgs_validas.append(img)

            if not imgs_validas:
                _log('Nenhuma imagem válida encontrada para clicar.')
                return False
                
            img_alvo = imgs_validas[-1]

            self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", img_alvo)
            time.sleep(0.5)

            _log('Tentando abrir galeria...')
            clicado = False
            fim_click = time.time() + 5
            while time.time() < fim_click:
                scroll_ao_fim(self.driver)
                try:
                    js_click(self.driver,img_alvo)
                    time.sleep(0.5)
                    if self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Download full size image"], button[data-test-id="download-generated-image-button"]'):
                        clicado = True
                        break
                except Exception:
                    pass
            
            if not clicado:
                _log('Falha ao abrir a galeria da imagem.')
                salvar_print_debug(self.driver,"BAIXAR_IMG_FALHA_GALERIA")
                return False

            _log('Imagem gerada clicada. Galeria aberta.')
            
            btn_download = None
            for _ in range(10):
                botoes = self.driver.find_elements(By.CSS_SELECTOR, 'button[data-test-id="download-generated-image-button"], button[aria-label="Download full size image"]')
                for b in botoes:
                    if b.is_displayed():
                        btn_download = b
                        break
                if btn_download:
                    break
                time.sleep(0.1)
                
            if not btn_download:
                _log('Botão de download não encontrado na interface.')
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                return False

            downloads_dir = Path.home() / "Downloads"
            arquivos_antes = set(downloads_dir.glob("*"))

            js_click(self.driver,btn_download)
            _log('Botão nativo de download clicado.')

            novo_arquivo = None
            fim_down = time.time() + 60 
            while time.time() < fim_down:
                scroll_ao_fim(self.driver)
                arquivos_agora = set(downloads_dir.glob("*"))
                novos = arquivos_agora - arquivos_antes
                
                novos_concluidos = [f for f in novos if not f.name.endswith('.crdownload') and not f.name.endswith('.tmp')]
                
                if novos_concluidos:
                    novo_arquivo = max(novos_concluidos, key=lambda f: f.stat().st_ctime)
                    break
                time.sleep(0.5)
                
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()

            if novo_arquivo:
                if destino.exists():
                    destino.unlink()
                shutil.move(str(novo_arquivo), str(destino))
                _log(f'✅ Imagem baixada em alta resolução e salva em: {destino.name}')
                return True
            else:
                _log('Timeout ao aguardar arquivo aparecer na pasta Downloads do Windows.')
                salvar_print_debug(self.driver,"BAIXAR_IMG_TIMEOUT_WINDOWS")
                return False

        except Exception as e:
            _log(f'ERRO ao baixar imagem nativamente: {e}')
            return False

    def _listar_candidatos_produto(self, tarefa: Any) -> List[Path]:
        assets = getattr(tarefa, 'candidate_product_assets', None)
        if assets:
            candidatos = [asset.path for asset in assets if getattr(asset, 'is_image', False)]
        else:
            task_assets = getattr(tarefa, 'assets', []) or []
            candidatos = [asset.path for asset in task_assets if getattr(asset, 'is_image', False)]
        candidatos = [p for p in candidatos if p.name.upper() != 'POV_VALIDADO.PNG']
        return candidatos

    def _validar_imagem_produto(
        self,
        caminho_imagem: Path,
        timeout_resposta: int = 60, # Timeout aumentado conforme solicitado
        max_reenvios_prompt: int = 2, # Vai tentar até 3 vezes na mesma conta
    ) -> bool:
        """
        Versão DEFINITIVA: Só reprova (retorna False) se a IA disser explicitamente 'NAO'.
        Qualquer outro erro (Timeout, Vácuo, Bugs) gera um Novo Chat na mesma conta.
        Se esgotar as tentativas na conta, gera uma Exceção para o main.py rodar a conta,
        NUNCA reprovando a imagem injustamente.
        """
        caminho_imagem = Path(caminho_imagem)
        
        # Loop de retentativas na MESMA CONTA (se max_reenvios=2, roda 3 vezes)
        for tentativa_geral in range(1, max_reenvios_prompt + 2):
            _log(f'Validando produto: {caminho_imagem.name} (Tentativa {tentativa_geral}/{max_reenvios_prompt + 1} na mesma conta)...')
            salvar_print_debug(self.driver,f"IA_VALIDACAO_INICIO_T{tentativa_geral}")
            
            try:
                self._forcar_modelo_pro()
                self.anexar_arquivo_local(caminho_imagem)
                
                # ...
                prompt_validacao = PROMPT_VALIDACAO_PRODUTO
                resposta_bruta = self.enviar_prompt(prompt_validacao, timeout=timeout_resposta)
                # ...
                
                # --- TRATAMENTO DE TIMEOUTS E F5 ---
                if resposta_bruta == 'RECOVERY_TRIGGERED':
                    _log("🔄 A interface travou (Timeout). Abrindo um NOVO CHAT na mesma conta para re-tentar...")
                    self.abrir_novo_chat_limpo()
                    continue # Volta para o topo do FOR e tenta de novo do zero na mesma conta
                
                resposta = resposta_bruta.strip().upper()
                _log(f"🕵️ Resposta da IA: '{resposta}'")
                salvar_print_debug(self.driver,f"RESPOSTA_DA_IA_{resposta}")

                # Se a resposta for um erro de leitura conhecido, tenta recuperar com novo chat
                if resposta in ('TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5'):
                    _log(f"⚠️ Falha de leitura ({resposta}). Abrindo NOVO CHAT na mesma conta...")
                    self.abrir_novo_chat_limpo()
                    continue

                # --- O VEREDICTO REAL (O SEGREDO ESTÁ AQUI) ---
                
                # 1. A IA aprovou?
                if 'SIM' in resposta or resposta.startswith('SIM'):
                    return True
                
                # 2. A IA reprovou EXPLICITAMENTE? (Único cenário onde retorna False)
                if 'NAO' in resposta or 'NÃO' in resposta or resposta.startswith('NAO'):
                    return False
                    
                # 3. Respondeu alguma loucura que não é nem SIM nem NAO
                _log(f"⚠️ A IA respondeu fora do padrão. Abrindo NOVO CHAT na mesma conta...")
                self.abrir_novo_chat_limpo()
                continue

            except Exception as e:
                msg_limpa = str(e).splitlines()[0] if str(e).splitlines() else str(e)
                _log(f"⚠️ Erro durante validação ({msg_limpa}). Abrindo NOVO CHAT na mesma conta...")
                try:
                    self.abrir_novo_chat_limpo()
                except Exception:
                    pass
                
        # --- PROTEÇÃO ABSOLUTA DA TAREFA ---
        # Se o código chegou até aqui, significa que esgotou todas as tentativas na MESMA CONTA
        # e o Gemini só deu Timeout ou erro. 
        # Nós NÃO retornamos False. Levantamos um erro fatal para o main.py.
        raise Exception("Esgotaram as tentativas de validação por falhas na interface (Timeouts/Bugs). A conta será rotacionada para preservar a imagem.")

    def _selecionar_foto_produto(self, tarefa: Any) -> Optional[Path]:
        candidatos = self._listar_candidatos_produto(tarefa)
        if not candidatos:
            _log('Nenhuma imagem candidata encontrada na pasta da tarefa.')
            return None
        for candidato in candidatos:
            try:
                if self._validar_imagem_produto(candidato, timeout_resposta=40, max_reenvios_prompt=1):
                    _log(f'Foto do produto selecionada: {candidato.name}')
                    return candidato
            except Exception:
                pass
        _log('Nenhum candidato foi aprovado como foto principal do produto.')
        return None

    def executar_fluxo_imagem_base(
        self,
        tarefa: Any,
        foto_produto_escolhida: Optional[Path] = None,
        max_versoes: int = 3,
        numero_roteiro: int = 1, 
    ) -> Optional[Path]:
        dir_anuncio = Path(getattr(tarefa, 'folder_path', '.'))
        caminho_final = dir_anuncio / f'IMG_BASE_VALIDADA_Roteiro{numero_roteiro}.png'

        if foto_produto_escolhida is None:
            foto_produto_escolhida = self._selecionar_foto_produto(tarefa)
            if not foto_produto_escolhida:
                return None
        else:
            foto_produto_escolhida = Path(foto_produto_escolhida)

        dados_anuncio = getattr(tarefa, 'dados_anuncio', {})
        nome_prod = dados_anuncio.get('nome_produto', 'o produto')
        beneficios = dados_anuncio.get('beneficios_extras', '')
        contexto_produto = f"O produto é '{nome_prod}'. " + (f"Detalhes: {beneficios}." if beneficios else "")

        descricoes = getattr(tarefa, 'descricoes_prompts', {})
        desc_maos = descricoes.get('modelo', {}).get('maos', 'mãos femininas delicadas')
        desc_estilo = descricoes.get('modelo', {}).get('estilo', 'estética casual e elegante')

        # NAVEGAÇÃO DE DIRETÓRIO PARA ACHAR O MODELO
        partes_caminho = dir_anuncio.parts
        estilo_filmagem_pasta = partes_caminho[-3]
        nome_modelo_pasta = partes_caminho[-4]     
        
        pasta_meu_drive = dir_anuncio.parents[4]
        caminho_foto_modelo = pasta_meu_drive / "Modelos" / f"{nome_modelo_pasta}.png"

        imagens_geradas = []

        for v_idx in range(1, max_versoes + 1):
            _log(f'Gerando Imagem Base {v_idx}/{max_versoes} (Estilo: {estilo_filmagem_pasta})...')
            caminho_parcial = dir_anuncio / f'ImgCand_R{numero_roteiro}_v{v_idx}.png'
            
            self.abrir_novo_chat_limpo()
            
            # === BIFURCAÇÃO DA GERAÇÃO (Sincronizado com prompts.py) ===
            pasta_estilo = estilo_filmagem_pasta.lower()
            
            if "frontal" in pasta_estilo or "caminhando" in pasta_estilo or "pes" in pasta_estilo:
                # Estes modelos precisam de DUAS imagens (Produto + Identidade da Modelo)
                self.anexar_arquivo_local(foto_produto_escolhida)
                time.sleep(1.5)
                if caminho_foto_modelo.exists():
                    self.anexar_arquivo_local(caminho_foto_modelo)
                else:
                    raise FileNotFoundError(f"Foto da modelo não encontrada em: {caminho_foto_modelo}")
                
                if "frontal" in pasta_estilo:
                    prompt_geracao = PROMPT_GERACAO_IMAGEM_FRONTAL.format(
                        nome_produto=nome_prod, contexto_produto=contexto_produto, desc_estilo=desc_estilo
                    )
                elif "caminhando" in pasta_estilo:
                    prompt_geracao = PROMPT_GERACAO_IMAGEM_CAMINHANDO.format(nome_produto=nome_prod)
                else: # pes
                    prompt_geracao = PROMPT_GERACAO_IMAGEM_PES.format(nome_produto=nome_prod)
            
            elif "flat" in pasta_estilo:
                # Apenas o produto (Still giratório)
                self.anexar_arquivo_local(foto_produto_escolhida)
                prompt_geracao = PROMPT_GERACAO_IMAGEM_FLAT.format(nome_produto=nome_prod)
                
            else:
                # Padrão POV
                self.anexar_arquivo_local(foto_produto_escolhida)
                prompt_geracao = PROMPT_GERACAO_IMAGEM_POV.format(
                    nome_produto=nome_prod, contexto_produto=contexto_produto, desc_maos=desc_maos
                )

            total_antes = self.contar_imagens_geradas()
            if self.enviar_prompt(prompt_geracao, aguardar_resposta=False) == 'ERRO_F5':
                continue

            if not self.aguardar_nova_imagem(total_antes, timeout=60):
                continue

            baixou = False
            for _ in range(3):
                scroll_ao_fim(self.driver)
                if self.baixar_ultima_imagem(caminho_parcial):
                    baixou = True
                    break
                
            if baixou and caminho_parcial.exists():
                imagens_geradas.append(caminho_parcial)

        if not imagens_geradas:
            return None

        if len(imagens_geradas) == 1:
            shutil.copy2(str(imagens_geradas[0]), str(caminho_final))
            return caminho_final

        _log(f'Iniciando Direção de Arte (Júri IA) entre as {len(imagens_geradas)} versões geradas...')
        self.abrir_novo_chat_limpo()
        self.anexar_arquivo_local(foto_produto_escolhida)
        
        nomes_candidatos = []
        for img in imagens_geradas:
            time.sleep(1.5)
            self.anexar_arquivo_local(img)
            nomes_candidatos.append(img.name)

        # === SELETOR DINÂMICO DE CRITÉRIOS DO JÚRI ===
        pasta_estilo = estilo_filmagem_pasta.lower()

        if "frontal" in pasta_estilo or "caminhando" in pasta_estilo:
            criterios_juri = "Anatomia Humana: O rosto está nítido, bonito e idêntico à modelo? O corpo está proporcional? A roupa/produto está visível e sem deformações?"
        elif "pes" in pasta_estilo:
            criterios_juri = "Foco nos Pés: O calçado está idêntico ao gabarito? As pernas e pés parecem reais e sem dedos extras?"
        elif "flat" in pasta_estilo:
            criterios_juri = "Still/Produto: O produto está centralizado e nítido? A base giratória parece profissional? Rejeite se houver pessoas ou mãos na cena."
        else:
            criterios_juri = "Anatomia POV (Foco extremo): Conte as mãos. É OBRIGATÓRIO ter EXATAMENTE 2 mãos. Rejeite se houver 3 mãos, rostos ou corpos."

        prompt_juri = PROMPT_JURI_CANDIDATOS_IMAGEM_BASE.format(
            nomes_candidatos=', '.join(nomes_candidatos),
            contexto_produto=contexto_produto,
            criterios_avaliacao=criterios_juri
        )
        
        resposta = self.enviar_prompt(prompt_juri, timeout=90, aguardar_resposta=True)
        
        if resposta in ('RECOVERY_TRIGGERED', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5', 'TIMEOUT'):
            _log(f"⚠️ O Júri falhou por engasgo da interface. Assumindo a primeira imagem gerada como fallback.")
            vencedor_path = imagens_geradas[0]
        else:
            _log(f"Resposta do Júri:\n{resposta.strip()}")
            vencedor_path = None
            resposta_limpa = str(resposta).lower().strip()
            
            # LÓGICA DE REPROVAÇÃO TOTAL (VETO)
            if "nenhuma" in resposta_limpa.split("vencedor:")[-1] or "nenhuma" in resposta_limpa:
                _log("🚨 VETO DO JÚRI: O Gemini detectou aberrações em TODAS as candidatas!")
                _log("Deletando aberrações e forçando falha para recomeçar o ciclo...")
                for img_suja in imagens_geradas:
                    img_suja.unlink(missing_ok=True)
                raise Exception("Todas as imagens geradas foram reprovadas pelo Júri de Qualidade.")

            for candidato in imagens_geradas:
                if candidato.name.lower() in resposta_limpa:
                    vencedor_path = candidato
                    break
                    
            if not vencedor_path:
                _log(f"Aviso: O Júri não nomeou o vencedor corretamente. Assumindo Variante 1.")
                vencedor_path = imagens_geradas[0]

        _log(f'🏆 O JÚRI DA IA DECIDIU! A Imagem Vencedora é: {vencedor_path.name}')
        shutil.copy2(str(vencedor_path), str(caminho_final))
        return caminho_final
    
    def treinar_e_gerar_roteiro(
        self,
        arquivos: List[Path],
        dados_produto: Dict,
        arquivo_ref: Optional[Path] = None,
        qtd_cenas: int = 3,
        roteiros_anteriores: Optional[List[str]] = None,
        tarefa_obj: Optional[Any] = None 
    ) -> str:
        id_pasta = dados_produto.get('nome', '1')
        scroll_ao_fim(self.driver)
        _log(f"Iniciando fase de roteirização (Tarefa {id_pasta})")
        salvar_print_debug(self.driver,"IA_ROTEIRO_INICIO")

        descricoes = getattr(tarefa_obj, 'descricoes_prompts', {}) if tarefa_obj else {}
        perfil_modelo = descricoes.get('modelo', {})
        estilo_filmagem = descricoes.get('filmagem', {})

        desc_maos = perfil_modelo.get('maos', 'mãos femininas')
        desc_corpo = perfil_modelo.get('corpo', 'mulher jovem')
        desc_estilo = perfil_modelo.get('estilo', 'estética casual')
        desc_nome_modelo = perfil_modelo.get('nome', 'A Modelo')

        nome_tipo_video = estilo_filmagem.get('nome', 'Vídeo Padrão')
        regras_video = estilo_filmagem.get('regras', '')

        prompt_mestre = PROMPT_MESTRE_ROTEIRO.format(
            qtd_cenas=qtd_cenas,
            nome_modelo=desc_nome_modelo,
            desc_maos=desc_maos,
            desc_corpo=desc_corpo,
            desc_estilo=desc_estilo,
            nome_tipo_video=nome_tipo_video,
            regras_video=regras_video
        )
        prompt_mestre_linear = " ".join(prompt_mestre.split())

        texto_referencia_dinamico = "Nenhuma referência extra."
        if arquivo_ref:
            extensao = str(arquivo_ref).lower()
            if extensao.endswith(('.mp4', '.mov', '.webm', '.avi')):
                texto_referencia_dinamico = "O vídeo com fala validada."
            else:
                texto_referencia_dinamico = "Outra imagem detalhada para compor a explicação."

        instrucoes_teste_ab = ""
        if roteiros_anteriores:
            _log(f"Injetando {len(roteiros_anteriores)} roteiro(s) anterior(es) para forçar variação no Teste A/B...")
            textos_anteriores = "\n\n".join([f"--- ROTEIRO ANTERIOR ---\n{r}\n------------------------" for r in roteiros_anteriores])
            instrucoes_teste_ab = (
                "\n\nATENÇÃO MÁXIMA (TESTE A/B): Eu já criei os roteiros abaixo para este produto. "
                "Crie um roteiro 100% INÉDITO e DIFERENTE mudando a abordagem de venda.\n\n"
                f"{textos_anteriores}\n"
            )

        prompt_execucao = PROMPT_EXECUCAO_ROTEIRO.format(
            qtd_cenas=qtd_cenas,
            nome_tipo_video=nome_tipo_video,
            texto_referencia_dinamico=texto_referencia_dinamico,
            nome_modelo=desc_nome_modelo,
            desc_maos=desc_maos,
            regras_video=regras_video,
            instrucoes_teste_ab=instrucoes_teste_ab
        )
        prompt_execucao_linear = " ".join(prompt_execucao.split())

        # --- LOOP BLINDADO DE RETENTATIVA NA MESMA CONTA ---
        erros_conhecidos = ('RECOVERY_TRIGGERED', 'TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5')
        
        for tentativa in range(1, 4):
            try:
                self.abrir_novo_chat_limpo()
                
                _log(f"Enviando Prompt Mestre de Treinamento (Tentativa {tentativa}/3)...")
                res_treino = self.enviar_prompt(prompt_mestre_linear, timeout=60, aguardar_resposta=True)
                
                if res_treino in erros_conhecidos:
                     _log(f"⚠️ A interface engasgou no Treinamento ({res_treino}). Reiniciando chat...")
                     continue

                # O treino deu certo, vamos anexar os arquivos
                for arq in arquivos:
                    caminho = Path(arq)
                    if caminho.exists():
                        self.anexar_arquivo_local(caminho)

                _log(f"Solicitando geração do roteiro em {qtd_cenas} cenas...")
                resposta = self.enviar_prompt(prompt_execucao_linear, timeout=60, aguardar_resposta=True)

                if resposta in erros_conhecidos:
                    _log(f"⚠️ A interface engasgou na Execução ({resposta}). Reiniciando chat...")
                    continue

                salvar_print_debug(self.driver,"IA_ROTEIRO_GERADO")
                return resposta

            except Exception as e:
                msg_erro = str(e).splitlines()[0] if str(e).splitlines() else str(e)
                _log(f"⚠️ Erro na tentativa {tentativa} de gerar roteiro: {msg_erro}")

        # Se falhou 3 vezes na mesma conta, devolvemos erro fatal para o main rotacionar a conta
        raise Exception("Esgotaram as tentativas de gerar roteiro devido a falhas na interface do Gemini.")

    def avaliar_melhor_variante_de_video(self, videos_720p: List[Path], roteiro: str) -> Path:
        if not videos_720p:
            raise ValueError("Nenhum vídeo fornecido para avaliação.")
            
        if len(videos_720p) == 1:
            _log(f"Apenas uma variante detectada ({videos_720p[0].name}). Pulando júri.")
            return videos_720p[0]

        _log(f"Iniciando JÚRI DE DIREÇÃO DE ARTE para {len(videos_720p)} variantes (720p)...")
        salvar_print_debug(self.driver,"IA_JURI_VIDEO_INICIO")
        self.abrir_novo_chat_limpo()
        
        for video in videos_720p:
            if video.exists():
                self.anexar_arquivo_local(video)

        # ...
        prompt_juri = PROMPT_JURI_VIDEO.format(
            qtd_variantes=len(videos_720p),
            roteiro=roteiro
        )
        # ...

        _log("Solicitando a decisão ao Gemini...")
        resposta_ia = self.enviar_prompt(prompt_juri, timeout=60, aguardar_resposta=True)

        if not resposta_ia or "TIMEOUT" in resposta_ia or "ERRO" in resposta_ia:
            _log(f"Aviso: O Gemini falhou em avaliar ({resposta_ia}). Assumindo a Variante 1.")
            return videos_720p[0]

        resposta_limpa = resposta_ia.strip().replace("`", "").replace('"', "").replace("'", "")
        _log(f"Resposta do Diretor de Arte: {resposta_limpa}")
        salvar_print_debug(self.driver,"IA_JURI_VIDEO_DECISAO")

        for video in videos_720p:
            if video.name.lower() in resposta_limpa.lower():
                _log(f"🎉 Variante eleita: {video.name}")
                return video
                
        for video in videos_720p:
            if video.stem.lower() in resposta_limpa.lower():
                _log(f"🎉 Variante eleita (pelo radical): {video.name}")
                return video

        _log(f"Aviso: Não foi possível casar a resposta '{resposta_limpa}' com os arquivos. Assumindo Variante 1.")
        return videos_720p[0]
    
    def classificar_arquivos_e_extrair_dados(self, arquivos: list[Path]) -> dict | None:
        # Loop de 2 tentativas na mesma conta antes de desistir
        for tentativa_geral in range(1, 3):
            _log(f"Iniciando classificação de arquivos (Tentativa {tentativa_geral}/2 na mesma conta)...")
            self.abrir_novo_chat_limpo()
            
            nomes_arquivos = []
            
            # --- BLOCO TUDO OU NADA: ANEXO DE ARQUIVOS ---
            try:
                for arq in arquivos:
                    # Se der TimeoutException aqui, ele pula direto pro except abaixo
                    self.anexar_arquivo_local(arq)
                    nomes_arquivos.append(arq.name)
            except Exception as e:
                # 🚨 Identificou falha no anexo? Não tenta mais nada, vaza da conta!
                _log(f"🚨 FALHA CRÍTICA NO ANEXO: {str(e).splitlines()[0]}")
                _log("Interrompendo classificação. Solicitando troca de conta ao sistema principal...")
                # Levanta o erro para o main.py capturar e rodar o 'finally' (fechar driver)
                raise e

            # Se chegou aqui, todos os arquivos foram anexados. Agora sim manda o prompt.
            prompt = PROMPT_CLASSIFICACAO_ARQUIVOS.format(nomes_arquivos=', '.join(nomes_arquivos))
            resposta = self.enviar_prompt(prompt, timeout=60, aguardar_resposta=True)

            # Se o sinal de Recovery foi disparado (F5), o loop recomeça (tentativa 2)
            if resposta == 'RECOVERY_TRIGGERED':
                _log("🔄 Interface reiniciada via Recovery. Tentando novamente nesta conta...")
                continue

            if not resposta or resposta in {'SEM_RESPOSTA_UTIL', 'TIMEOUT'}:
                _log("⚠️ Resposta inválida ou vazia. Tentando Recovery manual...")
                continue

            # Processamento do JSON
            import json
            match = re.search(r'\{.*\}', resposta, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception as e:
                    _log(f'Erro ao converter JSON: {e}')
            
            _log("⚠️ Falha ao extrair JSON da resposta. Tentando de novo...")
            
        _log("❌ Esgotadas as tentativas de classificação nesta conta.")
        return None
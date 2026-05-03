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
from integrations.self_healing import cacar_elemento_universal, clicar_com_hunter, interagir_com_menu_complexo, superar_obstaculo_desconhecido, detectar_com_hunter

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
    def __init__(self, driver: Any, url_gemini: str, timeout: int = 30, driver_acessibilidade=None, url_gemini_acessibilidade=None):
        self.driver = driver
        self.url_gemini = url_gemini
        self.wait = WebDriverWait(driver, timeout, poll_frequency=0.1)
        self.timeout = timeout

        # Salva o "médico" para o Hunter usar
        self.driver_acessibilidade = driver_acessibilidade
        self.url_gemini_acessibilidade = url_gemini_acessibilidade
        
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
            # 🛡️ HUNTER: Selecionamos o alvo principal (Microfone ou Caixa de Texto)
            alvo = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="gemini_alvo_ui_ociosa",
                descricao_para_ia="Botão de microfone ou caixa de texto contenteditable no chat do Gemini (indicando UI ociosa)",
                seletores_rapidos=[
                    'button.speech_dictation_mic_button',
                    'rich-textarea div[contenteditable="true"]',
                ],
                palavras_semanticas=["microphone", "microfone"],
                permitir_autocura=False,
                etapa="GEMINI_CHAT",
            )
            
            if alvo and alvo.is_displayed():
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
                # 🛡️ HUNTER: Check final pós-refresh
                mic_check = detectar_com_hunter(
                    driver=self.driver,
                    chave_memoria="gemini_mic_check_refresh",
                    descricao_para_ia="Botão de microfone no Gemini após refresh (indicando UI funcional)",
                    seletores_rapidos=['button.speech_dictation_mic_button', 'rich-textarea div[contenteditable="true"]'],
                    palavras_semanticas=["microphone", "microfone"],
                    etapa="GEMINI_CHAT",
                )
                if not mic_check:
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
            
            # 🧠 FALLBACK INTELIGENTE: Trator não resolveu, pede ajuda à IA
            _log("🧠 Trator falhou. Acionando resolução autônoma via IA...")
            resolveu = superar_obstaculo_desconhecido(
                driver=self.driver,
                driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                contexto="tela de bloqueio, onboarding ou popup de termos no Gemini impedindo acesso ao chat"
            )
            if resolveu:
                # Verifica se a caixa de texto apareceu após a resolução
                try:
                    textarea = self.driver.find_elements(By.CSS_SELECTOR, 'rich-textarea div[contenteditable="true"]')
                    if textarea and textarea[0].is_displayed():
                        _log("✅ IA resolveu o bloqueio! Interface de chat liberada.")
                        return True
                except: pass
            
            return False
            
        finally:
            # 🚨 RELIGA O FREIO DE MÃO (Timeout original de 5s estipulado no .env)
            self.driver.implicitly_wait(5)

    def _forcar_modelo_pro(self) -> None:
        _log('Verificando/Forçando modelo Pro...')
        
        time.sleep(1.0) 
        
        for tentativa in range(1, 4):
            try:
                # 🛡️ HUNTER: Encontra o botão do menu de modelo
                menu_btn = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="gemini_menu_modelo",
                    descricao_para_ia="Botão do menu de seleção de modelo (Pro/Flash) no topo do chat do Gemini",
                    seletores_rapidos=[
                        'button[data-test-id="bard-mode-menu-button"]',
                        'button[aria-label="Open mode picker"]',
                    ],
                    palavras_semanticas=["model", "modo", "pro", "flash"],
                    etapa="GEMINI_MODELO",
                    permitir_autocura=False,
                )
                
                if not menu_btn or not menu_btn.is_displayed():
                    _log(f'Botão de modelo ainda não apareceu (Tentativa {tentativa}/3)...')
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1.5)
                    continue

                texto_atual = (menu_btn.text or '').strip().lower()
                
                if 'pro' in texto_atual and 'thinking' not in texto_atual and 'pensamento' not in texto_atual:
                    _log('✅ Modelo Pro já está ativo.')
                    return 
                    
                _log(f'Modelo atual é "{texto_atual}". Abrindo menu de seleção (Tentativa {tentativa}/3)...')
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", menu_btn)
                time.sleep(0.5)
                js_click(self.driver, menu_btn)
                time.sleep(1.5) 
                
                # 🛡️ HUNTER: Busca a opção Pro no menu aberto
                opcao_pro = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="gemini_opcao_pro",
                    descricao_para_ia="Opção 'Pro' (sem Thinking/Pensamento) no dropdown de modelos do Gemini",
                    seletores_rapidos=[
                        'button[data-mode-id="e6fa609c3fa255c0"]',
                        'button[data-test-id="bard-mode-option-pro"]',
                    ],
                    palavras_semanticas=["pro"],
                    etapa="GEMINI_MODELO",
                    permitir_autocura=False,
                )
                
                # Filtra para não pegar Pro Thinking / Pro Fast
                clicou_pro = False
                if opcao_pro:
                    texto_opcao = (opcao_pro.text or '').strip().lower()
                    if 'thinking' not in texto_opcao and 'pensamento' not in texto_opcao and 'fast' not in texto_opcao:
                        if opcao_pro.is_displayed():
                            js_click(self.driver, opcao_pro)
                            clicou_pro = True

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
            clicou = clicar_com_hunter(
                driver=self.driver,
                chave_memoria="gemini_btn_novo_chat",
                descricao_para_ia="Botão de novo chat (New chat) na barra lateral do Gemini",
                seletores_rapidos=[
                    'side-nav-action-button[data-test-id="new-chat-button"] a',
                    'a.side-nav-action-collapsed-button[href="/app"]',
                    'span[data-test-id="new-chat-button"]',
                    'div[aria-label*="Novo chat"]',
                    'div[aria-label*="New chat"]',
                ],
                palavras_semanticas=["novo chat", "new chat", "nova conversa"],
                etapa="GEMINI_NAVEGACAO",
                permitir_autocura=True,
                driver_acessibilidade=self.driver_acessibilidade,
                url_gemini=self.url_gemini_acessibilidade,
                timeout_busca=5.0,
            )
            
            if clicou:
                _log('Botão "Novo Chat" acionado.')
            else:
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
        
        while time.time() < fim:
            # 🛡️ HUNTER: Tenta via cache/semântica primeiro
            el = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="gemini_input_file",
                descricao_para_ia="Campo input[type=file] para upload de imagens no Gemini",
                seletores_rapidos=[
                    'input[type="file"]',
                    'input[type="file"][multiple]',
                    'input[accept*="image"]',
                ],
                palavras_semanticas=[],  # input[type=file] não tem texto visível
                permitir_autocura=False,
                etapa="GEMINI_UPLOAD",
            )
            if el is not None:
                return el
            
            # Fallback: busca qualquer input file mesmo oculto
            try:
                self.driver.switch_to.default_content()
            except: pass
            
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                for e in elementos:
                    if e is not None:
                        return e
            except Exception as e:
                ultimo_erro = e
            
            time.sleep(0.1)
        
        if ultimo_erro:
            raise ultimo_erro
        raise TimeoutException('Nenhum input[type=file] encontrado no DOM.')

    def _obter_textarea_prompt(self) -> WebElement:
        # 🛡️ HUNTER: Busca via cache/semântica com performance
        el = cacar_elemento_universal(
            driver=self.driver,
            chave_memoria="gemini_textarea_prompt",
            descricao_para_ia="Caixa de digitação de texto (textarea/contenteditable) para enviar prompts no chat do Gemini",
            seletores_rapidos=[
                'rich-textarea div[contenteditable="true"]',
                'div[contenteditable="true"][role="textbox"]',
                '.initial-input-area-container textarea',
                'textarea[placeholder="Ask Gemini"]',
                'div[aria-label*="Message"]',
                'div.editor-container div[contenteditable="true"]',
            ],
            palavras_semanticas=[],  # textarea não tem innerText útil
            permitir_autocura=True,
            driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
            url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
            etapa="GEMINI_CHAT",
        )
        if el and el.is_displayed() and el.is_enabled():
            return el
        
        # Fallback com timeout estendido (8s)
        fim = time.time() + 8
        while time.time() < fim:
            for seletor in ['rich-textarea div[contenteditable="true"]', 'div[contenteditable="true"][role="textbox"]', 'textarea']:
                try:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for e in elementos:
                        if e.is_displayed() and e.is_enabled():
                            return e
                except: pass
            time.sleep(0.5)
            
        # Se chegou aqui, passou 8 segundos e a caixa não apareceu.
        _log("⚠️ Caixa de digitação sumiu! Chamando trator para tentar recuperar a tela...")
        if self._superar_bloqueios_e_onboarding():
            for seletor in ['rich-textarea div[contenteditable="true"]', 'div[contenteditable="true"][role="textbox"]', 'textarea']:
                try:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for e in elementos:
                        if e.is_displayed() and e.is_enabled():
                            return e
                except: pass
                    
        salvar_print_debug(self.driver,"ERRO_TEXTAREA_MORTA")
        raise TimeoutException('Falha irrecuperável: A caixa de digitação não existe na tela atual.')

    def _obter_botao_enviar(self, permitir_ia: bool = False) -> Optional[WebElement]:
        """Busca direta primeiro (instantâneo), Hunter como fallback com self-healing."""
        # ⚡ CAMINHO RÁPIDO: Seletores diretos (< 1ms)
        _CSS_ENVIAR = (
            'button[aria-label="Send message"], button[aria-label="Enviar mensagem"], '
            'button[data-test-id="send-button"], .send-button-container button'
        )
        try:
            btns = self.driver.find_elements(By.CSS_SELECTOR, _CSS_ENVIAR)
            for b in btns:
                if b.is_displayed() and b.get_attribute('disabled') is None and (b.get_attribute('aria-disabled') or '').strip().lower() != 'true':
                    return b
        except:
            pass
        
        # 🧠 FALLBACK HUNTER: Se Google mudou a interface
        btn = cacar_elemento_universal(
            driver=self.driver,
            chave_memoria="gemini_botao_enviar",
            descricao_para_ia="Botão de enviar mensagem (Send message) no chat do Gemini",
            seletores_rapidos=[
                'button[aria-label="Send message"]', 
                'button[aria-label="Enviar mensagem"]',
                '.send-button-container button', 
                'button[data-test-id="send-button"]'
            ],
            palavras_semanticas=['send message', 'enviar mensagem'],
            permitir_autocura=permitir_ia,
            driver_acessibilidade=self.driver_acessibilidade,
            url_gemini=self.url_gemini_acessibilidade,
            etapa="GEMINI_CHAT"
        )
        
        if btn and btn.is_displayed() and btn.get_attribute('disabled') is None and (btn.get_attribute('aria-disabled') or '').strip().lower() != 'true':
            return btn
            
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
                        # 🛡️ HUNTER: Detecta loaders de upload de vídeo
                        loaders = detectar_com_hunter(
                            driver=self.driver,
                            chave_memoria="gemini_upload_video_loaders",
                            descricao_para_ia="Indicadores de loading/upload de vídeo (progress bar, spinner, uploading) no Gemini",
                            seletores_rapidos=[
                                'mat-progress-bar', '.uploading', '[role="progressbar"]',
                                'mat-spinner', '.loading-spinner',
                                '[aria-label*="loading"]', '[aria-label*="uploading"]',
                            ],
                            palavras_semanticas=["loading", "uploading", "progress", "spinner"],
                            etapa="GEMINI_UPLOAD",
                        )
                        if loaders:
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

    def _aguardar_fim_analise(self, timeout: int = 120) -> bool:
        """
        Lógica baseada puramente no estado dos botões (Stop vs Mic/Send).
        Identifica quando o processamento terminou validando o sumiço do Stop
        e o reaparecimento do Microfone ou Seta de Envio.
        """
        _log(f'Gemini processando... Monitorando botões (Timeout: {timeout}s).')
        salvar_print_debug(self.driver,"AGUARDANDO_ANALISE_INICIO")
        fim = time.time() + timeout
        
        # ⚡ POLL RÁPIDO: Aguarda o Angular renderizar o botão Stop (em vez de sleep(5) cego)
        _CSS_STOP_RAPIDO = 'button[aria-label="Stop response"], button[aria-label="Parar resposta"], button[aria-label*="Stop"]'
        deadline_stop = time.time() + 5.0
        while time.time() < deadline_stop:
            try:
                stops = self.driver.find_elements(By.CSS_SELECTOR, _CSS_STOP_RAPIDO)
                if any(s.is_displayed() for s in stops):
                    break  # ⚡ Stop apareceu! Pula direto pro monitoramento
            except:
                pass
            time.sleep(0.2)  # Poll a cada 200ms (25x mais rápido que sleep(5))
        
        # 🛡️ SELETORES CONHECIDOS (rápidos, sem cache - botões que MUTAM no DOM)
        _CSS_STOP = 'button[aria-label="Stop response"], button[aria-label="Parar resposta"], button[aria-label*="Stop"]'
        _CSS_IDLE = (
            'button[aria-label*="Microphone"], button[aria-label*="Microfone"], '
            'button[aria-label*="Send message"], button[aria-label*="Enviar mensagem"], '
            'button.speech_dictation_mic_button'
        )
        _CSS_LOADERS = 'mat-progress-bar, .uploading, [role="progressbar"]'
        
        # Flag para fallback Hunter (só aciona se os seletores diretos falharem MUITAS vezes)
        falhas_diretas = 0
        
        while time.time() < fim:
            try:
                # === 1. DETECTA STOP (seletor direto = instantâneo) ===
                botoes_stop = self.driver.find_elements(By.CSS_SELECTOR, _CSS_STOP)
                stop_visivel = any(b.is_displayed() for b in botoes_stop) if botoes_stop else False
                
                if stop_visivel:
                    falhas_diretas = 0  # Reset - os seletores funcionam
                    pass  # IA ainda gerando...
                else:
                    # === 2. DETECTA IDLE (seletor direto) ===
                    botoes_ociosos = self.driver.find_elements(By.CSS_SELECTOR, _CSS_IDLE)
                    idle_visivel = any(b.is_displayed() for b in botoes_ociosos) if botoes_ociosos else False
                    
                    if idle_visivel:
                        falhas_diretas = 0
                        # 3. Confirma sem spinners
                        loaders = self.driver.find_elements(By.CSS_SELECTOR, _CSS_LOADERS)
                        loader_ativo = any(l.is_displayed() for l in loaders) if loaders else False
                        
                        if not loader_ativo:
                            _log("Gatilho detectado: Botão Stop sumiu e interface voltou a ficar ociosa. Geração concluída!")
                            time.sleep(1.0)
                            salvar_print_debug(self.driver,"AGUARDANDO_ANALISE_SUCESSO")
                            return True
                    else:
                        falhas_diretas += 1
                
                # === SELF-HEALING: Se os seletores diretos não acham NADA por 15 ciclos ===
                # Significa que o Google mudou a interface e precisamos reaprender
                if falhas_diretas >= 15:
                    _log("🧠 [SELF-HEALING] Seletores diretos falharam 15x. Ativando Hunter para reaprender interface...")
                    falhas_diretas = 0  # Reset para não spammar
                    
                    # Hunter SEM cache (permitir_autocura=False) para não envenenar com botões mutáveis
                    el_stop = cacar_elemento_universal(
                        driver=self.driver,
                        chave_memoria="_temp_stop_nao_cachear",
                        descricao_para_ia="Botão de parar/stop a geração de resposta no Gemini",
                        seletores_rapidos=['button.stop', 'button[aria-label*="top"]'],
                        palavras_semanticas=["stop", "parar"],
                        permitir_autocura=False,
                        etapa="GEMINI_CHAT"
                    )
                    if el_stop and el_stop.is_displayed():
                        # Aprende o novo seletor para Log (não cacheia)
                        label = el_stop.get_attribute('aria-label') or 'desconhecido'
                        _log(f"🧠 [SELF-HEALING] Stop reaprendido: aria-label='{label}'")
                        continue  # Continua monitorando
                    
                    el_idle = cacar_elemento_universal(
                        driver=self.driver,
                        chave_memoria="_temp_idle_nao_cachear",
                        descricao_para_ia="Botão de microfone ou enviar mensagem quando a IA terminou de responder",
                        seletores_rapidos=['button[aria-label*="icro"]', 'button[aria-label*="end"]'],
                        palavras_semanticas=["microphone", "microfone", "send", "enviar"],
                        permitir_autocura=False,
                        etapa="GEMINI_CHAT"
                    )
                    if el_idle and el_idle.is_displayed():
                        label = el_idle.get_attribute('aria-label') or 'desconhecido'
                        _log(f"🧠 [SELF-HEALING] Idle reaprendido: aria-label='{label}'. Geração concluída!")
                        time.sleep(1.0)
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
    
    def _aguardar_resposta_textual(self, timeout: int = 120) -> str:
        # A espera padrão (que pode dar timeout cego se o seletor oculto do Google mudar)
        finalizou = self._aguardar_fim_analise(timeout=timeout)
        
        # =========================================================================
        # 🛡️ INTERVENÇÃO DO HUNTER (SELF-HEALING) ANTES DO REFRESH
        # =========================================================================
        if not finalizou:
            _log("⚠️ Timeout na espera padrão. Acionando Hunter para verificar falso-positivo...")
            
            # Tenta achar o botão de enviar ou o campo de texto (indicadores de que o Gemini parou de escrever)
            # Usa os atributos de acessibilidade da classe caso existam
            driver_med = getattr(self, 'driver_acessibilidade', None)
            url_med = getattr(self, 'url_gemini_acessibilidade', None)
            
            ui_ociosa = cacar_elemento_universal(
                driver=self.driver,
                chave_memoria="gemini_ui_ociosa",
                descricao_para_ia="Input de texto ou botão de envio de prompt que fica habilitado quando a IA termina de responder",
                seletores_rapidos=["//button[@aria-label='Send message']", "//div[@role='textbox']", "//rich-textarea"],
                palavras_semanticas=["enviar", "send", "digite", "type", "mensagem", "message"],
                permitir_autocura=True,
                driver_acessibilidade=driver_med,
                url_gemini=url_med,
                etapa="GEMINI_MONITORAMENTO"
            )
            
            if ui_ociosa:
                _log("🎯 Hunter confirmou que a UI está livre. Falso timeout detectado e anulado!")
                finalizou = True  # Cancela o F5, a resposta já está lá e pronta pra ser copiada!
            else:
                _log("🚨 Hunter também não encontrou a UI livre. A tela travou de verdade.")
        # =========================================================================

        if not finalizou:
            # 📸 PRINT DE SEGURANÇA ANTES DO REFRESH
            salvar_print_debug(self.driver, "ESTADO_TELA_PRE_RECOVERY")

            _log('⚠️ Timeout confirmado na UI. Forçando F5 Recovery e reinício da etapa...')
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
        is_headless = self.driver.capabilities.get('moz:headless') or 'headless' in str(self.driver.capabilities).lower()
        if not is_headless:
            from integrations.utils import forcar_fechamento_janela_windows
            forcar_fechamento_janela_windows()

        try:
            scroll_ao_fim(self.driver)

            # 🛡️ PROTOCOLO HUNTER: Mapeia quantos arquivos já existem antes de começar
            xpath_remover = "//button[contains(@aria-label, 'Remover') or contains(@aria-label, 'Remove')]"
            qtd_antes = len(self.driver.find_elements(By.XPATH, xpath_remover))

            # --- TENTATIVA DE INPUT DIRETO (ULTRA RÁPIDA) ---
            input_file = None
            try:
                # ⚡ BUSCA RELÂMPAGO: Se o Gemini já deixou o input no DOM (comum em uploads subsequentes)
                inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                for inp in inputs:
                    if inp is not None:
                        input_file = inp
                        break
            except:
                pass

            if not input_file:
                # --- CAMINHO COMPLETO: Precisa abrir o menu de upload ---
                
                # 1. ACHAR O BOTÃO "+" (com cache do Hunter)
                seletores_mais = [
                    'button[aria-controls="upload-file-menu"]',
                    'button[aria-label*="envio de arquivo"]', 
                    'button[aria-label*="upload file menu"]',
                    'button[aria-label*="Open upload"]',
                    'button[aria-label*="Fazer upload"]',
                    'button[aria-label*="Anexar"]',
                    'mat-icon[fonticon="add_2"]/ancestor::button',
                    'button.upload-card-button',
                    'button[jslog*="188896"]',
                    'button[jslog*="188890"]',
                ]
                
                btn = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="gemini_btn_mais_anexo",
                    descricao_para_ia="O botão de '+' ao lado da caixa de texto no chat do Gemini, usado para fazer upload de imagens ou anexar arquivos.",
                    seletores_rapidos=seletores_mais,
                    palavras_semanticas=['upload', 'anexar', 'arquivo'],
                    permitir_autocura=True,
                    driver_acessibilidade=getattr(self, 'driver_acessibilidade', None),
                    url_gemini=getattr(self, 'url_gemini_acessibilidade', None),
                    etapa="GEMINI_DIRETOR"
                )

                if btn:
                    try:
                        if btn.is_displayed() and "close" not in (btn.get_attribute("class") or ""):
                            from selenium.webdriver.common.action_chains import ActionChains
                            from selenium.webdriver.common.keys import Keys
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(0.1)
                            
                            js_click(self.driver, btn)
                            time.sleep(0.3)
                            
                            # SNIPER DE POPUP DE IMAGEM (só na primeira vez da sessão)
                            if not getattr(self, '_agree_popup_ja_fechado', False):
                                try:
                                    btn_agree = self.driver.find_elements(By.CSS_SELECTOR, 
                                        'button[data-test-id="upload-image-agree-button"]')
                                    if btn_agree and btn_agree[0].is_displayed():
                                        _log("🛡️ Popup de 'Política de Imagens' detectado. Clicando em Agree...")
                                        js_click(self.driver, btn_agree[0])
                                        self._agree_popup_ja_fechado = True
                                        time.sleep(1.0) 
                                        js_click(self.driver, btn)
                                        time.sleep(0.3)
                                except:
                                    pass
                    except: 
                        pass

                # 2. BOTÃO "Enviar arquivo" DENTRO DO MENU (espera curta)
                try:
                    btn_enviar = WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((
                        By.CSS_SELECTOR, 'button[data-test-id="local-images-files-uploader-button"]'
                    )))
                    js_click(self.driver, btn_enviar)
                    time.sleep(0.3)
                except:
                    pass 

                # 3. AGORA BUSCA O INPUT (deve ter aparecido após os cliques)
                try:
                    inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                    for inp in inputs:
                        if inp is not None:
                            input_file = inp
                            break
                except:
                    pass

            # --- VALIDAÇÃO E INJEÇÃO ---
            if not input_file:
                # 🐌 FALLBACK LENTO: Só usa o loop pesado se tudo acima falhou
                input_file = self._encontrar_input_file_visivel_ou_oculto(timeout=10)
            
            self.driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1; arguments[0].style.height='1px'; arguments[0].style.width='1px';",
                input_file,
            )

            input_file.send_keys(str(caminho.resolve()))         
            _log(f'Upload iniciado: {caminho.name}')

            # Limpeza rápida de menus abertos
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            # 🚀 FIRE AND FORGET: Aceleração bruta sem esperar o carregamento visual da barra
            time.sleep(0.1)
            _log(f"✅ Arquivo '{caminho.name}' injetado na fila de upload.")

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

        # ⚡ COOLDOWN INTELIGENTE: Espera a textarea ficar pronta (em vez de sleep(2.5) cego)
        deadline_cool = time.time() + 3.0
        while time.time() < deadline_cool:
            try:
                ta = self.driver.find_elements(By.CSS_SELECTOR, 'div[contenteditable="true"], rich-textarea div[contenteditable]')
                if ta and ta[0].is_displayed() and ta[0].is_enabled():
                    break
            except: pass
            time.sleep(0.2)

        # 🛡️ ANTI-POPUP: Fecha popups promocionais (Deep Research, etc.) que bloqueiam o textarea
        try:
            popups_dismiss = self.driver.find_elements(By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'no thanks') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'não, obrigado') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dismiss') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fechar')]"
            )
            for btn in popups_dismiss:
                if btn.is_displayed():
                    _log("🛡️ Popup promocional detectado (Deep Research?). Fechando...")
                    js_click(self.driver, btn)
                    time.sleep(0.5)
                    break
        except: pass

        salvar_print_debug(self.driver,"PROMPT_PREPARACAO")
        
        try:
            scroll_ao_fim(self.driver)
            textarea = self._obter_textarea_prompt()
            
            textarea.click()
            time.sleep(0.1)
            
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
                time.sleep(0.2)
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
                # 🛠️ AJUSTE SELF-HEALING: Tenta obter o botão (na última tentativa do loop, permite IA)
                permitir_ia = (time.time() > fim - 1) 
                botao = self._obter_botao_enviar(permitir_ia=permitir_ia)
                
                if botao is not None:
                    botao_submit = botao
                    break
                time.sleep(0.1)

            if botao_submit is None:
                # Plano de Emergência: Se o botão sumiu de vez, tenta o Enter físico
                _log("⚠️ Botão de envio não localizado. Tentando disparo via tecla ENTER...")
                textarea.send_keys(Keys.ENTER)
                # Definimos como True para tentar validar o esvaziamento abaixo
                botao_submit = textarea 

            # === BLOQUEIO DE CONFIRMAÇÃO DE ENVIO ===
            # Clica no botão e espera até a caixa de texto ESVAZIAR
            tentativas_click = 0
            enviou = False
            
            while tentativas_click < 4 and not enviou:
                try:
                    js_click(self.driver,botao_submit)
                except Exception:
                    try: botao_submit.click()
                    except: pass
                
                # 🛠️ PLANO C: Se for a conta Ultra ou persistir, forçamos o ENTER no textarea
                if tentativas_click > 1:
                    textarea.send_keys(Keys.ENTER)
                
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
                                if any(word in t_text for word in ["wrong", "errado", "error", "tente", "try again"]):
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

    def avaliar_melhor_imagem_base(self, cand_a: Path, cand_b: Path, img_produto: Path, nome_produto: str, estilo: str) -> Path:
        """Faz o upload do Produto Original + Variante A + Variante B e julga a fidelidade."""
        from integrations.utils import _log, salvar_print_debug

        _log(f"Iniciando Teste A/B de Imagens com Validação de Produto: {cand_a.name} vs {cand_b.name}...", "GEMINI-IA")
        self.abrir_novo_chat_limpo()

        self.anexar_arquivo_local(img_produto)
        self.anexar_arquivo_local(cand_a)
        self.anexar_arquivo_local(cand_b)

        prompt_juri = (
            f"Você é um Júri técnico avaliando imagens geradas para anuncio do produto \"{nome_produto}\"."
            f" Recebi 3 imagens nesta ordem:\n"
            f"IMAGEM 1: Produto Original — referencia absoluta de estrutura, formato, cor e detalhes.\n"
            f"IMAGEM 2: Candidata A.\n"
            f"IMAGEM 3: Candidata B.\n\n"

            f"PASSO 1 — ELIMINACAO POR FALHA GRAVE (analise cada candidata separadamente)\n"
            f"Desclassifique imediatamente qualquer candidata que apresentar ao menos UMA das falhas abaixo:\n\n"

            f"FALHAS DE GERACAO (verifica primeiro — eliminacao imediata):\n"
            f"- Candidata identica ou quase identica a Imagem 1 (produto sozinho, sem modelo, sem cenario)\n"
            f"- Candidata sem presenca humana quando o estilo exige modelo ({estilo})\n"
            f"- Candidata que claramente nao foi gerada — parece foto de produto de catalogo ou e-commerce\n\n"

            f"FALHAS DE PRODUTO:\n"
            f"- Produto com estrutura, formato ou cor visivelmente diferentes da Imagem 1\n"
            f"- Pecas ou acessorios inventados que nao existem no produto original\n"
            f"- Produto entortado, fundido ao cenario ou parcialmente ausente\n\n"

            f"FALHAS DE ANATOMIA:\n"
            f"- Maos, bracos ou pernas em excesso ou faltando\n"
            f"- Dedos deformados, fundidos ou em numero errado\n"
            f"- Corpo com proporcoes claramente distorcidas\n\n"

            f"PASSO 2 — DESEMPATE (so se ambas passarem na eliminacao)\n"
            f"Avalie qual candidata tem melhor qualidade de anuncio para o estilo \"{estilo}\":\n"
            f"- Produto em destaque e bem iluminado\n"
            f"- Composicao e enquadramento mais atrativos\n"
            f"- Modelo com postura natural e confiante\n\n"

            f"PASSO 3 — VEREDITO\n"
            f"Se uma candidata foi eliminada no Passo 1, a outra vence automaticamente.\n"
            f"Se ambas forem eliminadas, escolha a menos ruim.\n"
            f"Responda APENAS neste formato exato, sem mais nada:\n"
            f"VENCEDOR: A\n"
            f"ou\n"
            f"VENCEDOR: B"
        )
        resposta_ia = self.enviar_prompt(prompt_juri, timeout=120, aguardar_resposta=True)

        if resposta_ia and "VENCEDOR: B" in resposta_ia.upper():
            _log("Gemini escolheu a Variante B.", "GEMINI-IA")
            return cand_b
        else:
            _log("Gemini escolheu a Variante A (ou fallback).", "GEMINI-IA")
            return cand_a

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
                btn_download = cacar_elemento_universal(
                    driver=self.driver,
                    chave_memoria="gemini_btn_download_img",
                    descricao_para_ia="Botão de download de imagem gerada na galeria do Gemini",
                    seletores_rapidos=[
                        'button[data-test-id="download-generated-image-button"]',
                        'button[aria-label="Download full size image"]',
                    ],
                    palavras_semanticas=["download", "baixar", "save"],
                    etapa="GEMINI_DOWNLOAD_IMG",
                    permitir_autocura=False,
                )
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
            qtd_cenas_menos_1=qtd_cenas - 1,
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
            qtd_cenas_menos_1=qtd_cenas - 1,
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
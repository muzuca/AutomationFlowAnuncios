# arquivo: integrations/gemini.py
# descricao: fachada GeminiAnunciosViaFlow blindada para validacao de imagem,
# geracao POV e criacao de roteiro dinâmico.
# Otimizado para VELOCIDADE EXTREMA, DOWNLOAD NATIVO (60s) e AUTO-F5 EM ERROS DA UI.
# Adicionado suporte para avaliar múltiplas variantes de vídeo e eleger a melhor via interface Web.

from __future__ import annotations

import re
import time
import shutil
import pyperclip
from pathlib import Path
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

EXTENSOES_IMAGEM = ('.jpg', '.jpeg', '.png', '.webp')

# ──────────────────────────────────────────────────────────────────────────────
# Templates de Roteirização (ENGENHARIA MASTER FULL TIKTOK SHOP - TEXTO PURO)
# ──────────────────────────────────────────────────────────────────────────────

_TEMPLATE_TREINO_MESTRE = """
INSTRUÇÃO DE SISTEMA: ENGENHEIRO DE ROTEIROS TIKTOK SHOP (MASTER FULL)

Você é um especialista em Social Commerce. Sua tarefa é transformar fotos e vídeos em 3 roteiros técnicos de 8 segundos cada.

1. REGRAS DE OURO (NÃO NEGOCIÁVEIS)
• MÉTRICA: Cada fala DEVE ter entre 24 e 25 palavras (para bater exatamente 8 segundos).
• TOM: Sotaque Carioca, energia máxima, "smiling voice", ritmo acelerado.
• VISUAL: Use sempre "REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO".
• MOVIMENTO SEGURO (ANTI-GLITCH): Câmera 100% estática (Locked static shot. NO camera movement). Mãos e braços devem permanecer IMÓVEIS segurando os produtos, exatamente como na foto original. NUNCA crie ações de apontar se as mãos estiverem ocupadas (isso gera uma "terceira mão" e violações). Foque os movimentos APENAS em expressões faciais sutis (sorrisos, piscar de olhos, respiração natural) e na fala da modelo.
• PREÇO (REGRA DE PRECISÃO): No áudio, arredonde SEMPRE para o próximo número inteiro imediatamente acima (Ex: R$ 30,40 vira "menos de trinta e um reais"; R$ 50,90 vira "menos de cinquenta e um reais"). Na legenda, PROIBIDO números ou frete.
• GATILHOS: Proibido começar com "Para tudo" ou "Gente olha". Comece com o benefício direto.
• INDEPENDÊNCIA DE CENA (FLOW): Cada cena é tratada pela IA como um arquivo único. É PROIBIDO usar palavras como "same", "repeat", "equal to previous" ou referências a outras cenas. Repita integralmente todas as descrições técnicas de áudio, voz e câmera em todas as cenas/prompts.
• FORMATAÇÃO (CAIXAS DE TEXTO): Os prompts de cada cena, bem como as legendas/hashtags, DEVEM ser entregues em texto direto no chat. NUNCA escreva a frase "PROMPT TÉCNICO:" em nenhum lugar. O texto deve começar diretamente na instrução de transformação ("Transform the input image...").

2. PROTOCOLO DE SAÍDA
Você deve entregar a resposta seguindo EXATAMENTE este modelo de estrutura em texto puro, direto no chat. A descrição da cena fica acima do prompt, e o prompt fica logo abaixo:

[Cena 1: Título da Cena - Breve resumo da emoção da modelo]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement.
ACTION SEQUENCE — Model keeps hands completely still, firmly holding the items exactly as in the photo. Subtle facial expression of joyful shock and smiling. 3️⃣ Very subtle natural breathing.
Model voiceover says: "[Texto exato de 24-25 palavras]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Cena 2: Título da Cena - Breve resumo focado nos benefícios e qualidade do produto]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement.
ACTION SEQUENCE — Model keeps hands completely still, firmly holding the items exactly as in the photo. 2️⃣ NO camera rotation or zoom. 3️⃣ Model smiles and speaks naturally to the camera.
Model voiceover says: "[Texto exato de 24-25 palavras focando em benefícios]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Cena 3: Título da Cena - Breve resumo sobre o Call to Action sem o uso de gestos com as mãos]
Transform the input image into an ultra realistic 8-second vertical video (9:16). REPLICATE THE MODEL AND SCENE EXACTLY AS SHOWN IN THE PHOTO.
CAMERA — Vertical 9:16. Locked static shot. NO camera movement.
ACTION SEQUENCE — Model keeps hands completely still, holding the items. Do NOT point or move arms. 2️Friendly wink and wide smile. 3️⃣ NO glitches.
Model voiceover says: "[Texto de 24-25 palavras com preço arredondado e CTA do carrinho]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Legenda e Hashtags]
[Texto curto com 10 palavras, direto, SEM preços, SEM frete, SEM link. Use emojis.]
#hashtag1 #hashtag2 #tiktokshop

1. EXEMPLO DE CONTAGEM PARA VALIDAR (25 PALAVRAS):
"Esse kit maravilhoso sai por menos de cinquenta e um reais hoje no TikTok Shop então corre agora no carrinho pra garantir o seu antes que acabe!"

DIRETRIZ FINAL: 
Quando o usuário enviar arquivos, processe as informações e responda APENAS seguindo a estrutura visual acima. 
Assegure-se de que cada prompt e a legenda estejam escrivos em texto puro, sem emojis na sequencia do chat. 
NUNCA invente movimentos de mãos se o modelo já estiver segurando algo na foto de referência.

Confirme brevemente que entendeu a função e aguarde o comando com os arquivos.
"""

_TEMPLATE_ROTEIRO_EXECUCAO = """Vamos gerar um novo roteiro para um anúncio de {qtd_cenas} cenas do produto que está sendo apresentado nos arquivos em anexo. 
Na fala devemos garantir o gancho na cena 1, falar as qualidades e benefícios do produto no meio e fala do preço e o CTA no final. 

Estou enviando em anexo:
- A foto do produto sendo apresentado em estilo POV (apenas duas mãos segurando o produto)
- Uma imagem com o nome do produto e o preço
- {texto_referencia_dinamico}

Extraia o nome do produto, o preço e os detalhes diretamente da leitura/transcrição das imagens/vídeo.

DIRETRIZES POV (NÃO NEGOCIÁVEIS):
Como a filmagem é em POV (Point of View), os prompts técnicos DEVEM refletir isso. 
Especifique claramente nos prompts que a câmera é POV e mostre apenas as mãos. É ESTRITAMENTE PROIBIDO gerar rostos, cabeças, corpos inteiros, pessoas ao fundo ou qualquer elemento que não esteja na imagem de referência POV. Foque apenas em movimentos sutis de respiração ou da própria luz/cenário, mantendo as mãos 100% estáticas.

Siga ESTRITAMENTE o Protocolo de Saída definido no seu treinamento em texto puro corrido, usando as tags [CENA 1], [CENA 2], etc.
Lembre-se da regra de ouro: Câmera 100% estática, mãos completamente imóveis (anti-glitch), preço arredondado para cima, exatas 24-25 palavras por cena.
Responda APENAS com as {qtd_cenas} cenas estruturadas, nada mais.
"""


def _log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] [GEMINI-IA] {msg}')


class GeminiAnunciosViaFlow:
    def __init__(self, driver: Any, url_gemini: str, timeout: int = 30):
        self.driver = driver
        self.url_gemini = url_gemini
        self.wait = WebDriverWait(driver, timeout, poll_frequency=0.1)
        self.timeout = timeout

    def abrir_gemini(self) -> None:
        if 'gemini.google.com' not in self.driver.current_url:
            _log('Abrindo Gemini...')
            self.driver.get(self.url_gemini) 
            self.wait.until(lambda d: 'gemini.google.com' in d.current_url)
            
            # Validação instantânea da URL
            time.sleep(1.5) # Dá 1 segundo e meio pro Google decidir se vai redirecionar
            if '/app' not in self.driver.current_url:
                _log(f'🚨 URL redirecionada para a página inicial ({self.driver.current_url}). Conta inoperante.')
                raise Exception("Conta redirecionada para fora do Gemini App. Trocando de conta.")

    def _forcar_modelo_pro(self) -> None:
        """Procura o seletor de modelo do Gemini e força a opção Pro, evitando Fast e Thinking."""
        _log('Verificando/Forçando modelo Pro...')
        
        # Pausa inicial vital: Dá tempo para o Angular renderizar o botão após criar o chat
        time.sleep(2.0) 
        
        for tentativa in range(1, 4):
            try:
                # 1. Procura o botão de abrir o menu
                menu_btn_elements = self.driver.find_elements(By.CSS_SELECTOR, 'button[data-test-id="bard-mode-menu-button"], button[aria-label="Open mode picker"]')
                if not menu_btn_elements:
                    _log(f'Botão de modelo ainda não apareceu (Tentativa {tentativa}/3)...')
                    time.sleep(1.5)
                    continue 

                menu_btn = menu_btn_elements[0]
                
                # 2. Lê o texto do botão para ver se já estamos no Pro
                texto_atual = (menu_btn.text or '').strip().lower()
                if 'pro' in texto_atual and 'thinking' not in texto_atual and 'pensamento' not in texto_atual:
                    _log('✅ Modelo Pro já está ativo.')
                    return # Sucesso, sai da função
                    
                _log(f'Modelo atual é "{texto_atual}". Abrindo menu de seleção (Tentativa {tentativa}/3)...')
                
                # Traz o botão pro meio da tela e clica
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", menu_btn)
                time.sleep(0.5)
                self._js_click(menu_btn)
                time.sleep(1.5) # Espera a animação do menu abrir
                
                # 3. Procura a opção Pro exata
                seletores_pro = [
                    'button[data-mode-id="e6fa609c3fa255c0"]',
                    'button[data-test-id="bard-mode-option-pro"]'
                ]
                
                clicou_pro = False
                for seletor in seletores_pro:
                    opcoes_pro = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for opcao in opcoes_pro:
                        # Trava de segurança extra
                        texto_opcao = (opcao.text or '').strip().lower()
                        if 'thinking' not in texto_opcao and 'pensamento' not in texto_opcao and 'fast' not in texto_opcao:
                            self._js_click(opcao)
                            clicou_pro = True
                            break
                    if clicou_pro:
                        break

                if clicou_pro:
                    time.sleep(1.5) # Espera a interface confirmar e fechar o menu
                    _log('✅ Modelo Pro selecionado com sucesso.')
                    return # Missão cumprida, sai da função
                else:
                    _log('⚠️ Opção Pro não encontrada no DOM. Fechando menu e recomeçando...')
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1.0)
                    
            except Exception as e:
                _log(f'⚠️ Erro na interface ao tentar mudar pro Pro ({e}). Tentando novamente...')
                time.sleep(1.0)
                
        _log('🚨 Aviso: Esgotaram as tentativas de forçar o modelo Pro. Seguindo em frente...')

    def abrir_novo_chat_limpo(self) -> None:
        self._scroll_chat_ate_fim()
        _log('Criando novo chat nativamente via botão da interface...')
        
        if 'gemini.google.com' not in self.driver.current_url:
            self.abrir_gemini()
            
        # VALIDAÇÃO AGRESSIVA DE URL (O "Pulo do Gato")
        if '/app' not in self.driver.current_url:
            _log('Forçando URL principal do Gemini...')
            self.driver.get(self.url_gemini)
            time.sleep(1.5)
            
            if '/app' not in self.driver.current_url:
                _log(f'🚨 CONTA INOPERANTE! Redirecionou para: {self.driver.current_url}')
                raise Exception('Conta bloqueada/inoperante. O Gemini redirecionou a URL.')

        try:
            seletores_botao = [
                'side-nav-action-button[data-test-id="new-chat-button"] a',
                'a.side-nav-action-collapsed-button[href="/app"]',
                'span[data-test-id="new-chat-button"]'
            ]
            
            clicou = False
            for seletor in seletores_botao:
                botoes = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for btn in botoes:
                    if btn.is_displayed():
                        self._js_click(btn)
                        _log('Botão "New Chat" clicado.')
                        clicou = True
                        break
                if clicou:
                    break
                    
            if not clicou:
                _log('Botão de Novo Chat não encontrado. Forçando URL raiz...')
                self.driver.get(self.url_gemini)
                time.sleep(2)
                
                if '/app' not in self.driver.current_url:
                    _log(f'🚨 CONTA INOPERANTE APÓS REFRESH! Redirecionou para: {self.driver.current_url}')
                    raise Exception('Conta bloqueada/inoperante. O Gemini redirecionou a URL.')
                
            fim = time.time() + 10
            while time.time() < fim:
                self._scroll_chat_ate_fim()
                respostas = self.driver.find_elements(By.CSS_SELECTOR, 'model-response')
                if not respostas:
                    break
                time.sleep(0.1)
                
            self._obter_textarea_prompt()
            self._scroll_chat_ate_fim()
            _log('Novo chat pronto para receber comandos.')
            
            # --- NOVO: Força o Gemini para a versão PRO logo após iniciar o chat ---
            self._forcar_modelo_pro()
            
        except TimeoutException:
            _log('🚨 ERRO RÁPIDO: Campo de prompt não encontrado.')
            raise Exception('Interface do Gemini falhou em inicializar o chat.')
        except Exception as e:
            _log(f'Erro ao tentar criar novo chat: {e}')
            raise

    def _js_click(self, element: WebElement) -> None:
        self.driver.execute_script('arguments[0].click();', element)

    def _scroll_chat_ate_fim(self) -> None:
        """Scroll Nuclear: Desce tudo que pode rolar na página."""
        try:
            self.driver.execute_script(
                """
                const scrollers = document.querySelectorAll('infinite-scroller, #chat-history, .chat-history-scroll-container, .conversation-container');
                scrollers.forEach(scroller => {
                    scroller.scrollTop = scroller.scrollHeight;
                });
                
                const allElements = document.querySelectorAll('*');
                for (let i = 0; i < allElements.length; i++) {
                    let el = allElements[i];
                    if (el.scrollHeight > el.clientHeight) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
                
                window.scrollTo(0, document.documentElement.scrollHeight || document.body.scrollHeight);
                """
            )
        except Exception:
            pass

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
                        self._js_click(el)
                        _log(f'Popup tardio do Chrome tratado: {texto}')
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
        ]
        fim = time.time() + 10
        while time.time() < fim:
            for seletor in seletores:
                try:
                    elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                    for el in elementos:
                        if el.is_displayed() and el.is_enabled():
                            return el
                except Exception:
                    pass
            time.sleep(0.1)
        raise TimeoutException('Campo de prompt do Gemini nao encontrado.')

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
        """Dupla estratégia: rápida para imagens, minuciosa para vídeos."""
        fim = time.time() + timeout
        
        if is_video:
            _log(f'Aguardando estabilização do upload de VÍDEO (max {timeout}s)...')
            while time.time() < fim:
                try:
                    self._scroll_chat_ate_fim()
                    carregando = False
                    try:
                        # --- SELETORES ATUALIZADOS PARA O LOADER DE VÍDEO ---
                        loaders = self.driver.find_elements(By.CSS_SELECTOR, 'mat-progress-bar, .uploading, [role="progressbar"], mat-spinner, .loading-spinner, [aria-label*="loading"], [aria-label*="uploading"]')
                        if loaders and any(l.is_displayed() for l in loaders):
                            carregando = True
                    except Exception:
                        pass
                    
                    if not carregando:
                        btn = self._obter_botao_enviar()
                        if btn is not None:
                            # --- PAUSA EXTRA APENAS PARA VÍDEO (Garante que a UI atualizou) ---
                            time.sleep(2.0)
                            _log('Upload de vídeo estabilizado e botão de envio habilitado.')
                            return
                except Exception:
                    pass
                time.sleep(1.0)
        else:
            # Lógica ORIGINAL e rápida para imagens
            while time.time() < fim:
                try:
                    self._scroll_chat_ate_fim()
                    btn = self._obter_botao_enviar()
                    if btn is not None:
                        _log('Botão de envio habilitado apos upload.')
                        return
                except Exception:
                    pass
                time.sleep(0.1)
                
        _log('Aviso: upload nao confirmou estado pronto dentro do tempo esperado.')

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
        """Sensor de Microfone."""
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

    def _extrair_resposta_binaria_direta(self) -> Optional[bool]:
        seletores = [
            'model-response',
            'message-content',
            '.model-response-text'
        ]
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                if not elementos:
                    continue
                
                el = elementos[-1]
                txt = el.get_attribute('textContent') or el.get_attribute('innerText') or el.text or ''
                txt = self._texto_limpo(txt).upper()
                
                if not txt or self._parece_texto_inutil_ui(txt):
                    continue
                
                up_clean = re.sub(r'[*_.\-",:;]', ' ', txt)
                sim_matches = list(re.finditer(r'\bSIM\b', up_clean))
                nao_matches = list(re.finditer(r'\b(NAO|NÃO)\b', up_clean))
                
                last_sim = sim_matches[-1].start() if sim_matches else -1
                last_nao = nao_matches[-1].start() if nao_matches else -1
                
                if last_sim > last_nao:
                    return True
                elif last_nao > last_sim:
                    return False
            except Exception:
                pass
        return None

    def _extrair_texto_resposta_recente(self) -> str:
        binaria = self._extrair_resposta_binaria_direta()
        if binaria is True:
            return 'SIM'
        if binaria is False:
            return 'NAO'
            
        seletores = [
            'model-response',
            'message-content',
            '.model-response-text'
        ]
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                if not elementos:
                    continue
                
                el = elementos[-1]
                txt = self._texto_limpo(el.get_attribute('textContent') or el.get_attribute('innerText') or el.text or '')
                if not txt or self._parece_texto_inutil_ui(txt):
                    continue
                return txt.strip()
            except Exception:
                pass
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

    def _aguardar_fim_analise(self, timeout: int = 90) -> bool:
        fim = time.time() + timeout
        viu_processando = False
        while time.time() < fim:
            try:
                self._scroll_chat_ate_fim()
                binaria = self._extrair_resposta_binaria_direta()
                if binaria is not None:
                    return True
                
                if self._gemini_esta_processando():
                    if not viu_processando:
                        _log('Gemini esta processando... aguardando conclusao.')
                    viu_processando = True
                    time.sleep(0.1)
                    continue
                
                if viu_processando:
                    for _ in range(5):
                        self._scroll_chat_ate_fim()
                        binaria = self._extrair_resposta_binaria_direta()
                        if binaria is not None:
                            return True
                        time.sleep(0.1)
                    return True
                
                texto = self._extrair_texto_resposta_recente()
                if texto:
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def _aguardar_resposta_textual(self, timeout: int = 40) -> str:
        finalizou = self._aguardar_fim_analise(timeout=timeout)
        
        if not finalizou:
            _log('⚠️ Timeout na UI. Forçando F5 Recovery...')
            self.driver.refresh()
            self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
            self._scroll_chat_ate_fim()
            
            for _ in range(10):
                self._scroll_chat_ate_fim()
                binaria = self._extrair_resposta_binaria_direta()
                if binaria is True:
                    _log('F5 Recovery com sucesso. Resposta capturada: SIM')
                    return 'SIM'
                if binaria is False:
                    _log('F5 Recovery com sucesso. Resposta capturada: NAO')
                    return 'NAO'
                texto = self._extrair_texto_resposta_recente()
                if texto:
                    interpretacao = self._interpretar_resposta_binaria(texto)
                    if interpretacao is not None:
                        _log(f'F5 Recovery com sucesso. Resposta capturada: {"SIM" if interpretacao else "NAO"}')
                        return 'SIM' if interpretacao else 'NAO'
                    return texto
                time.sleep(0.5)
            
            return 'TIMEOUT_ANALISE'
        
        fim = time.time() + 2.5
        ultima = ''
        while time.time() < fim:
            try:
                self._scroll_chat_ate_fim()
                binaria = self._extrair_resposta_binaria_direta()
                if binaria is True:
                    return 'SIM'
                if binaria is False:
                    return 'NAO'
                texto = self._extrair_texto_resposta_recente()
                if texto:
                    ultima = texto
                    interpretacao = self._interpretar_resposta_binaria(texto)
                    if interpretacao is True:
                        return 'SIM'
                    if interpretacao is False:
                        return 'NAO'
                    return texto
            except Exception:
                pass
            time.sleep(0.1)
        return ultima or 'SEM_RESPOSTA_UTIL'

    def anexar_arquivo_local(self, caminho: Path) -> None:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f'Arquivo nao encontrado: {caminho}')
        _log(f'Anexando arquivo: {caminho.name}')
        try:
            self._scroll_chat_ate_fim()
            botao_mais = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label="Open upload file menu"]')))
            self._js_click(botao_mais)
            
            upload_files = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-test-id="local-images-files-uploader-button"]')))
            self._js_click(upload_files)
            
            input_file = self._encontrar_input_file_visivel_ou_oculto()
            self.driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                input_file,
            )
            input_file.send_keys(str(caminho.resolve()))
            _log(f'Upload iniciado para: {caminho.name}')
            
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            
            is_video = caminho.suffix.lower() in ['.mov', '.mp4', '.avi', '.mkv', '.webm']
            
            if is_video:
                time.sleep(3.0) 

            timeout_upload = 180 if is_video else 20
            self._aguardar_upload_estabilizar(timeout=timeout_upload, is_video=is_video)
            
        except TimeoutException as e:
            _log(f'ERRO: Timeout ao anexar {caminho.name}: {e}')
            raise
        except Exception as e:
            _log(f'ERRO: Falha ao anexar {caminho.name}: {e}')
            raise

    def enviar_prompt(
        self,
        prompt: str,
        timeout: int = 60,
        aguardar_resposta: bool = True,
    ) -> str:
        _log(f'Enviando prompt ({len(prompt)} chars)...')
        
        try:
            self._scroll_chat_ate_fim()
            textarea = self._obter_textarea_prompt()
            
            textarea.click()
            time.sleep(0.2)
            
            try:
                # Tenta colar super rápido usando a área de transferência (suporta EMOJIS nativamente)
                pyperclip.copy(prompt)
                textarea.send_keys(Keys.CONTROL, "v")
                time.sleep(0.5)
            except Exception:
                # Fallback removendo emojis caso o pyperclip falhe (Evita erro do ChromeDriver BMP)
                prompt_seguro = re.sub(r'[^\u0000-\uFFFF]', '', prompt)
                textarea.send_keys(prompt_seguro)
            
            _log('Prompt digitado')
            
            self._scroll_chat_ate_fim()
            
            botao_submit = None
            fim = time.time() + 5
            while time.time() < fim:
                self._scroll_chat_ate_fim()
                botao = self._obter_botao_enviar()
                if botao is not None:
                    botao_submit = botao
                    break
                time.sleep(0.1)

            if botao_submit is None:
                raise TimeoutException('Botao de envio nao ficou disponivel.')
            
            try:
                botao_submit.click()
            except Exception:
                self._js_click(botao_submit)
                
            _log('Prompt submetido')
            
            fim_erro = time.time() + 4
            while time.time() < fim_erro:
                try:
                    retry_btns = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Retry') or contains(text(), 'Tentar novamente')]/ancestor::button")
                    if retry_btns and retry_btns[0].is_displayed():
                        _log("⚠️ Erro de servidor detectado. Clicando em Retry...")
                        self._js_click(retry_btns[0])
                        break
                    
                    toasts = self.driver.find_elements(By.CSS_SELECTOR, "simple-snack-bar, snack-bar-container, div[class*='snackbar'], div[class*='toast'], [role='alert']")
                    if toasts:
                        for toast in toasts:
                            if toast.is_displayed():
                                t_text = toast.text.lower()
                                if "wrong" in t_text or "errado" in t_text or "error" in t_text or "tente" in t_text or "try again" in t_text:
                                    _log(f"⚠️ Erro na UI detectado ('{t_text[:30]}...'). Dando F5 e abortando...")
                                    self.driver.refresh()
                                    time.sleep(3)
                                    return 'ERRO_F5'

                    if self._gemini_esta_processando() or self._obter_botao_enviar() is None:
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            
            self._scroll_chat_ate_fim()
            
            if aguardar_resposta:
                return self._aguardar_resposta_textual(timeout=timeout)
            return 'ENVIADO'
            
        except TimeoutException:
            _log('ERRO: Timeout ao enviar prompt')
            return 'TIMEOUT'
        except Exception as e:
            _log(f'ERRO ao enviar prompt: {e}')
            return f'ERRO: {e}'

    def contar_imagens_geradas(self) -> int:
        seletores = [
            'model-response:last-of-type img[data-test-id*="generated"]',
            'model-response:last-of-type img[src^="blob:"]',
            'model-response:last-of-type img[alt*="Generated"]',
            'model-response:last-of-type img'
        ]
        vistos = []
        for seletor in seletores:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, seletor):
                    if not el.is_displayed():
                        continue
                    src = el.get_attribute('src') or ''
                    if 'profile/picture' in src or 'avatar' in src.lower() or 'logo' in src.lower():
                        continue
                    alt = (el.get_attribute('alt') or '').strip().lower()
                    key = (src, alt)
                    if key not in vistos:
                        vistos.append(key)
            except Exception:
                pass
        return len(vistos)

    def aguardar_nova_imagem(self, total_antes: int, timeout: int = 180) -> bool:
        fim = time.time() + timeout
        while time.time() < fim:
            self._scroll_chat_ate_fim()
            total_agora = self.contar_imagens_geradas()
            if total_agora > total_antes:
                _log(f'Nova imagem detectada: {total_agora} > {total_antes}')
                return True
            time.sleep(0.5) 
        _log('Timeout aguardando nova imagem.')
        return False

    def baixar_ultima_imagem(self, destino: Path) -> bool:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._scroll_chat_ate_fim()
            
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
                self._scroll_chat_ate_fim()
                try:
                    self._js_click(img_alvo)
                    time.sleep(0.5)
                    if self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Download full size image"], button[data-test-id="download-generated-image-button"]'):
                        clicado = True
                        break
                except Exception:
                    pass
            
            if not clicado:
                _log('Falha ao abrir a galeria da imagem.')
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

            self._js_click(btn_download)
            _log('Botão nativo de download clicado.')

            novo_arquivo = None
            fim_down = time.time() + 60 
            while time.time() < fim_down:
                self._scroll_chat_ate_fim()
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
        timeout_resposta: int = 40,
        max_reenvios_prompt: int = 1,
    ) -> bool:
        caminho_imagem = Path(caminho_imagem)
        _log(f'Validando candidato a produto com Gemini: {caminho_imagem.name}')
        
        # --- GARANTIA ABSOLUTA: Força o modelo Pro antes de anexar o primeiro arquivo ---
        self._forcar_modelo_pro()
        
        self.anexar_arquivo_local(caminho_imagem)
        prompt_validacao_produto = (
            'A imagem anexada contem um produto fisico claramente visivel e identificavel? '
            'Nao importa se ha textos, preco, interface de loja ou elementos promocionais. '
            "Se o produto estiver claramente visivel, responda APENAS com 'SIM'. "
            "Se nao houver produto visivel ou ele nao puder ser identificado, responda APENAS com 'NAO'."
        )
        resposta = ''
        for tentativa in range(1, max_reenvios_prompt + 2):
            self._scroll_chat_ate_fim()
            if tentativa > 1:
                _log(f'Reenviando prompt da imagem {caminho_imagem.name} (tentativa {tentativa})')
            resposta = self.enviar_prompt(prompt_validacao_produto, timeout=timeout_resposta).strip().upper()
            if resposta in ('TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5'):
                if tentativa <= max_reenvios_prompt:
                    self.abrir_novo_chat_limpo()
                    continue
                raise TimeoutException(f'Gemini nao concluiu validacao util para {caminho_imagem.name}')
            break
        return resposta == 'SIM' or resposta.startswith('SIM') or '\nSIM' in resposta

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

    def executar_fluxo_imagem_pov(
        self,
        tarefa: Any,
        foto_produto_escolhida: Optional[Path] = None,
        max_tentativas: int = 3,
    ) -> Optional[Path]:
        dir_anuncio = Path(getattr(tarefa, 'folder_path', '.'))
        caminho_saida = dir_anuncio / 'POV_VALIDADO.png'

        if foto_produto_escolhida is None:
            foto_produto_escolhida = self._selecionar_foto_produto(tarefa)
            if not foto_produto_escolhida:
                return None
        else:
            foto_produto_escolhida = Path(foto_produto_escolhida)

        for tentativa in range(1, max_tentativas + 1):
            self._scroll_chat_ate_fim()
            _log(f'Fluxo POV iniciado (tentativa {tentativa}/{max_tentativas}).')

            caminho_saida.parent.mkdir(parents=True, exist_ok=True)
            
            if tentativa == 1:
                _log('Aproveitando contexto do chat atual (imagem já anexada na Etapa 10).')
            else:
                _log('Abrindo novo chat para regerar imagem POV do zero...')
                self.abrir_novo_chat_limpo()
                self.anexar_arquivo_local(foto_produto_escolhida)

            prompt_geracao = (
                'Usando a imagem do produto que já está anexada nesta conversa como referência principal, '
                'gere uma nova imagem ultra-realista vertical 9:16 para anuncio. '
                'A cena deve estar em POV, como se a camera fosse os olhos da pessoa. '
                f'Mostre exatamente duas maos humanas de {getattr(tarefa, "characteristics_model", getattr(tarefa, "caracteristicas_modelo", "uma modelo"))} '
                'segurando ou interagindo naturally com o produto em primeiro plano. '
                'O produto deve continuar fiel ao item original, claramente visivel, central, '
                'bem enquadrado e sem deformacoes. '
                'Estilo lifestyle premium, iluminacao natural de estudo, fundo coerente e realista. '
                'Nao adicione textos, colagens, molduras, elementos de interface ou objetos extras competindo com o produto. '
                'Responda gerando apenas a imagem.'
            )

            total_imagens_antes = self.contar_imagens_geradas()
            status_envio = self.enviar_prompt(prompt_geracao, aguardar_resposta=False)

            if status_envio == 'ERRO_F5':
                _log('Aviso: Abortando espera e recomeçando tentativa devido ao F5 de emergência.')
                continue

            if not self.aguardar_nova_imagem(total_antes=total_imagens_antes, timeout=180):
                continue

            baixou = False
            for _ in range(3):
                self._scroll_chat_ate_fim()
                if self.baixar_ultima_imagem(caminho_saida):
                    baixou = True
                    break
                
            if not baixou:
                _log('Falha persistente ao baixar imagem gerada.')
                continue

            self._scroll_chat_ate_fim()
            _log('Validando qualidade da imagem POV gerada...')
            self.abrir_novo_chat_limpo()
            self.anexar_arquivo_local(caminho_saida)

            regerar_imagem = False
            for tentativa_val in range(1, 4):
                self._scroll_chat_ate_fim()
                
                if tentativa_val > 1:
                    prompt_validacao = "Não entendi ou houve um erro. Por favor, analise carefully a imagem anexada acima. Se ela mostrar mãos humanas segurando o produto em primeira pessoa (POV), responda SIM. Caso contrário, NAO. Responda apenas SIM ou NAO."
                else:
                    prompt_validacao = (
                        "Você é um avaliador de anúncios, NÃO um fotógrafo perfeccionista. "
                        "Analise esta imagem publicitária anexada e responda apenas com 'SIM' ou 'NAO'. "
                        "Responda 'SIM' se TODAS as condições forem verdadeiras: "
                        "- Existe um produto físico visível em destaque na imagem. "
                        "- Existem mãos humanas visíveis segurando ou interagindo com o produto. "
                        "- A cena transmite claramente um efeito POV ou próxima de primeira pessoa. "
                        "- A imagem tem qualidade aceitável para uso em anúncio de redes sociais. "
                        "Responda 'NAO' apenas se NÃO houver mãos, ou NÃO houver produto visível, "
                        "ou se a imagem estiver confusa demais para uso publicitário. "
                        "Não use critérios extremamente rígidos; seja tolerante se o conceito geral estiver correto."
                    )

                veredito = self.enviar_prompt(prompt_validacao, timeout=60, aguardar_resposta=True).strip().upper()
                
                if not veredito or veredito in {'ENVIADO', 'TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5'}:
                    veredito = self._aguardar_resposta_textual(timeout=60).strip().upper()

                resultado_final = self._interpretar_resposta_binaria(veredito)

                if resultado_final is True:
                    _log(f'✅ Imagem POV aprovada: {caminho_saida.name}')
                    return caminho_saida

                if resultado_final is False:
                    if tentativa_val == 1:
                        _log(f'⚠️ Recebi um NAO. Vou pedir uma reavaliação no mesmo chat antes de descartar...')
                        continue
                    else:
                        _log(f'❌ Imagem POV reprovada após reavaliação. Motivo: {veredito[:120]}')
                        regerar_imagem = True
                        break 
                
                _log(f'⚠️ Falha na leitura do veredito (Resposta: {veredito[:50]}). Retentando no mesmo chat...')

            if regerar_imagem:
                continue 
            else:
                continue

        _log('🚨 Erro fatal: Não foi possível gerar uma imagem POV válida.')
        return None

    def treinar_e_gerar_roteiro(
        self,
        arquivos: List[Path],
        dados_produto: Dict,
        arquivo_ref: Optional[Path] = None,
        qtd_cenas: int = 3
    ) -> str:
        id_pasta = dados_produto.get('nome', '1')
        
        self._scroll_chat_ate_fim()
        _log(f"Iniciando fase de roteirização (Tarefa {id_pasta})")
        
        self.abrir_novo_chat_limpo()
        
        _log("Enviando Prompt Mestre de Treinamento...")
        prompt_mestre_linear = " ".join(_TEMPLATE_TREINO_MESTRE.split())
        
        res_treino = self.enviar_prompt(prompt_mestre_linear, timeout=60, aguardar_resposta=True)
        if res_treino == 'ERRO_F5':
             _log("Aviso: Erro de F5 no treinamento. Pode impactar o fluxo final.")
        
        for arq in arquivos:
            caminho = Path(arq)
            if not caminho.exists():
                _log(f'Aviso: Arquivo de contexto não encontrado: {caminho.name}')
                continue
            self.anexar_arquivo_local(caminho)

        texto_referencia_dinamico = "Nenhuma referência extra fornecida."
        if arquivo_ref:
            extensao = str(arquivo_ref).lower()
            if extensao.endswith(('.mp4', '.mov', '.webm', '.avi')):
                texto_referencia_dinamico = "O vídeo com fala validada que deve ser usado como base."
            else:
                texto_referencia_dinamico = "Outra imagem com a descrição detalhada que deve ser usada para compor os detalhes das explicacoes do produto."

        prompt_execucao = _TEMPLATE_ROTEIRO_EXECUCAO.format(
            qtd_cenas=qtd_cenas,
            texto_referencia_dinamico=texto_referencia_dinamico
        )
        
        prompt_execucao_linear = " ".join(prompt_execucao.split())
        
        _log(f"Solicitando geração do roteiro em {qtd_cenas} cenas...")
        resposta = self.enviar_prompt(prompt_execucao_linear, timeout=90, aguardar_resposta=True)
        
        return resposta

    # =========================================================================
    # AVALIAÇÃO DE VARIANTES (DIRETOR DE ARTE) VIA SELENIUM WEB
    # =========================================================================
    def avaliar_melhor_variante_de_video(self, videos_720p: List[Path], roteiro: str) -> Path:
        """
        Sobe as variantes 720p na interface Web do Gemini e pede para escolher a melhor.
        """
        if not videos_720p:
            raise ValueError("Nenhum vídeo fornecido para avaliação.")
            
        if len(videos_720p) == 1:
            _log(f"Apenas uma variante detectada ({videos_720p[0].name}). Pulando júri.")
            return videos_720p[0]

        _log(f"Iniciando JÚRI DE DIREÇÃO DE ARTE para {len(videos_720p)} variantes (720p)...")
        self.abrir_novo_chat_limpo()
        
        for video in videos_720p:
            if video.exists():
                self.anexar_arquivo_local(video)

        prompt_juri = (
            f"Você é um Diretor de Arte sênior especialista em TikTok Ads. "
            f"Analise estes {len(videos_720p)} vídeos lado a lado que foram gerados "
            f"a partir do roteiro abaixo:\n\n"
            f"--- ROTEIRO ---\n{roteiro}\n----------------\n\n"
            f"Escolha qual variante possui a melhor fluidez, movimentos mais naturais "
            f"e menor distorção visual.\n"
            f"IMPORTANTE: Você deve responder APENAS com o NOME EXATO do arquivo vencedor. "
            f"Exemplo de resposta: video_candidato_final.mp4\n"
            f"Não escreva justificativas. Não use aspas ou marcações."
        )

        _log("Solicitando a decisão ao Gemini...")
        resposta_ia = self.enviar_prompt(prompt_juri, timeout=120, aguardar_resposta=True)

        if not resposta_ia or "TIMEOUT" in resposta_ia or "ERRO" in resposta_ia:
            _log(f"Aviso: O Gemini falhou em avaliar ({resposta_ia}). Assumindo a Variante 1.")
            return videos_720p[0]

        resposta_limpa = resposta_ia.strip().replace("`", "").replace('"', "").replace("'", "")
        _log(f"Resposta do Diretor de Arte: {resposta_limpa}")

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
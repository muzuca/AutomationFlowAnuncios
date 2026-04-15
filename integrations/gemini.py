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
• QUEBRA DE LINHA: Você DEVE inserir uma linha em branco (dar um ENTER duplo) após o final de cada cena e, OBRIGATORIAMENTE, antes de iniciar a tag [Legenda e Hashtags]. NUNCA cole a legenda na mesma linha do áudio.

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
ACTION SEQUENCE — Model keeps hands completely still, holding the items. Do NOT point or move arms. 2️⃣ Friendly wink and wide smile. 3️⃣ NO glitches.
Model voiceover says: "[Texto de 24-25 palavras com preço arredondado e CTA do carrinho]"
AUDIO — Brazilian Portuguese. Strong carioca accent, high energy, fast-paced.

[Legenda e Hashtags]
[Texto curto com 10 palavras, direto, SEM preços, SEM frete, SEM link. Use emojis.]
#hashtag1 #hashtag2 #tiktokshop

1. EXEMPLO DE CONTAGEM PARA VALIDAR (25 PALAVRAS):
"Esse kit maravilhoso sai por menos de cinquenta e um reais hoje no TikTok Shop então corre agora no carrinho pra garantir o seu antes que acabe!"

DIRETRIZ FINAL: 
Quando o usuário enviar arquivos, processe as informações e responda APENAS seguindo a estrutura visual acima. 
Assegure-se de que cada prompt e a legenda estejam escritos em texto puro, sem emojis na sequencia do chat. 
NUNCA invente movimentos de mãos se o modelo já estiver segurando algo na foto de referência.

Confirme brevemente que entendeu a função e aguarde o comando com os arquivos.
"""

_TEMPLATE_ROTEIRO_EXECUCAO = """Vamos gerar um novo roteiro para um anúncio de {qtd_cenas} cenas do produto que está sendo apresentado por uma vendedora mulher usando como referência os arquivos em anexo. 
Na fala devemos garantir o gancho na primeira cena, falar as qualidades e benefícios do produto no meio e fazer o cta no final. 

Estou enviando em anexo:
- A foto do produto sendo apresentado em estilo POV (apenas duas mãos segurando o produto)
- Uma imagem com o nome do produto e o preço
- {texto_referencia_dinamico}

Extraia o nome do produto, o preço e os detalhes diretamente da leitura/transcrição das imagens/vídeo.

DIRETRIZES POV (NÃO NEGOCIÁVEIS):
Como a filmagem é em POV (Point of View), os prompts técnicos DEVEM refletir isso. 
Especifique claramente nos prompts que a câmera é POV e mostre apenas as mãos. 
É ESTRITAMENTE PROIBIDO gerar rostos, cabeças, corpos inteiros, pessoas ao fundo ou qualquer elemento que não esteja na imagem de referência POV, deixe isso claro em cada cena. 
Foque apenas em movimentos sutis de respiração ou da própria luz/cenário, mantendo as mãos 100% estáticas.
Deixe claro em cada cena que a voz é de uma mulher.

{instrucoes_teste_ab}

Siga ESTRITAMENTE o Protocolo de Saída definido no seu treinamento em texto puro corrido, usando as tags [Cena 1: ...], [Cena 2: ...], etc.
Lembre-se da regra de ouro: Câmera 100% estática, mãos completamente imóveis (anti-glitch), preço arredondado para cima, exatas 24-25 palavras por cena.
Responda APENAS com as {qtd_cenas} cenas estruturadas, com a legenda separada de forma clara por um parágrafo no final, sem nenhuma introdução antes, apenas as cenas e a legenda+hashtags.
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

    def _extrair_texto_resposta_recente(self) -> str:
        """Extrai o texto da última resposta da IA de forma direta e simplificada."""
        seletores = ['model-response', 'message-content', '.model-response-text']
        
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                if not elementos: continue
                
                el = elementos[-1]
                txt_bruto = self.driver.execute_script("return arguments[0].textContent;", el)
                txt = self._texto_limpo(txt_bruto or '').strip()
                
                # FILTRO SIMPLIFICADO EM LINHA: Ignora apenas se for vazio ou lixo de interface/carregamento
                if not txt or any(lixo in txt for lixo in ["Show thinking", "Gemini said", "Carregando"]):
                    continue
                
                return txt
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

    def _aguardar_fim_analise(self, timeout: int = 120) -> bool:
        """Aguarda o Gemini terminar monitorando o estado dos botões da UI em tempo real"""
        _log('Gemini processando... rastreando botões (modo inteligente).')
        fim = time.time() + timeout
        
        # Pausa minúscula (0.5s) só para o navegador registrar o clique de enviar e virar o botão pra Stop
        time.sleep(0.5) 
        
        # XPaths mapeados exatamente a partir da DOM do Gemini
        xpath_stop = "//button[@aria-label='Stop response' or contains(@class, 'stop')]"
        xpath_idle = "//button[@aria-label='Microphone' or @aria-label='Send message' or @data-node-type='speech_dictation_mic_button']"
        
        while time.time() < fim:
            try:
                # 1. Verifica se o botão "Stop response" está na tela (IA gerando)
                stop_btns = self.driver.find_elements(By.XPATH, xpath_stop)
                is_stopping = any(b.is_displayed() for b in stop_btns)
                
                if not is_stopping:
                    # 2. Se o Stop não está lá, verifica se Mic ou Send voltaram a ficar ativos
                    idle_btns = self.driver.find_elements(By.XPATH, xpath_idle)
                    is_idle = any(b.is_displayed() and b.is_enabled() for b in idle_btns)
                    
                    if is_idle:
                        # Extra-check: garante que não sobrou nenhum loader de 'generating' solto
                        if not self._gemini_esta_processando():
                            return True
                            
            except StaleElementReferenceException:
                pass # A DOM atualizou neste milissegundo. Ignora e tenta no próximo ciclo.
            except Exception:
                pass
                
            # Polling rápido: checa a tela 5 vezes por segundo. Zero esperas cegas.
            time.sleep(0.2) 
            
        _log(f'Aviso: Timeout de {timeout}s atingido aguardando botões do Gemini.')
        return False

    def _aguardar_resposta_textual(self, timeout: int = 40) -> str:
        """Aguarda a IA terminar de responder e retorna o texto capturado, sem interceptações."""
        finalizou = self._aguardar_fim_analise(timeout=timeout)
        
        if not finalizou:
            _log('⚠️ Timeout na UI. Forçando F5 Recovery...')
            self.driver.refresh()
            self.wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
            self._scroll_chat_ate_fim()
            
            for _ in range(10):
                self._scroll_chat_ate_fim()
                texto = self._extrair_texto_resposta_recente()
                if texto:
                    _log('F5 Recovery com sucesso. Resposta capturada.')
                    return texto
                time.sleep(0.5)
            
            return 'TIMEOUT_ANALISE'
        
        # Pega a resposta imediatamente após o Gemini sinalizar que terminou (botão submit voltou)
        fim = time.time() + 2.5
        ultima = ''
        while time.time() < fim:
            try:
                self._scroll_chat_ate_fim()
                texto = self._extrair_texto_resposta_recente()
                if texto:
                    # AQUI ESTAVA O SEU ERRO ANTIGO: O código tentava forçar o texto a virar SIM/NÃO.
                    # Agora ele apenas pega o texto 100% puro e devolve. A função que chamou que lute pra interpretar.
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
        """
        Conta as imagens geradas de forma instantânea via JavaScript.
        Isso elimina o gargalo de ~20 segundos do Implicit Wait do Selenium
        ao procurar elementos que ainda não existem na tela.
        """
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
                // Ignora fotos de perfil, avatares ou logos
                const src = (el.src || '').toLowerCase();
                if (src.includes('profile/picture') || src.includes('avatar') || src.includes('logo')) {
                    return;
                }
                
                // O elemento precisa ter alguma dimensão para ser considerado visível
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
            # Caso o JS falhe por algum motivo muito estranho, retorna 0 instantaneamente
            return 0

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
            'A imagem não deve conter textos ou preços do produto. '
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

        # PROMPT DE CORREÇÃO GENÉRICO: Para ser usado se a imagem reprovar
        prompt_correcao_fidelidade = (
            "A imagem que você gerou REPROVOU no controle de qualidade. A geometria, o design ou os detalhes "
            "do produto estão diferentes da imagem de referência original. Isso é inaceitável para o anúncio.\n\n"
            "Gere uma NOVA versão agora. Instruções cruciais:\n"
            "1. Olhe atentamente para a forma e proporções do produto na PRIMEIRA imagem que te enviei.\n"
            "2. O produto na nova imagem deve ser uma CÓPIA IDÊNTICA em termos de design e estrutura.\n"
            "3. Mantenha as mãos em POV, mas não deixe a IA alucinar no formato do objeto."
        )

        for tentativa in range(1, max_tentativas + 1):
            self._scroll_chat_ate_fim()
            _log(f'Fluxo POV iniciado (tentativa {tentativa}/{max_tentativas}).')

            caminho_saida.parent.mkdir(parents=True, exist_ok=True)
            
            if tentativa == 1:
                _log('Aproveitando contexto do chat atual (imagem já anexada na Etapa 10).')
            else:
                _log('Enviando instrução de correção de fidelidade visual no chat de geração...')
                # Voltamos para o chat onde a imagem foi gerada para enviar a bronca
                self.driver.back()
                time.sleep(2)

            prompt_geracao = (
                # Começamos com uma instrução de referência absoluta para forma e detalhes
                'Usando a imagem do produto anexada como referência absoluta e imutável de forma, textura e detalhes, '
                'gere uma nova imagem ultra-realista vertical 9:16 para anúncio. '
                
                # POV detalhado
                'A cena deve estar em POV (ponto de vista em primeira pessoa), simulando a visão direta do usuário. '
                
                # Bloco dinâmico e restritivo das mãos: define quantidade estrita de "apenas duas"
                f'Mostre exatamente e estritamente apenas duas mãos humanas de {getattr(tarefa, "characteristics_model", getattr(tarefa, "caracteristicas_modelo", "uma modelo"))}, '
                
                # Pose genérica mas funcional: força segurar pelas bordas para manter anatomia lógica
                'em uma pose de pinça ou segurando pelas bordas ou outra posição coerente que interaja naturalmente com o produto em primeiro plano. '
                
                # Restrição de fidelidade do produto: elimina "deformações" e foca em "geometria" e "design"
                'O produto deve ser uma réplica exata e idêntica do item original, central, em foco nítido e sem qualquer alteração em sua geometria ou design. '
                
                # Estilo e iluminação suaves
                'Estilo lifestyle premium, com iluminação natural de estúdio suave e o fundo deve ser um cenário coerente e realista. '
                
                # Instrução de Bokeh para evitar conflito com o produto
                'Mantenha o fundo em desfoque suave (bokeh) para não competir com o foco principal. '
                
                # Lista negativa reforçada
                'Nao adicione textos, colagens, molduras, elementos de interface, mãos, dedos ou quaisquer objetos extras. '
                
                # Conclusão obrigatória
                'ATENÇÃO: Responda gerando apenas a imagem, SEM TEXTO!'
            )

            # Define qual prompt vai ser enviado (geração normal na 1ª vez, bronca nas seguintes)
            prompt_envio = prompt_geracao if tentativa == 1 else prompt_correcao_fidelidade

            total_imagens_antes = self.contar_imagens_geradas()
            status_envio = self.enviar_prompt(prompt_envio, aguardar_resposta=False)

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
            _log('Validando a similaridade (>80%) do produto na imagem POV gerada...')
            self.abrir_novo_chat_limpo()
            
            # Anexa as duas imagens para o comparativo
            if foto_produto_escolhida and foto_produto_escolhida.exists():
                self.anexar_arquivo_local(foto_produto_escolhida)
            self.anexar_arquivo_local(caminho_saida)

            regerar_imagem = False
            for tentativa_val in range(1, 4):
                self._scroll_chat_ate_fim()
                
                # JÚRI DE SIMILARIDADE: Sem loop de reavaliação de notas baixas
                prompt_validacao = (
                    "Você é um inspetor de Controle de Qualidade visual hiper-rigoroso. "
                    "Eu acabei de enviar DUAS IMAGENS nesta exata ordem: "
                    "1) A primeira imagem é o PRODUTO ORIGINAL (referência absoluta). "
                    "2) A segunda imagem é a NOVA GERAÇÃO (a que tem as mãos em POV). "
                    "Compare estritamente o design, a forma geométrica e a estrutura do produto nas duas imagens.\n"
                    "Ignore o fundo, as mãos e a iluminação. Foque apenas no OBJETO.\n"
                    "Responda EXCLUSIVAMENTE com a porcentagem de igualdade estrutural (ex: 85%) e nada mais."
                )

                veredito = self.enviar_prompt(prompt_validacao, timeout=60, aguardar_resposta=True).strip().upper()
                
                if not veredito or veredito in {'ENVIADO', 'TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5'}:
                    veredito = self._aguardar_resposta_textual(timeout=60).strip().upper()

                # Lógica de extração da porcentagem
                import re
                match_perc = re.search(r'(\d{1,3})\s*%', veredito)
                
                if match_perc:
                    porcentagem = int(match_perc.group(1))
                    if porcentagem >= 80:
                        _log(f'✅ Imagem POV aprovada ({porcentagem}% de similaridade estrutural).')
                        return caminho_saida
                    else:
                        # Se deu nota baixa, NÃO PERDE TEMPO REAVALIANDO. Já manda regerar a imagem.
                        _log(f'❌ Imagem POV reprovada ({porcentagem}% de similaridade). Repetindo fluxo de geração...')
                        regerar_imagem = True
                        break 
                else:
                    # Fallback caso ele teime em não dar número na primeira tentativa da validação
                    if tentativa_val == 1:
                        _log(f'⚠️ Recebi veredito sem %. Pedindo reavaliação no chat de juri...')
                        prompt_reaval = "Você não respondeu com a porcentagem. Qual o grau de similaridade (ex: 85%)?"
                        self.enviar_prompt(prompt_reaval, aguardar_resposta=False)
                        continue
                    else:
                        _log(f'❌ Falha na extração de nota do juri: {veredito[:60]}')
                        regerar_imagem = True
                        break

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
        qtd_cenas: int = 3,
        roteiros_anteriores: Optional[List[str]] = None
    ) -> str:
        """
        Gera um roteiro com base nas imagens. Se roteiros_anteriores forem fornecidos (Teste A/B), 
        injeta uma instrução rigorosa para que a IA crie abordagens inéditas, evitando repetição.
        """
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

        # LÓGICA DE TESTE A/B (VARIAÇÃO DE ROTEIROS)
        instrucoes_teste_ab = ""
        if roteiros_anteriores:
            _log(f"Injetando {len(roteiros_anteriores)} roteiro(s) anterior(es) para forçar variação no Teste A/B...")
            textos_anteriores = "\n\n".join([f"--- ROTEIRO ANTERIOR ---\n{r}\n------------------------" for r in roteiros_anteriores])
            instrucoes_teste_ab = (
                "\n\nATENÇÃO MÁXIMA (TESTE A/B): Eu já criei os roteiros abaixo para este produto. "
                "Sua tarefa agora é criar um roteiro 100% INÉDITO e DIFERENTE. "
                "Mude completamente o ângulo de venda, utilize um gancho inicial radicalmente diferente na Cena 1, "
                "e destaque benefícios que não foram o foco principal na versão anterior. "
                "Aja como um copywriter criativo testando uma nova hipótese de venda para um público diferente.\n\n"
                f"{textos_anteriores}\n\n"
                "LEMBRE-SE: Apesar do texto e da abordagem mudarem completamente, você DEVE manter as regras "
                "técnicas de 24-25 palavras, câmera estática, formato POV e arredondamento de preço."
            )

        prompt_execucao = _TEMPLATE_ROTEIRO_EXECUCAO.format(
            qtd_cenas=qtd_cenas,
            texto_referencia_dinamico=texto_referencia_dinamico,
            instrucoes_teste_ab=instrucoes_teste_ab
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
    
    def classificar_arquivos_e_extrair_dados(self, arquivos: list[Path]) -> dict | None:
        """Faz o upload dos arquivos brutos, pede para a IA classificar quem é quem e extrair os textos de venda."""
        self.abrir_novo_chat_limpo()
        
        nomes_arquivos = []
        for arq in arquivos:
            self.anexar_arquivo_local(arq)
            nomes_arquivos.append(arq.name)
            
        _log(f'Solicitando classificação visual e OCR para: {", ".join(nomes_arquivos)}')

        prompt = f"""
        Eu fiz o upload dos seguintes arquivos nesta exata ordem: {', '.join(nomes_arquivos)}.
        Eu preciso que você aja como um organizador de arquivos e extrator de dados.
        
        Analise o conteúdo visual de cada arquivo e faça o mapeamento:
        1. "arquivo_produto": O nome exato do arquivo que mostra APENAS a foto limpa do produto (ideal para recorte).
        2. "arquivo_preco": O nome exato do arquivo que contém o PREÇO, condições ou nome do produto em texto.
        3. "arquivo_referencia": O nome exato do arquivo restante (pode ser vídeo ou foto).

        Além disso, leia os textos presentes na imagem de PREÇO e extraia os dados REAIS de venda:
        - "nome_produto": Nome real do produto lido.
        - "preco_condicoes": Valor do produto e regras de pagamento/parcelamento que você conseguir ler.
        - "beneficios": Breve resumo de qualquer benefício ou slogan escrito.

        Retorne EXCLUSIVAMENTE um objeto JSON válido, sem markdown (sem ```json), com estas exatas 6 chaves em minúsculo. Não escreva mais nenhuma palavra.
        """

        resposta = self.enviar_prompt(prompt, timeout=120, aguardar_resposta=True)
        if not resposta or resposta in {'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL', 'ERRO_F5'}:
            resposta = self._aguardar_resposta_textual(timeout=60)

        import json
        import re
        # Tenta caçar o JSON na resposta bruta
        match = re.search(r'\{.*\}', resposta, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception as e:
                _log(f'Erro ao converter JSON da IA: {e}\nResposta Bruta: {resposta}')
                
        return None
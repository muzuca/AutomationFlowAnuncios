# arquivo: integrations/gemini.py
# descricao: fachada GeminiAnunciosViaFlow para validacao de imagem de produto,
# com contrato compativel com o fluxo atual e upload sem deixar o popup nativo aberto.
# Mantem o fluxo funcional atual e otimiza apenas as validacoes/esperas.
from __future__ import annotations

import re
import time
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


def _log(msg: str) -> None:
    ts = time.strftime('%H:%M:%S')
    print(f'[{ts}] [GEMINI-IA] {msg}')


class GeminiAnunciosViaFlow:
    def __init__(self, driver: Any, timeout: int = 30):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)
        self.wait_curta = WebDriverWait(driver, 5, poll_frequency=0.10)
        self.timeout = timeout
        self._auto_scroll_enabled = True
        self._last_scroll_tick = 0.0

    def abrir_gemini(self) -> None:
        _log('Stub ativo: abrir_gemini() preparado para integracao posterior.')

    def abrir_novo_chat_limpo(self) -> None:
        _log('Stub ativo: abrir_novo_chat_limpo() preparado para integracao posterior.')

    def _js_click(self, element: WebElement) -> None:
        self.driver.execute_script('arguments[0].click();', element)

    def _scroll_chat_ate_fim(self) -> None:
        if not self._auto_scroll_enabled:
            return

        agora = time.time()
        if agora - self._last_scroll_tick < 0.08:
            return
        self._last_scroll_tick = agora

        try:
            self.driver.execute_script(
                """
                const candidates = [
                'div#chat-history.chat-history-scroll-container',
                '#chat-history',
                'infinite-scroller[data-test-id="chat-history-container"]',
                '[data-test-id="chat-history-container"]'
                ];

                let host = null;
                for (const sel of candidates) {
                const el = document.querySelector(sel);
                if (el) {
                    host = el;
                    break;
                }
                }

                if (!host) {
                return;
                }

                const target = host.querySelector('.restart-chat-button-scroll-placeholder')
                            || host.querySelector('model-response:last-of-type')
                            || host.querySelector('.response-footer:last-of-type')
                            || host.lastElementChild
                            || host;

                try {
                target.scrollIntoView({ block: 'end', inline: 'nearest' });
                } catch (e) {}

                host.scrollTop = host.scrollHeight;

                const parent = host.parentElement;
                if (parent && parent.scrollHeight > parent.clientHeight) {
                parent.scrollTop = parent.scrollHeight;
                }
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
                        _log(f'Popup tardio do Chrome tratado dentro do Gemini: {texto}')
                        time.sleep(0.25)
                        return
            except Exception:
                pass

    def _encontrar_input_file_visivel_ou_oculto(self) -> WebElement:
        seletores = ['input[type="file"]', 'input[type="file"][multiple]', 'input[accept*="image"]']
        ultimo_erro = None
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    if el is not None:
                        return el
            except Exception as e:
                ultimo_erro = e
        if ultimo_erro:
            raise ultimo_erro
        raise TimeoutException('Nenhum input[type=file] encontrado no DOM.')

    def _obter_textarea_prompt(self) -> WebElement:
        seletores = [
            'div[contenteditable="true"][role="textbox"][data-placeholder*="Enter a prompt"]',
            '.initial-input-area-container textarea',
            'textarea[placeholder="Ask Gemini"]',
            'textarea',
        ]
        ultimo_erro = None
        for seletor in seletores:
            try:
                return self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, seletor)))
            except Exception as e:
                ultimo_erro = e
        if ultimo_erro:
            raise ultimo_erro
        raise TimeoutException('Campo de prompt do Gemini nao encontrado.')

    def _obter_botao_enviar(self) -> Optional[WebElement]:
        seletores = ['button[aria-label="Send message"]', '.send-button-container button', '.initial-input-area-container .send-icon']
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    try:
                        if not el.is_displayed():
                            continue
                        aria_disabled = (el.get_attribute('aria-disabled') or '').strip().lower()
                        disabled = el.get_attribute('disabled')
                        classes = (el.get_attribute('class') or '').lower()
                        if aria_disabled == 'false':
                            return el
                        if disabled is None and 'send-icon' in classes:
                            return el
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    def _aguardar_upload_estabilizar(self, timeout: int = 12) -> None:
        fim = time.time() + timeout
        while time.time() < fim:
            try:
                self._scroll_chat_ate_fim()
                btn = self._obter_botao_enviar()
                if btn is not None:
                    _log('Botao de envio habilitado apos upload.')
                    return
                textareas = self.driver.find_elements(By.CSS_SELECTOR, '.initial-input-area-container textarea, textarea')
                for ta in textareas:
                    try:
                        if ta.is_displayed() and ta.is_enabled():
                            _log('Textarea pronta apos upload.')
                            return
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(0.10)
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
        seletores = [
            'processing-state .processing-state_container--processing',
            '.processing-state_container--processing',
            'bard-avatar .thinking',
            '.bard-avatar.thinking',
            '.avatar-gutter .thinking',
            '.extension-processing-state',
        ]
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    try:
                        if el.is_displayed():
                            return True
                    except StaleElementReferenceException:
                        return True
                    except Exception:
                        pass
            except Exception:
                pass
        return False

    def _extrair_resposta_binaria_direta(self) -> Optional[bool]:
        seletores = [
            'message-content .markdown p',
            'message-content .markdown li',
            'message-content .markdown span',
            'message-content .markdown',
            'structured-content-container.model-response-text message-content p',
            'structured-content-container.model-response-text message-content span',
            'structured-content-container.model-response-text .markdown p',
            'structured-content-container.model-response-text .markdown',
            '.response-content message-content p',
            '.response-content .markdown p',
        ]
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    try:
                        if not el.is_displayed():
                            continue
                        candidatos = [
                            self._texto_limpo(el.text or ''),
                            self._texto_limpo(el.get_attribute('textContent') or ''),
                            self._texto_limpo(el.get_attribute('innerText') or ''),
                        ]
                        for txt in candidatos:
                            if not txt:
                                continue
                            up = txt.upper()
                            if self._parece_texto_inutil_ui(up):
                                continue
                            if up == 'SIM' or re.fullmatch(r'SIM[\.! ]*', up):
                                return True
                            if up == 'NAO' or up == 'NÃO' or re.fullmatch(r'(NAO|NÃO)[\.! ]*', up):
                                return False
                    except Exception:
                        pass
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
            'message-content .markdown',
            'structured-content-container.model-response-text .markdown',
            '.response-content .markdown',
            '.model-response-text',
            'message-content',
        ]
        textos: List[str] = []
        for seletor in seletores:
            try:
                elementos = self.driver.find_elements(By.CSS_SELECTOR, seletor)
                for el in elementos:
                    try:
                        if not el.is_displayed():
                            continue
                        txt = self._texto_limpo(el.get_attribute('textContent') or el.text or '')
                        if not txt or self._parece_texto_inutil_ui(txt):
                            continue
                        textos.append(txt)
                    except Exception:
                        pass
            except Exception:
                pass
        if not textos:
            return ''
        return textos[-1].strip().upper()

    def _interpretar_resposta_binaria(self, texto: str) -> Optional[bool]:
        if not texto:
            return None
        texto = self._texto_limpo(texto).upper()
        if re.search(r'(^|\n)\s*SIM\s*($|\n)', texto):
            return True
        if re.search(r'(^|\n)\s*NAO\s*($|\n)', texto) or re.search(r'(^|\n)\s*NÃO\s*($|\n)', texto):
            return False
        if texto.startswith('SIM'):
            return True
        if texto.startswith('NAO') or texto.startswith('NÃO'):
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
                        _log('Gemini esta analisando a imagem... aguardando conclusao.')
                    viu_processando = True
                    time.sleep(0.10)
                    continue
                if viu_processando:
                    for _ in range(10):
                        self._scroll_chat_ate_fim()
                        binaria = self._extrair_resposta_binaria_direta()
                        if binaria is not None:
                            return True
                        time.sleep(0.10)
                    return True
                texto = self._extrair_texto_resposta_recente()
                if texto and self._interpretar_resposta_binaria(texto) is not None:
                    return True
            except Exception:
                pass
            time.sleep(0.10)
        return False

    def _aguardar_resposta_textual(self, timeout: int = 40) -> str:
        finalizou = self._aguardar_fim_analise(timeout=timeout)
        if not finalizou:
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
            except Exception:
                pass
            time.sleep(0.10)
        return ultima or 'SEM_RESPOSTA_UTIL'

    def anexar_arquivo_local(self, caminho: Path) -> None:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f'Arquivo nao encontrado: {caminho}')
        _log(f'Anexando arquivo: {caminho.name}')
        try:
            botao_mais = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label="Open upload file menu"]'))
            )
            self._js_click(botao_mais)
            _log('Botao + clicado')
            time.sleep(0.20)
            upload_files = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-test-id="local-images-files-uploader-button"]'))
            )
            self._js_click(upload_files)
            _log('Upload files clicado')
            time.sleep(0.15)
            input_file = self._encontrar_input_file_visivel_ou_oculto()
            self.driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible'; arguments[0].style.opacity=1;",
                input_file,
            )
            input_file.send_keys(str(caminho.resolve()))
            _log(f'Arquivo {caminho.name} enviado para upload')
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.10)
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            _log('ESC enviado para fechar qualquer popup residual')
            self._aguardar_upload_estabilizar(timeout=12)
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
        _log(f'Enviando prompt ({len(prompt)} chars)')
        try:
            textarea = self._obter_textarea_prompt()
            textarea.click()
            try:
                textarea.clear()
            except Exception:
                pass
            textarea.send_keys(prompt)
            _log('Prompt digitado')
            self._scroll_chat_ate_fim()
            self.wait.until(lambda d: self._obter_botao_enviar() is not None)
            botao_submit = self._obter_botao_enviar()
            if botao_submit is None:
                raise TimeoutException('Botao de envio nao ficou disponivel.')
            self._js_click(botao_submit)
            _log('Prompt submetido')
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
        _log('Stub ativo: contar_imagens_geradas() retornando 0.')
        return 0

    def aguardar_nova_imagem(self, total_antes: int, timeout: int = 180) -> bool:
        _log('Stub ativo: aguardar_nova_imagem() chamado ' f'(total_antes={total_antes}, timeout={timeout}).')
        return False

    def baixar_ultima_imagem(self, destino: Path) -> bool:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        _log(f'Stub ativo: baixar_ultima_imagem() preparado para salvar em {destino}.')
        return False

    def gerar_roteiro_especifico(self, modelo: str, estilo: str, id_pasta: str) -> Dict[str, str]:
        _log('Stub ativo: gerar_roteiro_especifico() chamado ' f'para modelo={modelo}, estilo={estilo}, id_pasta={id_pasta}.')
        return {'cena_1': '', 'cena_2': '', 'cena_3': ''}

    def _listar_candidatos_produto(self, tarefa: Any) -> List[Path]:
        arquivos = getattr(tarefa, 'arquivos', []) or []
        candidatos = [Path(arq) for arq in arquivos if Path(arq).suffix.lower() in EXTENSOES_IMAGEM]
        if candidatos:
            _log('Candidatos a foto do produto: ' + ', '.join(arq.name for arq in candidatos))
        else:
            _log('Nenhum candidato de imagem encontrado.')
        return candidatos

    def _validar_imagem_produto(
        self,
        caminho_imagem: Path,
        timeout_resposta: int = 40,
        max_reenvios_prompt: int = 1,
    ) -> bool:
        caminho_imagem = Path(caminho_imagem)
        _log(f'Validando candidato a produto com Gemini: {caminho_imagem.name}')
        self.anexar_arquivo_local(caminho_imagem)
        prompt_validacao_produto = (
            'A imagem anexada contem um produto fisico claramente visivel e identificavel? '
            'Nao importa se ha textos, preco, interface de loja ou elementos promocionais. '
            "Se o produto estiver claramente visivel, responda APENAS com 'SIM'. "
            "Se nao houver produto visivel ou ele nao puder ser identificado, responda APENAS com 'NAO'."
        )
        resposta = ''
        for tentativa in range(1, max_reenvios_prompt + 2):
            if tentativa > 1:
                _log(f'Reenviando o mesmo prompt da imagem {caminho_imagem.name} (tentativa {tentativa}/{max_reenvios_prompt + 1})')
            resposta = self.enviar_prompt(prompt_validacao_produto, timeout=timeout_resposta).strip().upper()
            _log(f'Resposta da validacao de produto para {caminho_imagem.name}: {resposta}')
            if resposta in ('TIMEOUT', 'TIMEOUT_ANALISE', 'SEM_RESPOSTA_UTIL'):
                if tentativa <= max_reenvios_prompt:
                    _log('Timeout na analise; o prompt sera reenviado sem anexar novamente a imagem.')
                    try:
                        self.abrir_novo_chat_limpo()
                    except Exception:
                        pass
                    time.sleep(0.8)
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
            except Exception as e:
                _log(f'Erro ao validar candidato {candidato.name}: {e}')
        _log('Nenhum candidato foi aprovado como foto principal do produto.')
        return None

    def _tentar_baixar_pov(self, destino: Path, tentativas: int = 3) -> bool:
        for tentativa in range(1, tentativas + 1):
            _log(f'Tentando baixar imagem POV (tentativa {tentativa}/{tentativas})...')
            ok = self.baixar_ultima_imagem(destino)
            if ok:
                return True
            time.sleep(1)
        return False

    def executar_fluxo_imagem_pov(
        self,
        tarefa: Any,
        max_tentativas: int = 3,
    ) -> Optional[Path]:
        dir_anuncio = Path(getattr(tarefa, 'dir_anuncio', '.'))
        caminho_saida = dir_anuncio / 'POV_VALIDADO.png'
        foto_produto_escolhida = self._selecionar_foto_produto(tarefa)
        if not foto_produto_escolhida:
            _log('Nao foi possivel identificar a foto correta do produto.')
            return None
        for tentativa in range(1, max_tentativas + 1):
            _log(
                'Fluxo POV iniciado para '
                f'{getattr(tarefa, "modelo_nome", "Modelo")} '
                f'usando {foto_produto_escolhida.name} '
                f'(tentativa {tentativa}/{max_tentativas}).'
            )
            caminho_saida.parent.mkdir(parents=True, exist_ok=True)
            if self._tentar_baixar_pov(caminho_saida, tentativas=1):
                _log(f'Imagem POV disponivel em: {caminho_saida.name}')
                return caminho_saida
        _log('Nao foi possivel concluir o fluxo POV nesta implementacao.')
        return None

    def treinar_e_gerar_roteiro(
        self,
        imagens: List[Path],
        dados_produto: Dict,
    ) -> Dict[str, str]:
        modelo = dados_produto.get('modelo', 'Modelo')
        estilo = dados_produto.get('estilo', 'POV')
        id_pasta = dados_produto.get('nome', '1')
        for img in imagens:
            caminho = Path(img)
            if not caminho.exists():
                raise FileNotFoundError(f'Imagem nao encontrada para roteiro: {caminho}')
            _log(f'Imagem validada para roteiro: {caminho.name}')
        return self.gerar_roteiro_especifico(modelo, estilo, id_pasta)
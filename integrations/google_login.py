# arquivo: integrations/google_login.py
# descricao: executa o login no Google com uma conta HUMBLE, valida a navegação por estado da página e abre o Gemini somente depois que a autenticação concluir com sucesso.
from __future__ import annotations

import msvcrt
import re
import sys
import time
import os
from selenium.webdriver.common.keys import Keys
from pathlib import Path
from integrations.browser import create_driver, close_driver

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import GoogleAccount, Settings
from integrations.waits import wait_for_clickable, wait_for_visible
# Central de utilitários
from integrations.utils import _get_logs_dir, _log, salvar_print_debug


def login_google(driver: WebDriver, settings: Settings, account: GoogleAccount) -> None:
    try:
        _log(f"Iniciando login para a conta: {account.email}", "LOGIN")
        driver.get(settings.google_login_url)
        time.sleep(2)
        salvar_print_debug(driver, "login_01_tela_inicial")

        # --- ETAPA 1: E-MAIL ---
        email_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="email"]', timeout=30)
        email_input.clear()
        email_input.send_keys(account.email)
        
        salvar_print_debug(driver, "login_02_email_preenchido")

        next_button = wait_for_clickable(driver, By.ID, 'identifierNext', timeout=20)
        next_button.click()
        
        # Pausa para transição de tela
        time.sleep(3)
        salvar_print_debug(driver, "login_03_pos_email_next")

       # =========================================================
        # 🚨 RESGATE DE CAPTCHA AUTOMATIZADO (IA AUXILIAR COM RETRY)
        # =========================================================
        img_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
        captcha_visivel = any(img.is_displayed() for img in img_captcha) if img_captcha else False
        
        if captcha_visivel:
            _log("⚠️ CAPTCHA DETECTADO! Acionando IA Auxiliar de Acessibilidade...", "LOGIN")
            
            # Instanciamos o driver do assistente FORA do loop para manter a sessão aberta nas retentativas
            personal_driver = None
            tentativas_captcha = 0
            max_tentativas = 3
            codigo_sugerido = ""

            while tentativas_captcha < max_tentativas:
                tentativas_captcha += 1
                _log(f"Iniciando tentativa {tentativas_captcha}/{max_tentativas} de resolver CAPTCHA...", "LOGIN")

                # 1. Captura o print do desafio (Sempre atualiza o print se houver erro)
                img_path = _get_logs_dir() / "CAPTCHA_SEGURO.png"
                try:
                    # Tenta pegar o elemento exato
                    img_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
                    img_captcha[0].screenshot(str(img_path))
                    time.sleep(1.5)
                except Exception:
                    driver.save_screenshot(str(img_path))
                    time.sleep(1.5)
                
                # 2. IA Auxiliar - MÉTODO INTEGRADO COM GEMINIFLOW (HEADLESS)
                try:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options
                    from selenium.webdriver.chrome.service import Service
                    from webdriver_manager.chrome import ChromeDriverManager
                    from integrations.gemini import GeminiAnunciosViaFlow

                    # Só cria o navegador do assistente se ele ainda não existir
                    if personal_driver is None:
                        options = Options()
                        options.add_argument("--remote-debugging-port=9225")
                        options.add_argument("--headless=new") 
                        
                        perfil_dir = _get_logs_dir() / "perfil_pessoal_assistente"
                        perfil_dir.mkdir(parents=True, exist_ok=True)
                        options.add_argument(f"--user-data-dir={perfil_dir}")
                        options.add_experimental_option("excludeSwitches", ["enable-automation"])
                        options.add_experimental_option('useAutomationExtension', False)
                        
                        service = Service(ChromeDriverManager().install())
                        personal_driver = webdriver.Chrome(service=service, options=options)
                    
                    # Uso das funções do seu GEMINI.PY
                    url_gemini = os.getenv("PERSONAL_CHAT_LINK", "https://gemini.google.com/app")
                    ai_assist = GeminiAnunciosViaFlow(personal_driver, url_gemini=url_gemini)
                    
                    # Se não estiver no Gemini, abre. Se já estiver, só anexa no mesmo chat.
                    if "gemini.google.com" not in personal_driver.current_url:
                        ai_assist.abrir_gemini()
                    
                    ai_assist.anexar_arquivo_local(img_path)
                    
                    prompt_bot = f"Este é um novo desafio (tentativa {tentativas_captcha}). Retorne apenas as letras e números desta imagem, sem explicações."
                    resposta = ai_assist.enviar_prompt(prompt_bot, timeout=40)
                    
                    if resposta and resposta not in ['RECOVERY_TRIGGERED', 'TIMEOUT', 'SEM_RESPOSTA_UTIL']:
                        codigo_sugerido = re.sub(r'[^a-zA-Z0-9]', '', resposta.lower()).strip()
                        _log(f"🧠 IA Sugeriu (via GeminiFlow): '{codigo_sugerido}'", "LOGIN")

                except Exception as e:
                    _log(f"❌ Falha na precisão da IA Auxiliar: {str(e)[:60]}", "LOGIN")
                
                # 4. Injeção Automática e Validação de Re-tentativa
                sys.stdout.write('\a') # Beep
                
                # Na primeira tentativa do código atual, tenta o automático da IA
                tentar_automatico = True if codigo_sugerido else False
                
                if tentar_automatico:
                    _log(f"🤖 Tentando preenchimento automático: '{codigo_sugerido}'", "LOGIN")
                    codigo_final = codigo_sugerido
                else:
                    # Fallback manual se a IA falhar ou for a segunda tentativa do mesmo código
                    try: os.startfile(str(img_path))
                    except: pass
                    
                    msg = f"\n👉 [URGENTE] DIGITE O CAPTCHA ({account.email}). Tentativa {tentativas_captcha}/{max_tentativas}\nIA Sugeriu: '{codigo_sugerido}' \n[ENTER para confirmar ou digite o correto]: "
                    codigo_final = input_com_timeout(msg, timeout=40)
                    if not codigo_final:
                        codigo_final = codigo_sugerido
                
                if codigo_final:
                    _log(f"Injetando: '{codigo_final}'...", "LOGIN")
                    xpath_ca = "//input[@name='ca'] | //input[@id='ca'] | //input[contains(@aria-label, 'letras')] | //input[@type='text' and @maxlength='6']"
                    
                    try:
                        ca_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath_ca)))
                        ca_input.clear()
                        ca_input.send_keys(codigo_final)
                        ca_input.send_keys(Keys.ENTER)
                        time.sleep(5)
                        
                        # Verifica se o CAPTCHA continua na tela (Google rejeitou)
                        novo_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
                        captcha_ainda_visivel = any(img.is_displayed() for img in novo_captcha) if novo_captcha else False

                        if captcha_ainda_visivel:
                            _log(f"❌ Código '{codigo_final}' incorreto! O Google gerou um novo CAPTCHA.", "LOGIN")
                            codigo_sugerido = "" # Limpa para a IA tentar ler o novo print
                            continue # Volta para o topo do While para tirar novo print e perguntar à IA
                        else:
                            _log("✅ CAPTCHA superado com sucesso!", "LOGIN")
                            break # Sai do While de tentativas e segue para a senha
                            
                    except Exception as e:
                        _log(f"Erro ao interagir com campo de CAPTCHA: {e}", "LOGIN")
                        break
                else:
                    # Se não houver código final (timeout/vazio) e for a última tentativa, explode erro
                    if tentativas_captcha >= max_tentativas:
                        if personal_driver: personal_driver.quit()
                        raise Exception("Falha no CAPTCHA: Sem resposta da IA e do Usuário após 3 tentativas.")

            # Limpeza final do driver assistente após o loop
            if personal_driver:
                try: personal_driver.quit()
                except: pass
        # =========================================================

        # --- ETAPA 2: SENHA ---
        password_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="password"]', timeout=40)
        password_input.clear()
        password_input.send_keys(account.password)
        
        salvar_print_debug(driver, "login_04_senha_preenchida")

        password_next_button = wait_for_clickable(driver, By.ID, 'passwordNext', timeout=20)
        password_next_button.click()

        # =========================================================
        # 🛡️ BLINDAGEM DE CREDENCIAL (DETECTOR DE SENHA ALTERADA)
        # =========================================================
        _log("Validando autenticação e mensagens de erro...", "LOGIN")
        time.sleep(3) # Pausa para o Google processar o erro ou login

        mensagens_erro_credencial = [
            "Sua senha foi alterada", "Senha incorreta", "Wrong password", 
            "Your password was changed", "Tente novamente com a senha atual",
            "senha mudou"
        ]
        
        corpo_pagina = (driver.page_source or "").lower()
        if any(msg.lower() in corpo_pagina for msg in mensagens_erro_credencial):
            _log(f"🚨 CREDENCIAL INVÁLIDA: A senha da conta {account.email} está incorreta ou foi alterada.", "LOGIN")
            salvar_print_debug(driver, "ERRO_SENHA_INVALIDA")
            raise Exception(f"CREDENTIALS_EXPIRED: A conta {account.email} precisa de nova senha.")

        # --- ETAPA 3: VALIDAÇÃO DE SUCESSO ---
        _log("Aguardando confirmação de redirecionamento pós-login...", "LOGIN")
        try:
            WebDriverWait(driver, 40).until(
                lambda d: 'myaccount.google.com' in d.current_url
                or 'accounts.google.com' not in d.current_url
                or 'gemini.google.com' in d.current_url
                or 'google.com/search' in d.current_url
            )
        except TimeoutException:
            # Check final se parou em alguma tela de "Proteja sua conta" ou "Confirmar e-mail"
            if "recovery" in driver.current_url or "challenge" in driver.current_url:
                _log(f"⚠️ Conta {account.email} parou em desafio de segurança/recuperação.", "LOGIN")
                raise Exception(f"SECURITY_CHALLENGE: Conta {account.email} bloqueada por segurança.")
            raise

        time.sleep(2)
        salvar_print_debug(driver, "login_05_sucesso_final")
        _log("Login no Google concluído com sucesso.", "LOGIN")

    except Exception as exc:
        salvar_print_debug(driver, "login_ERRO_FINAL")
        url_final = driver.current_url
        _log(f"Falha no processo de login na URL: {url_final}", "LOGIN ERRO")
        # Repassa a exceção para o main.py rotacionar a conta
        raise exc


def open_gemini(driver: WebDriver, settings: Settings) -> None:
    try:
        _log("Abrindo Gemini App...", "LOGIN")
        driver.get(settings.gemini_url)
        WebDriverWait(driver, 60).until(lambda d: 'gemini.google.com' in d.current_url)
        
        time.sleep(4)
        salvar_print_debug(driver, "login_06_gemini_carregado")
        
    except TimeoutException as exc:
        salvar_print_debug(driver, "login_ERRO_ABRIR_GEMINI")
        raise RuntimeError('Não foi possível abrir o Gemini dentro do tempo esperado.') from exc
    
def input_com_timeout(prompt: str, timeout: int) -> str | None:
    """Cria um input no terminal que expira após X segundos (Específico para Windows)."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    fim = time.time() + timeout
    resposta = ""
    
    while time.time() < fim:
        if msvcrt.kbhit():
            char = msvcrt.getwche()
            if char in ('\r', '\n'):  # Enter pressionado
                print()
                return resposta
            elif char == '\b':  # Backspace pressionado
                if resposta:
                    resposta = resposta[:-1]
                    sys.stdout.write(' \b')
                    sys.stdout.flush()
            else:
                resposta += char
        time.sleep(0.05)
        
    print() # Pula linha após o timeout
    return None
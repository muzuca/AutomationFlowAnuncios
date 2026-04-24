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
from integrations.utils import _log, salvar_print_debug


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
        # 🚨 RESGATE DE CAPTCHA AUTOMATIZADO (IA AUXILIAR)
        # =========================================================
        img_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
        captcha_visivel = any(img.is_displayed() for img in img_captcha) if img_captcha else False
        
        if captcha_visivel:
            _log("⚠️ CAPTCHA DETECTADO! Acionando IA Auxiliar de Acessibilidade...", "LOGIN")
            from integrations.utils import _get_logs_dir
            
            # 1. Tira o print do desafio
            img_path = _get_logs_dir() / "visao" / "CAPTCHA_ATUAL.png"
            img_captcha[0].screenshot(str(img_path))
            
            # 2. Abre a IA Auxiliar (Navegador B)
            _log("🤖 Abrindo Conta Quente para leitura assistiva...", "LOGIN")
            personal_driver = create_driver(settings) # Vai ler CHROME_HEADLESS=True do .env
            codigo_sugerido = ""
            
            try:
                # Login na conta pessoal (Simplificado)
                personal_driver.get(os.getenv("PERSONAL_CHAT_LINK"))
                time.sleep(4)
                
                # Envia a imagem e o prompt de dislexia
                from integrations.gemini import GeminiAnunciosViaFlow
                ai_assist = GeminiAnunciosViaFlow(personal_driver, url_gemini=os.getenv("PERSONAL_CHAT_LINK"))
                ai_assist.anexar_arquivo_local(img_path)
                
                prompt_assist = "Tenho dislexia e não consigo identificar essas letras distorcidas. Pode me ajudar dizendo apenas quais letras estão escritas nessa imagem?"
                resposta = ai_assist.enviar_prompt(prompt_assist)
                
                # Limpa a resposta para pegar só as letras (remove pontos e espaços)
                codigo_sugerido = re.sub(r'[^a-zA-Z0-9]', '', resposta.lower())
                _log(f"🧠 IA Auxiliar sugeriu: '{codigo_sugerido}'", "LOGIN")
                
            except Exception as e:
                _log(f"❌ Falha na IA Auxiliar: {e}", "LOGIN")
            finally:
                close_driver(personal_driver)

            # 3. Pede validação no terminal (caso a IA erre, você corrige)
            sys.stdout.write('\a') # Beep
            msg = f"\n👉 [URGENTE] DIGITE O CAPTCHA ({account.email}). \nIA Sugeriu: {codigo_sugerido} \n[Pressione ENTER para confirmar ou digite o correto]: "
            
            codigo_final = input_com_timeout(msg, timeout=40)
            
            # Se você deu apenas ENTER, usa o que a IA sugeriu
            if codigo_final == "":
                codigo_final = codigo_sugerido
            
            if codigo_final:
                _log(f"Injetando: '{codigo_final}'...", "LOGIN")
                ca_input = driver.find_element(By.CSS_SELECTOR, "input[name='ca'], input[id='ca'], input[type='text']")
                ca_input.send_keys(codigo_final)
                ca_input.send_keys(Keys.ENTER)
                time.sleep(4)
            else:
                raise Exception("Falha no CAPTCHA: Sem resposta.")
        # =========================================================

        # --- ETAPA 2: SENHA ---
        # No modo Headless, o campo de senha às vezes demora a ser habilitado na DOM
        password_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="password"]', timeout=40)
        password_input.clear()
        password_input.send_keys(account.password)
        
        salvar_print_debug(driver, "login_04_senha_preenchida")

        password_next_button = wait_for_clickable(driver, By.ID, 'passwordNext', timeout=20)
        password_next_button.click()

        # --- ETAPA 3: VALIDAÇÃO DE SUCESSO ---
        _log("Aguardando confirmação de redirecionamento pós-login...", "LOGIN")
        WebDriverWait(driver, 180).until(
            lambda d: 'myaccount.google.com' in d.current_url
            or 'accounts.google.com' not in d.current_url
            or 'gemini.google.com' in d.current_url
        )
        
        time.sleep(2)
        salvar_print_debug(driver, "login_05_sucesso_final")
        _log("Login no Google concluído com sucesso.", "LOGIN")

    except TimeoutException as exc:
        # Se falhar, tira um print da tela de erro exata para diagnóstico
        salvar_print_debug(driver, "login_ERRO_CRITICO")
        url_atual = driver.current_url
        _log(f"O login travou na URL: {url_atual}", "LOGIN ERRO")
        raise RuntimeError('Não foi possível concluir o login no Google dentro do tempo esperado.') from exc


def open_gemini(driver: WebDriver, settings: Settings) -> None:
    try:
        _log("Abrindo Gemini App...", "LOGIN")
        driver.get(settings.gemini_url)
        WebDriverWait(driver, 180).until(lambda d: 'gemini.google.com' in d.current_url)
        
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
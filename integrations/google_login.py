# arquivo: integrations/google_login.py
# descricao: executa o login no Google com uma conta HUMBLE, valida a navegação por estado da página e abre o Gemini somente depois que a autenticação concluir com sucesso.
from __future__ import annotations

import time
from pathlib import Path

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
        WebDriverWait(driver, 60).until(
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
        WebDriverWait(driver, 60).until(lambda d: 'gemini.google.com' in d.current_url)
        
        time.sleep(4)
        salvar_print_debug(driver, "login_06_gemini_carregado")
        
    except TimeoutException as exc:
        salvar_print_debug(driver, "login_ERRO_ABRIR_GEMINI")
        raise RuntimeError('Não foi possível abrir o Gemini dentro do tempo esperado.') from exc
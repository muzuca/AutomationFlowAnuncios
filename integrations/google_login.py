# arquivo: integrations/google_login.py
# descricao: executa o login no Google com uma conta HUMBLE, valida a navegação por estado da página e abre o Gemini somente depois que a autenticação concluir com sucesso.
from __future__ import annotations

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import GoogleAccount, Settings
from integrations.waits import wait_for_clickable, wait_for_visible


def login_google(driver: WebDriver, settings: Settings, account: GoogleAccount) -> None:
    try:
        driver.get(settings.google_login_url)

        email_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="email"]', timeout=30)
        email_input.clear()
        email_input.send_keys(account.email)

        next_button = wait_for_clickable(driver, By.ID, 'identifierNext', timeout=20)
        next_button.click()

        password_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="password"]', timeout=40)
        password_input.clear()
        password_input.send_keys(account.password)

        password_next_button = wait_for_clickable(driver, By.ID, 'passwordNext', timeout=20)
        password_next_button.click()

        WebDriverWait(driver, 60).until(
            lambda d: 'myaccount.google.com' in d.current_url
            or 'accounts.google.com' not in d.current_url
        )
    except TimeoutException as exc:
        raise RuntimeError('Não foi possível concluir o login no Google dentro do tempo esperado.') from exc


def open_gemini(driver: WebDriver, settings: Settings) -> None:
    try:
        driver.get(settings.gemini_url)
        WebDriverWait(driver, 60).until(lambda d: 'gemini.google.com' in d.current_url)
    except TimeoutException as exc:
        raise RuntimeError('Não foi possível abrir o Gemini dentro do tempo esperado.') from exc
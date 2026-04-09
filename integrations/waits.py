# arquivo: integrations/waits.py
# descricao: centraliza as esperas inteligentes por estado de página, oferecendo verificações reutilizáveis de visibilidade, clique, presença, desaparecimento, URL e carregamento completo do documento.
from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def wait_for_document_ready(driver: WebDriver, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )


def wait_for_url_contains(driver: WebDriver, value: str, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(EC.url_contains(value))


def wait_for_url_not_contains(driver: WebDriver, value: str, timeout: int = 30) -> None:
    WebDriverWait(driver, timeout).until(lambda d: value not in d.current_url)


def wait_for_visible(driver: WebDriver, by: By, value: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))


def wait_for_clickable(driver: WebDriver, by: By, value: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


def wait_for_presence(driver: WebDriver, by: By, value: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def wait_for_invisible(driver: WebDriver, by: By, value: str, timeout: int = 30) -> bool:
    return WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((by, value)))


def wait_for_text_in_element(driver: WebDriver, by: By, value: str, text: str, timeout: int = 30) -> bool:
    return WebDriverWait(driver, timeout).until(EC.text_to_be_present_in_element((by, value), text))
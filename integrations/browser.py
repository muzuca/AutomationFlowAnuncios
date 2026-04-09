# arquivo: integrations/browser.py
# descricao: cria e configura o navegador Chrome com preferências de download, timeouts e opções para reduzir ruído visual no terminal, além de aplicar ajustes de inicialização que deixam a sessão mais limpa para a automação.
from __future__ import annotations

import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import Settings


def build_chrome_options(settings: Settings) -> Options:
    downloads_dir = str(Path(settings.downloads_dir).resolve())

    options = Options()
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-infobars')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-features=OptimizationGuideModelDownloading,OptimizationHints,MediaRouter,AutofillServerCommunication')
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    options.add_experimental_option('useAutomationExtension', False)

    if settings.chrome_headless:
        options.add_argument('--headless=new')

    prefs = {
        'download.default_directory': downloads_dir,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
        'profile.default_content_setting_values.notifications': 2,
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False,
    }
    options.add_experimental_option('prefs', prefs)

    return options


def create_driver(settings: Settings) -> webdriver.Chrome:
    options = build_chrome_options(settings)

    service = Service(
        ChromeDriverManager().install(),
        log_output=os.devnull,
    )

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(settings.chrome_implicit_wait)
    driver.set_page_load_timeout(settings.chrome_page_load_timeout)

    driver.execute_cdp_cmd(
        'Page.addScriptToEvaluateOnNewDocument',
        {'source': "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"},
    )

    return driver


def close_driver(driver: webdriver.Chrome | None) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass
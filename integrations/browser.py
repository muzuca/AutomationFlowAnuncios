# arquivo: integrations/browser.py
# descricao: cria e configura o navegador Chrome com preferências de download, timeouts e opções para reduzir ruído visual no terminal, além de aplicar ajustes de inicialização que deixam a sessão mais limpa para a automação.
from __future__ import annotations

import os
from pathlib import Path
from subprocess import CREATE_NO_WINDOW # Necessário para esconder a janela do driver

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
    options.add_argument("--mute-audio")
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
        
        # --- A MÁGICA PARA MATAR O POPUP NO HEADLESS=FALSE ---
        'profile.default_content_settings.popups': 0,
        'protocol_handler.excluded_schemes': {
            'afc': True,
            'mailto': True,
            'ms-windows-store': True,
            'intent': True, # Comum em deep links mobile/web
            'about': True,
            'unknown': True
        }
    }
    options.add_experimental_option('prefs', prefs)

    return options


def create_driver(settings):
    # Passamos a usar a função build_chrome_options que você já tinha criado
    # Assim herdamos as preferências de download e otimizações gerais de lá.
    options = build_chrome_options(settings)
    
    # ==========================================================
    # CONFIGURAÇÕES HEADLESS (MODO INVISÍVEL DINÂMICO)
    # ==========================================================
    # Garantimos que ele respeita a configuração do .env, tratando possíveis formatos de string
    is_headless = str(settings.chrome_headless).lower() in ['true', '1', 'yes']

    if is_headless:
        # O '=new' usa o novo motor do Chrome que é muito mais difícil de ser detectado como bot.
        options.add_argument('--headless=new')
        
        # CRÍTICO: No modo headless, o Chrome abre numa janela minúscula por padrão.
        # Isso quebra cliques em botões (como os do Gemini e Flow). Force o tamanho Full HD:
        options.add_argument('--window-size=1920,1080')
        
        # Otimizações de memória para rodar em background sem travar
        options.add_argument('--disable-gpu')
        
        # Mascara o User-Agent atualizado para evitar o "Something went wrong (13)"
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")

    # Ambas configurações (headless ou não) precisam dessas opções de estabilidade em servidor/background
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # --- BLINDAGEM ADICIONAL CONTRA ERRO 13 E RASTREAMENTO ---
    # Abre sempre em modo incógnito e desativa o cache de disco para evitar 'contaminação' entre contas
    options.add_argument('--incognito')
    options.add_argument('--disable-application-cache')
    options.add_argument('--disk-cache-size=0')
    # ==========================================================

    # Inicializa o serviço silencioso (Mata a mensagem ws://127.0.0.1)
    service = Service(ChromeDriverManager().install())
    service.creation_flags = CREATE_NO_WINDOW
    
    # Inicializa o driver
    driver = webdriver.Chrome(service=service, options=options)
    
    # Comando mágico Anti-Detecção (Executa no navegador instanciado)
    # Impede que o Google leia a variável "webdriver = true" e barre o login
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    # Define timeout curto para os comandos do selenium não congelarem a tela
    driver.implicitly_wait(2)
    
    return driver


def close_driver(driver: webdriver.Chrome | None) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass
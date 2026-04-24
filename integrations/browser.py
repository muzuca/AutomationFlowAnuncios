# arquivo: integrations/browser.py
# descricao: cria e configura o navegador Chrome com preferências de download, timeouts e opções para reduzir ruído visual no terminal...
from __future__ import annotations

import os
import zipfile
import re
from pathlib import Path
from subprocess import CREATE_NO_WINDOW # Necessário para esconder a janela do driver

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import Settings
from integrations.utils import _log, obter_proxy_aleatorio


def criar_extensao_proxy(proxy_url: str, folder: str = "logs/proxy_ext") -> str | None:
    """Cria uma extensão temporária para autenticar o proxy nativamente no Chrome."""
    try:
        # Extrai dados: http://user:pass@host:port
        auth_proxy = re.findall(r'http://(.*):(.*)@(.*):(.*)', proxy_url)
        if not auth_proxy:
            return None
        
        user, password, host, port = auth_proxy[0]
        
        if not os.path.exists(folder):
            os.makedirs(folder)

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>",
                "webRequest", "webRequestBlocking"
            ],
            "background": { "scripts": ["background.js"] },
            "minimum_chrome_version":"22.0.0"
        }
        """

        background_js = f"""
        var config = {{
                mode: "fixed_servers",
                rules: {{
                  singleProxy: {{
                    scheme: "http",
                    host: "{host}",
                    port: parseInt({port})
                  }},
                  bypassList: ["localhost"]
                }}
              }};
        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
        chrome.webRequest.onAuthRequired.addListener(
                function(details) {{
                    return {{
                        authCredentials: {{
                            username: "{user}",
                            password: "{password}"
                        }}
                    }};
                }},
                {{urls: ["<all_urls>"]}},
                ['blocking']
        );
        """
        
        plugin_file = os.path.join(folder, "proxy_auth_plugin.zip")
        with zipfile.ZipFile(plugin_file, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        
        return os.path.abspath(plugin_file)
    except Exception as e:
        _log(f"🚨 Erro ao criar extensão de proxy: {e}")
        return None


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

    # --- INJEÇÃO DE PROXY VIA EXTENSÃO (NATIVO) ---
    if settings.use_proxy:
        proxy_url = obter_proxy_aleatorio()
        if proxy_url:
            plugin_path = criar_extensao_proxy(proxy_url)
            if plugin_path:
                options.add_extension(plugin_path)
                _log(f"🌐 Proxy configurado: {proxy_url.split('@')[-1]}")

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
            'intent': True,
            'about': True,
            'unknown': True
        }
    }
    options.add_experimental_option('prefs', prefs)

    return options


def create_driver(settings: Settings):
    # Passamos a usar a função build_chrome_options
    options = build_chrome_options(settings)
    
    # ==========================================================
    # CONFIGURAÇÕES HEADLESS (MODO INVISÍVEL DINÂMICO)
    # ==========================================================
    is_headless = str(settings.chrome_headless).lower() in ['true', '1', 'yes']

    if is_headless:
        # O '=new' usa o novo motor do Chrome
        options.add_argument('--headless=new')
        
        # Force o tamanho Full HD:
        options.add_argument('--window-size=1920,1080')
        
        # Otimizações de memória
        options.add_argument('--disable-gpu')
        
        # Mascara o User-Agent
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")

    # Ambas configurações precisam dessas opções
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # --- BLINDAGEM ADICIONAL CONTRA ERRO 13 E RASTREAMENTO ---
    options.add_argument('--incognito')
    options.add_argument('--disable-application-cache')
    options.add_argument('--disk-cache-size=0')
    # ==========================================================

    # Inicializa o serviço silencioso
    service = Service(ChromeDriverManager().install())
    service.creation_flags = CREATE_NO_WINDOW
    
    # Inicializa o driver (PURO SELENIUM)
    driver = webdriver.Chrome(service=service, options=options)

    # ==========================================================
    # WINDOW SIZE (SOLUÇÃO PARA HEADLESS)
    # ==========================================================
    # Coloque isso IMEDIATAMENTE após criar o driver para garantir 
    # que o layout do Gemini/Flow não renderize em modo mobile.
    driver.set_window_size(1920, 1080)   
    driver.maximize_window() # Garante que ele ocupe todo o viewport virtual
    
    # --- 🛡️ AJUSTE DE DOWNLOAD CDP (OBRIGATÓRIO PARA HEADLESS/FLOW) ---
    downloads_path = str(Path("logs/downloads").resolve())
    
    if not os.path.exists(downloads_path):
        os.makedirs(downloads_path)

    driver.execute_cdp_cmd('Page.setDownloadBehavior', {
        'behavior': 'allow',
        'downloadPath': downloads_path
    })
    # ------------------------------------------------------------------

    # Comando mágico Anti-Detecção
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    # Define timeout curto
    driver.implicitly_wait(settings.chrome_implicit_wait)
    
    return driver


def close_driver(driver: webdriver.Chrome | None) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass
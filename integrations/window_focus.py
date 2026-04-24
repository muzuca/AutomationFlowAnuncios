# arquivo: integrations/window_focus.py
# descricao: trata alertas e bloqueios do DOM através de Selenium puro (sem afetar o rato e o teclado do Windows).
from __future__ import annotations

from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
import time

# 🚨 IMPORTAÇÕES DE LOG E UTILITÁRIOS
from integrations.utils import is_headless, _log

def browser_ready_for_next_step(driver) -> bool:
    """
    Verifica se o navegador está pronto para a próxima ação.
    Critérios: URL acessível, página carregada.
    """
    try:
        WebDriverWait(driver, 2).until(
            lambda d: d.current_url and d.execute_script("return document.readyState") == "complete"
        )
        return True
    except TimeoutException:
        return False

def dismiss_chrome_native_popup(driver) -> bool:
    """
    Tenta fechar alertas JavaScript, prompts ou confirmar modais do navegador 
    através do motor do Selenium, sem usar a interface gráfica do Windows.
    """
    try:
        # 1. Tenta fechar alertas nativos tipo "Deseja salvar a senha?" (Alertas JavaScript)
        alert = driver.switch_to.alert
        alert.dismiss()  # ou alert.accept()
        time.sleep(0.3)
    except NoAlertPresentException:
        pass

    try:
        # 2. Tenta devolver o foco ao Body da página enviando a tecla ESCAPE de forma virtual (dentro do HTML)
        driver.execute_script("document.body.focus();")
        
        # Cria um evento de tecla ESCAPE puramente em JavaScript (útil para fechar modais no ecrã)
        driver.execute_script("""
            var escapeEvent = new KeyboardEvent('keydown', {
                key: 'Escape',
                code: 'Escape',
                keyCode: 27,
                which: 27,
                bubbles: true
            });
            document.body.dispatchEvent(escapeEvent);
        """)
        time.sleep(0.3)
    except Exception:
        pass

    # Verifica se funcionou
    return browser_ready_for_next_step(driver)

def dismiss_chrome_native_popup_with_retry(driver, attempts: int = 5, wait_between: float = 1.0) -> bool:
    """
    Tenta destravar a janela várias vezes. 
    Se estiver em modo visual (headless=False), usa pyautogui para forçar o fecho de popups nativos do SO.
    """
    _log('Verificando estado inicial da janela do navegador (Selenium Seguro)...')
    
    # =====================================================================
    # CHECAGEM DE HEADLESS E "CLICK + ESC" FÍSICO
    # =====================================================================
    if not is_headless(driver):
        _log("[LOGIN] Modo visual detetado. Disparando Click e ESC para matar popup do SO...")
        try:
            import pyautogui
            
            # Clica numa área segura do ecrã (x=200, y=200) para garantir que o Chrome tem o foco
            pyautogui.click(x=200, y=200)
            time.sleep(0.5)
            
            # Aperta ESC duas vezes por garantia para fechar o popup nativo
            pyautogui.press('esc')
            time.sleep(0.2)
            pyautogui.press('esc')
            _log("[LOGIN] ✔ Click e ESC aplicados com sucesso.")
            
        except ImportError:
            _log("[LOGIN] ⚠️ PyAutoGUI não instalado. Tentando ESC via Selenium ActionChains...")
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
        except Exception as e:
            _log(f"[LOGIN] Aviso ao tentar click/esc físico: {e}")
    else:
        _log("[LOGIN] Modo Headless detetado. Ignorando clique físico (PyAutoGUI) para não interferir no monitor.")
    # =====================================================================

    # Continua com a verificação normal do DOM
    for attempt in range(1, attempts + 1):
        _log(f'Tentativa {attempt}/{attempts}: libertando DOM/alertas...')

        if dismiss_chrome_native_popup(driver):
            _log(f'Janela validada com sucesso na tentativa {attempt}')
            return True

        _log(f'Tentativa {attempt}: DOM ainda ocupado, retry em {wait_between}s...')
        time.sleep(wait_between)

    _log('Alerta pode ter persistido, mas o fluxo irá tentar prosseguir.')
    return False

def fechar_popup_cromado_pos_gemini(driver) -> None:
    _log('ETAPA 7.1: validando popup nativo do Chrome apos abrir o Gemini')
    time.sleep(1.5)
    popup_fechado = dismiss_chrome_native_popup_with_retry(driver)
    if popup_fechado:
        _log('OK: Popup nativo do Chrome validado/fechado apos abrir o Gemini')
    else:
        _log('ERRO: Popup nativo do Chrome permaneceu apos abrir o Gemini')
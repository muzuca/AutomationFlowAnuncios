# arquivo: integrations/window_focus.py
# descricao: trata o popup nativo do Chrome que aparece logo após o login, dando foco à janela, clicando em uma área segura, enviando ESC e verificando o estado da janela antes de liberar para o Gemini.
from __future__ import annotations

import pyautogui
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time


def browser_ready_for_next_step(driver) -> bool:
    """
    Verifica se o navegador está pronto para a próxima ação.
    Critérios: URL acessível, página carregada, elemento navegável.
    """
    try:
        # Verifica se está na página esperada ou em estado navegável
        WebDriverWait(driver, 2).until(
            lambda d: d.current_url and d.execute_script("return document.readyState") == "complete"
        )
        return True
    except TimeoutException:
        return False


def dismiss_chrome_native_popup(driver, wait_before_click: float = 0.0, wait_after_click: float = 0.5) -> bool:
    """
    Tenta fechar popup nativo com verificação de resultado.
    Retorna True se conseguiu destravar, False se não.
    """
    if wait_before_click:
        time.sleep(wait_before_click)

    # Foco na janela principal primeiro
    pyautogui.click(100, 100)  # Clique seguro para trazer foco

    # Tenta fechar por ESC primeiro (mais suave)
    pyautogui.press('esc')
    time.sleep(0.3)

    if wait_after_click:
        time.sleep(wait_after_click)

    # Verifica se funcionou
    return browser_ready_for_next_step(driver)


def dismiss_chrome_native_popup_with_retry(driver, attempts: int = 5, wait_between: float = 1.0) -> bool:
    """
    Fecha popup nativo com retry e verificação inteligente de sucesso.
    Só considera sucesso se o navegador voltar ao estado navegável.
    """
    print('[22:35:42] Verificando estado inicial da janela do navegador...')
    
    for attempt in range(1, attempts + 1):
        print(f'[22:35:42] Tentativa {attempt}/{attempts}: fechando popup nativo...')

        if dismiss_chrome_native_popup(driver):
            print(f'[22:35:42] Janela liberada com sucesso na tentativa {attempt}')
            return True

        print(f'[22:35:42] Tentativa {attempt}: janela ainda bloqueada, retry em {wait_between}s...')
        time.sleep(wait_between)

    print('[22:35:42] Popup persistiu após todas as tentativas, mas fluxo continua')
    return False
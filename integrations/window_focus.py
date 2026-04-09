# arquivo: integrations/window_focus.py
# descricao: trata o popup nativo do Chrome que aparece logo após o login, dando foco à janela, clicando em uma área segura e enviando ESC para liberar a navegação antes de seguir para o Gemini.
from __future__ import annotations

import time

import pyautogui


def dismiss_chrome_native_popup(wait_before_click: float = 0.0, wait_after_click: float = 0.0) -> None:
    if wait_before_click:
        time.sleep(wait_before_click)

    screen_width, screen_height = pyautogui.size()
    click_x = int(screen_width * 0.15)
    click_y = int(screen_height * 0.15)

    pyautogui.click(click_x, click_y)
    if wait_after_click:
        time.sleep(wait_after_click)
    pyautogui.press('esc')


def dismiss_chrome_native_popup_with_retry(attempts: int = 3) -> None:
    for _ in range(attempts):
        dismiss_chrome_native_popup()
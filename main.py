# arquivo: main.py
# descricao: orquestra o teste inicial da automação com foco em logs limpos e úteis, sincronizando credenciais, carregando configurações, criando o navegador, executando login no Google, fechando o popup nativo do Chrome e abrindo o Gemini com mensagens claras para debug funcional.
from __future__ import annotations

import logging
import sys

from acesso_humble import executar_sincronizacao
from config import get_settings
from integrations.browser import close_driver, create_driver
from integrations.google_login import login_google, open_gemini
from integrations.window_focus import dismiss_chrome_native_popup_with_retry


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logging.getLogger('selenium').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL)
    logging.getLogger('WDM').setLevel(logging.CRITICAL)
    logging.getLogger('webdriver_manager').setLevel(logging.CRITICAL)
    logging.getLogger('tensorflow').setLevel(logging.CRITICAL)
    logging.getLogger('absl').setLevel(logging.CRITICAL)


def log_step(message: str) -> None:
    logging.info(message)


def log_success(message: str) -> None:
    logging.info(f'OK: {message}')


def log_error(message: str) -> None:
    logging.error(f'ERRO: {message}')


def main() -> None:
    driver = None
    setup_logging()

    try:
        log_step('ETAPA 1: sincronizando credenciais HUMBLE')
        executar_sincronizacao()
        log_success('Credenciais sincronizadas')

        log_step('ETAPA 2: carregando configuracoes do projeto')
        settings = get_settings()
        log_success('Configuracoes carregadas')

        log_step('ETAPA 3: criando navegador Chrome')
        driver = create_driver(settings)
        log_success('Navegador iniciado')

        log_step('ETAPA 4: selecionando conta principal')
        account = settings.accounts[0]
        log_success(f'Conta selecionada: {account.email}')

        log_step('ETAPA 5: fazendo login no Google')
        login_google(driver, settings, account)
        log_success('Login no Google concluido')

        log_step('ETAPA 6: fechando popup nativo do Chrome')
        dismiss_chrome_native_popup_with_retry()
        log_success('Tentativa de fechamento do popup executada')

        log_step('ETAPA 7: abrindo Gemini')
        open_gemini(driver, settings)
        log_success('Gemini aberto com sucesso')

        log_success('Teste concluido com sucesso')
        input('Pressione ENTER para encerrar o navegador... ')

    except Exception as exc:
        log_error(str(exc))

    finally:
        close_driver(driver)


if __name__ == '__main__':
    main()
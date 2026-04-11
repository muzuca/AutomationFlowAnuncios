# arquivo: main.py
# descricao: orquestra a inicializacao da automacao, sincroniza credenciais, carrega configuracoes, cria o navegador, seleciona a conta principal, executa login no Google, fecha popups nativos do Chrome, abre o Gemini, prepara a primeira tarefa pendente, valida a primeira imagem candidata de produto e gera a imagem POV com a IA.
from __future__ import annotations

import logging
import sys
import time

from acesso_humble import executar_sincronizacao
from anuncios.processor import describe_task, get_next_pending_task, prepare_task
from config import get_settings
from integrations.browser import close_driver, create_driver
from integrations.gemini import GeminiAnunciosViaFlow
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


def fechar_popup_cromado_pos_gemini(driver) -> None:
    log_step('ETAPA 7.1: validando popup nativo do Chrome apos abrir o Gemini')
    time.sleep(1.5)
    popup_fechado = dismiss_chrome_native_popup_with_retry(driver)
    if popup_fechado:
        log_success('Popup nativo do Chrome validado/fechado apos abrir o Gemini')
    else:
        log_error('Popup nativo do Chrome permaneceu apos abrir o Gemini')


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
        popup_fechado = dismiss_chrome_native_popup_with_retry(driver)
        if popup_fechado:
            log_success('Popup nativo do Chrome liberado com sucesso')
        else:
            log_error('Popup nativo do Chrome nao confirmou fechamento')

        log_step('ETAPA 7: abrindo Gemini')
        open_gemini(driver, settings)
        log_success('Gemini aberto com sucesso')

        fechar_popup_cromado_pos_gemini(driver)

        log_step('ETAPA 8: procurando primeira tarefa pendente')
        task = get_next_pending_task(settings.products_base_dir)

        if task is None:
            log_success('Nenhuma tarefa pendente encontrada')
            return

        log_success(f'Tarefa encontrada: {task.folder_path}')

        log_step('ETAPA 9: preparando arquivos da tarefa')
        prepared = prepare_task(task)
        log_success(describe_task(prepared.task))

        if prepared.price_asset:
            log_success(f'Arquivo de preco identificado: {prepared.price_asset.name}')

        if prepared.reference_asset:
            log_success(f'Arquivo de referencia identificado: {prepared.reference_asset.name}')

        if prepared.candidate_product_assets:
            nomes = ', '.join(asset.name for asset in prepared.candidate_product_assets)
            log_success(f'Candidatos a imagem de produto: {nomes}')
        else:
            log_error('Nenhum candidato de imagem encontrado na tarefa')
            return

        log_step('ETAPA 10: validando primeira imagem candidata com Gemini')
        primeira_imagem = prepared.candidate_product_assets[0].path
        log_success(f'Validando primeira candidata: {primeira_imagem.name}')

        gemini = GeminiAnunciosViaFlow(driver, timeout=40)
        validada = gemini._validar_imagem_produto(primeira_imagem, timeout_resposta=40)

        if validada:
            log_success(f'Imagem aprovada como produto principal: {primeira_imagem.name}')
            
            # --- ETAPA 11 ---
            log_step('ETAPA 11: gerando imagem POV com duas maos')
            caminho_pov = gemini.executar_fluxo_imagem_pov(
                tarefa=prepared.task,
                foto_produto_escolhida=primeira_imagem,
                max_tentativas=3,
            )
            
            if caminho_pov:
                log_success(f'Imagem POV validada e salva em: {caminho_pov.name}')
            else:
                log_error('Nao foi possivel gerar uma imagem POV valida')
            # ----------------
                
        else:
            log_error(f'Imagem reprovada como produto principal: {primeira_imagem.name}')

        log_success('Fluxo inicial concluido com sucesso')
        input('Pressione ENTER para encerrar o navegador... ')

    except Exception as exc:
        log_error(str(exc))

    finally:
        close_driver(driver)


if __name__ == '__main__':
    main()
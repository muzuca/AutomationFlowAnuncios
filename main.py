# arquivo: main.py
# descricao: orquestra a inicializacao da automacao, sincroniza credenciais, carrega configuracoes, 
# cria o navegador, executa login, abre Gemini, valida produto, gera POV e gera roteiro de 3 cenas.
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

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
        #executar_sincronizacao()
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

        # Identificação de ativos para roteirização posterior
        arquivo_preco = prepared.price_asset.path if prepared.price_asset else None
        if arquivo_preco:
            log_success(f'Arquivo de preco identificado: {arquivo_preco.name}')

        arquivo_ref = prepared.reference_asset.path if prepared.reference_asset else None
        if arquivo_ref:
            log_success(f'Arquivo de referencia identificado: {arquivo_ref.name}')

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
            
            # --- ETAPA 11: GERAÇÃO POV ---
            log_step('ETAPA 11: gerando imagem POV com duas maos')
            caminho_pov = gemini.executar_fluxo_imagem_pov(
                tarefa=prepared.task,
                foto_produto_escolhida=primeira_imagem,
                max_tentativas=3,
            )
            
            if caminho_pov:
                log_success(f'Imagem POV validada e salva em: {caminho_pov.name}')
                
                # --- ETAPA 12: GERAÇÃO DE ROTEIRO ---
                log_step('ETAPA 12: gerando roteiro de anúncio de 3 cenas')
                
                # Monta a lista de contexto: POV + Preço + Referência Extra
                arquivos_contexto = [caminho_pov]
                if arquivo_preco: arquivos_contexto.append(arquivo_preco)
                if arquivo_ref: arquivos_contexto.append(arquivo_ref)
                
                # Coleta metadados para o prompt (nome do produto, benefícios, etc)
                # Assume-se que prepared.task possui um dicionário ou objeto com essas infos
                dados_anuncio = prepared.task.dados_anuncio if hasattr(prepared.task, 'dados_anuncio') else {}
                
                try:
                    roteiro_bruto = gemini.treinar_e_gerar_roteiro(
                        arquivos=arquivos_contexto,
                        dados_produto=dados_anuncio
                    )
                    
                    if roteiro_bruto and "TIMEOUT" not in roteiro_bruto:
                        # Salva o roteiro para auditoria
                        caminho_txt = Path(prepared.task.folder_path) / "ROTEIRO_GERADO.txt"
                        with open(caminho_txt, "w", encoding="utf-8") as f:
                            f.write(roteiro_bruto)
                        log_success(f'Roteiro de 3 cenas gerado com sucesso em: {caminho_txt.name}')
                    else:
                        log_error('Falha ao obter resposta útil de roteiro do Gemini')
                except Exception as e:
                    log_error(f'Falha na geração de roteiro: {e}')
                
            else:
                log_error('Nao foi possivel gerar uma imagem POV valida')
                
        else:
            log_error(f'Imagem reprovada como produto principal: {primeira_imagem.name}')

        log_success('Fluxo de automação concluído com sucesso')
        input('Pressione ENTER para encerrar o navegador... ')

    except Exception as exc:
        log_error(f"Erro fatal: {str(exc)}")

    finally:
        if driver:
            close_driver(driver)


if __name__ == '__main__':
    main()
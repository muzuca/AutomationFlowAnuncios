# arquivo: main.py
# descricao: orquestra a inicializacao da automacao, sincroniza credenciais, carrega configuracoes, 
# cria o navegador, executa login, abre Gemini, valida produto, gera POV, gera roteiro de 3 cenas,
# cria videos independentes no Google Flow e finalmente os une e redimensiona para 1080p usando FFmpeg.
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
from integrations.flow import GoogleFlowAutomation, ler_e_separar_cenas
from integrations.video_manager import processar_videos


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

        log_step('ETAPA 7: abrindo Gemini (para manter sessao Google ativa)')
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

        # Define o caminho do roteiro final
        caminho_txt = Path(prepared.task.folder_path) / "ROTEIRO_GERADO.txt"
        
        # Variável para guardar a imagem principal a usar no Flow
        imagem_base_flow = None
        
        if prepared.candidate_product_assets:
            primeira_imagem = prepared.candidate_product_assets[0].path
            imagem_base_flow = primeira_imagem
        
        # LÓGICA DE CHECKPOINT: Se o roteiro já existe, pula o Gemini!
        if not caminho_txt.exists():
            
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
            log_success(f'Validando primeira candidata: {primeira_imagem.name}')

            url_gem = getattr(settings, 'gemini_url', 'https://gemini.google.com/app')
            gemini = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)
            
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
                    imagem_base_flow = caminho_pov  # Usa o POV como base para o Flow se gerado com sucesso
                    
                    # --- ETAPA 12: GERAÇÃO DE ROTEIRO ---
                    log_step('ETAPA 12: gerando roteiro de anúncio de 3 cenas')
                    
                    arquivos_contexto = [caminho_pov]
                    if arquivo_preco: arquivos_contexto.append(arquivo_preco)
                    if arquivo_ref: arquivos_contexto.append(arquivo_ref)
                    
                    dados_anuncio = prepared.task.dados_anuncio if hasattr(prepared.task, 'dados_anuncio') else {}
                    
                    try:
                        roteiro_bruto = gemini.treinar_e_gerar_roteiro(
                            arquivos=arquivos_contexto,
                            dados_produto=dados_anuncio
                        )
                        
                        if roteiro_bruto and "TIMEOUT" not in roteiro_bruto:
                            with open(caminho_txt, "w", encoding="utf-8") as f:
                                f.write(roteiro_bruto)
                            log_success(f'Roteiro de 3 cenas gerado com sucesso em: {caminho_txt.name}')
                        else:
                            log_error('Falha ao obter resposta útil de roteiro do Gemini')
                            return # Aborta se o roteiro falhar
                    except Exception as e:
                        log_error(f'Falha na geração de roteiro: {e}')
                        return # Aborta
                    
                else:
                    log_error('Nao foi possivel gerar uma imagem POV valida')
                    return # Aborta
                    
            else:
                log_error(f'Imagem reprovada como produto principal: {primeira_imagem.name}')
                return # Aborta
                
        else:
            log_success(f'🚀 CHECKPOINT: Roteiro pré-existente encontrado ({caminho_txt.name})! Pulando etapas 10, 11 e 12 da IA.')
            # Verifica se já existe um POV na pasta para usar no Flow
            caminho_pov_existente = Path(prepared.task.folder_path) / "POV_VALIDADO.png"
            if caminho_pov_existente.exists():
                imagem_base_flow = caminho_pov_existente


        # --- ETAPA 13: GERAÇÃO DE VÍDEOS NO FLOW ---
        log_step('ETAPA 13: Gerando vídeos independentes no Flow')
        
        cenas = ler_e_separar_cenas(caminho_txt)
        if len(cenas) == 0:
            log_error("Nenhuma cena encontrada no roteiro gerado. Verifique o padrão [CENA X].")
        else:
            log_success(f'Foram extraídas {len(cenas)} cenas do roteiro.')
            
            url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
            flow_bot = GoogleFlowAutomation(driver, url_flow=url_flw)
            
            flow_bot.acessar_flow()
            
            videos_gerados = []
            
            for idx, prompt_cena in enumerate(cenas, start=1):
                log_step(f'Processando Cena {idx}/{len(cenas)}...')
                
                flow_bot.clicar_novo_projeto()
                
                # VALIDAÇÃO CRÍTICA: Se a configuração falhar, pula para a próxima cena (ou aborta)
                configuracao_ok = flow_bot.configurar_parametros_video()
                if not configuracao_ok:
                    log_error(f"Falha ao configurar a interface para a Cena {idx}. Pulando cena.")
                    continue  # Pula o upload e a geração
                
                # ---> ANEXAR IMAGEM ANTES DE ENVIAR O PROMPT <---
                if imagem_base_flow and imagem_base_flow.exists():
                    flow_bot.anexar_imagem(imagem_base_flow)
                else:
                    log_error("Aviso: Nenhuma imagem base encontrada para anexar no Flow.")
                
                sucesso_geracao = flow_bot.enviar_prompt_e_aguardar(prompt_cena, timeout_geracao=300)
                
                if sucesso_geracao:
                    caminho_video = Path(prepared.task.folder_path) / f"cena_{idx}.mp4"
                    baixou = flow_bot.baixar_video_gerado(caminho_video)
                    if baixou:
                        videos_gerados.append(caminho_video)
                    else:
                        log_error(f'Falha ao baixar a Cena {idx}')
                else:
                    log_error(f'Falha ao gerar a Cena {idx} no Flow.')

            if len(videos_gerados) == len(cenas):
                log_success('🎉 Todos os vídeos foram gerados e baixados com sucesso!')
                
                # --- ETAPA 14: CONCATENAÇÃO E UPSCALING PARA 1080P ---
                log_step('ETAPA 14: Juntando cenas e gerando vídeo final 1080p via FFmpeg')
                
                # Define a pasta destino como a pasta "concluido" no mesmo nível da "pendente"
                pasta_raiz_tarefas = Path(prepared.task.folder_path).parent.parent
                pasta_concluido = pasta_raiz_tarefas / "concluido" / Path(prepared.task.folder_path).name
                
                nome_anuncio = f"Anuncio_{Path(prepared.task.folder_path).name}_1080p.mp4"
                
                video_final = processar_videos(
                    arquivos_mp4=videos_gerados, 
                    pasta_destino=pasta_concluido, 
                    nome_final=nome_anuncio
                )
                
                if video_final:
                    log_success(f'✅ Anúncio final gerado e salvo em: {video_final}')
                    log_success(f'Você já pode apagar a pasta: {prepared.task.folder_path}')
                else:
                    log_error('Falha ao processar o vídeo final no FFmpeg.')
                    
            else:
                log_error(f'Atenção: Apenas {len(videos_gerados)} de {len(cenas)} vídeos foram gerados.')

        log_success('Fluxo de automação concluído com sucesso')
        input('Pressione ENTER para encerrar o navegador... ')

    except Exception as exc:
        log_error(f"Erro fatal: {str(exc)}")

    finally:
        if driver:
            close_driver(driver)


if __name__ == '__main__':
    main()
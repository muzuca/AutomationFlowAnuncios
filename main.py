# arquivo: main.py
# descricao: Orquestrador blindado. Sincroniza credenciais, carrega configuracoes,
# cria navegador e executa o fluxo completo. Possui LOOP INFINITO DE RETENTATIVAS
# com rodízio automático de contas em caso de qualquer falha no meio do processo.
from __future__ import annotations

import os
import logging
import sys
import time
import shutil
from pathlib import Path

from acesso_humble import executar_sincronizacao
from anuncios.processor import describe_task, get_next_pending_task, prepare_task
from config import get_settings
from integrations.browser import close_driver, create_driver
from integrations.gemini import GeminiAnunciosViaFlow
from integrations.google_login import login_google, open_gemini
from integrations.window_focus import dismiss_chrome_native_popup_with_retry
from integrations.flow import GoogleFlowAutomation, ler_e_separar_cenas
from integrations.video_manager import concatenar_cenas_720p, converter_para_1080p, limpar_arquivos_temporarios


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


def salvar_ultima_conta_env(index: int) -> None:
    """Atualiza ou insere a variável LAST_ACCOUNT_INDEX no arquivo .env"""
    try:
        env_path = Path('.env')
        if not env_path.exists():
            env_path.write_text(f"LAST_ACCOUNT_INDEX={index}\n", encoding='utf-8')
            return
        
        lines = env_path.read_text(encoding='utf-8').splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith("LAST_ACCOUNT_INDEX="):
                new_lines.append(f"LAST_ACCOUNT_INDEX={index}")
                found = True
            else:
                new_lines.append(line)
        
        if not found:
            new_lines.append(f"LAST_ACCOUNT_INDEX={index}")
            
        env_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
    except Exception as e:
        log_error(f"Aviso: Não foi possível salvar o índice da conta no .env: {e}")


def main() -> None:
    setup_logging()

    try:
        log_step('ETAPA 1: sincronizando credenciais HUMBLE')
        executar_sincronizacao()
        log_success('Credenciais prontas')

        log_step('ETAPA 2: carregando configuracoes do projeto')
        settings = get_settings()
        
        # --- PARÂMETROS GLOBAIS DO .ENV ---
        qtd_variantes = int(os.getenv("VIDEOS_POR_ANUNCIO", 1))
        qtd_cenas_anuncio = int(os.getenv("CENAS_POR_ANUNCIO", 3))
        
        log_success(f'Configuração ativa: {qtd_variantes} variante(s) de {qtd_cenas_anuncio} cena(s) cada.')

        log_step('ETAPA 3: procurando primeira tarefa pendente')
        task = get_next_pending_task(settings.products_base_dir)

        if task is None:
            log_success('Nenhuma tarefa pendente encontrada. Encerrando.')
            return

        log_success(f'Tarefa encontrada: {task.folder_path}')

        accounts = settings.accounts
        if not accounts:
            log_error("Nenhuma conta configurada nas settings. Encerrando.")
            return

        sucesso_absoluto = False
        
        # Inicia a contagem baseada na última conta salva no .env (ou 0)
        tentativa_atual = int(os.getenv("LAST_ACCOUNT_INDEX", "0"))
        falhas_consecutivas = 0

        # =========================================================================
        # O LOOP DE TITÂNIO: Roda infinitamente alternando as contas até dar certo
        # =========================================================================
        while not sucesso_absoluto:
            
            # Se todas as contas da fila falharem, roda o bot pra atualizar a planilha
            if falhas_consecutivas > 0 and falhas_consecutivas >= len(accounts):
                log_error("🚨 TODAS as contas do rodízio atual falharam! Reciclando contas...")
                try:
                    executar_sincronizacao()
                except Exception as e:
                    log_error(f"Erro ao ressincronizar contas: {e}")
                
                settings = get_settings()
                accounts = settings.accounts
                if not accounts:
                    log_error("Nenhuma conta encontrada após sincronizar. Encerrando.")
                    return
                
                tentativa_atual = 0
                falhas_consecutivas = 0
                salvar_ultima_conta_env(0)

            # Define qual será o e-mail da vez
            idx_conta = tentativa_atual % len(accounts)
            account = accounts[idx_conta]
            
            log_step("=====================================================================")
            log_step(f"▶ INICIANDO TENTATIVA {falhas_consecutivas + 1} | Conta [{idx_conta}]: {account.email}")
            log_step("=====================================================================")

            driver = None
            try:
                log_step('Preparando ambiente e navegador...')
                driver = create_driver(settings)
                
                login_google(driver, settings, account)
                dismiss_chrome_native_popup_with_retry(driver)
                
                open_gemini(driver, settings)
                fechar_popup_cromado_pos_gemini(driver)

                prepared = prepare_task(task)
                log_success(describe_task(prepared.task))

                caminho_txt = Path(prepared.task.folder_path) / "ROTEIRO_GERADO.txt"
                imagem_base_flow = None
                
                if prepared.candidate_product_assets:
                    primeira_imagem = prepared.candidate_product_assets[0].path
                    imagem_base_flow = primeira_imagem
                
                arquivo_ref = prepared.reference_asset.path if prepared.reference_asset else None
                
                # --- CHECKPOINT: IA (Validação e Roteiro) ---
                if not caminho_txt.exists():
                    arquivo_preco = prepared.price_asset.path if prepared.price_asset else None
                    if arquivo_preco: log_success(f'Arquivo de preco: {arquivo_preco.name}')
                    if arquivo_ref: log_success(f'Arquivo de referencia: {arquivo_ref.name}')

                    if not prepared.candidate_product_assets:
                        raise Exception('Nenhum candidato de imagem encontrado na tarefa')

                    log_step('ETAPA IA: Validando imagem e gerando POV / Roteiro')
                    url_gem = getattr(settings, 'gemini_url', 'https://gemini.google.com/app')
                    gemini = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)
                    
                    validada = gemini._validar_imagem_produto(primeira_imagem, timeout_resposta=40)

                    if validada:
                        log_success(f'Imagem aprovada como produto principal: {primeira_imagem.name}')
                        caminho_pov = gemini.executar_fluxo_imagem_pov(
                            tarefa=prepared.task,
                            foto_produto_escolhida=primeira_imagem,
                            max_tentativas=3,
                        )
                        
                        if caminho_pov:
                            log_success(f'Imagem POV validada e salva em: {caminho_pov.name}')
                            imagem_base_flow = caminho_pov
                            
                            arquivos_contexto = [caminho_pov]
                            if arquivo_preco: arquivos_contexto.append(arquivo_preco)
                            if arquivo_ref: arquivos_contexto.append(arquivo_ref)
                            
                            dados_anuncio = prepared.task.dados_anuncio if hasattr(prepared.task, 'dados_anuncio') else {}
                            
                            roteiro_bruto = gemini.treinar_e_gerar_roteiro(
                                arquivos=arquivos_contexto,
                                dados_produto=dados_anuncio,
                                arquivo_ref=arquivo_ref,
                                qtd_cenas=qtd_cenas_anuncio
                            )
                            
                            if roteiro_bruto and "TIMEOUT" not in roteiro_bruto and "ERRO" not in roteiro_bruto:
                                with open(caminho_txt, "w", encoding="utf-8") as f:
                                    f.write(roteiro_bruto)
                                log_success(f'Roteiro gerado: {caminho_txt.name}')
                            else:
                                raise Exception('Falha ao obter resposta útil de roteiro do Gemini')
                        else:
                            raise Exception('Nao foi possivel gerar uma imagem POV valida')
                    else:
                        raise Exception(f'Imagem reprovada como produto principal: {primeira_imagem.name}')
                else:
                    log_success(f'🚀 CHECKPOINT ROTEIRO ALCANÇADO: Pulando etapas de IA iniciais.')
                    caminho_pov_existente = Path(prepared.task.folder_path) / "POV_VALIDADO.png"
                    if caminho_pov_existente.exists():
                        imagem_base_flow = caminho_pov_existente

                # --- CHECKPOINT: GERAÇÃO FLOW ---
                log_step('ETAPA FLOW: Gerando Variantes')
                cenas = ler_e_separar_cenas(caminho_txt, qtd_cenas=qtd_cenas_anuncio)
                if len(cenas) == 0:
                    raise Exception("Nenhuma cena encontrada no roteiro gerado.")
                elif len(cenas) < qtd_cenas_anuncio:
                    log_error(f"Aviso: O roteiro gerou apenas {len(cenas)} cenas, mas {qtd_cenas_anuncio} eram esperadas.")
                    
                url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
                variantes_720p_geradas = []
                
                for v_idx in range(1, qtd_variantes + 1):
                    caminho_var_720p = Path(prepared.task.folder_path) / f"Variante_{v_idx}_720p.mp4"
                    
                    if caminho_var_720p.exists():
                        log_success(f'🚀 CHECKPOINT VARIANTE: Variante {v_idx} já existe!')
                        variantes_720p_geradas.append(caminho_var_720p)
                        continue

                    log_step(f'--- GERANDO VARIANTE {v_idx}/{qtd_variantes} ---')
                    driver.get("about:blank")
                    time.sleep(1)
                    
                    flow_bot = GoogleFlowAutomation(driver, url_flow=url_flw)
                    flow_bot.acessar_flow()
                    videos_cenas_parciais = []
                    
                    for c_idx, prompt_cena in enumerate(cenas, start=1):
                        flow_bot.clicar_novo_projeto()
                        if not flow_bot.configurar_parametros_video():
                            raise Exception(f"Falha ao configurar a interface para a Cena {c_idx}.")
                        
                        if imagem_base_flow and imagem_base_flow.exists():
                            flow_bot.anexar_imagem(imagem_base_flow)
                        
                        sucesso_geracao = flow_bot.enviar_prompt_e_aguardar(prompt_cena, timeout_geracao=300)
                        
                        if sucesso_geracao:
                            caminho_video = Path(prepared.task.folder_path) / f"var{v_idx}_cena_{c_idx}.mp4"
                            if flow_bot.baixar_video_gerado(caminho_video):
                                videos_cenas_parciais.append(caminho_video)
                            else:
                                raise Exception(f'Falha ao baixar a Cena {c_idx}')
                        else:
                            raise Exception(f'Falha ao gerar a Cena {c_idx} no Flow.')

                    if len(videos_cenas_parciais) == len(cenas):
                        if concatenar_cenas_720p(arquivos_mp4=videos_cenas_parciais, saida_path=caminho_var_720p):
                            variantes_720p_geradas.append(caminho_var_720p)
                            limpar_arquivos_temporarios(videos_cenas_parciais)
                        else:
                            raise Exception(f"Falha ao concatenar as cenas da Variante {v_idx}.")
                    else:
                        raise Exception(f'Variante {v_idx} falhou em gerar todas as cenas parciais.')

                if not variantes_720p_geradas:
                    raise Exception("Nenhuma variante foi gerada com sucesso.")

                # --- CHECKPOINT: JÚRI IA ---
                log_step('ETAPA JÚRI: Avaliação do Diretor de Arte (IA)')
                video_vencedor_720 = variantes_720p_geradas[0]
                
                if len(variantes_720p_geradas) > 1:
                    url_gem = getattr(settings, 'gemini_url', 'https://gemini.google.com/app')
                    gemini_juri = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)
                    gemini_juri.abrir_gemini()
                    
                    roteiro_texto = caminho_txt.read_text(encoding='utf-8')
                    video_vencedor_720 = gemini_juri.avaliar_melhor_variante_de_video(variantes_720p_geradas, roteiro_texto)
                        
                log_success(f'🎉 VARIANTE VENCEDORA: {video_vencedor_720.name}')

                # --- ETAPA FINAIS: UPSCALE E ORGANIZAÇÃO ---
                log_step('ETAPA FINAL: Upscale 1080p e Organização')
                nome_pasta = Path(prepared.task.folder_path).name
                video_final_1080 = Path(prepared.task.folder_path) / f"[01_ESCOLHIDO]_Anuncio_{nome_pasta}_1080p.mp4"
                
                sucesso_upscale = converter_para_1080p(entrada=video_vencedor_720, saida=video_final_1080)
                
                if not sucesso_upscale or not video_final_1080.exists():
                    raise Exception("Erro fatal no upscaling do FFmpeg. Arquivo final não foi gerado.")

                pasta_pendente = Path(prepared.task.folder_path)
                pasta_raiz_tarefas = pasta_pendente.parent.parent
                pasta_concluido = pasta_raiz_tarefas / "concluido" / nome_pasta
                pasta_concluido.mkdir(parents=True, exist_ok=True)
                
                # Cópia segura (Copy em vez de Move)
                for variante in variantes_720p_geradas:
                    if variante != video_vencedor_720:
                        shutil.copy2(str(variante), str(pasta_concluido / f"[02_ALTERNATIVA]_{variante.name}"))
                    else:
                        shutil.copy2(str(variante), str(pasta_concluido / f"[BACKUP_720p]_{variante.name}"))
                    
                for arquivo in pasta_pendente.iterdir():
                    if arquivo.is_file():
                        shutil.copy2(str(arquivo), str(pasta_concluido / arquivo.name))
                        
                # Apenas limpa O CONTEÚDO da pasta pendente, MANTENDO o diretório vivo.
                for f in pasta_pendente.iterdir():
                    if f.is_file(): 
                        f.unlink(missing_ok=True)
                # pasta_pendente.rmdir() <- Removido, a pasta continua existindo!
                
                log_success(f'Conteúdo da pasta {nome_pasta} movido para concluído. O diretório original ficou preservado e vazio.')
                
                # Grava a conta atual como vencedora e encerra o loop de retentativas
                salvar_ultima_conta_env(idx_conta)
                sucesso_absoluto = True 

            except Exception as exc:
                log_error(f"Falha na execução: {str(exc)}")
                log_step("Iniciando próximo rodízio de conta/tentativa instantaneamente...")
                falhas_consecutivas += 1
                tentativa_atual += 1

            finally:
                if driver:
                    close_driver(driver)
                    driver = None

        log_success('Fluxo de automação 100% concluído para esta tarefa!')
        input('Pressione ENTER para encerrar... ')

    except Exception as exc:
        log_error(f"Erro Crítico de Inicialização: {str(exc)}")


if __name__ == '__main__':
    main()
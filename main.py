# arquivo: main.py
# descricao: Orquestrador blindado. Sincroniza credenciais, carrega configuracoes,
# cria navegador e executa o fluxo completo. Possui LOOP INFINITO DE RETENTATIVAS
# com rodízio automático de contas em caso de falha.
# ATUALIZAÇÃO MODO WATCHER 24/7: Escuta pastas continuamente e SINCRONIZA AS 
# CREDENCIAIS SEMPRE que uma nova tarefa é encontrada, antes de iniciar.
from __future__ import annotations

import os
import logging
import sys
import time
import shutil
import re
from pathlib import Path
from datetime import datetime

from acesso_humble import executar_sincronizacao
from anuncios.processor import describe_task, get_next_pending_task, prepare_task
# ADICIONADO: Captura de exceção específica de anexo
from selenium.common.exceptions import TimeoutException
from config import get_settings
from integrations.browser import close_driver, create_driver
from integrations.gemini import GeminiAnunciosViaFlow
from integrations.google_login import login_google, open_gemini
from integrations.window_focus import dismiss_chrome_native_popup_with_retry, fechar_popup_cromado_pos_gemini
from integrations.flow import GoogleFlowAutomation, ler_e_separar_cenas
from integrations.video_manager import concatenar_cenas_720p, converter_para_1080p, limpar_arquivos_temporarios
from anuncios.prompts import PROMPT_GERACAO_IMAGEM_CAMINHANDO, PROMPT_GERACAO_IMAGEM_FLAT, PROMPT_GERACAO_IMAGEM_FRONTAL, PROMPT_GERACAO_IMAGEM_PES, PROMPT_GERACAO_IMAGEM_POV
# 🚨 IMPORTAÇÕES DE UTILS PADRONIZADAS
from integrations.utils import (
    setup_logging,
    _log, 
    log_step,          
    log_success,       
    log_error,
    limpar_diretorio_visao, 
    limpar_residuos_proxy,
    formatar_roteiro_limpo,
    salvar_bloco_unificado,
    extrair_e_salvar_legenda,
    salvar_ultima_conta_env
)

def main() -> None:
    setup_logging()

    try:
        log_step('🚀 INICIANDO MODO WATCHER (MONITORAMENTO 24/7)')
        log_step('ETAPA 1: sincronizando credenciais HUMBLE iniciais')
        executar_sincronizacao()
        log_success('Credenciais prontas')
        
        limpar_diretorio_visao()
        limpar_residuos_proxy()

        em_espera = False

        # =========================================================================
        # O LOOP DE ESCUTA INFINITA: Fica rodando 24/7 monitorando as pastas
        # =========================================================================
        while True:
            try:
                settings = get_settings()
                
                # --- PARÂMETROS GLOBAIS DO .ENV (Lidos a cada ciclo para permitir updates em tempo real) ---
                qtd_variantes = int(os.getenv("VIDEOS_POR_ANUNCIO", 1))
                qtd_cenas_anuncio = int(os.getenv("CENAS_POR_ANUNCIO", 3))
                qtd_roteiros = int(os.getenv("ROTEIROS_POR_ANUNCIO", 1))
                fonte_imagem = os.getenv("IMAGE_GENERATOR_SOURCE", "GEMINI").upper() # NOVO: GEMINI OU FLOW
                diretorio_anuncios_raiz = Path(os.getenv("ANUNCIOS_DIR", "G:/Meu Drive/Anuncios"))
                
                task = get_next_pending_task(settings.products_base_dir)
            except Exception as e_watcher:
                # SE O DRIVE PISCAR (G:\ sumir), O ROBÔ CAI AQUI, ESPERA 15s E TENTA DE NOVO.
                if not em_espera:
                    log_error(f"Aviso de instabilidade na leitura da pasta (Drive offline?): {e_watcher}")
                time.sleep(15)
                continue

            # VALIDAÇÃO CRÍTICA: Ignora a pasta se ela estiver vazia de arquivos brutos
            tem_arquivos_validos = False
            if task is not None:
                for asset in task.assets:
                    if asset.is_image or asset.is_video:
                        tem_arquivos_validos = True
                        break

            if task is None or not tem_arquivos_validos:
                if not em_espera:
                    log_step('ZzZz Nenhuma tarefa pendente com arquivos encontrada. Aguardando novas inserções...')
                    em_espera = True
                
                time.sleep(10) # Dorme por 10 segundos antes de olhar a pasta novamente
                continue

            # ACORDA E INICIA O PROCESSAMENTO DA TAREFA
            em_espera = False
            
            # A cada nova tarefa encontrada, zera a pasta de logs para manter o foco na tarefa atual
            #limpar_diretorio_visao()
            
            log_step("=====================================================================")
            log_success(f'NOVA TAREFA ENCONTRADA: {task.folder_path}')
            
            # --- NOVA LÓGICA DE SINCRONIZAÇÃO A CADA TAREFA ---
            log_step('🔄 Sincronizando credenciais HUMBLE frescas para esta tarefa...')
            try:
                executar_sincronizacao()
                settings = get_settings() # Recarrega as contas fresquinhas do .env atualizado
                log_success('Credenciais atualizadas com sucesso.')
            except Exception as e:
                log_error(f"Aviso: Falha ao ressincronizar credenciais agora. Usando as anteriores. Detalhe: {e}")
                
            log_step("=====================================================================")
            log_success(f'Configuração ativa: {qtd_roteiros} roteiro(s) com {qtd_variantes} variante(s) de {qtd_cenas_anuncio} cena(s) cada.')

            accounts = settings.accounts
            if not accounts:
                log_error("Nenhuma conta configurada nas settings. Pausando...")
                time.sleep(30)
                continue

            sucesso_absoluto_tarefa = False
            
            # Inicia a contagem baseada no último e-mail salvo no .env
            ultimo_email = os.getenv("LAST_ACCOUNT_INDEX", "").strip().lower()
            tentativa_atual = 0
            
            if ultimo_email and ultimo_email != "0":
                for i, acc in enumerate(accounts):
                    if acc.email.strip().lower() == ultimo_email:
                        tentativa_atual = i
                        break
                        
            falhas_consecutivas = 0

            # =========================================================================
            # O LOOP DE TITÂNIO DA TAREFA: Roda alternando as contas até a tarefa atual dar certo
            # =========================================================================
            while not sucesso_absoluto_tarefa:
                
                # Se todas as contas da fila falharem, roda o bot pra atualizar a planilha
                if falhas_consecutivas > 0 and falhas_consecutivas >= len(accounts):
                    log_error("🚨 TODAS as contas do rodízio atual falharam para esta tarefa! Reciclando contas...")
                    try:
                        executar_sincronizacao()
                    except Exception as e:
                        log_error(f"Erro ao ressincronizar contas: {e}")
                    
                    settings = get_settings()
                    accounts = settings.accounts
                    if not accounts:
                        log_error("Nenhuma conta encontrada após sincronizar. Abortando tentativa da tarefa atual.")
                        break # Quebra o loop da tarefa atual, volta pro Watcher
                    
                    tentativa_atual = 0
                    falhas_consecutivas = 0
                    salvar_ultima_conta_env(accounts[0].email)

                # Define qual será o e-mail da vez
                idx_conta = tentativa_atual % len(accounts)
                account = accounts[idx_conta]
                
                log_step(f"▶ INICIANDO TENTATIVA {falhas_consecutivas + 1} | Conta [{idx_conta}]: {account.email}")

                driver = None
                try:
                    log_step('Preparando ambiente e navegador...')
                    driver = create_driver(settings)
                    
                    login_google(driver, settings, account)
                    dismiss_chrome_native_popup_with_retry(driver)
                    
                    # --- CONFIGURAÇÃO DA IA ---
                    salvar_ultima_conta_env(account.email)
                    url_gem = getattr(settings, 'gemini_url', 'https://gemini.google.com/app/pt')
                    gemini = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)

                    # ACIONAMENTO DO TANQUE: Aqui ele vai abrir, checar bloqueios e usar o trator
                    gemini.abrir_gemini() 
                    
                    # Validação de popups nativos logo após o trator agir
                    fechar_popup_cromado_pos_gemini(driver)

                    # =====================================================================
                    # ETAPA IA-0: CLASSIFICAÇÃO INTELIGENTE E OCR (EXTRAÇÃO DE DADOS)
                    # =====================================================================
                    pasta_task = Path(task.folder_path)
                    caminho_metadados = pasta_task / "metadados.txt"

                    # Trava de segurança dupla: Verifica se os arquivos de fato já foram renomeados
                    arquivos_ja_renomeados = any(f.name.startswith("Base_Produto") for f in pasta_task.iterdir() if f.is_file())

                    if not caminho_metadados.exists() or not arquivos_ja_renomeados:
                        log_step('ETAPA IA-0: Organizando arquivos e extraindo metadados de venda')
                        # Pega apenas os arquivos crus (ignora arquivos ocultos e coisas já geradas)
                        arquivos_brutos = [f for f in pasta_task.iterdir() if f.is_file() and not f.name.startswith('.') and "roteiro" not in f.name.lower() and "ia_" not in f.name.lower() and "metadados" not in f.name.lower()]                        

                        if len(arquivos_brutos) >= 2:
                            # 🚨 CORREÇÃO: Pulo de conta se o anexo falhar no OCR
                            try:
                                dados_ia = gemini.classificar_arquivos_e_extrair_dados(arquivos_brutos)
                            except Exception as e:
                                if "Timeout" in str(e) or "anexar" in str(e).lower():
                                    raise Exception(f"SWITCH_ACCOUNT: Falha anexo OCR na conta {account.email}")
                                raise e
                            
                            if dados_ia:
                                log_success('IA classificou os arquivos e extraiu os dados!')
                                mapa_arquivos = {f.name.lower(): f for f in arquivos_brutos}

                                # 1. Renomeia os arquivos focando SÓ no nome base, ignorando extensões
                                def renomear_seguro(chave_json, prefixo):
                                    nome_ia = str(dados_ia.get(chave_json, "")).strip().lower()
                                    if not nome_ia:
                                        return
                                    
                                    base_ia = Path(nome_ia).stem 
                                    
                                    for nome_real, arq_obj in list(mapa_arquivos.items()):
                                        base_real = arq_obj.stem.lower()
                                        if base_ia == base_real or base_ia in base_real:
                                            if not arq_obj.name.startswith(prefixo):
                                                novo_nome = f"{prefixo}_{arq_obj.name}"
                                                novo_caminho = arq_obj.parent / novo_nome
                                                arq_obj.rename(novo_caminho)
                                                
                                                log_success(f'Arquivo renomeado: {arq_obj.name} -> {novo_nome}')
                                                
                                                mapa_arquivos[novo_nome.lower()] = Path(novo_caminho)
                                                del mapa_arquivos[nome_real]
                                            break

                                renomear_seguro('arquivo_produto', 'Base_Produto')
                                renomear_seguro('arquivo_preco', 'Ref_Preco')
                                renomear_seguro('arquivo_referencia', 'Ref_Extra')

                                # 2. Salva o TXT com a riqueza de detalhes
                                conteudo_txt = (
                                    f"NOME_REAL: {dados_ia.get('nome_produto', 'Não lido')}\n"
                                    f"NOME_RESUMIDO: {dados_ia.get('nome_resumido', 'ProdutoGenerico')}\n"
                                    f"PRECO_E_CONDICOES: {dados_ia.get('preco_condicoes', 'Não lido')}\n"
                                    f"BENEFICIOS_EXTRAS: {dados_ia.get('beneficios', 'Não lido')}\n"
                                )
                                caminho_metadados.write_text(conteudo_txt, encoding='utf-8')
                            else:
                                raise Exception("IA falhou ao gerar o JSON de classificação de arquivos.")
                        else:
                            log_step("Aviso: Poucos arquivos na pasta para classificação IA. Seguindo fluxo normal...")

                    # 3. Injeta os dados riquíssimos do TXT direto na variável da Tarefa
                    # 3.1. Primeiro você estabiliza qual é a tarefa definitiva e prepara os assets
                    task = get_next_pending_task(settings.products_base_dir)
                    prepared = prepare_task(task)
                    log_success(describe_task(prepared.task))

                    # 3.2. SÓ AGORA você injeta os dados do metadados.txt (para nada sobrescrever eles)
                    pasta_task = Path(task.folder_path)
                    caminho_metadados = pasta_task / "metadados.txt"

                    if caminho_metadados.exists():
                        txt_lines = caminho_metadados.read_text(encoding='utf-8').splitlines()
                        for line in txt_lines:
                            if line.startswith('NOME_REAL:'):
                                task.dados_anuncio['nome_produto'] = line.replace('NOME_REAL:', '').strip()
                            if line.startswith('NOME_RESUMIDO:'):
                                task.dados_anuncio['nome_resumido'] = line.replace('NOME_RESUMIDO:', '').strip()
                            if line.startswith('PRECO_E_CONDICOES:'):
                                task.dados_anuncio['preco'] = line.replace('PRECO_E_CONDICOES:', '').strip()
                            if line.startswith('BENEFICIOS_EXTRAS:'):
                                task.dados_anuncio['beneficios_extras'] = line.replace('BENEFICIOS_EXTRAS:', '').strip()
                    
                    arquivos_produto = list(pasta_task.glob("Base_Produto*"))
                    if arquivos_produto:
                        primeira_imagem = arquivos_produto[0]
                    elif prepared.candidate_product_assets:
                        primeira_imagem = prepared.candidate_product_assets[0].path
                    else:
                        raise Exception('Nenhum candidato de imagem de produto encontrado na tarefa')
                    
                    arquivo_ref = list(pasta_task.glob("Ref_Extra*"))[0] if list(pasta_task.glob("Ref_Extra*")) else prepared.reference_asset.path if prepared.reference_asset else None
                    arquivo_preco = list(pasta_task.glob("Ref_Preco*"))[0] if list(pasta_task.glob("Ref_Preco*")) else prepared.price_asset.path if prepared.price_asset else None

                    if arquivo_preco:
                        log_success(f'Arquivo de preco mapeado: {arquivo_preco.name}')
                    if arquivo_ref:
                        log_success(f'Arquivo de referencia mapeado: {arquivo_ref.name}')

                    # --- IDENTIFICAÇÃO DO TIPO DE PASTA ---
                    partes_caminho_task = Path(prepared.task.folder_path).parts
                    estilo_filmagem_pasta = partes_caminho_task[-2] if len(partes_caminho_task) >= 2 else ""

                    # --- CHECKPOINT INTELIGENTE: EXISTE AO MENOS UM ROTEIRO? (Atualizado para roteiros.txt) ---
                    tem_roteiro_pronto = False
                    caminho_roteiros_unificado = Path(task.folder_path) / "roteiros.txt"
                    
                    if caminho_roteiros_unificado.exists():
                        conteudo_check = caminho_roteiros_unificado.read_text(encoding='utf-8')
                        for r_idx_check in range(1, qtd_roteiros + 1):
                            if f"=== ROTEIRO {r_idx_check} ===" in conteudo_check and len(conteudo_check) > 500:
                                tem_roteiro_pronto = True
                                break
                    
                    if tem_roteiro_pronto:
                        log_success("🚀 CHECKPOINT: Roteiro detectado no arquivo unificado. Pulando login no Gemini e indo pro Flow.")
                        precisa_abrir_gemini = False
                        
                        # Define a imagem base para o Flow (usa a ImgBase do Roteiro 1 ou o padrão)
                        imagem_base_flow = Path(task.folder_path) / "IA_Roteiro1.png"
                        if not imagem_base_flow.exists():
                            imagem_base_flow = Path(task.folder_path) / "IA_Base.png"
                    else:
                        precisa_abrir_gemini = True

                    # --- BLOCO COM TRAVA DE CHECKPOINT ---
                    if precisa_abrir_gemini:
                        open_gemini(driver, settings)
                        fechar_popup_cromado_pos_gemini(driver)

                        # --- NOVA LÓGICA DE VALIDAÇÃO DE PRODUTO COM O BYPASS DO .ENV ---
                        pular_validacao = os.getenv('IGNORAR_VALIDACAO_PRODUTO', 'False').lower() == 'true'
                        
                        if pular_validacao:
                            log_success("⏭️ Validação visual do produto pelo Gemini ignorada (Flag .env ativa). Aprovando direto.")
                            produto_valido = True
                        else:
                            log_step('ETAPA IA: Validando candidato a produto original...')
                            # 🚨 CORREÇÃO: Pulo de conta se o anexo falhar na validação
                            try:
                                produto_valido = gemini._validar_imagem_produto(primeira_imagem, timeout_resposta=60)
                            except Exception as e:
                                if "Timeout" in str(e) or "anexar" in str(e).lower():
                                    raise Exception(f"SWITCH_ACCOUNT: Falha anexo validação na conta {account.email}")
                                raise e

                        if not produto_valido:
                            # --- TRATAMENTO DE EXCEÇÃO (DESCARTE RÁPIDO) ---
                            log_error(f'A imagem foi reprovada pela IA (ou erro de leitura): {primeira_imagem.name}')
                            log_step("🛑 Tarefa abortada por rejeição de imagem. Movendo para 'concluido' como REPROVADO.")
                            
                            try:
                                nome_prod_raw = task.dados_anuncio.get('nome_resumido') or task.dados_anuncio.get('nome_produto') or f"Produto_{id_original}"
                                nome_prod_slug = re.sub(r'[^\w]', '', nome_prod_raw).title()
                                
                                partes_origem = pasta_task.parts
                                estilo_ref = re.sub(r'[^\w]', '', partes_origem[-2]) if len(partes_origem) >= 2 else "Estilo" 
                                modelo_ref = partes_origem[-3] if len(partes_origem) >= 3 else "Modelo"
                                id_original = str(partes_origem[-1])
                                
                                nome_pasta_reprovada = f"{modelo_ref}_{estilo_ref}_{nome_prod_slug}_{id_original}_REPROVADO"
                                destino_reprovado = diretorio_anuncios_raiz / nome_pasta_reprovada
                                destino_reprovado.mkdir(parents=True, exist_ok=True)
                                
                                # Esvazia a pasta original e move pra reprovados
                                for arquivo in pasta_task.iterdir():
                                    if arquivo.is_file():
                                        shutil.copy2(str(arquivo), str(destino_reprovado / arquivo.name))
                                        arquivo.unlink(missing_ok=True)
                                        
                                log_success(f"Tarefa arquivada com sucesso em: {destino_reprovado}")
                            except Exception as e:
                                log_error(f"Aviso: Não foi possível mover a pasta reprovada: {e}")

                            # Finge sucesso absoluto para quebrar o loop de tentativas e não penalizar a conta
                            sucesso_absoluto_tarefa = True 
                            continue # Pula para o 'finally', fecha o navegador e o Watcher puxa a próxima pasta
                            # ------------------------------------------------

                        log_success(f'Imagem base do produto aprovada: {primeira_imagem.name}')
                    else:
                        log_success("🚀 Fluxo de Checkpoint: Ignorando Etapas Gemini.")

                    # =========================================================================
                    # 🚀 DEFINIÇÃO DO DIRETÓRIO DE ENTREGA (SÓ CRIARÁ A PASTA NO FINAL)
                    # =========================================================================
                    nome_resumido = task.dados_anuncio.get('nome_resumido', 'ProdutoGenerico')
                    nome_prod_slug = re.sub(r'[^\w]', '', nome_resumido).title()
                    
                    partes_origem = pasta_task.parts
                    estilo_ref = re.sub(r'[^\w]', '', partes_origem[-2]) if len(partes_origem) >= 2 else "Estilo" 
                    modelo_ref = partes_origem[-3] if len(partes_origem) >= 3 else "Modelo"
                    id_original = str(partes_origem[-1])
                    
                    nome_pasta_final = f"{modelo_ref}_{estilo_ref}_{nome_prod_slug}_{id_original}"
                    pasta_entrega = diretorio_anuncios_raiz / nome_pasta_final
                    log_step(f"📂 Diretório de entrega mapeado para o final do processo: {pasta_entrega.name}")

                    roteiros_anteriores_textos = []

                    # =========================================================================
                    # LOOP DE TESTE A/B (MÚLTIPLOS ROTEIROS) E GERAÇÃO DO FLOW
                    # =========================================================================
                    for r_idx in range(1, qtd_roteiros + 1):
                        sufixo_rot = f"Roteiro{r_idx}"
                        caminho_roteiros_unificado = Path(task.folder_path) / "roteiros.txt"
                        caminho_legendas_unificado = Path(task.folder_path) / "legendas.txt"
                        caminho_img_base_roteiro = Path(task.folder_path) / f"IA_{sufixo_rot}.png"

                        # --- CHECKPOINT MESTRE: SE O VÍDEO FINAL JÁ EXISTE NA ENTREGA, PULA TUDO DESSE ROTEIRO ---
                        arquivos_1080_existentes = list(pasta_entrega.glob(f"Video_R{r_idx}v*.mp4"))
                        if arquivos_1080_existentes:
                            log_success(f'🚀 CHECKPOINT FINAL ALCANÇADO: Vídeo(s) do {sufixo_rot} já existem em {pasta_entrega.name}.')
                            
                            if caminho_roteiros_unificado.exists():
                                cont_total = caminho_roteiros_unificado.read_text(encoding='utf-8')
                                if f"=== ROTEIRO {r_idx} ===" in cont_total:
                                    bloco = cont_total.split(f"=== ROTEIRO {r_idx} ===")[1]
                                    bloco = bloco.split("\n===")[0] if "\n===" in bloco else bloco
                                    roteiros_anteriores_textos.append(bloco.strip())
                            
                            continue 

                        # --- CHECKPOINT IMAGEM BASE INDIVIDUAL POR ROTEIRO ---
                        imagem_base_flow = None
                        if caminho_img_base_roteiro.exists():
                            log_success(f'🚀 CHECKPOINT IMAGEM BASE ALCANÇADO: {caminho_img_base_roteiro.name} já existe.')
                            imagem_base_flow = caminho_img_base_roteiro
                        else:
                            log_step(f'Gerando Imagem Base para {sufixo_rot}...')
                            if fonte_imagem == "FLOW":
                                url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
                                flow_bot_img = GoogleFlowAutomation(driver, url_flow=url_flw)
                                
                                # --- BUSCA DE IDENTIDADE (MODELO) VIA .ENV ---
                                path_task = Path(prepared.task.folder_path)
                                # Sobe níveis para achar o nome da pasta pai (Ex: LaraSelect)
                                nome_identidade = task.model_name
                                
                                # Tenta achar o arquivo na pasta configurada no .env
                                foto_modelo = Path(settings.modelos_dir) / f"{nome_identidade}.png"
                                if not foto_modelo.exists():
                                    foto_modelo = Path(settings.modelos_dir) / f"{nome_identidade}.jpg"
                                
                                cam_modelo_param = foto_modelo if foto_modelo.exists() else None
                                if cam_modelo_param:
                                    log_success(f"Modelo identificado via .env: {foto_modelo.name}")
                                # ---------------------------------------------

                                # --- PREPARAÇÃO DOS DADOS PARA OS NOVOS PROMPTS ---
                                dados_anuncio = prepared.task.dados_anuncio
                                nome_prod = dados_anuncio.get('nome_produto', 'produto')

                                # Busca os dicionários que o processor carregou
                                descricoes = getattr(prepared.task, 'descricoes_prompts', {})
                                perfil_modelo = descricoes.get('modelo', {})
                                perfil_filmagem = descricoes.get('filmagem', {})

                                # 1. desc_maos (Vem do perfil da modelo no processor)
                                desc_maos = perfil_modelo.get('maos', 'mãos femininas delicadas, unhas bem cuidadas')

                                # 2. desc_estilo (Vem das regras de filmagem ou fallback premium)
                                desc_estilo = perfil_filmagem.get('estilo_visual', 'lifestyle premium, cinematográfico, alta nitidez')

                                # 3. contexto_produto (Vem dos benefícios do produto ou fallback de cenário)
                                contexto_produto = dados_anuncio.get('beneficios', 'ambiente elegante e moderno condizente com o produto')

                                # --- SELETOR DINÂMICO DE PROMPT POR CATEGORIA ---
                                pasta_estilo = estilo_filmagem_pasta.lower()

                                if "frontal" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_GERACAO_IMAGEM_FRONTAL.format(
                                        nome_produto=nome_prod,
                                        contexto_produto=contexto_produto,
                                        desc_estilo=desc_estilo
                                    )
                                elif "caminhando" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_GERACAO_IMAGEM_CAMINHANDO.format(
                                        nome_produto=nome_prod,
                                        desc_estilo=desc_estilo
                                    )
                                elif "pes" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_GERACAO_IMAGEM_PES.format(
                                        nome_produto=nome_prod,
                                        contexto_produto=contexto_produto,
                                        desc_estilo=desc_estilo
                                    )
                                elif "flat" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_GERACAO_IMAGEM_FLAT.format(
                                        nome_produto=nome_prod,
                                        contexto_produto=contexto_produto,
                                        desc_estilo=desc_estilo
                                    )
                                else:
                                    # PROMPT_GERACAO_IMAGEM_POV pede nome_produto e desc_maos
                                    prompt_img_base_flow = PROMPT_GERACAO_IMAGEM_POV.format(
                                        nome_produto=nome_prod,
                                        desc_maos=desc_maos
                                    )
                                
                                try:
                                    pasta_tarefa = Path(prepared.task.folder_path)
                                    cand_a = pasta_tarefa / f"ImgCand_A_{sufixo_rot}.png"
                                    cand_b = pasta_tarefa / f"ImgCand_B_{sufixo_rot}.png"
                                    
                                    if cand_a.exists(): cand_a.unlink()
                                    if cand_b.exists(): cand_b.unlink()
                                    
                                    # 1. Gera Variante A (Passando o caminho_modelo)
                                    log_step(f"Gerando Imagem Base Variante A ({sufixo_rot}) no Flow...")
                                    flow_bot_img.gerar_imagem_base(
                                        caminho_referencia=primeira_imagem,
                                        prompt=prompt_img_base_flow,
                                        caminho_saida=cand_a,
                                        caminho_modelo=cam_modelo_param 
                                    )
                                    
                                    # 2. Gera Variante B (Passando o caminho_modelo)
                                    log_step(f"Gerando Imagem Base Variante B ({sufixo_rot}) no Flow...")
                                    flow_bot_img.gerar_imagem_base(
                                        caminho_referencia=primeira_imagem,
                                        prompt=prompt_img_base_flow + " Ultra realistic details, subtle dynamic lighting shift.",
                                        caminho_saida=cand_b,
                                        caminho_modelo=cam_modelo_param
                                    )
                                    
                                    # 3. Avaliação no Gemini
                                    log_step("Enviando Variantes para o Diretor de Arte (Gemini) escolher a melhor...")
                                    gemini_juri = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=60)
                                    gemini_juri.abrir_gemini()
                                    
                                    # 🚨 CORREÇÃO: Pulo de conta se o anexo falhar no Júri
                                    try:
                                        melhor_img_base = gemini_juri.avaliar_melhor_imagem_base(cand_a, cand_b, nome_prod, estilo_filmagem_pasta)
                                    except Exception as e:
                                        if "Timeout" in str(e) or "anexar" in str(e).lower():
                                            raise Exception(f"SWITCH_ACCOUNT: Falha anexo Júri na conta {account.email}")
                                        raise e
                                    
                                    shutil.copy2(str(melhor_img_base), str(caminho_img_base_roteiro))
                                    log_success(f'Imagem Base gerada e validada via FLOW para {sufixo_rot}: {caminho_img_base_roteiro.name}')
                                    
                                    cand_a.unlink(missing_ok=True)
                                    cand_b.unlink(missing_ok=True)
                                    
                                    imagem_base_flow = caminho_img_base_roteiro
                                    
                                except Exception as e:
                                    if "SWITCH_ACCOUNT" in str(e): raise e
                                    log_error(f"Erro no fluxo A/B de imagem FLOW/GEMINI: {e}")
                                    raise Exception(f'Falha fatal ao gerar Imagem Base para {sufixo_rot} via FLOW')
                            else:
                                log_step(f'ETAPA IA: Gerando e curando Imagem Base para {sufixo_rot} via GEMINI...')
                                nova_img_base = gemini.executar_fluxo_imagem_base(
                                    tarefa=prepared.task,
                                    foto_produto_escolhida=primeira_imagem,
                                    max_versoes=3,
                                    numero_roteiro=r_idx
                                )
                                if nova_img_base:
                                    nova_img_base.rename(caminho_img_base_roteiro)
                                    log_success(f'Imagem Base validada pelo Júri para {sufixo_rot}: {caminho_img_base_roteiro.name}')
                                    imagem_base_flow = caminho_img_base_roteiro
                                else:
                                    raise Exception(f'Falha fatal ao gerar Imagem Base para {sufixo_rot}')

                        # --- CHECKPOINT: IA ROTEIRO (NOVO MODELO DE ARQUIVO UNIFICADO) ---
                        precisa_gerar_roteiro = True
                        texto_roteiro_atual = ""
                        
                        if caminho_roteiros_unificado.exists():
                            conteudo_total = caminho_roteiros_unificado.read_text(encoding='utf-8')
                            marcador_roteiro = f"=== ROTEIRO {r_idx} ==="
                            
                            if marcador_roteiro in conteudo_total:
                                bloco = conteudo_total.split(marcador_roteiro)[1]
                                bloco = bloco.split("\n===")[0] if "\n===" in bloco else bloco
                                
                                if len(bloco.strip()) < 500 or not re.search(r'\[[Cc]ena\s*1', bloco):
                                    log_error(f'⚠️ Roteiro {r_idx} pequeno ou sem cenas válidas no arquivo unificado. Regerando...')
                                else:
                                    log_success(f'🚀 CHECKPOINT ROTEIRO ALCANÇADO: Roteiro {r_idx} já existe em roteiros.txt.')
                                    precisa_gerar_roteiro = False
                                    texto_roteiro_atual = bloco.strip()

                        if precisa_gerar_roteiro:
                            log_step(f'ETAPA IA: Gerando roteiro para {sufixo_rot} ({r_idx}/{qtd_roteiros})...')
                            
                            arquivos_contexto = [imagem_base_flow]
                            if arquivo_preco:
                                arquivos_contexto.append(arquivo_preco)
                            if arquivo_ref:
                                arquivos_contexto.append(arquivo_ref)
                            
                            dados_anuncio = prepared.task.dados_anuncio if hasattr(prepared.task, 'dados_anuncio') else {}
                            
                            # 🚨 CORREÇÃO: Pulo de conta se o anexo falhar no Roteiro
                            try:
                                roteiro_bruto = gemini.treinar_e_gerar_roteiro(
                                    arquivos=arquivos_contexto,
                                    dados_produto=dados_anuncio,
                                    arquivo_ref=arquivo_ref,
                                    qtd_cenas=qtd_cenas_anuncio,
                                    roteiros_anteriores=roteiros_anteriores_textos,
                                    tarefa_obj=prepared.task
                                )
                                roteiro_limpo = formatar_roteiro_limpo(roteiro_bruto)
                            except Exception as e:
                                if "Timeout" in str(e) or "anexar" in str(e).lower():
                                    raise Exception(f"SWITCH_ACCOUNT: Falha anexo roteiro na conta {account.email}")
                                raise e

                            # 🚨 SALVA NO ARQUIVO UNIFICADO
                            salvar_bloco_unificado(caminho_roteiros_unificado, f"ROTEIRO {r_idx}", roteiro_limpo)
                            texto_roteiro_atual = roteiro_limpo
                            log_success(f'Roteiro {r_idx} gerado e anexado ao roteiros.txt')
                            salvar_ultima_conta_env(account.email)

                        # Extrai a legenda e salva no arquivo unificado legendas.txt
                        extrair_e_salvar_legenda(texto_roteiro_atual, caminho_legendas_unificado, r_idx)
                        roteiros_anteriores_textos.append(texto_roteiro_atual)

                        # --- ETAPA FLOW: GERAÇÃO DE VARIANTES ---
                        log_step(f'ETAPA FLOW: Gerando {qtd_variantes} Variantes para {sufixo_rot}')
                        
                        cenas = ler_e_separar_cenas(caminho_roteiros_unificado, num_roteiro=r_idx, qtd_cenas=qtd_cenas_anuncio)
                        
                        if not cenas:
                            log_error(f"O arquivo roteiros.txt não retornou cenas válidas! Deletando lixo do Gemini...")
                            caminho_roteiros_unificado.unlink(missing_ok=True) # DELETA PARA SAIR DO LOOP INFINITO
                            raise Exception("Lista de cenas vazia. O arquivo de roteiro era inválido.")
                            
                        url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
                        
                        for v_idx in range(1, qtd_variantes + 1):
                            nome_video_final = f"Video_R{r_idx}v{v_idx}.mp4"
                            # Salva LOCALMENTE primeiro na pasta de origem
                            caminho_final_1080 = Path(task.folder_path) / nome_video_final
                            
                            # Verifica se já está na pasta de entrega ou localmente
                            if (pasta_entrega / nome_video_final).exists() or caminho_final_1080.exists():
                                log_success(f'🚀 CHECKPOINT VARIANTE: {nome_video_final} já existe!')
                                continue

                            driver.get("about:blank")
                            time.sleep(1)
                            
                            flow_bot = GoogleFlowAutomation(driver, url_flow=url_flw)
                            flow_bot.acessar_flow()
                            videos_cenas_parciais = []
                            
                            for c_idx, prompt_cena in enumerate(cenas, start=1):
                                log_step(f"🎬 [DEBUG] Roteiro: {sufixo_rot} | Cena {c_idx} | Texto: {prompt_cena[:50]}...")
                                flow_bot.clicar_novo_projeto()
                                flow_bot.configurar_parametros_video()
                                
                                if imagem_base_flow:
                                    flow_bot.anexar_imagem(imagem_base_flow)
                                
                                sucesso_geracao = flow_bot.enviar_prompt_e_aguardar(prompt_cena, timeout_geracao=300)
                                
                                if sucesso_geracao:
                                    caminho_video = Path(task.folder_path) / f"temp_R{r_idx}v{v_idx}c{c_idx}.mp4"
                                    if flow_bot.baixar_video_gerado(caminho_video):
                                        videos_cenas_parciais.append(caminho_video)
                                    else:
                                        raise Exception(f'Falha download Cena {c_idx}')
                                else:
                                    raise Exception(f'Falha gerar Cena {c_idx} no Flow.')

                            if len(videos_cenas_parciais) == len(cenas):
                                var_720_temp = Path(task.folder_path) / f"temp_concat_R{r_idx}V{v_idx}.mp4"
                                if concatenar_cenas_720p(videos_cenas_parciais, var_720_temp):
                                    
                                    # 🚀 CONVERSÃO OBRIGATÓRIA PARA 1080P DE TODAS AS VARIANTES (SEM JÚRI)
                                    log_step(f"Realizando upscale local para 1080p: {nome_video_final}")
                                    if converter_para_1080p(var_720_temp, caminho_final_1080):
                                        log_success(f"✅ Vídeo convertido localmente: {nome_video_final}")
                                    else:
                                        log_error(f"Erro FFmpeg upscale. Copiando original 720p...")
                                        shutil.copy2(str(var_720_temp), str(caminho_final_1080.with_name(f"Video_R{r_idx}v{v_idx}_720p.mp4")))
                                        
                                    limpar_arquivos_temporarios(videos_cenas_parciais + [var_720_temp])
                                else:
                                    raise Exception("Falha ao concatenar cenas.")

                    # =========================================================================
                    # 🚀 ENTREGA FINAL: MOVE TUDO PARA A PASTA DE ANUNCIOS E LIMPA A ORIGEM
                    # =========================================================================
                    log_step(f"🏆 Concluído! Movendo todos os arquivos gerados para: {pasta_entrega.name}")
                    pasta_entrega.mkdir(parents=True, exist_ok=True)
                    
                    for item_final in Path(prepared.task.folder_path).iterdir():
                        if item_final.is_file():
                            shutil.copy2(str(item_final), str(pasta_entrega / item_final.name))
                            item_final.unlink(missing_ok=True)
                    
                    log_success(f'TAREFA CONCLUÍDA! O diretório de origem ficou vazio.')
                    
                    salvar_ultima_conta_env(account.email)
                    sucesso_absoluto_tarefa = True

                except Exception as exc:
                    log_error(f"Falha na execução: {str(exc)}")
                    log_step("Encerrando driver e trocando de conta para próxima tentativa...")
                    falhas_consecutivas += 1
                    tentativa_atual += 1

                finally:
                    if driver:
                        close_driver(driver)
                        driver = None
                        
            # Fim do Loop da Tarefa (sucesso_absoluto_tarefa = True)

    except Exception as exc:
        log_error(f"Erro Crítico: {str(exc)}")
        input('Pressione ENTER para encerrar...')

if __name__ == '__main__':
    main()
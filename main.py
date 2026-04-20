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
from config import get_settings
from integrations.browser import close_driver, create_driver
from integrations.gemini import GeminiAnunciosViaFlow
from integrations.google_login import login_google, open_gemini
from integrations.window_focus import dismiss_chrome_native_popup_with_retry
from integrations.flow import GoogleFlowAutomation, ler_e_separar_cenas
from integrations.video_manager import concatenar_cenas_720p, converter_para_1080p, limpar_arquivos_temporarios
from anuncios.prompts import PROMPT_DESCRICAO_DIRETA_FRONTAL, PROMPT_DESCRICAO_DIRETA_POV, PROMPT_DESCRICAO_DIRETA_CAMINHANDO, PROMPT_DESCRICAO_DIRETA_PES, PROMPT_DESCRICAO_DIRETA_FLAT


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


def limpar_diretorio_logs_visao() -> None:
    """Zera o diretório de prints de monitoramento para não acumular lixo entre ciclos."""
    try:
        pasta_logs = Path("logs_visao")
        if pasta_logs.exists():
            log_step('Limpando imagens antigas de monitoramento (logs_visao)...')
            for arquivo in pasta_logs.glob("*.png"):
                try:
                    arquivo.unlink()
                except Exception:
                    pass
        else:
            pasta_logs.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log_error(f"Aviso: Falha ao limpar pasta logs_visao: {e}")


def fechar_popup_cromado_pos_gemini(driver) -> None:
    log_step('ETAPA 7.1: validando popup nativo do Chrome apos abrir o Gemini')
    time.sleep(1.5)
    popup_fechado = dismiss_chrome_native_popup_with_retry(driver)
    if popup_fechado:
        log_success('Popup nativo do Chrome validado/fechado apos abrir o Gemini')
    else:
        log_error('Popup nativo do Chrome permaneceu apos abrir o Gemini')


def salvar_ultima_conta_env(email: str) -> None:
    """Atualiza ou insere a variável LAST_ACCOUNT_INDEX no arquivo .env com o EMAIL da conta"""
    try:
        env_path = Path('.env')
        if not env_path.exists():
            env_path.write_text(f"LAST_ACCOUNT_INDEX={email}\n", encoding='utf-8')
            return
        
        lines = env_path.read_text(encoding='utf-8').splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith("LAST_ACCOUNT_INDEX="):
                new_lines.append(f"LAST_ACCOUNT_INDEX={email}")
                found = True
            else:
                new_lines.append(line)
        
        if not found:
            new_lines.append(f"LAST_ACCOUNT_INDEX={email}")
            
        env_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
    except Exception as e:
        log_error(f"Aviso: Não foi possível salvar o email da conta no .env: {e}")


def formatar_roteiro_limpo(texto_bruto: str) -> str:
    """Limpa lixo da UI do Gemini e força as quebras de linha para evitar colapso no flow.py"""
    crases = chr(96) * 3
    lixos = ["Show thinking Gemini said", "Show thinking", "Gemini said", f"{crases}text", crases, "PROMPT TÉCNICO:"]
    for lixo in lixos:
        texto_bruto = texto_bruto.replace(lixo, "")
    
    match_inicio = re.search(r'\[[Cc]ena\s*1', texto_bruto, re.IGNORECASE)
    if match_inicio:
        texto_bruto = texto_bruto[match_inicio.start():]
        
    texto_bruto = re.sub(r'(\[[Cc]ena\s*\d+)', r'\n\n\1', texto_bruto, flags=re.IGNORECASE)
    texto_bruto = re.sub(r'(\[[Ll]egenda)', r'\n\n\1', texto_bruto, flags=re.IGNORECASE)
    
    texto_bruto = re.sub(r'\n{3,}', '\n\n', texto_bruto)
    return texto_bruto.strip()


def extrair_e_salvar_legenda(texto_limpo: str, caminho_legenda: Path) -> None:
    """Procura a tag da legenda no roteiro gerado e a salva em arquivo isolado"""
    match = re.search(r"\[[Ll]egenda.*?\](.*)", texto_limpo, re.IGNORECASE | re.DOTALL)
    if match:
        texto_legenda = match.group(1).strip()
        marcadores_fim = ["1. EXEMPLO", "DIRETRIZ FINAL", "Confirme brevemente", "SISTEMA CALIBRADO"]
        for marcador in marcadores_fim:
            idx = texto_legenda.upper().find(marcador.upper())
            if idx != -1:
                texto_legenda = texto_legenda[:idx].strip()
        caminho_legenda.write_text(texto_legenda, encoding='utf-8')
        log_success(f'Legenda extraída e salva isoladamente: {caminho_legenda.name}')


def main() -> None:
    setup_logging()

    try:
        log_step('🚀 INICIANDO MODO WATCHER (MONITORAMENTO 24/7)')
        log_step('ETAPA 1: sincronizando credenciais HUMBLE iniciais')
        executar_sincronizacao()
        log_success('Credenciais prontas')
        
        limpar_diretorio_logs_visao()

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
            #limpar_diretorio_logs_visao()
            
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
                    
                    open_gemini(driver, settings)
                    fechar_popup_cromado_pos_gemini(driver)

                    salvar_ultima_conta_env(account.email)

                    url_gem = getattr(settings, 'gemini_url', 'https://gemini.google.com/app')
                    gemini = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)

                    # =====================================================================
                    # ETAPA IA-0: CLASSIFICAÇÃO INTELIGENTE E OCR (EXTRAÇÃO DE DADOS)
                    # =====================================================================
                    pasta_task = Path(task.folder_path)
                    caminho_metadados = pasta_task / "Metadados_do_Produto.txt"

                    if not caminho_metadados.exists():
                        log_step('ETAPA IA-0: Organizando arquivos e extraindo metadados de venda')
                        # Pega apenas os arquivos crus (ignora arquivos ocultos e coisas já geradas)
                        arquivos_brutos = [f for f in pasta_task.iterdir() if f.is_file() and not f.name.startswith('.') and "roteiro" not in f.name.lower() and "img_base" not in f.name.lower()]

                        if len(arquivos_brutos) >= 2:
                            dados_ia = gemini.classificar_arquivos_e_extrair_dados(arquivos_brutos)
                            
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

                                renomear_seguro('arquivo_produto', '00_Produto')
                                renomear_seguro('arquivo_preco', '01_Preco')
                                renomear_seguro('arquivo_referencia', '02_Referencia')

                                # 2. Salva o TXT com a riqueza de detalhes
                                conteudo_txt = (
                                    f"NOME_REAL: {dados_ia.get('nome_produto', 'Não lido')}\n"
                                    f"PRECO_E_CONDICOES: {dados_ia.get('preco_condicoes', 'Não lido')}\n"
                                    f"BENEFICIOS_EXTRAS: {dados_ia.get('beneficios', 'Não lido')}\n"
                                )
                                caminho_metadados.write_text(conteudo_txt, encoding='utf-8')
                            else:
                                raise Exception("IA falhou ao gerar o JSON de classificação de arquivos.")
                        else:
                            log_step("Aviso: Poucos arquivos na pasta para classificação IA. Seguindo fluxo normal...")

                    # 3. Injeta os dados riquíssimos do TXT direto na variável da Tarefa
                    if caminho_metadados.exists():
                        txt_lines = caminho_metadados.read_text(encoding='utf-8').splitlines()
                        for line in txt_lines:
                            if line.startswith('NOME_REAL:'):
                                task.dados_anuncio['nome_produto'] = line.replace('NOME_REAL:', '').strip()
                            if line.startswith('PRECO_E_CONDICOES:'):
                                task.dados_anuncio['preco'] = line.replace('PRECO_E_CONDICOES:', '').strip()
                            if line.startswith('BENEFICIOS_EXTRAS:'):
                                task.dados_anuncio['beneficios_extras'] = line.replace('BENEFICIOS_EXTRAS:', '').strip()

                    # =====================================================================
                    # PREPARAÇÃO DA TAREFA E EXTRAÇÃO DE VARIÁVEIS (PÓS-LIMPEZA)
                    # =====================================================================
                    # Reconstrói a task para ela ler a pasta com os nomes NOVOS que a IA acabou de gerar
                    task = get_next_pending_task(settings.products_base_dir)
                    prepared = prepare_task(task)
                    log_success(describe_task(prepared.task))

                    # Se a IA já renomeou para "00_Produto", nós pegamos ele primeiro.
                    # Se não, usamos a lógica padrão do prepared
                    pasta_task = Path(task.folder_path)
                    
                    arquivos_produto = list(pasta_task.glob("00_Produto*"))
                    if arquivos_produto:
                        primeira_imagem = arquivos_produto[0]
                    elif prepared.candidate_product_assets:
                        primeira_imagem = prepared.candidate_product_assets[0].path
                    else:
                        raise Exception('Nenhum candidato de imagem de produto encontrado na tarefa')
                    
                    arquivo_ref = list(pasta_task.glob("02_Referencia*"))[0] if list(pasta_task.glob("02_Referencia*")) else prepared.reference_asset.path if prepared.reference_asset else None
                    arquivo_preco = list(pasta_task.glob("01_Preco*"))[0] if list(pasta_task.glob("01_Preco*")) else prepared.price_asset.path if prepared.price_asset else None

                    if arquivo_preco:
                        log_success(f'Arquivo de preco mapeado: {arquivo_preco.name}')
                    if arquivo_ref:
                        log_success(f'Arquivo de referencia mapeado: {arquivo_ref.name}')

                    # --- IDENTIFICAÇÃO DO TIPO DE PASTA ---
                    partes_caminho_task = Path(prepared.task.folder_path).parts
                    estilo_filmagem_pasta = partes_caminho_task[-3] if len(partes_caminho_task) >= 3 else ""

                    # --- CHECKPOINT INTELIGENTE: EXISTE AO MENOS UM ROTEIRO? ---
                    # Verifica se existe o Roteiro1 ou qualquer outro válido para não abrir o Gemini à toa
                    tem_roteiro_pronto = False
                    for r_idx_check in range(1, qtd_roteiros + 1):
                        path_check = Path(task.folder_path) / f"Roteiro{r_idx_check}_Cenas.txt"
                        if path_check.exists() and len(path_check.read_text(encoding='utf-8').strip()) > 500:
                            tem_roteiro_pronto = True
                            break
                    
                    if tem_roteiro_pronto:
                        log_success("🚀 CHECKPOINT: Roteiro detectado na pasta. Pulando login no Gemini e indo pro Flow.")
                        precisa_abrir_gemini = False
                        
                        # Define a imagem base para o Flow (usa a ImgBase do Roteiro 1 ou o padrão)
                        imagem_base_flow = Path(task.folder_path) / "IMG_BASE_VALIDADA_Roteiro1.png"
                        if not imagem_base_flow.exists():
                            imagem_base_flow = Path(task.folder_path) / "IMG_BASE_VALIDADA.png"
                    else:
                        precisa_abrir_gemini = True

                    # --- BLOCO COM TRAVA DE CHECKPOINT ---
                    # --- BLOCO COM TRAVA DE CHECKPOINT ---
                    if precisa_abrir_gemini:
                        open_gemini(driver, settings)
                        fechar_popup_cromado_pos_gemini(driver)

                        # Validação única da foto original do produto
                        log_step('ETAPA IA: Validando candidato a produto original...')
                        if not gemini._validar_imagem_produto(primeira_imagem, timeout_resposta=60):
                            
                            # --- TRATAMENTO DE EXCEÇÃO (DESCARTE RÁPIDO) ---
                            log_error(f'A imagem foi reprovada pela IA (ou erro de leitura): {primeira_imagem.name}')
                            log_step("🛑 Tarefa abortada por rejeição de imagem. Movendo para 'concluido' como REPROVADO.")
                            
                            try:
                                pasta_raiz_tarefas = pasta_task.parent.parent # Volta de 'pendente' para a raiz do modelo
                                pasta_concluido_base = pasta_raiz_tarefas / "concluido"
                                pasta_concluido_base.mkdir(parents=True, exist_ok=True)
                                
                                nova_pasta_reprovada = pasta_concluido_base / f"{pasta_task.name}_REPROVADO"
                                
                                # Move a pasta inteira de pendente para concluido renomeando-a
                                shutil.move(str(pasta_task), str(nova_pasta_reprovada))
                                log_success(f"Tarefa arquivada com sucesso em: {nova_pasta_reprovada}")
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
                    # LOOP DE TESTE A/B (MÚLTIPLOS ROTEIROS) E GERAÇÃO DO FLOW
                    # =========================================================================
                    roteiros_anteriores_textos = []
                    resultados_roteiros = []

                    for r_idx in range(1, qtd_roteiros + 1):
                        sufixo_rot = f"Roteiro{r_idx}"
                        caminho_txt_cenas = Path(prepared.task.folder_path) / f"{sufixo_rot}_Cenas.txt"
                        caminho_txt_legenda = Path(prepared.task.folder_path) / f"{sufixo_rot}_Legenda.txt"
                        caminho_img_base_roteiro = Path(prepared.task.folder_path) / f"IMG_BASE_VALIDADA_{sufixo_rot}.png"

                        # --- CHECKPOINT MESTRE: SE O VÍDEO FINAL JÁ EXISTE, PULA TUDO DESSE ROTEIRO ---
                        arquivos_1080_existentes = list(Path(prepared.task.folder_path).glob(f"01_Escolhido_{sufixo_rot}_Variante*_1080p.mp4"))
                        if arquivos_1080_existentes:
                            log_success(f'🚀 CHECKPOINT FINAL ALCANÇADO: Vídeo final 1080p do {sufixo_rot} já existe ({arquivos_1080_existentes[0].name}).')
                            
                            if caminho_txt_cenas.exists():
                                roteiros_anteriores_textos.append(caminho_txt_cenas.read_text(encoding='utf-8'))
                            
                            vencedor_simulado = arquivos_1080_existentes[0] 
                            alt_simuladas = list(Path(prepared.task.folder_path).glob(f"{sufixo_rot}_Variante*_720p.mp4"))
                            
                            resultados_roteiros.append({
                                'vencedor_ja_1080p': vencedor_simulado, 
                                'alternativas': alt_simuladas
                            })
                            continue  # Vai direto para o próximo r_idx (Roteiro2)

                        # --- CHECKPOINT IMAGEM BASE INDIVIDUAL POR ROTEIRO ---
                        imagem_base_flow = None
                        if caminho_img_base_roteiro.exists():
                            log_success(f'🚀 CHECKPOINT IMAGEM BASE ALCANÇADO: {caminho_img_base_roteiro.name} já existe.')
                            imagem_base_flow = caminho_img_base_roteiro
                        else:
                            if fonte_imagem == "FLOW":
                                log_step(f'ETAPA FLOW-IMG: Gerando Imagem Base para {sufixo_rot} via FLOW (A/B Test)...')
                                url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
                                flow_bot_img = GoogleFlowAutomation(driver, url_flow=url_flw)
                                
                                # --- BUSCA DE IDENTIDADE (MODELO) VIA .ENV ---
                                path_task = Path(prepared.task.folder_path)
                                # Sobe níveis para achar o nome da pasta pai (Ex: LaraSelect)
                                nome_identidade = path_task.parents[2].name 
                                
                                # Tenta achar o arquivo na pasta configurada no .env
                                foto_modelo = Path(settings.modelos_dir) / f"{nome_identidade}.png"
                                if not foto_modelo.exists():
                                    foto_modelo = Path(settings.modelos_dir) / f"{nome_identidade}.jpg"
                                
                                cam_modelo_param = foto_modelo if foto_modelo.exists() else None
                                if cam_modelo_param:
                                    log_success(f"Modelo identificado via .env: {foto_modelo.name}")
                                # ---------------------------------------------

                                dados_anuncio = prepared.task.dados_anuncio
                                nome_prod = dados_anuncio.get('nome_produto', 'produto')
                                
                                descricoes = getattr(prepared.task, 'descricoes_prompts', {})
                                perfil_modelo = descricoes.get('modelo', {})
                                desc_maos = perfil_modelo.get('maos', 'mãos femininas delicadas')

                                # --- SELETOR DINÂMICO DE PROMPT POR CATEGORIA ---
                                pasta_estilo = estilo_filmagem_pasta.lower()
                                
                                if "frontal" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_DESCRICAO_DIRETA_FRONTAL.format(nome_produto=nome_prod)
                                elif "caminhando" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_DESCRICAO_DIRETA_CAMINHANDO.format(nome_produto=nome_prod)
                                elif "pes" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_DESCRICAO_DIRETA_PES.format(nome_produto=nome_prod)
                                elif "flat" in pasta_estilo:
                                    prompt_img_base_flow = PROMPT_DESCRICAO_DIRETA_FLAT.format(nome_produto=nome_prod)
                                else:
                                    prompt_img_base_flow = PROMPT_DESCRICAO_DIRETA_POV.format(
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
                                    
                                    melhor_img_base = gemini_juri.avaliar_melhor_imagem_base(cand_a, cand_b, nome_prod, estilo_filmagem_pasta)
                                    
                                    shutil.copy2(str(melhor_img_base), str(caminho_img_base_roteiro))
                                    log_success(f'Imagem Base gerada e validada via FLOW para {sufixo_rot}: {caminho_img_base_roteiro.name}')
                                    
                                    cand_a.unlink(missing_ok=True)
                                    cand_b.unlink(missing_ok=True)
                                    
                                    imagem_base_flow = caminho_img_base_roteiro
                                    
                                except Exception as e:
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
                                    log_success(f'Imagem Base validada pelo Júri para {sufixo_rot}: {nova_img_base.name}')
                                    imagem_base_flow = nova_img_base
                                else:
                                    raise Exception(f'Falha fatal ao gerar Imagem Base para {sufixo_rot}')

                        # --- CHECKPOINT: IA ROTEIRO E VALIDAÇÃO DE TAMANHO ---
                        precisa_gerar_roteiro = True
                        if caminho_txt_cenas.exists():
                            conteudo_teste = caminho_txt_cenas.read_text(encoding='utf-8').strip()
                            
                            # VALIDAÇÃO DUPLA: Tamanho mínimo E existência obrigatória da tag da cena
                            if len(conteudo_teste) < 500 or not re.search(r'\[[Cc]ena\s*1', conteudo_teste):
                                log_error(f'⚠️ Arquivo {caminho_txt_cenas.name} pequeno ou sem cenas válidas. Apagando para regerar...')
                                caminho_txt_cenas.unlink(missing_ok=True)
                            else:
                                log_success(f'🚀 CHECKPOINT ROTEIRO ALCANÇADO: {caminho_txt_cenas.name} já existe e possui tamanho válido.')
                                precisa_gerar_roteiro = False

                        if precisa_gerar_roteiro:
                            log_step(f'ETAPA IA: Gerando {sufixo_rot} ({r_idx}/{qtd_roteiros})')
                            
                            arquivos_contexto = [imagem_base_flow]
                            if arquivo_preco:
                                arquivos_contexto.append(arquivo_preco)
                            if arquivo_ref:
                                arquivos_contexto.append(arquivo_ref)
                            
                            dados_anuncio = prepared.task.dados_anuncio if hasattr(prepared.task, 'dados_anuncio') else {}
                            
                            # --- RETRY LOCAL DE IA ---
                            roteiro_valido = False
                            roteiro_limpo = ""
                            for tentativa_ia in range(1, 4):
                                roteiro_bruto = gemini.treinar_e_gerar_roteiro(
                                    arquivos=arquivos_contexto,
                                    dados_produto=dados_anuncio,
                                    arquivo_ref=arquivo_ref,
                                    qtd_cenas=qtd_cenas_anuncio,
                                    roteiros_anteriores=roteiros_anteriores_textos,
                                    tarefa_obj=prepared.task
                                )
                                
                                if roteiro_bruto and "TIMEOUT" not in roteiro_bruto and "ERRO" not in roteiro_bruto:
                                    roteiro_limpo = formatar_roteiro_limpo(roteiro_bruto)
                                    if len(roteiro_limpo) >= 500:
                                        roteiro_valido = True
                                        break
                                    else:
                                        log_error(f'⚠️ Gemini gerou um texto muito curto ({len(roteiro_limpo)} chars). Re-tentando...')
                                        time.sleep(3)
                                else:
                                    log_error('⚠️ Falha de comunicação com Gemini. Re-tentando...')
                                    time.sleep(3)
                                    
                            if not roteiro_valido:
                                raise Exception(f'IA falhou 3x ao gerar um texto válido para o {sufixo_rot}. Abortando.')

                            with open(caminho_txt_cenas, "w", encoding="utf-8") as f:
                                f.write(roteiro_limpo)
                                
                            log_success(f'{sufixo_rot} gerado: {caminho_txt_cenas.name}')
                            salvar_ultima_conta_env(account.email)

                        texto_roteiro_atual = caminho_txt_cenas.read_text(encoding='utf-8')
                        extrair_e_salvar_legenda(texto_roteiro_atual, caminho_txt_legenda)
                        roteiros_anteriores_textos.append(texto_roteiro_atual)

                        # --- CHECKPOINT: GERAÇÃO FLOW ---
                        log_step(f'ETAPA FLOW: Gerando Variantes para o {sufixo_rot}')
                        
                        cenas = ler_e_separar_cenas(caminho_txt_cenas, qtd_cenas=qtd_cenas_anuncio)
                        if not cenas:
                            log_error(f"O arquivo {caminho_txt_cenas.name} não retornou cenas válidas! Deletando lixo do Gemini...")
                            caminho_txt_cenas.unlink(missing_ok=True) # DELETA PARA SAIR DO LOOP INFINITO
                            raise Exception("Lista de cenas vazia. O arquivo de roteiro era inválido.")
                            
                        url_flw = getattr(settings, 'flow_url', 'https://labs.google/fx/pt/tools/flow')
                        variantes_720p_geradas = []
                        
                        for v_idx in range(1, qtd_variantes + 1):
                            caminho_var_720p = Path(prepared.task.folder_path) / f"{sufixo_rot}_Variante{v_idx}_720p.mp4"
                            if caminho_var_720p.exists():
                                log_success(f'🚀 CHECKPOINT VARIANTE: {caminho_var_720p.name} já existe!')
                                variantes_720p_geradas.append(caminho_var_720p)
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
                                    caminho_video = Path(prepared.task.folder_path) / f"{sufixo_rot}_Variante{v_idx}_Cena{c_idx}.mp4"
                                    if flow_bot.baixar_video_gerado(caminho_video):
                                        videos_cenas_parciais.append(caminho_video)
                                    else:
                                        raise Exception(f'Falha download Cena {c_idx}')
                                else:
                                    raise Exception(f'Falha gerar Cena {c_idx} no Flow.')

                            if len(videos_cenas_parciais) == len(cenas):
                                if concatenar_cenas_720p(videos_cenas_parciais, caminho_var_720p):
                                    variantes_720p_geradas.append(caminho_var_720p)
                                    limpar_arquivos_temporarios(videos_cenas_parciais)
                                else:
                                    raise Exception("Falha ao concatenar cenas.")

                        if not variantes_720p_geradas:
                            raise Exception(f"Nenhuma variante gerada para {sufixo_rot}.")

                        # --- JÚRI IA ---
                        log_step(f'ETAPA JÚRI: Avaliação do Diretor de Arte (IA) - {sufixo_rot}')
                        video_vencedor_720 = variantes_720p_geradas[0]
                        
                        if len(variantes_720p_geradas) > 1:
                            gemini_juri = GeminiAnunciosViaFlow(driver, url_gemini=url_gem, timeout=40)
                            gemini_juri.abrir_gemini()
                            video_vencedor_720 = gemini_juri.avaliar_melhor_variante_de_video(variantes_720p_geradas, texto_roteiro_atual)
                                
                        log_success(f'🎉 VARIANTE VENCEDORA {sufixo_rot.upper()}: {video_vencedor_720.name}')

                        # --- ETAPA FINAL E LIMPEZA DE ESPAÇO ---
                        log_step(f'ETAPA FINAL: Upscale 1080p - {sufixo_rot}')
                        nome_base_vencedor = video_vencedor_720.stem.replace("_720p", "")
                        video_final_1080 = Path(prepared.task.folder_path) / f"01_Escolhido_{nome_base_vencedor}_1080p.mp4"
                        
                        sucesso_upscale = converter_para_1080p(video_vencedor_720, video_final_1080)
                        if not sucesso_upscale or not video_final_1080.exists():
                            raise Exception(f"Erro FFmpeg upscale {sufixo_rot}.")
                        
                        log_success(f"✔ Upscale concluído: {video_final_1080.name}")
                        
                        # Apaga o arquivo original de 720p do vencedor para economizar espaço
                        try:
                            video_vencedor_720.unlink()
                            log_success("Vídeo vencedor original 720p apagado para economizar espaço.")
                        except Exception:
                            pass
                        
                        resultados_roteiros.append({
                            'vencedor_ja_1080p': video_final_1080,
                            'alternativas': [v for v in variantes_720p_geradas if v != video_vencedor_720]
                        })

                    # =========================================================================
                    # ORGANIZAÇÃO FINAL (Mover para Concluído)
                    # =========================================================================
                    pasta_pendente = Path(prepared.task.folder_path)
                    pasta_raiz_tarefas = pasta_pendente.parent.parent
                    nome_pasta = pasta_pendente.name
                    pasta_concluido = pasta_raiz_tarefas / "concluido" / nome_pasta
                    pasta_concluido.mkdir(parents=True, exist_ok=True)
                    
                    # Cópias específicas (Apenas Renomeia Alternativas e lida com o Vencedor Simulado)
                    for res in resultados_roteiros:
                        for alt in res['alternativas']:
                            nome_alt_limpo = alt.stem.replace('_720p', '')
                            if alt.exists():
                                shutil.copy2(str(alt), str(pasta_concluido / f"02_Alternativa_{nome_alt_limpo}_720p.mp4"))
                        
                    # Cópia geral (Garante que os 1080p, txt, PNGs vão tudo para lá)
                    for arquivo in pasta_pendente.iterdir():
                        if arquivo.is_file():
                            # O vencedor em 1080p é copiado junto com os TXTs aqui
                            shutil.copy2(str(arquivo), str(pasta_concluido / arquivo.name))
                            
                    # Limpa O CONTEÚDO da pasta pendente, MANTENDO o diretório vivo.
                    for f in pasta_pendente.iterdir():
                        if f.is_file(): 
                            f.unlink(missing_ok=True)
                    
                    log_success(f'Conteúdo da pasta {nome_pasta} movido para concluído. O diretório original ficou preservado e vazio.')
                    
                    salvar_ultima_conta_env(account.email)
                    sucesso_absoluto_tarefa = True 

                except Exception as exc:
                    log_error(f"Falha na execução: {str(exc)}")
                    log_step("Iniciando próximo rodízio de conta/tentativa instantaneamente...")
                    falhas_consecutivas += 1
                    tentativa_atual += 1

                finally:
                    if driver:
                        close_driver(driver)
                        driver = None
                        
            # Fim do Loop da Tarefa (sucesso_absoluto_tarefa = True)
            # O sistema voltará naturalmente ao início do `while True` principal para procurar a próxima pasta ou dormir.

    except Exception as exc:
        log_error(f"Erro Crítico: {str(exc)}")
        input('Pressione ENTER para encerrar...')


if __name__ == '__main__':
    main()
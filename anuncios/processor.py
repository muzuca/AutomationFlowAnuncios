# arquivo: anuncios/processor.py
# descricao: Responsavel por ler a estrutura de diretorios do Drive,
# detectar tarefas pendentes e orquestrar a classificacao dos arquivos

from __future__ import annotations
from pathlib import Path
import time
from anuncios.models import AdTask, PreparedTaskResult, TaskAsset, PERFIS_MODELOS, PERFIL_PADRAO, TIPOS_FILMAGEM

def _detect_role_by_position(index: int) -> str:
    if index == 0:
        return 'produto_candidato'
    if index == 1:
        return 'info_produto_preco'
    return 'referencia_extra'

def _parse_task_assets(task: AdTask) -> AdTask:
    files = []
    extensoes_validas = {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.avi', '.mkv'}
    
    # Adicionado try-except para evitar quebra silenciosa por falta de permissao de leitura no Drive
    try:
        for item in task.folder_path.iterdir():
            if item.is_file():
                nome_arquivo = item.name.lower()
                extensao = item.suffix.lower()
                
                if extensao in extensoes_validas:
                    if not (nome_arquivo.startswith("roteiro") or 
                            nome_arquivo.startswith("01_escolhido") or 
                            nome_arquivo.startswith("02_alternativa") or 
                            nome_arquivo.startswith("[backup_720p]") or 
                            "pov_validado" in nome_arquivo or
                            "pov_candidato" in nome_arquivo):
                        files.append(item)
    except Exception as e:
        print(f"Aviso: Erro ao ler pasta {task.folder_path}. Detalhe: {e}")
                
    files.sort(key=lambda item: (item.stat().st_ctime, item.name.lower()))

    assets: list[TaskAsset] = []
    for index, file_path in enumerate(files):
        asset = TaskAsset(
            path=file_path,
            modified_at=file_path.stat().st_ctime, 
            extension=file_path.suffix.lower(),
            role=_detect_role_by_position(index),
        )
        assets.append(asset)

    task.assets = assets
    task.validated_product_asset = None
    
    task.price_info_asset = assets[1] if len(assets) > 1 else None
    task.reference_asset = assets[2] if len(assets) > 2 else None

    return task


def scan_pending_tasks(products_dir: str) -> list[AdTask]:
    base_path = Path(products_dir)
    tasks: list[AdTask] = []

    if not base_path.exists():
        raise RuntimeError(f'Pasta base de produtos não encontrada: {base_path}')

    # NOVA BUSCA: A estrutura agora é Base_Dir / Nome_Modelo / Tipo_Filme / [ID_Tarefa]
    # Usamos glob("*/*/*") para capturar todas as pastas no nível ID_Tarefa
    pastas_tarefa = [p for p in base_path.glob("*/*/*") if p.is_dir()]

    for task_dir in pastas_tarefa:
        # Se por algum motivo ele pegar a lixeira do Windows, pastas ocultas ou resíduos de concluido, ignoramos
        if task_dir.name.startswith('$') or task_dir.name.startswith('.') or 'concluido' in [p.lower() for p in task_dir.parts]:
            continue

        # A estrutura esperada é: Base_Dir / Nome_Modelo / Tipo_Filme / [ID_Tarefa]
        try:
            tipo_filme_dir = task_dir.parent
            modelo_dir = tipo_filme_dir.parent
        except Exception:
            continue # Se a hierarquia nao fizer sentido, ignora

        # Identificação de Modelo e Filmagem baseada nas pastas acima
        nome_modelo = modelo_dir.name.lower()
        nome_filmagem = tipo_filme_dir.name.lower()
        
        modelo_identificada = PERFIL_PADRAO
        for chave, perfil in PERFIS_MODELOS.items():
            if chave in nome_modelo:
                modelo_identificada = perfil
                break

        filmagem_identificada = TIPOS_FILMAGEM.get("pov-maos") 
        for chave, regras in TIPOS_FILMAGEM.items():
            if chave in nome_filmagem:
                filmagem_identificada = regras
                break
                
        descricoes_prompts = {
            "modelo": modelo_identificada,
            "filmagem": filmagem_identificada
        }

        # Melhore este bloco para evitar confusão de nomes
        metadados_produto = {
            'modelo_identidade': modelo_dir.name, # Nome da pasta LaraSelect
            'tom': 'Feminino, persuasivo e comercial',
            'duracao': '15',
            'nome_produto': '', # Deixe vazio para o Gemini/TXT preencher
            'nome_resumido': '', 
            'contexto': '',     # Deixe vazio para o Gemini/TXT preencher
            'beneficios': '',   # Deixe vazio para o Gemini/TXT preencher
            'nome_pasta_id': task_dir.name
        }

        tarefa_bruta = AdTask(
            task_id=task_dir.name,
            model_name=modelo_dir.name,
            shoot_type=tipo_filme_dir.name,
            status='pendente',
            folder_path=task_dir,
            dados_anuncio=metadados_produto,
            descricoes_prompts=descricoes_prompts
        )
        
        tarefa_com_arquivos = _parse_task_assets(tarefa_bruta)
        
        # Condição crucial: Só adiciona à fila se houver arquivos de mídia brutos
        if len(tarefa_com_arquivos.assets) > 0:
            tasks.append(tarefa_com_arquivos)

    tasks.sort(key=lambda item: (item.model_name.lower(), item.shoot_type.lower(), item.task_id))
    return tasks

def get_next_pending_task(products_dir: str) -> AdTask | None:
    tasks = scan_pending_tasks(products_dir)
    return tasks[0] if tasks else None

def prepare_task(task: AdTask) -> PreparedTaskResult:
    candidatos = []
    reference = None
    price_asset = None

    assets = task.assets

    for asset in assets:
        nome_arquivo = asset.path.name.lower()
        if nome_arquivo.startswith('00_produto') or nome_arquivo.startswith('base_produto'):
            candidatos.append(asset)
        elif nome_arquivo.startswith('01_preco') or nome_arquivo.startswith('ref_preco'):
            price_asset = asset
        elif nome_arquivo.startswith('02_referencia') or nome_arquivo.startswith('ref_extra'):
            if not reference:
                reference = asset

    if not candidatos and not price_asset and not reference:
        for index, asset in enumerate(assets):
            if index == 0:
                candidatos.append(asset) 
            elif index == 1:
                price_asset = asset      
            elif index >= 2:
                if not reference:
                    reference = asset

    return PreparedTaskResult(
        task=task,
        candidate_product_assets=candidatos,
        reference_asset=reference,
        price_asset=price_asset
    )

def describe_task(task: AdTask) -> str:
    parts = [f'{asset.role}: {asset.path.name}' for asset in task.assets]
    return f'Tarefa {task.task_id} | modelo={task.model_name} | filmagem={task.shoot_type} | arquivos=[{", ".join(parts)}]'

def consolidar_arquivos_unificados(pasta_task: Path, metadados_texto: str, roteiros_lista: list, legendas_lista: list):
    """Cria os 3 arquivos unificados com divisores claros."""
    # 1. metadados.txt
    (pasta_task / "metadados.txt").write_text(metadados_texto, encoding='utf-8')

    # 2. roteiros.txt
    conteudo_roteiros = ""
    for i, roteiro in enumerate(roteiros_lista, 1):
        conteudo_roteiros += f"=== ROTEIRO {i} ===\n{roteiro}\n\n"
    (pasta_task / "roteiros.txt").write_text(conteudo_roteiros.strip(), encoding='utf-8')

    # 3. legendas.txt
    conteudo_legendas = ""
    for i, legenda in enumerate(legendas_lista, 1):
        conteudo_legendas += f"=== LEGENDA {i} ===\n{legenda}\n\n"
    (pasta_task / "legendas.txt").write_text(conteudo_legendas.strip(), encoding='utf-8')


def classificar_e_renomear_arquivos(gemini, pasta_task: Path, arquivos_brutos: list) -> dict | None:
    """
    Usa o Gemini para classificar arquivos e renomear com prefixos padrão.
    Retorna os dados extraídos (dict) ou None se falhou.
    """
    from integrations.utils import _log, log_success, log_error, formatar_dados_produto
    
    if len(arquivos_brutos) < 2:
        _log("Aviso: Poucos arquivos na pasta para classificação IA. Seguindo fluxo normal...")
        return None
    
    dados_ia = gemini.classificar_arquivos_e_extrair_dados(arquivos_brutos)
    
    if not dados_ia:
        raise Exception("IA falhou ao gerar o JSON de classificação de arquivos.")
    
    log_success('IA classificou os arquivos e extraiu os dados!')
    mapa_arquivos = {f.name.lower(): f for f in arquivos_brutos}
    
    def _renomear_seguro(chave_json, prefixo):
        nome_ia = str(dados_ia.get(chave_json, "")).strip().lower()
        if not nome_ia or nome_ia == "none" or nome_ia == "não lido":
            return
        
        base_ia = Path(nome_ia).stem.lower()
        
        for nome_real, arq_obj in list(mapa_arquivos.items()):
            base_real = arq_obj.stem.lower()
            
            if base_ia == base_real or base_ia in base_real or base_real in base_ia:
                if arq_obj.name.startswith(prefixo):
                    break
                
                novo_nome = f"{prefixo}_{arq_obj.name}"
                novo_caminho = arq_obj.parent / novo_nome
                
                try:
                    arq_obj.rename(novo_caminho)
                    log_success(f'Arquivo renomeado: {arq_obj.name} -> {novo_nome}')
                    mapa_arquivos[novo_nome.lower()] = Path(novo_caminho)
                    if nome_real in mapa_arquivos:
                        del mapa_arquivos[nome_real]
                    break
                except Exception as e:
                    log_error(f"Erro físico ao renomear {arq_obj.name}: {e}")
    
    # Executa renomeações padrão
    _renomear_seguro('arquivo_produto', 'Base_Produto')
    _renomear_seguro('arquivo_preco', 'Ref_Preco')
    _renomear_seguro('referencia_extra', 'Ref_Extra')
    _renomear_seguro('arquivo_referencia', 'Ref_Extra')
    
    # Salva metadados do produto
    conteudo_txt = formatar_dados_produto(dados_ia)
    (pasta_task / "metadados.txt").write_text(conteudo_txt, encoding='utf-8')
    
    return dados_ia


def injetar_metadados_na_tarefa(task: AdTask, pasta_task: Path) -> tuple:
    """
    Lê metadados.txt e preenche task.dados_anuncio.
    Mapeia os arquivos Base_Produto, Ref_Extra e Ref_Preco.
    
    Retorna: (primeira_imagem, arquivo_ref, arquivo_preco)
    """
    from integrations.utils import log_success
    
    caminho_metadados = pasta_task / "metadados.txt"
    
    if caminho_metadados.exists():
        txt_lines = caminho_metadados.read_text(encoding='utf-8').splitlines()
        _campos = {
            'NOME_REAL:': 'nome_produto',
            'NOME_RESUMIDO:': 'nome_resumido',
            'PRECO_E_CONDICOES:': 'preco',
            'BENEFICIOS_EXTRAS:': 'beneficios_extras',
        }
        for line in txt_lines:
            for prefixo, chave in _campos.items():
                if line.startswith(prefixo):
                    task.dados_anuncio[chave] = line.replace(prefixo, '').strip()
    
    # Mapeia arquivos
    arquivos_produto = list(pasta_task.glob("Base_Produto*"))
    if arquivos_produto:
        primeira_imagem = arquivos_produto[0]
    else:
        # Fallback: prepara a tarefa e pega o candidato
        prepared = prepare_task(task)
        if prepared.candidate_product_assets:
            primeira_imagem = prepared.candidate_product_assets[0].path
        else:
            raise Exception('Nenhum candidato de imagem de produto encontrado na tarefa')
    
    arquivo_ref = None
    refs = list(pasta_task.glob("Ref_Extra*"))
    if refs:
        arquivo_ref = refs[0]
    
    arquivo_preco = None
    precos = list(pasta_task.glob("Ref_Preco*"))
    if precos:
        arquivo_preco = precos[0]
    
    if arquivo_preco:
        log_success(f'Arquivo de preco mapeado: {arquivo_preco.name}')
    if arquivo_ref:
        log_success(f'Arquivo de referencia mapeado: {arquivo_ref.name}')
    
    return primeira_imagem, arquivo_ref, arquivo_preco
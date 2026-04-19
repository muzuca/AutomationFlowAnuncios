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


def scan_pending_tasks(products_base_dir: str) -> list[AdTask]:
    base_path = Path(products_base_dir)
    tasks: list[AdTask] = []

    if not base_path.exists():
        raise RuntimeError(f'Pasta base de produtos não encontrada: {base_path}')

    # BUSCA RESILIENTE: Procura por todas as pastas que se chamam 'pendente' dentro do Drive
    # Isso resolve o problema caso a estrutura de pastas tenha sido alterada acidentalmente.
    pastas_pendentes = base_path.rglob("pendente")

    for pending_dir in pastas_pendentes:
        if not pending_dir.is_dir():
            continue

        # A estrutura esperada é: Base_Dir / Nome_Modelo / Tipo_Filme / pendente / [ID_Tarefa]
        try:
            tipo_filme_dir = pending_dir.parent
            modelo_dir = tipo_filme_dir.parent
        except Exception:
            continue # Se a hierarquia nao fizer sentido, ignora

        # Varre o conteudo da pasta pendente procurando a subpasta do ID da tarefa (ex: "1", "2")
        for task_dir in pending_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
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

            metadados_produto = {
                'modelo': modelo_dir.name,
                'tom': 'Feminino, persuasivo e comercial',
                'duracao': '15',
                'nome_produto': modelo_dir.name, 
                'beneficios': 'Prático, alta qualidade e indispensável',
                'nome': task_dir.name
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

def get_next_pending_task(products_base_dir: str) -> AdTask | None:
    tasks = scan_pending_tasks(products_base_dir)
    return tasks[0] if tasks else None

def prepare_task(task: AdTask) -> PreparedTaskResult:
    candidatos = []
    reference = None
    price_asset = None

    assets = task.assets

    for asset in assets:
        nome_arquivo = asset.path.name.lower()
        if nome_arquivo.startswith('00_produto'):
            candidatos.append(asset)
        elif nome_arquivo.startswith('01_preco'):
            price_asset = asset
        elif nome_arquivo.startswith('02_referencia'):
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
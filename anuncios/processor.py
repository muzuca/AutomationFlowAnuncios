# arquivo: anuncios/processor.py
# descricao: Responsavel por ler a estrutura de diretorios do Drive,
# detectar tarefas pendentes e orquestrar a classificacao dos arquivos
# da tarefa (produto, preco, referencia) baseando-se em prefixos da IA
# ou, como fallback, ordem de criacao e nome.

from __future__ import annotations
from pathlib import Path
from anuncios.models import AdTask, PreparedTaskResult, TaskAsset

def _detect_role_by_position(index: int) -> str:
    if index == 0:
        return 'produto_candidato'
    if index == 1:
        return 'info_produto_preco'
    return 'referencia_extra'

def _parse_task_assets(task: AdTask) -> AdTask:
    # Filtra arquivos, ignorando os arquivos gerados pelo bot
    files = []
    for item in task.folder_path.iterdir():
        if item.is_file():
            nome_arquivo = item.name.lower()
            if not (nome_arquivo.startswith("roteiro") or nome_arquivo.startswith("01_escolhido") or nome_arquivo.startswith("02_alternativa") or nome_arquivo.startswith("[backup_720p]") or "pov_validado" in nome_arquivo):
                files.append(item)
                
    # A MÁGICA AQUI: Ordena PRIMEIRO pela data de criação (st_ctime). 
    # Em caso de EMPATE exato (mesmo segundo), usa o Nome Alfabético como desempate.
    files.sort(key=lambda item: (item.stat().st_ctime, item.name.lower()))

    assets: list[TaskAsset] = []
    for index, file_path in enumerate(files):
        asset = TaskAsset(
            path=file_path,
            modified_at=file_path.stat().st_ctime, # Ajustado para st_ctime
            extension=file_path.suffix.lower(),
            role=_detect_role_by_position(index),
        )
        assets.append(asset)

    task.assets = assets
    task.validated_product_asset = None
    
    # Preenche os papéis baseado na ordem
    task.price_info_asset = assets[1] if len(assets) > 1 else None
    task.reference_asset = assets[2] if len(assets) > 2 else None

    return task

def scan_pending_tasks(products_base_dir: str) -> list[AdTask]:
    base_path = Path(products_base_dir)
    tasks: list[AdTask] = []

    if not base_path.exists():
        raise RuntimeError(f'Pasta base de produtos não encontrada: {base_path}')

    for model_dir in base_path.iterdir():
        if not model_dir.is_dir():
            continue

        for shoot_type_dir in model_dir.iterdir():
            if not shoot_type_dir.is_dir():
                continue

            pending_dir = shoot_type_dir / 'pendente'
            if not pending_dir.exists() or not pending_dir.is_dir():
                continue

            for task_dir in pending_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                if not task_dir.name.isdigit():
                    continue

                # AJUSTE CIRÚRGICO: Preenchimento automático de metadados para a Etapa 12
                # Você pode futuramente expandir isso para ler um JSON ou TXT na pasta
                metadados_produto = {
                    'modelo': model_dir.name,
                    'tom': 'Feminino, persuasivo e comercial',
                    'duracao': '15',
                    'nome_produto': model_dir.name, 
                    'beneficios': 'Prático, alta qualidade e indispensável',
                    'nome': task_dir.name
                }

                tasks.append(
                    AdTask(
                        task_id=task_dir.name,
                        model_name=model_dir.name,
                        shoot_type=shoot_type_dir.name,
                        status='pendente',
                        folder_path=task_dir,
                        dados_anuncio=metadados_produto 
                    )
                )

    tasks.sort(key=lambda item: (item.model_name.lower(), item.shoot_type.lower(), int(item.task_id)))
    return tasks

def get_next_pending_task(products_base_dir: str) -> AdTask | None:
    tasks = scan_pending_tasks(products_base_dir)
    return tasks[0] if tasks else None

def prepare_task(task: AdTask) -> PreparedTaskResult:
    """
    Classifica os arquivos pela inteligência da IA (Prefixos 00_, 01_, 02_).
    Se não houver prefixo, recua para a ordem alfabética.
    """
    task = _parse_task_assets(task)
    
    candidatos = []
    reference = None
    price_asset = None

    assets = task.assets

    # Primeiro, tentamos classificar pelos prefixos inteligentes que a IA colocou
    for asset in assets:
        nome_arquivo = asset.path.name.lower()
        if nome_arquivo.startswith('00_produto'):
            candidatos.append(asset)
        elif nome_arquivo.startswith('01_preco'):
            price_asset = asset
        elif nome_arquivo.startswith('02_referencia'):
            if not reference:
                reference = asset

    # Fallback (Se por acaso a IA-0 não rodou, usa a ordem cega 0, 1, 2)
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
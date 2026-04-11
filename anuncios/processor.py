# arquivo: anuncios/processor.py
# descricao: concentra a leitura da fila em pendente, encontra a próxima tarefa válida, ordena os arquivos da pasta por data de modificação e prepara os papéis operacionais iniciais para o restante do fluxo.
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
    # Filtra arquivos, ignorando o arquivo de roteiro caso ele já exista de uma execução parcial
    files = [item for item in task.folder_path.iterdir() if item.is_file() and item.name != "ROTEIRO_GERADO.txt"]
    files.sort(key=lambda item: item.stat().st_mtime)

    assets: list[TaskAsset] = []
    for index, file_path in enumerate(files):
        asset = TaskAsset(
            path=file_path,
            modified_at=file_path.stat().st_mtime,
            extension=file_path.suffix.lower(),
            role=_detect_role_by_position(index),
        )
        assets.append(asset)

    task.assets = assets
    task.validated_product_asset = None
    task.price_info_asset = task.second_asset()
    task.reference_asset = task.third_asset()

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
                    'nome_produto': model_dir.name,  # Usa o nome da pasta do modelo como nome do produto
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
                        dados_anuncio=metadados_produto # Garante que os dados cheguem no main.py
                    )
                )

    tasks.sort(key=lambda item: (item.model_name.lower(), item.shoot_type.lower(), int(item.task_id)))
    return tasks


def get_next_pending_task(products_base_dir: str) -> AdTask | None:
    tasks = scan_pending_tasks(products_base_dir)
    return tasks[0] if tasks else None


def prepare_task(task: AdTask) -> PreparedTaskResult:
    task = _parse_task_assets(task)
    candidate_product_assets = task.candidate_product_assets

    return PreparedTaskResult(
        task=task,
        candidate_product_assets=candidate_product_assets,
        price_asset=task.price_info_asset,
        reference_asset=task.reference_asset,
    )


def describe_task(task: AdTask) -> str:
    parts = [f'{asset.role}: {asset.name}' for asset in task.ordered_assets]
    return f'Tarefa {task.task_id} | modelo={task.model_name} | filmagem={task.shoot_type} | arquivos=[{", ".join(parts)}]'
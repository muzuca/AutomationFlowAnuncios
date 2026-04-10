# arquivo: anuncios/models.py
# descricao: define as estruturas de dados da tarefa de anúncio, representando a pasta em pendente, os arquivos ordenados por data e os campos operacionais que serão preenchidos ao longo do processamento.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


AssetRole = Literal[
    'produto_candidato',
    'info_produto_preco',
    'referencia_extra',
]


@dataclass(frozen=True)
class TaskAsset:
    path: Path
    modified_at: float
    extension: str
    role: AssetRole

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_image(self) -> bool:
        return self.extension.lower() in {'.jpg', '.jpeg', '.png', '.webp'}

    @property
    def is_video(self) -> bool:
        return self.extension.lower() in {'.mp4', '.mov', '.avi', '.mkv'}


@dataclass
class AdTask:
    task_id: str
    model_name: str
    shoot_type: str
    status: str
    folder_path: Path
    assets: list[TaskAsset] = field(default_factory=list)

    validated_product_asset: TaskAsset | None = None
    price_info_asset: TaskAsset | None = None
    reference_asset: TaskAsset | None = None
    generated_ad_image_path: Path | None = None
    generated_ad_image_url: str | None = None
    generated_ad_validated: bool = False
    product_name: str | None = None
    product_price: str | None = None

    @property
    def ordered_assets(self) -> list[TaskAsset]:
        return sorted(self.assets, key=lambda item: item.modified_at)

    @property
    def candidate_product_assets(self) -> list[TaskAsset]:
        return [asset for asset in self.ordered_assets if asset.is_image]

    def first_asset(self) -> TaskAsset | None:
        return self.ordered_assets[0] if self.ordered_assets else None

    def second_asset(self) -> TaskAsset | None:
        return self.ordered_assets[1] if len(self.ordered_assets) > 1 else None

    def third_asset(self) -> TaskAsset | None:
        return self.ordered_assets[2] if len(self.ordered_assets) > 2 else None


@dataclass(frozen=True)
class PreparedTaskResult:
    task: AdTask
    candidate_product_assets: list[TaskAsset]
    price_asset: TaskAsset | None
    reference_asset: TaskAsset | None
# arquivo: anuncios/models.py
# descricao: define as estruturas de dados da tarefa de anúncio, representando a pasta em pendente, os arquivos ordenados por data e os campos operacionais que serão preenchidos ao longo do processamento.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Dict

# =========================================================================
# 1. BASE DE CONHECIMENTO DE MODELOS (DIRETOR DE ELENCO)
# =========================================================================
PERFIS_MODELOS: Dict[str, Dict[str, str]] = {
    "laraselect": {
        "nome": "Lara",
        "maos": "Mãos de pele clara com subtom rosado, dedos finos e alongados. Unhas de tamanho médio, formato oval, pintadas com um esmalte vermelho vivo e brilhante.",
        "corpo": "Idade aparente entre 25-30 anos, pele clara. Cabelo ruivo acobreado vibrante, corte bob na altura dos ombros, textura ondulada e volumosa. Formato do rosto oval.",
        "estilo": "Fitness chic e minimalista, focado em alta performance e conforto. Uso de conjunto de athleisure monocromático cinza escuro de alta qualidade, tênis modernos e acessórios discretos como relógio inteligente."
    },
    "anaindica": {
        "nome": "Ana",
        "maos": "Mãos de pele morena bronzeada, dedos medianos. Unhas curtas, lixadas em formato quadrado natural, com um esmalte azul escuro clássico.",
        "corpo": "Idade aparente entre 28-33 anos, pele clara bronzeada. Cabelo loiro dourado com mechas mais claras, longo e ondulado abaixo dos ombros. Formato do rosto em coração.",
        "estilo": "Activewear praiano e casual. Conjunto de top sem alças e legging cinza médio focado em liberdade de movimento. Visual clean complementado por relógio inteligente preto e tênis branco."
    },
    "paulapratica": {
        "nome": "Paula",
        "maos": "Mãos de pele retinta com tom quente, dedos proporcionais e firmes. Unhas curtas, formato oval, pintadas com esmalte vermelho vibrante, criando alto contraste.",
        "corpo": "Idade aparente entre 25-30 anos, pele negra retinta. Cabelo preto azeviche, corte bob alinhado e liso na altura do queixo. Formato do rosto redondo com maxilar definido.",
        "estilo": "Sporty glam sofisticado. O conjunto de athleisure cinza escuro ganha contraste com a pele retinta. Acessórios dourados (colar) trazem elegância ao visual esportivo."
    },
    "gabiessencial": {
        "nome": "Gabi",
        "maos": "Mãos de pele clara com subtom neutro, dedos longos e elegantes. Unhas médias, formato amendoado, com esmalte vermelho clássico intenso.",
        "corpo": "Idade aparente entre 28-33 anos, pele clara. Cabelo castanho escuro, longo, com ondas suaves e mechas discretas. Formato do rosto oval alongado. Uso de óculos de grau modernos.",
        "estilo": "Casual athleisure com toque 'intelectual'. A estética esportiva do conjunto cinza é equilibrada pelos óculos de grau de armação fina e o colar dourado, criando um visual prático, porém polido."
    },
    "laraferreira": {
        "nome": "Lara Ferreira",
        "maos": "Mãos de pele clara com subtom neutro, dedos proporcionais. Unhas curtas, lixadas em formato natural e com aparência limpa, com esmalte vermelho clássico intenso.",
        "corpo": "Idade aparente entre 25-30 anos, pele clara. Cabelo loiro com raízes levemente mais escuras, comprimento médio na altura dos ombros, textura ondulada, repicada e com volume natural. Formato do rosto oval com um sorriso aberto e marcante.",
        "estilo": "Fitness moderno e clean. Veste um conjunto de activewear (top esportivo clássico e legging de cintura alta) liso em tom azul-acinzentado (slate blue). Acessórios minimalistas incluindo um colar dourado delicado com pingente redondo pequeno, um smartwatch de pulseira clara e tênis esportivos cinza/azulados com sola de borracha natural."
    },
    "vidaachadinhos": {
        "nome": "Vida Achadinhos Da Vida",
        "maos": "Mãos de pele clara, dedos longos e delicados. Unhas curtas, formato quadrado natural, mantendo uma aparência minimalista e prática para o dia a dia, com esmalte vermelho clássico intenso.",
        "corpo": "Idade aparente entre 25-30 anos, pele clara com brilho natural. Cabelo loiro claro, corte bob curto e liso na altura do queixo, levemente jogado para o lado. Rosto com maxilar e maçãs do rosto bem definidos e um sorriso suave.",
        "estilo": "Athleisure minimalista e elegante. Veste um conjunto esportivo com textura levemente canelada em tom verde-oliva acinzentado escuro (top esportivo de alças médias e legging com costuras modeladoras). Visual limpo complementado apenas por um smartwatch branco esportivo no pulso esquerdo e tênis brancos clássicos casuais."
    }
}

PERFIL_PADRAO: Dict[str, str] = {
    "nome": "Modelo Padrão",
    "maos": "mãos femininas de pele clara e unhas curtas",
    "corpo": "mulher jovem",
    "estilo": "estilo casual e moderno"
}

# =========================================================================
# 2. DEFINIÇÃO DE ESTILOS DE FILMAGEM (DIRETOR DE FOTOGRAFIA)
# =========================================================================
TIPOS_FILMAGEM: Dict[str, Dict[str, str]] = {
    "pov-maos": {
        "nome": "POV (Ponto de Vista - Mãos)",
        "regras": "Câmera em 1ª pessoa (POV), mostrando estritamente DUAS MÃOS da modelo interagindo de forma tátil e próxima com o produto. O fundo deve estar em desfoque (bokeh). O foco é o toque, a textura e o uso."
    },
    "modelocaminhando": {
        "nome": "Modelo Caminhando",
        "regras": "Vídeo em plano médio ou corpo inteiro, mostrando a modelo a caminhar em direção à câmera ou lateralmente. O produto deve estar em uso natural. Enquadramento dinâmico focado no movimento."
    },
    "modelofrontal": {
        "nome": "Modelo Frontal (Média)",
        "regras": "Enquadramento em plano médio (da cintura para cima). A modelo está de frente ou ligeiramente de perfil, interagindo com o produto de forma natural e premium."
    },
    "modelopés": {
        "nome": "Modelo (Foco nos Pés)",
        "regras": "Enquadramento em plano fechado (close-up) focado estritamente nos pés da modelo. Mostre o produto (calçado) em uso sobre uma superfície (calçada, tapete). Foco total no detalhe."
    },
    "produtoflat": {
        "nome": "Produto Flat (Flat Lay)",
        "regras": "NÃO use a modelo neste vídeo. Enquadramento overhead (ângulo de 90 graus de cima para baixo). O produto e acessórios estão organizados de forma plana sobre uma superfície neutra e estética. Sem movimento humano."
    }
}

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
    
    # Campo adicionado para suportar metadados do roteiro (Etapa 12)
    dados_anuncio: dict = field(default_factory=dict)

    # NOVO: Carrega as descrições dinâmicas da Modelo e do Tipo de Filmagem
    descricoes_prompts: dict = field(default_factory=dict)

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
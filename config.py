# arquivo: config.py
# descricao: carrega o ambiente do projeto, centraliza caminhos e parâmetros globais, e expõe as contas HUMBLE sincronizadas para que a automação use uma fonte única e consistente de configuração.
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'


@dataclass(frozen=True)
class GoogleAccount:
    email: str
    password: str


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    env_path: Path
    products_base_dir: str
    downloads_dir: str
    ffmpeg_path: str
    gemini_url: str
    google_login_url: str
    chrome_headless: bool
    chrome_implicit_wait: int
    chrome_page_load_timeout: int
    accounts: list[GoogleAccount]


def reload_env() -> None:
    load_dotenv(ENV_PATH, override=True)


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f'Variável obrigatória ausente no .env: {name}')
    return value or ''


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _load_accounts(max_accounts: int = 30) -> list[GoogleAccount]:
    accounts: list[GoogleAccount] = []

    for i in range(1, max_accounts + 1):
        email = os.getenv(f'HUMBLE_EMAIL_{i}')
        password = os.getenv(f'HUMBLE_PASSWORD_{i}')

        if email and password:
            accounts.append(
                GoogleAccount(
                    email=email.strip(),
                    password=password.strip(),
                )
            )

    if not accounts:
        raise RuntimeError(
            'Nenhuma conta HUMBLE encontrada no .env. '
            'Execute a sincronização do acesso_humble.py antes de carregar as configurações.'
        )

    return accounts


def get_settings(reload: bool = True) -> Settings:
    if reload:
        reload_env()

    return Settings(
        base_dir=BASE_DIR,
        env_path=ENV_PATH,
        products_base_dir=_get_env('PRODUCTS_BASE_DIR', required=True),
        downloads_dir=_get_env('DOWNLOADS_DIR', required=True),
        ffmpeg_path=_get_env('FFMPEG_PATH', default='ffmpeg.exe'),
        gemini_url=_get_env('GEMINI_URL', default='https://gemini.google.com/app'),
        google_login_url=_get_env('GOOGLE_LOGIN_URL', default='https://accounts.google.com/'),
        chrome_headless=_get_bool('CHROME_HEADLESS', default=False),
        chrome_implicit_wait=int(_get_env('CHROME_IMPLICIT_WAIT', default='5')),
        chrome_page_load_timeout=int(_get_env('CHROME_PAGE_LOAD_TIMEOUT', default='60')),
        accounts=_load_accounts(),
    )
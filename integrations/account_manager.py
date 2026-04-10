# arquivo: integrations/account_manager.py
# descricao: controla a tentativa sequencial de contas de autenticação, testando cada credencial até encontrar uma sessão válida e retornando o primeiro login bem-sucedido para que o fluxo siga sem interromper o processamento.
from __future__ import annotations

from dataclasses import dataclass

from config import GoogleAccount, Settings
from integrations.google_login import login_google


@dataclass(frozen=True)
class LoginAttemptResult:
    account: GoogleAccount | None
    success: bool
    error_message: str | None = None


def try_login_with_accounts(driver, settings: Settings) -> LoginAttemptResult:
    last_error: str | None = None

    for account in settings.accounts:
        try:
            login_google(driver, settings, account)
            return LoginAttemptResult(account=account, success=True)
        except Exception as exc:
            last_error = str(exc)
            continue

    return LoginAttemptResult(
        account=None,
        success=False,
        error_message=last_error or 'Todas as contas falharam no login.',
    )
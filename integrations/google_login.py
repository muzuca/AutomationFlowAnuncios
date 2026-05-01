# arquivo: integrations/google_login.py
# descricao: executa o login no Google com uma conta HUMBLE, valida a navegação por estado da página e abre o Gemini somente depois que a autenticação concluir com sucesso.
from __future__ import annotations

import msvcrt
import re
import sys
import time
import os
from selenium.webdriver.common.keys import Keys
from pathlib import Path
from integrations.browser import create_driver, close_driver

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import GoogleAccount, Settings
from integrations.gemini import GeminiAnunciosViaFlow
from integrations.waits import wait_for_clickable, wait_for_visible
# Central de utilitários
from integrations.utils import _get_logs_dir, _log, salvar_print_debug, limpar_meus_zumbis


def login_google(driver: WebDriver, settings: Settings, account: GoogleAccount, driver_acessibilidade: WebDriver | None = None) -> None:
    try:
        _log(f"Iniciando login para a conta: {account.email}", "LOGIN")
        driver.get(settings.google_login_url)
        time.sleep(2)
        salvar_print_debug(driver, "login_01_tela_inicial")

        # --- ETAPA 1: E-MAIL ---
        email_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="email"]', timeout=30)
        email_input.clear()
        email_input.send_keys(account.email)
        
        salvar_print_debug(driver, "login_02_email_preenchido")

        next_button = wait_for_clickable(driver, By.ID, 'identifierNext', timeout=20)
        next_button.click()
        
        # Pausa para transição de tela
        time.sleep(3)
        salvar_print_debug(driver, "login_03_pos_email_next")

       # =========================================================
        # 🚨 RESGATE DE CAPTCHA AUTOMATIZADO (IA AUXILIAR COM RETRY)
        # =========================================================
        img_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
        captcha_visivel = any(img.is_displayed() for img in img_captcha) if img_captcha else False
        
        if captcha_visivel:
            _log("⚠️ CAPTCHA DETECTADO! Acionando IA Auxiliar de Acessibilidade...", "LOGIN")
            
            # Instanciamos as variáveis de controle 
            tentativas_captcha = 0
            max_tentativas = 10
            codigo_sugerido = ""
            
            # 🔥 INICIA FORA DO LOOP PARA REAPROVEITAR O MESMO NAVEGADOR 🔥
            driver_medico_temp = None

            try:
                while tentativas_captcha < max_tentativas:
                    tentativas_captcha += 1
                    _log(f"Iniciando tentativa {tentativas_captcha}/{max_tentativas} de resolver CAPTCHA...", "LOGIN")

                    # 1. Captura o print do desafio (Sempre atualiza o print se houver erro)
                    img_path = _get_logs_dir() / "captcha_seguro.png"
                    try:
                        # Tenta pegar o elemento exato
                        img_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
                        img_captcha[0].screenshot(str(img_path))
                        time.sleep(1.5)
                    except Exception:
                        driver.save_screenshot(str(img_path))
                        time.sleep(1.5)
                    
                    # 2. IA Auxiliar - NAVEGADOR MANTIDO ABERTO DURANTE AS TENTATIVAS
                    try:
                        url_gemini = os.getenv("GEMINI_CAPTCHA_URL", "https://gemini.google.com/app/bb6cbeb2a8123972")
                        
                        if driver_medico_temp is None:
                            _log("🏥 Abrindo Unidade Médica...", "LOGIN")
                            driver_medico_temp = inicializar_medico_seguro(settings, url_gemini)
                            salvar_print_debug(driver_medico_temp, f"medico_01_tela_inicial_t{tentativas_captcha}")
                        else:
                            # Se já tá aberto, só garante que tá na URL certa
                            if url_gemini not in driver_medico_temp.current_url:
                                driver_medico_temp.get(url_gemini)
                                time.sleep(3)
                        
                        ai_assist = GeminiAnunciosViaFlow(driver_medico_temp, url_gemini=url_gemini)
                        ai_assist._forcar_modelo_pro()
                        
                        salvar_print_debug(driver_medico_temp, f"medico_02_antes_do_anexo_t{tentativas_captcha}")
                        ai_assist.anexar_arquivo_local(img_path)
                        salvar_print_debug(driver_medico_temp, f"medico_03_apos_o_anexo_t{tentativas_captcha}")
                        
                        prompt_bot = f"Este é um novo desafio (tentativa {tentativas_captcha}). Retorne apenas as letras e números desta imagem, sem explicações."
                        resposta = ai_assist.enviar_prompt(prompt_bot, timeout=40)
                        
                        salvar_print_debug(driver_medico_temp, f"medico_04_apos_resposta_t{tentativas_captcha}")
                        
                        if resposta and resposta not in ['RECOVERY_TRIGGERED', 'TIMEOUT', 'SEM_RESPOSTA_UTIL']:
                            codigo_sugerido = re.sub(r'[^a-zA-Z0-9]', '', resposta.lower()).strip()
                            _log(f"🧠 IA Sugeriu: '{codigo_sugerido}'", "LOGIN")

                    except Exception as e:
                        _log(f"❌ Falha na precisão da IA Auxiliar: {str(e)[:60]}", "LOGIN")
                        if driver_medico_temp:
                            salvar_print_debug(driver_medico_temp, f"medico_ERRO_CRITICO_t{tentativas_captcha}")
                        limpar_meus_zumbis()
                        # Se deu merda muito feia, fecha pra recriar do zero na próxima iteração
                        if driver_medico_temp:
                            try: close_driver(driver_medico_temp)
                            except: pass
                            driver_medico_temp = None
                    
                    # 4. Injeção Automática e Validação de Re-tentativa
                    sys.stdout.write('\a') # Beep
                    
                    # Na primeira tentativa do código atual, tenta o automático da IA
                    tentar_automatico = True if codigo_sugerido else False
                    
                    if tentar_automatico:
                        _log(f"🤖 Tentando preenchimento automático: '{codigo_sugerido}'", "LOGIN")
                        codigo_final = codigo_sugerido
                    else:
                        # Fallback manual se a IA falhar ou for a segunda tentativa do mesmo código
                        try: os.startfile(str(img_path))
                        except: pass
                        
                        msg = f"\n👉 [URGENTE] DIGITE O CAPTCHA ({account.email}). Tentativa {tentativas_captcha}/{max_tentativas}\nIA Sugeriu: '{codigo_sugerido}' \n[ENTER para confirmar ou digite o correto]: "
                        codigo_final = input_com_timeout(msg, timeout=40)
                        if not codigo_final:
                            codigo_final = codigo_sugerido
                    
                    if codigo_final:
                        _log(f"Injetando: '{codigo_final}'...", "LOGIN")
                        xpath_ca = "//input[@name='ca'] | //input[@id='ca'] | //input[contains(@aria-label, 'letras')] | //input[@type='text' and @maxlength='6']"
                        
                        try:
                            ca_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath_ca)))
                            ca_input.clear()
                            ca_input.send_keys(codigo_final)
                            ca_input.send_keys(Keys.ENTER)
                            time.sleep(5)
                            
                            # Verifica se o CAPTCHA continua na tela (Google rejeitou)
                            novo_captcha = driver.find_elements(By.CSS_SELECTOR, "img[id='captchaimg']")
                            captcha_ainda_visivel = any(img.is_displayed() for img in novo_captcha) if novo_captcha else False

                            if captcha_ainda_visivel:
                                _log(f"❌ Código '{codigo_final}' incorreto! O Google gerou um novo CAPTCHA.", "LOGIN")
                                codigo_sugerido = "" # Limpa para a IA tentar ler o novo print
                                continue # Volta para o topo do While para tirar novo print e perguntar à IA
                            else:
                                _log("✅ CAPTCHA superado com sucesso!", "LOGIN")
                                break # Sai do While de tentativas e segue para a senha
                                
                        except Exception as e:
                            _log(f"Erro ao interagir com campo de CAPTCHA: {e}", "LOGIN")
                            break
                    else:
                        # Se não houver código final (timeout/vazio) e for a última tentativa, explode erro
                        if tentativas_captcha >= max_tentativas:
                            raise Exception("Falha no CAPTCHA: Sem resposta da IA e do Usuário após 10 tentativas.")
            finally:
                # 🔥 FECHA A UNIDADE MÉDICA APENAS NO FINAL DE TUDO (SUCESSO OU FALHA TOTAL) 🔥
                if driver_medico_temp:
                    _log("🏥 Fechando Unidade Médica...", "LOGIN")
                    try:
                        close_driver(driver_medico_temp)
                    except:
                        pass
                    driver_medico_temp = None

        # =========================================================

        # --- ETAPA 2: SENHA ---
        password_input = wait_for_visible(driver, By.CSS_SELECTOR, 'input[type="password"]', timeout=40)
        password_input.clear()
        password_input.send_keys(account.password)
        
        salvar_print_debug(driver, "login_04_senha_preenchida")

        password_next_button = wait_for_clickable(driver, By.ID, 'passwordNext', timeout=20)
        password_next_button.click()

        # =========================================================
        # 🛡️ BLINDAGEM DE CREDENCIAL (DETECTOR DE SENHA ALTERADA)
        # =========================================================
        _log("Validando autenticação e mensagens de erro...", "LOGIN")
        time.sleep(3) # Pausa para o Google processar o erro ou login

        mensagens_erro_credencial = [
            "Sua senha foi alterada", "Senha incorreta", "Wrong password", 
            "Your password was changed", "Tente novamente com a senha atual",
            "senha mudou"
        ]
        
        corpo_pagina = (driver.page_source or "").lower()
        if any(msg.lower() in corpo_pagina for msg in mensagens_erro_credencial):
            _log(f"🚨 CREDENCIAL INVÁLIDA: A senha da conta {account.email} está incorreta ou foi alterada.", "LOGIN")
            salvar_print_debug(driver, "ERRO_SENHA_INVALIDA")
            raise Exception(f"CREDENTIALS_EXPIRED: A conta {account.email} precisa de nova senha.")

        # --- ETAPA 3: VALIDAÇÃO DE SUCESSO ---
        _log("Aguardando confirmação de redirecionamento pós-login...", "LOGIN")
        try:
            WebDriverWait(driver, 40).until(
                lambda d: 'myaccount.google.com' in d.current_url
                or 'accounts.google.com' not in d.current_url
                or 'gemini.google.com' in d.current_url
                or 'google.com/search' in d.current_url
            )
        except TimeoutException:
            # Check final se parou em alguma tela de "Proteja sua conta" ou "Confirmar e-mail"
            if "recovery" in driver.current_url or "challenge" in driver.current_url:
                _log(f"⚠️ Conta {account.email} parou em desafio de segurança/recuperação.", "LOGIN")
                raise Exception(f"SECURITY_CHALLENGE: Conta {account.email} bloqueada por segurança.")
            raise

        time.sleep(2)
        salvar_print_debug(driver, "login_05_sucesso_final")
        _log("Login no Google concluído com sucesso.", "LOGIN")

    except Exception as exc:
        salvar_print_debug(driver, "login_ERRO_FINAL")
        url_final = driver.current_url
        _log(f"Falha no processo de login na URL: {url_final}", "LOGIN ERRO")
        # Repassa a exceção para o main.py rotacionar a conta
        raise exc


def open_gemini(driver: WebDriver, settings: Settings) -> None:
    try:
        _log("Abrindo Gemini App...", "LOGIN")
        driver.get(settings.gemini_url)
        WebDriverWait(driver, 60).until(lambda d: 'gemini.google.com' in d.current_url)
        
        time.sleep(4)
        salvar_print_debug(driver, "login_06_gemini_carregado")
        
    except TimeoutException as exc:
        salvar_print_debug(driver, "login_ERRO_ABRIR_GEMINI")
        raise RuntimeError('Não foi possível abrir o Gemini dentro do tempo esperado.') from exc
    
def input_com_timeout(prompt: str, timeout: int) -> str | None:
    """Cria um input no terminal que expira após X segundos (Específico para Windows)."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    fim = time.time() + timeout
    resposta = ""
    
    while time.time() < fim:
        if msvcrt.kbhit():
            char = msvcrt.getwche()
            if char in ('\r', '\n'):  # Enter pressionado
                print()
                return resposta
            elif char == '\b':  # Backspace pressionado
                if resposta:
                    resposta = resposta[:-1]
                    sys.stdout.write(' \b')
                    sys.stdout.flush()
            else:
                resposta += char
        time.sleep(0.05)
        
    print() # Pula linha após o timeout
    return None

def inicializar_medico_seguro(settings: Settings, url_alvo: str) -> WebDriver:
    """
    Função EXCLUSIVA de Acessibilidade.
    Cria a Unidade Médica, verifica o login e, se a pasta estiver zerada, 
    força uma janela visível independente para o login manual.
    """
    from integrations.browser import create_driver, close_driver
    from integrations.utils import _get_logs_dir
    import sys
    
    _log("🏥 Verificando sessão da Unidade Médica em background...", "SISTEMA")
    driver = create_driver(settings, perfil_acessibilidade=True)
    driver.set_window_size(1920, 1080) # 🛡️ FORÇA RESOLUÇÃO DESKTOP PARA O HEADLESS
    
    driver.get(settings.google_login_url)
    time.sleep(3)
    
    # Se a URL não for a do Google Accounts logado, o perfil tá vazio.
    if "signin" in driver.current_url.lower() or "identifier" in driver.current_url.lower():
        _log("⚠️ Perfil médico deslogado! Isolando processo para resgate manual...", "SISTEMA")
        close_driver(driver) # Mata o fantasma para destravar a pasta
        
        # 🛡️ SOLUÇÃO DO PERFIL TRAVADO: Garante que o SO liberou a pasta e deleta o cadeado
        time.sleep(2) # Dá tempo para o processo do Windows realmente morrer
        perfil_dir = _get_logs_dir() / "perfil_acessibilidade"
        lock_file = perfil_dir / "SingletonLock"
        try:
            if lock_file.exists():
                lock_file.unlink() # Quebra o cadeado na força bruta
        except:
            pass # Se não conseguir deletar, o SO já liberou
            
        # Opcional: Garante que não tem nenhum zumbi segurando a pasta
        from integrations.utils import limpar_meus_zumbis
        limpar_meus_zumbis()
        time.sleep(1)
        
        # --- RESGATE BRUTO: Chrome 100% visível independente do seu .env ---
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        options_visivel = Options()
        options_visivel.add_argument("--window-size=1000,800") # Janela grande visível
        options_visivel.add_argument("--start-maximized") # 🛡️ BÔNUS: Inicia maximizado pro resgate manual
        
        # 🛡️ MÁGICA ANTI-DETECÇÃO DO GOOGLE (Oculta o Selenium) 🛡️
        options_visivel.add_argument("--disable-blink-features=AutomationControlled")
        options_visivel.add_experimental_option("excludeSwitches", ["enable-automation"])
        options_visivel.add_experimental_option("useAutomationExtension", False)
        
        # Aponta exatamente pra mesma pasta de acessibilidade
        perfil_dir = _get_logs_dir() / "perfil_acessibilidade"
        perfil_dir.mkdir(parents=True, exist_ok=True)
        options_visivel.add_argument(f"--user-data-dir={perfil_dir}")
        
        _log("Abrindo janela de resgate VISÍVEL na sua tela...", "SISTEMA")
        service = Service(ChromeDriverManager().install())
        driver_resgate = webdriver.Chrome(service=service, options=options_visivel)
        driver_resgate.get(settings.google_login_url)
        
        sys.stdout.write('\a') # Apita
        print("\n👉 [AÇÃO MANUAL NECESSÁRIA]")
        print("1. O Chrome VISÍVEL da Unidade Médica acabou de abrir.")
        print("2. Faça o login na sua conta do Google normalmente.")
        input("✅ APÓS CONCLUIR O LOGIN, PRESSIONE ENTER AQUI... ")
        
        try: driver_resgate.quit()
        except: pass
        
        _log("Login concluído. Retornando Unidade Médica para as sombras (Headless)...", "SISTEMA")
        driver = create_driver(settings, perfil_acessibilidade=True)
        driver.set_window_size(1920, 1080) # 🛡️ FORÇA RESOLUÇÃO DESKTOP DE NOVO
        
    # 🚀 JÁ LOGADO, VAI PARA A URL ALVO (TREINADA OU PADRÃO) E DEVOLVE O DRIVER
    driver.get(url_alvo)
    time.sleep(4)
    return driver

def garantir_medico_vivo(driver_medico: WebDriver | None, settings: Settings, url_alvo: str) -> WebDriver:
    """
    Verifica se o driver médico ainda responde. 
    Se houver falha de conexão (zumbi), mata o processo e reinicia do zero.
    """
    try:
        if driver_medico is not None:
            # Tenta uma operação mínima para checar se o browser ainda fala com o Selenium
            _ = driver_medico.current_url
            return driver_medico
    except Exception:
        _log("🏥 Unidade Médica parou de responder (Zumbi)! Iniciando ressurreição...", "SISTEMA")
    
    # Se caiu aqui, o driver está morto ou desconectado
    from integrations.browser import close_driver
    try:
        if driver_medico: close_driver(driver_medico)
    except: pass
    
    # Cria um novo driver usando a lógica robusta já existente
    return inicializar_medico_seguro(settings, url_alvo)

def realizar_checkup_medico_pre_voo(settings: Settings) -> None:
    """
    PARA O SCRIPT e abre o perfil de acessibilidade de forma visível.
    Objetivo: Permitir que o usuário faça o login manual e aceite os termos 
    do Gemini/Google para salvar os cookies no perfil persistente.
    """
    from integrations.utils import _get_logs_dir, _log
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import sys
    import time

    _log("🏥 [PRE-FLIGHT] Iniciando configuração manual da Unidade Médica...", "SISTEMA")

    driver_setup = None
    try:
        # 1. Configura o Chrome VISÍVEL e aponta para a pasta de acessibilidade
        options = Options()
        options.add_argument("--window-size=1200,900")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        perfil_dir = _get_logs_dir() / "perfil_acessibilidade"
        perfil_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={perfil_dir}")

        # 2. Lança o navegador e vai para o Gemini
        service = Service(ChromeDriverManager().install())
        driver_setup = webdriver.Chrome(service=service, options=options)
        
        url_gemini = getattr(settings, 'gemini_url', 'https://gemini.google.com/app')
        driver_setup.get(url_gemini)

        # 3. BLOQUEIO TOTAL DO SCRIPT (Aguardando o humano)
        sys.stdout.write('\a') # Beep de atenção
        print("\n" + "!"*60)
        print("👉 [AÇÃO MANUAL OBRIGATÓRIA]")
        print("1. O navegador abriu de forma VISÍVEL.")
        print("2. Faça o login na conta do Google que será a 'MÉDICA'.")
        print("3. Aceite todos os termos, pop-ups e onbordering do Gemini.")
        print("4. Mande um 'Oi' no chat só para garantir que está funcionando.")
        print("!"*60)
        
        input("\n✅ APÓS ESTAR LOGADO E COM O CHAT LIBERADO, APERTE [ENTER] AQUI PARA CONTINUAR... ")

        _log("Configuração concluída. Salvando perfil e fechando...", "SISTEMA")

    except Exception as e:
        _log(f"🚨 Erro durante o setup do médico: {e}", "ERRO")
        sys.exit(1)
    finally:
        if driver_setup:
            try:
                driver_setup.quit()
            except:
                pass
            time.sleep(5) # Tempo de segurança para o Windows liberar os arquivos de lock da pasta
# arquivo: reverter.py
import shutil
from pathlib import Path

# Caminho base que apareceu no seu log
BASE_DIR = Path(r"G:\Meu Drive\Produtos\LaraSelect\POV-Maos")
PASTA_ID = "1"

def reverter_para_teste():
    concluido_dir = BASE_DIR / "concluido" / PASTA_ID
    pendente_dir = BASE_DIR / "pendente" / PASTA_ID

    if not concluido_dir.exists():
        print(f"A pasta {concluido_dir} não existe. Nada a reverter.")
        return

    pendente_dir.mkdir(parents=True, exist_ok=True)

    for arquivo in concluido_dir.iterdir():
        if not arquivo.is_file():
            continue
        
        nome = arquivo.name
        
        # Deleta a versão 1080p gerada de forma errada/fallback
        if "1080p" in nome or "Fallback" in nome:
            print(f"🗑️ Deletando vídeo final: {nome}")
            arquivo.unlink()
            continue
            
        # Limpa os prefixos das variantes 720p
        if nome.startswith("[BACKUP_720p]_"):
            novo_nome = nome.replace("[BACKUP_720p]_", "")
        elif nome.startswith("[02_ALTERNATIVA]_"):
            novo_nome = nome.replace("[02_ALTERNATIVA]_", "")
        else:
            novo_nome = nome

        destino = pendente_dir / novo_nome
        shutil.move(str(arquivo), str(destino))
        print(f"✅ Movido/Renomeado: {nome} -> {novo_nome}")

    try:
        concluido_dir.rmdir()
        print(f"\n🗑️ Pasta concluido/{PASTA_ID} limpa.")
    except:
        pass

    print("\n🚀 REVERSÃO CONCLUÍDA! Pode rodar o main.py novamente para testar a Etapa 14 direto.")

if __name__ == "__main__":
    reverter_para_teste()
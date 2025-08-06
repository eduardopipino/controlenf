# reset_password_manual.py

from pymongo import MongoClient
from werkzeug.security import generate_password_hash
import getpass # Para digitar a senha sem que ela apareça no terminal

# Tenta importar a configuração local
try:
    import config
    MONGO_URI = config.MONGO_URI
except (ImportError, AttributeError):
    print("ERRO: Arquivo 'config.py' não encontrado ou não contém a variável MONGO_URI.")
    print("Certifique-se de que o arquivo está na mesma pasta e configurado corretamente.")
    exit()

# Conecta ao banco de dados
try:
    client = MongoClient(MONGO_URI)
    db = client.get_database('bd')
    users_collection = db['users']
    client.admin.command('ping') # Testa a conexão
    print("Conexão com o banco de dados estabelecida com sucesso.")
except Exception as e:
    print(f"ERRO: Não foi possível conectar ao banco de dados. Erro: {e}")
    exit()

def reset_user_password():
    """Função principal para redefinir a senha de um usuário."""
    
    # 1. Pede o nome do usuário que terá a senha alterada
    username_to_reset = input("Digite o nome de usuário (username) que deseja alterar: ").strip()
    
    # 2. Verifica se o usuário existe
    user_data = users_collection.find_one({'username': username_to_reset})
    if not user_data:
        print(f"ERRO: Usuário '{username_to_reset}' não encontrado no banco de dados.")
        return

    print(f"Usuário encontrado: {user_data['username']} (Email: {user_data['email']})")
    
    # 3. Pede a nova senha de forma segura
    new_password = getpass.getpass("Digite a NOVA senha: ")
    confirm_password = getpass.getpass("Confirme a NOVA senha: ")

    if new_password != confirm_password:
        print("ERRO: As senhas não coincidem. Operação cancelada.")
        return
        
    if not new_password:
        print("ERRO: A senha não pode ser vazia. Operação cancelada.")
        return

    # 4. Gera o hash da nova senha
    new_password_hash = generate_password_hash(new_password)
    
    # 5. Atualiza o banco de dados
    try:
        result = users_collection.update_one(
            {'_id': user_data['_id']},
            {'$set': {'password_hash': new_password_hash}}
        )
        if result.modified_count > 0:
            print(f"\nSUCESSO! A senha do usuário '{username_to_reset}' foi alterada.")
        else:
            print("\nAVISO: A senha não foi alterada (talvez a nova senha seja igual à antiga).")
    except Exception as e:
        print(f"ERRO: Ocorreu um erro ao atualizar o banco de dados: {e}")

# Executa a função
if __name__ == '__main__':
    reset_user_password()
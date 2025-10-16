# 1. Bibliotecas Padrão e de Terceiros
import os
from datetime import datetime
import certifi
from flask import Flask, session, redirect, url_for
from flask_login import LoginManager
from pymongo import MongoClient
from bson.objectid import ObjectId

# --- INICIALIZAÇÃO DE EXTENSÕES ---
# Criamos as instâncias das extensões aqui, fora da função.
# Elas estarão "vazias" até que a aplicação seja criada e associada a elas.
db = None
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # 'auth' é o nome do Blueprint

@login_manager.unauthorized_handler
def unauthorized():
    # Redireciona para a página de login do blueprint de autenticação
    return redirect(url_for('auth.login'))

# --- FÁBRICA DE APLICAÇÃO ---
def create_app():
    """
    Função que cria e configura a instância da aplicação Flask.
    """
    global db
    
    app = Flask(__name__)

    # --- CONFIGURAÇÕES DA APLICAÇÃO ---
    app.config['JSON_SORT_KEYS'] = False
    app.secret_key = os.environ.get('SECRET_KEY', 'uma_chave_padrao_para_desenvolvimento_local')

    # --- CONEXÃO COM O BANCO DE DADOS ---
    MONGO_URI = os.environ.get('MONGO_URI')
    if not MONGO_URI:
        print("AVISO: Variável de ambiente MONGO_URI não encontrada. Tentando importar de config.py...")
        try:
            from config import MONGO_URI
            print(">>> Usando MONGO_URI do arquivo config.py local.")
        except (ImportError, AttributeError):
            print("ERRO CRÍTICO: config.py não encontrado ou não contém MONGO_URI.")
            MONGO_URI = None

    if MONGO_URI:
        try:
            ca = certifi.where()
            client = MongoClient(MONGO_URI, tlsCAFile=ca)
            client.admin.command('ping')
            db = client.get_database('bd')
            print(">>> Conexão com MongoDB Atlas estabelecida com sucesso! <<<")
        except Exception as e:
            print(f"ERRO: Falha na conexão com MongoDB Atlas. Erro: {e}")
            db = None # Garante que db seja None em caso de falha

    # --- INICIALIZAÇÃO DAS EXTENSÕES COM A APP ---
    login_manager.init_app(app)

    # Importa o modelo User aqui para evitar importação circular
    from .models import User, users_collection

    @login_manager.user_loader
    def load_user(user_id):
        user_data = users_collection.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                id=user_data['_id'],
                theme=user_data.get('theme', 'theme-blue'),
                colunas_visiveis=user_data.get('colunas_visiveis_controle'),
                colunas_visiveis_pendencias=user_data.get('colunas_visiveis_pendencias'),
                font_size_preference=user_data.get('font_size_preference', 'media'),
                spacing_preference=user_data.get('spacing_preference', 'regular'),
                view_mode_controle=user_data.get('view_mode_controle'),
                card_fields_controle=user_data.get('card_fields_controle'),
                color_coding_controle=user_data.get('color_coding_controle', False),
                view_mode_pendencias=user_data.get('view_mode_pendencias'),
                card_fields_pendencias=user_data.get('card_fields_pendencias')
            )
        return None

    # --- REGISTRO DOS BLUEPRINTS (ROTAS) ---
    with app.app_context():
        # O ponto '.' antes de routes significa "do pacote atual"
        from .routes.auth import auth_bp
        from .routes.core import core_bp
        from .routes.instrumentos import instrumentos_bp
        from .routes.cadastros_gerais import cadastros_bp
        from .routes.controle import controle_bp
        from .routes.pendencias import pendencias_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(core_bp)
        app.register_blueprint(instrumentos_bp, url_prefix='/cadastros')
        app.register_blueprint(cadastros_bp, url_prefix='/cadastros')
        app.register_blueprint(controle_bp, url_prefix='/controle')
        app.register_blueprint(pendencias_bp, url_prefix='/pendencias')

    # --- FUNÇÕES DE CONTEXTO E GLOBAIS ---
    app.jinja_env.globals.update(datetime=datetime)

    @app.before_request
    def make_session_non_permanent():
        session.permanent = False
        
    return app

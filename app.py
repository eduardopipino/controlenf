from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import json
from bson import json_util
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from collections import Counter
import os
import re
import io
import csv
import certifi

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

app.config['JSON_SORT_KEYS'] = False

#app.secret_key = os.urandom(24)
app.secret_key = os.environ.get('SECRET_KEY', 'uma_chave_padrao_para_desenvolvimento_local')

# ======================================================================
# LÓGICA DE CONEXÃO FLEXÍVEL (HOSPEDAGEM ONLINE / LOCAL)
# ======================================================================

# --- CONFIGURAÇÃO DA CONEXÃO COM O BANCO DE DADOS (VERSÃO CORRIGIDA) ---
MONGO_URI = os.environ.get('MONGO_URI')

# Se a variável de ambiente não for encontrada (estamos rodando localmente)
if not MONGO_URI:
    print("AVISO: Variável de ambiente MONGO_URI não encontrada. Tentando importar de config.py...")
    try:
        import config
        MONGO_URI = config.MONGO_URI
        print(">>> Usando MONGO_URI do arquivo config.py local.")
    except (ImportError, AttributeError):
        print("ERRO CRÍTICO: config.py não encontrado ou não contém MONGO_URI.")
        MONGO_URI = None

# Tenta conectar ao banco de dados se uma URI foi encontrada
client = None
db = None
if MONGO_URI:
    try:
        ca = certifi.where()
        client = MongoClient(MONGO_URI, tlsCAFile=ca)
        # Testa a conexão para falhar rapidamente se algo estiver errado
        client.admin.command('ping')
        db = client.get_database('bd')
        print(">>> Conexão com MongoDB Atlas estabelecida com sucesso! <<<")
    except Exception as e:
        print(f"ERRO: Falha na conexão com MongoDB Atlas. Erro: {e}")


# Coleções
instrumentos_collection = db['INSTRUMENTOCONTRATUAL']
itens_collection = db['ITENS_INSTRUMENTO'] # <<< NOVA COLEÇÃO
situacao_collection = db['SITUACAO']
controle_collection = db['CONTROLE']
users_collection = db['users']
documentacao_tipos_collection = db['DOCUMENTACAO']
pendencias_collection = db['PENDENCIAS']

# Logo após a definição das coleções
TODAS_AS_COLUNAS_CONTROLE = [
    ['tipo_documento', 'Tipo Documento'],
    ['n_instrumento', 'Nº Instrumento'],
    ['contratada', 'Contratada'],
    ['objeto', 'Objeto'],
    ['item_descricao', 'Item'],
    ['referencia', 'Referência'],
    ['documentacao', 'Documentação'],
    ['observacoes', 'Observações'],
    ['situacao', 'Situação']
]

# --- Configuração Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

class User(UserMixin):
    def __init__(self, username, email, password_hash, id=None, theme='theme-blue', colunas_visiveis=None):
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.id = str(id) if id else None
        self.theme = theme
        # Se o usuário não tiver preferência salva, usa a lista completa como padrão
        self.colunas_visiveis = colunas_visiveis or [col[0] for col in TODAS_AS_COLUNAS_CONTROLE]

    def get_id(self):
        return self.id

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
            colunas_visiveis=user_data.get('colunas_visiveis_controle')
        )
    return None

# --- Funções Auxiliares Atualizadas para Multi-usuário ---

def get_itens_para_dropdown_js(somente_vigentes=False):
    """
    Busca ITENS para popular dropdowns no JavaScript.
    Faz um join com os instrumentos para obter dados gerais.
    """
    user_id_obj = ObjectId(current_user.id)
    
    pipeline = [
        # 1. Encontra os instrumentos do usuário (e filtra por vigentes se necessário)
        {'$match': {'user_id': user_id_obj, 'vigente': True} if somente_vigentes else {'user_id': user_id_obj}},
        # 2. Faz o join com os itens
        {'$lookup': {
            'from': 'ITENS_INSTRUMENTO',
            'localField': '_id',
            'foreignField': 'instrumento_id',
            'as': 'itens'
        }},
        # 3. Desconstrói o array de itens para ter um documento por item
        {'$unwind': '$itens'},
        # 4. Formata o output
        {'$project': {
            '_id': '$itens._id',
            'n_instrumento': '$n_instrumento',
            'tipo_documento': '$tipo_documento',
            'contratada': '$contratada',
            'objeto_resumido': '$objeto_resumido',
            'descricao_item': '$itens.descricao_item',
            'tipo_frequencia': '$itens.tipo_frequencia',
            'documentos_exigidos': '$itens.documentos_exigidos' # <<< CAMPO NOVO ADICIONADO
        }}
    ]
    
    itens_raw = list(instrumentos_collection.aggregate(pipeline))
    for item in itens_raw:
        item['_id'] = str(item['_id'])
    return itens_raw

def get_situacoes_para_dropdown():
    return list(situacao_collection.find({'user_id': ObjectId(current_user.id)}, {'situacao': 1}))

def get_controle_data(query_filter=None, sort_document=None):
    """
    Função de busca de dados de controle, com suporte a ordenação.
    """
    if query_filter is None:
        query_filter = {}
    
    query_filter['user_id'] = ObjectId(current_user.id)

    pipeline = [
        {'$match': query_filter},
        {'$lookup': {
            'from': 'ITENS_INSTRUMENTO',
            'localField': 'item_id',
            'foreignField': '_id',
            'as': 'item_join'
        }},
        {'$unwind': {'path': '$item_join', 'preserveNullAndEmptyArrays': True}},
        {'$lookup': {
            'from': 'INSTRUMENTOCONTRATUAL',
            'localField': 'item_join.instrumento_id',
            'foreignField': '_id',
            'as': 'instrumento_join'
        }},
        {'$unwind': {'path': '$instrumento_join', 'preserveNullAndEmptyArrays': True}},
        {'$addFields': {
            'n_instrumento': {'$ifNull': ['$instrumento_join.n_instrumento', '$n_instrumento']},
            'tipo_documento': {'$ifNull': ['$instrumento_join.tipo_documento', '$tipo_documento']},
            'contratada': {'$ifNull': ['$instrumento_join.contratada', '$contratada']},
            'objeto': {'$ifNull': ['$instrumento_join.objeto_resumido', '$objeto']},
            'item_descricao': {'$ifNull': ['$item_join.descricao_item', '']}
        }}
    ]

    # Adiciona a lógica de ordenação à pipeline se ela for fornecida
    if sort_document:
        pipeline.append({'$sort': sort_document})
    
    # Adiciona o último estágio para limpar os campos temporários
    pipeline.append({'$project': {'item_join': 0, 'instrumento_join': 0}})
    
    return list(controle_collection.aggregate(pipeline))

def prepare_chart_data(controles):
    contratadas_data = Counter([c.get('contratada', 'Desconhecida') for c in controles])
    situacoes_data = Counter([c.get('situacao', 'Desconhecida') for c in controles])
    chart_data = {
        'contratadas': { 'labels': list(contratadas_data.keys()), 'data': list(contratadas_data.values()) },
        'situacoes': { 'labels': list(situacoes_data.keys()), 'data': list(situacoes_data.values()) }
    }
    return json.dumps(chart_data, default=json_util.default)

def get_situacoes_que_arquivam():
    """Busca no banco e retorna uma lista com os nomes de todas as situações
       que foram marcadas com 'arquiva_registro' = True."""
    situacoes = situacao_collection.find(
        {'user_id': ObjectId(current_user.id), 'arquiva_registro': True},
        {'_id': 0, 'situacao': 1}
    )
    return [s['situacao'] for s in situacoes]

def get_instrumentos_para_dropdown():
    # Busca os instrumentos
    instrumentos = list(instrumentos_collection.find(
        {'user_id': ObjectId(current_user.id)},
        {'n_instrumento': 1, 'tipo_documento': 1, 'contratada': 1, 'objeto_resumido': 1}
    ))
    
    # <<< INÍCIO DA CORREÇÃO >>>
    # Converte o ObjectId de cada instrumento para uma string
    for inst in instrumentos:
        inst['_id'] = str(inst['_id'])
    # <<< FIM DA CORREÇÃO >>>
        
    return instrumentos

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_data = users_collection.find_one({'username': username})
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(
                username=user_data['username'], email=user_data['email'],
                password_hash=user_data['password_hash'], id=user_data['_id'],
                theme=user_data.get('theme', 'theme-blue')
            )
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Login inválido. Verifique seu nome de usuário e senha.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
#@limiter.limit("1 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if not all([username, email, password, confirm_password]):
            flash('Todos os campos são obrigatórios.', 'error')
            return render_template('register.html', form_data=request.form)
        if password != confirm_password:
            flash('As senhas não coincidem.', 'error')
            return render_template('register.html', form_data=request.form)
        if users_collection.find_one({'username': username}):
            flash('Nome de usuário já existe. Escolha outro.', 'error')
            return render_template('register.html', form_data=request.form)
        if users_collection.find_one({'email': email}):
            flash('Email já registrado. Use outro ou faça login.', 'error')
            return render_template('register.html', form_data=request.form)
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'username': username, 'email': email,
            'password_hash': hashed_password, 'theme': 'theme-blue'
        })
        flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form_data={})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/set_theme', methods=['POST'])
@login_required
def set_theme():
    data = request.get_json()
    theme = data.get('theme')
    allowed_themes = ['theme-light', 'theme-blue', 'theme-green', 'theme-dark', 'theme-pink']
    if theme in allowed_themes:
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'theme': theme}}
        )
        return {'status': 'success', 'theme': theme}
    return {'status': 'error', 'message': 'Invalid theme'}, 400

@app.route('/user/save_column_prefs', methods=['POST'])
@login_required
def save_column_prefs():
    data = request.get_json()
    colunas = data.get('colunas', [])
    
    # Valida se as colunas recebidas são válidas, comparando com nossa lista
    colunas_permitidas = [col[0] for col in TODAS_AS_COLUNAS_CONTROLE]
    colunas_validas = [c for c in colunas if c in colunas_permitidas]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'colunas_visiveis_controle': colunas_validas}}
    )
    return {'status': 'success'}

# --- Rotas Principais ---
@app.route('/')
@login_required
def index():
    try:
        user_id_obj = ObjectId(current_user.id)
        
        # Pipeline para contar frequências a partir dos ITENS de instrumentos VIGENTES
        frequencia_pipeline = [
            {'$match': {'user_id': user_id_obj, 'vigente': True}},
            {'$lookup': {
                'from': 'ITENS_INSTRUMENTO',
                'localField': '_id',
                'foreignField': 'instrumento_id',
                'as': 'itens'
            }},
            {'$unwind': '$itens'},
            {'$group': {'_id': '$itens.tipo_frequencia', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        
        summary_data = {
            'pendentes': controle_collection.count_documents({'user_id': user_id_obj, 'situacao': {'$ne': 'FINANCEIRO'}}),
            'vigentes': instrumentos_collection.count_documents({'user_id': user_id_obj, 'vigente': True}),
            'total_instrumentos': instrumentos_collection.count_documents({'user_id': user_id_obj}),
            'frequencias': list(instrumentos_collection.aggregate(frequencia_pipeline))
        }
    except Exception as e:
        flash(f"Não foi possível carregar os dados do resumo: {e}", "error")
        summary_data = {'pendentes': 0, 'vigentes': 0, 'total_instrumentos': 0, 'frequencias': []}

    try:
        with open('changelog.json', 'r', encoding='utf-8') as f:
            changelog_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        changelog_data = [] # Se o arquivo não existir ou for inválido, envia uma lista vazia

    # Adiciona o 'changelog' ao render_template
    return render_template('index.html', summary=summary_data, changelog=changelog_data)

    #return render_template('index.html', summary=summary_data)

# --- CADASTROS DE INSTRUMENTOS ---

@app.route('/cadastros/instrumentos_contratuais')
@login_required
def instrumentos_contratuais():
    instrumentos = instrumentos_collection.find({'user_id': ObjectId(current_user.id)})
    # <<< ADICIONADO: Informa ao template que o filtro 'todos' está ativo >>>
    return render_template('instrumentos_contratuais.html', instrumentos=list(instrumentos), filtro_ic_ativo='todos')

@app.route('/cadastros/instrumentos_contratuais/vigentes')
@login_required
def instrumentos_contratuais_vigentes():
    instrumentos = instrumentos_collection.find({'user_id': ObjectId(current_user.id), 'vigente': True})
    # <<< ADICIONADO: Informa ao template que o filtro 'vigentes' está ativo >>>
    return render_template('instrumentos_contratuais.html', instrumentos=list(instrumentos), filtro_ic_ativo='vigentes')

@app.route('/cadastros/instrumentos_contratuais/extintos')
@login_required
def instrumentos_contratuais_extintos():
    instrumentos = instrumentos_collection.find({'user_id': ObjectId(current_user.id), 'vigente': False})
    # <<< ADICIONADO: Informa ao template que o filtro 'extintos' está ativo >>>
    return render_template('instrumentos_contratuais.html', instrumentos=list(instrumentos), filtro_ic_ativo='extintos')

@app.route('/cadastros/instrumentos_contratuais/novo', methods=['GET', 'POST'])
@login_required
def novo_instrumento_contratual():
    if request.method == 'POST':
        n_instrumento = request.form['n_instrumento'].strip()
        tipo_documento = request.form['tipo_documento'].strip()
        if instrumentos_collection.find_one({'n_instrumento': n_instrumento, 'tipo_documento': tipo_documento, 'user_id': ObjectId(current_user.id)}):
            flash('Você já possui um instrumento com este Nº e Tipo de Documento.', 'error')
            return render_template('form_instrumento.html', instrumento=request.form)

        novo_instrumento = {
            'n_instrumento': n_instrumento,
            'tipo_documento': tipo_documento,
            'contratada': request.form['contratada'].strip(),
            'objeto_resumido': request.form['objeto_resumido'].strip(),
            # O campo 'tipo_frequencia' foi REMOVIDO
            'vigente': 'vigente' in request.form,
            'user_id': ObjectId(current_user.id)
        }
        result = instrumentos_collection.insert_one(novo_instrumento)
        
        # <<< ALTERAÇÃO CRÍTICA >>>
        # Redireciona para a página de gerenciamento de itens do novo instrumento
        flash('Instrumento Contratual criado! Agora, adicione os itens de faturamento.', 'success')
        return redirect(url_for('gerenciar_instrumento', instrumento_id=str(result.inserted_id)))

    # Aponta para um novo template mais simples ou reutiliza um genérico
    return render_template('form_instrumento.html', instrumento={}, novo=True)

@app.route('/cadastros/instrumentos/<string:instrumento_id>/itens/novo', methods=['POST'])
@login_required
def novo_item_instrumento(instrumento_id):
    # Garante que o instrumento pai existe e pertence ao usuário
    instrumento = instrumentos_collection.find_one({'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)})
    if not instrumento:
        flash('Instrumento pai não encontrado.', 'error')
        return redirect(url_for('instrumentos_contratuais'))

    descricao = request.form.get('descricao_item', '').strip()
    frequencia = request.form.get('tipo_frequencia', '').strip()

    if not descricao or not frequencia:
        flash('Descrição e Frequência do item são obrigatórios.', 'error')
    else:
        itens_collection.insert_one({
            'instrumento_id': ObjectId(instrumento_id),
            'descricao_item': descricao,
            'tipo_frequencia': frequencia,
            'user_id': ObjectId(current_user.id)
        })
        flash('Novo item adicionado com sucesso!', 'success')
    
    return redirect(url_for('gerenciar_instrumento', instrumento_id=instrumento_id))


@app.route('/cadastros/itens/<string:item_id>/excluir', methods=['POST'])
@login_required
def excluir_item_instrumento(item_id):
    item = itens_collection.find_one({'_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)})
    if not item:
        flash('Item não encontrado.', 'error')
        return redirect(url_for('instrumentos_contratuais'))

    # VERIFICAÇÃO CRÍTICA: O item está em uso?
    if controle_collection.find_one({'item_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)}):
        flash('Não é possível excluir este item, pois ele está sendo usado em registros de controle.', 'error')
        return redirect(url_for('gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))

    itens_collection.delete_one({'_id': ObjectId(item_id)})
    flash('Item excluído com sucesso.', 'success')
    return redirect(url_for('gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))


@app.route('/cadastros/instrumentos_contratuais/excluir/<string:instrumento_id>', methods=['POST'])
@login_required
def excluir_instrumento_contratual(instrumento_id):
    user_id_obj = ObjectId(current_user.id)
    instrumento_id_obj = ObjectId(instrumento_id)

    # Lógica de segurança: verifica se algum item deste instrumento está em uso.
    # Passo 1: Encontrar todos os IDs dos itens pertencentes a este instrumento.
    itens_do_instrumento = list(itens_collection.find(
        {'instrumento_id': instrumento_id_obj, 'user_id': user_id_obj},
        {'_id': 1}
    ))
    
    # Se não houver itens, pode deletar sem problemas. Se houver, prossegue a verificação.
    if itens_do_instrumento:
        item_ids = [item['_id'] for item in itens_do_instrumento]

        # Passo 2: Verificar se algum desses IDs de item está na coleção de controle.
        controle_em_uso = controle_collection.find_one({
            'item_id': {'$in': item_ids},
            'user_id': user_id_obj
        })

        # Se encontrou um controle em uso, bloqueia a exclusão e informa o usuário.
        if controle_em_uso:
            flash('Não é possível excluir. Existem registros de controle vinculados a itens deste instrumento.', 'error')
            return redirect(url_for('gerenciar_instrumento', instrumento_id=instrumento_id))

    # Se passou pela verificação, pode excluir o instrumento e todos os seus itens associados.
    instrumentos_collection.delete_one({'_id': instrumento_id_obj, 'user_id': user_id_obj})
    itens_collection.delete_many({'instrumento_id': instrumento_id_obj, 'user_id': user_id_obj})
    
    flash('Instrumento Contratual e todos os seus itens foram excluídos com sucesso!', 'success')
    return redirect(url_for('instrumentos_contratuais'))

# --- CADASTROS DE SITUAÇÃO ---
@app.route('/cadastros/situacao')
@login_required
def cadastros_situacao():
    situacoes = situacao_collection.find({'user_id': ObjectId(current_user.id)})
    return render_template('situacao.html', situacoes=list(situacoes))

@app.route('/cadastros/situacao/novo', methods=['GET', 'POST'])
@login_required
def nova_situacao():
    if request.method == 'POST':
        situacao_nome = request.form['situacao'].strip()
        # <<< ADICIONADO: Pega o valor da cor do formulário >>>
        cor_situacao = request.form.get('cor_situacao', '#ffffff').strip()
        arquiva = 'arquiva_registro' in request.form

        if not situacao_nome:
            flash('O nome da situação não pode ser vazio.', 'error')
            return render_template('form_situacao.html', situacao=request.form, novo=True)
        if situacao_collection.find_one({'situacao': situacao_nome, 'user_id': ObjectId(current_user.id)}):
            flash('Você já possui uma situação com este nome.', 'error')
            return render_template('form_situacao.html', situacao=request.form, novo=True)

        # <<< ADICIONADO: Salva a cor no banco de dados >>>
        situacao_collection.insert_one({
            'situacao': situacao_nome, 
            'cor': cor_situacao,
            'user_id': ObjectId(current_user.id),
            'arquiva_registro': arquiva
        })
        flash('Situação criada com sucesso!', 'success')
        return redirect(url_for('cadastros_situacao'))
    return render_template('form_situacao.html', situacao={}, novo=True)

@app.route('/cadastros/situacao/editar/<string:situacao_id>', methods=['GET', 'POST'])
@login_required
def editar_situacao(situacao_id):
    situacao = situacao_collection.find_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    if not situacao:
        flash('Situação não encontrada ou não pertence a você.', 'error')
        return redirect(url_for('cadastros_situacao'))
    
    if request.method == 'POST':
        nova_situacao_nome = request.form['situacao'].strip()
        # <<< ADICIONADO: Pega o valor da cor do formulário >>>
        nova_cor_situacao = request.form.get('cor_situacao', '#ffffff').strip()
        arquiva = 'arquiva_registro' in request.form

        if not nova_situacao_nome:
            flash('O nome da situação não pode ser vazio.', 'error')
            return render_template('form_situacao.html', situacao=situacao, novo=False)
        
        controle_collection.update_many(
            {'situacao': situacao['situacao'], 'user_id': ObjectId(current_user.id)},
            {'$set': {'situacao': nova_situacao_nome}}
        )
        situacao_collection.update_one(
            {'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)},
            # <<< ADICIONADO: Atualiza a cor no banco de dados >>>
            {'$set': {'situacao': nova_situacao_nome, 'cor': nova_cor_situacao, 'arquiva_registro': arquiva}}
        )
        flash('Situação atualizada com sucesso!', 'success')
        return redirect(url_for('cadastros_situacao'))
    return render_template('form_situacao.html', situacao=situacao, novo=False)

@app.route('/cadastros/situacao/excluir/<string:situacao_id>', methods=['POST'])
@login_required
def excluir_situacao(situacao_id):
    situacao = situacao_collection.find_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    if not situacao:
        flash('Situação não encontrada.', 'error')
        return redirect(url_for('cadastros_situacao'))

    if controle_collection.find_one({'situacao': situacao['situacao'], 'user_id': ObjectId(current_user.id)}):
        flash('Não é possível excluir. Esta situação está em uso por registros de controle.', 'error')
        return redirect(url_for('cadastros_situacao'))
        
    result = situacao_collection.delete_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    if result.deleted_count > 0:
        flash('Situação excluída com sucesso!', 'success')
    else:
        flash('Erro ao excluir ou situação não encontrada.', 'error')
    return redirect(url_for('cadastros_situacao'))

# --- ROTAS DE CONTROLE ATUALIZADAS PARA ENVIAR O MAPA DE CORES ---

def get_color_map_for_user():
    """Função auxiliar para criar um mapa de Situação -> Cor."""
    situacoes = situacao_collection.find({'user_id': ObjectId(current_user.id)}, {'situacao': 1, 'cor': 1})
    # Cria um dicionário, ex: {'FAZER': '#ff0000', 'CONCLUÍDO': '#00ff00'}
    return {s['situacao']: s.get('cor', '#ffffff') for s in situacoes}

# --- CADASTROS DE TIPOS DE DOCUMENTO ---

@app.route('/cadastros/documentacao')
@login_required
def cadastros_documentacao():
    documentos = documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)})
    return render_template('cadastros_documentacao.html', documentos=list(documentos))

@app.route('/cadastros/documentacao/novo', methods=['GET', 'POST'])
@login_required
def novo_tipo_documento():
    if request.method == 'POST':
        nome_doc = request.form.get('nome_documento', '').strip()
        if nome_doc:
            documentacao_tipos_collection.insert_one({
                'nome': nome_doc,
                'user_id': ObjectId(current_user.id)
            })
            flash('Tipo de documento criado com sucesso!', 'success')
            return redirect(url_for('cadastros_documentacao'))
        else:
            flash('O nome do documento não pode ser vazio.', 'error')
    return render_template('form_documentacao.html', documento={}, novo=True)

@app.route('/cadastros/documentacao/excluir/<string:doc_id>', methods=['POST'])
@login_required
def excluir_tipo_documento(doc_id):
    # Opcional: Adicionar uma verificação para ver se o tipo de documento está em uso por algum item
    documentacao_tipos_collection.delete_one({'_id': ObjectId(doc_id), 'user_id': ObjectId(current_user.id)})
    flash('Tipo de documento excluído com sucesso!', 'success')
    return redirect(url_for('cadastros_documentacao'))

# --- ROTAS DE CONTROLE ---
@app.route('/controle/pendentes')
@login_required
def controle_pendentes():
    situacoes_arquivadoras = get_situacoes_que_arquivam()

    # <<< LÓGICA DE ORDENAÇÃO ADICIONADA AQUI >>>
    sort_by = request.args.get('sort_by', 'data_criacao') # Campo padrão para ordenar
    order = request.args.get('order', 'asc') # Ordem padrão (descendente)
    
    # Converte 'asc'/'desc' para 1/-1 do MongoDB
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}


    # Passa o documento de ordenação para a função de busca
    controles = get_controle_data(
        query_filter={'situacao': {'$nin': situacoes_arquivadoras}}, # nin = not in
        sort_document=sort_document
    )
    
    # O resto da função permanece igual...
    situacoes_para_filtro = get_situacoes_para_dropdown()
    chart_data_json = prepare_chart_data(controles)
    color_map_json = json.dumps(get_color_map_for_user())
    
    # Passa os parâmetros de ordenação para o template, para que ele possa montar os links
    return render_template(
        'controle_notas_fiscais.html', 
        controles=list(controles), 
        situacoes_para_filtro=situacoes_para_filtro, 
        filter_mode='pendentes', 
        chart_data=chart_data_json, 
        filter_values={}, 
        color_map_json=color_map_json, # <<< ENVIANDO O ESTADO ATUAL DA ORDENAÇÃO PARA O TEMPLATE >>>
        filtro_ativo=False,
        arquivadores_json=json.dumps(situacoes_arquivadoras),
        sort_by=sort_by,
        order=order,
        todas_as_colunas=TODAS_AS_COLUNAS_CONTROLE,
        colunas_visiveis=current_user.colunas_visiveis
    )

# --- CONTROLE DE PENDÊNCIAS ---

@app.route('/pendencias/diversos')
@login_required
def pendencias_diversos():
    # <<< INÍCIO DA LÓGICA DE ORDENAÇÃO >>>
    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = [(sort_by, sort_order_mongo)]
    # <<< FIM DA LÓGICA DE ORDENAÇÃO >>>

    lista_pendencias = pendencias_collection.find({
        'user_id': ObjectId(current_user.id),
        'status': 'Pendente',
        'instrumento_id': {'$exists': False}
    }).sort(sort_document) # <<< ADICIONADO O .sort() >>>

    return render_template(
        'pendencias_diversos.html', 
        pendencias=list(lista_pendencias),
        sort_by=sort_by,
        order=order,
        filter_values={}
    )

@app.route('/pendencias/novo', methods=['GET', 'POST'])
@login_required
def nova_pendencia():
    if request.method == 'POST':
        instrumento_id = request.form.get('instrumento_id') # <<< Pega o ID do instrumento
        nova = {
            'pendencia': request.form.get('pendencia'),
            'prazo': datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None,
            'responsavel': request.form.get('responsavel'),
            'situacao': request.form.get('situacao'),
            'observacoes': request.form.get('observacoes'),
            'status': 'Pendente',
            'user_id': ObjectId(current_user.id),
            'data_criacao': datetime.now(),
            # <<< Salva o ID se ele for selecionado >>>
            'instrumento_id': ObjectId(instrumento_id) if instrumento_id else None
        }
        pendencias_collection.insert_one(nova)
        flash('Nova pendência criada com sucesso!', 'success')
        # Redireciona para a lista correta dependendo se foi vinculada ou não
        if instrumento_id:
            return redirect(url_for('pendencias_por_instrumento')) # (Criaremos esta rota depois)
        else:
            return redirect(url_for('pendencias_diversos'))

    # <<< Busca os instrumentos para popular o dropdown >>>
    instrumentos = get_instrumentos_para_dropdown()
    return render_template('form_pendencia.html', pendencia={}, novo=True, instrumentos=instrumentos)

@app.route('/pendencias/detalhes/<string:pendencia_id>', methods=['GET', 'POST'])
@login_required
def detalhes_pendencia(pendencia_id):
    pendencia = pendencias_collection.find_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    if not pendencia:
        flash('Pendência não encontrada.', 'error')
        return redirect(url_for('pendencias_diversos'))

    if request.method == 'POST':
        instrumento_id = request.form.get('instrumento_id') # <<< Pega o ID do instrumento
        update = {
            'pendencia': request.form.get('pendencia'),
            'prazo': datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None,
            'responsavel': request.form.get('responsavel'),
            'situacao': request.form.get('situacao'),
            'observacoes': request.form.get('observacoes'),
            'status': request.form.get('status'),
            # <<< Salva o ID se ele for selecionado >>>
            'instrumento_id': ObjectId(instrumento_id) if instrumento_id else None
        }
        pendencias_collection.update_one({'_id': ObjectId(pendencia_id)}, {'$set': update})
        flash('Pendência atualizada com sucesso!', 'success')
        return redirect(url_for('detalhes_pendencia', pendencia_id=pendencia_id))
    
    # <<< Busca os instrumentos para popular o dropdown >>>
    instrumentos = get_instrumentos_para_dropdown()
    return render_template('form_pendencia.html', pendencia=pendencia, novo=False, instrumentos=instrumentos)

@app.route('/pendencias/excluir/<string:pendencia_id>', methods=['POST'])
@login_required
def excluir_pendencia(pendencia_id):
    pendencias_collection.delete_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    flash('Pendência excluída com sucesso!', 'success')
    return redirect(url_for('pendencias_diversos'))

@app.route('/pendencias/filtrar', methods=['POST'])
@login_required
def pendencias_filtrar():
    filter_values = {key.replace('filter_', ''): val.strip() for key, val in request.form.items() if key.startswith('filter_')}
    
    query_filter = {
        'user_id': ObjectId(current_user.id),
        'status': 'Pendente',
        'instrumento_id': {'$exists': False} # Mantém o filtro de pendências diversas
    }

    for key, value in filter_values.items():
        if value:
            query_filter[key] = {'$regex': value, '$options': 'i'}
            
    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = [(sort_by, sort_order_mongo)]

    lista_pendencias = pendencias_collection.find(query_filter).sort(sort_document)

    return render_template(
        'pendencias_diversos.html', 
        pendencias=list(lista_pendencias), 
        sort_by=sort_by,
        order=order,
        filter_values=request.form
    )



@app.route('/controle/concluidas')
@login_required
def controle_concluidas():
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    
    # <<< LÓGICA DE ORDENAÇÃO ADICIONADA AQUI >>>
    sort_by = request.args.get('sort_by', 'data_criacao') # Campo padrão para ordenar
    order = request.args.get('order', 'asc') # Ordem padrão (descendente)
    
    # Converte 'asc'/'desc' para 1/-1 do MongoDB
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}

    # Passa o documento de ordenação para a função de busca
    controles = get_controle_data(
    query_filter={'situacao': {'$in': situacoes_arquivadoras}}, # in = está na lista
        sort_document=sort_document
    )
    
    situacoes_para_filtro = get_situacoes_para_dropdown()
    chart_data_json = prepare_chart_data(controles)
    # <<< ADICIONADO: Envia o mapa de cores para o template >>>
    color_map_json = json.dumps(get_color_map_for_user())
    return render_template(
        'controle_notas_fiscais.html', 
        controles=list(controles), 
        situacoes_para_filtro=situacoes_para_filtro, 
        filter_mode='concluidas', 
        chart_data=chart_data_json, 
        filter_values={}, 
        color_map_json=color_map_json,
        filtro_ativo=False,
        arquivadores_json=json.dumps(situacoes_arquivadoras),
        sort_by=sort_by,
        order=order,
        todas_as_colunas=TODAS_AS_COLUNAS_CONTROLE,
        colunas_visiveis=current_user.colunas_visiveis
    )

@app.route('/controle/filtrar', methods=['POST'])
@login_required
def controle_filtrar():
    filter_values = {key.replace('filter_', ''): val.strip() for key, val in request.form.items() if key.startswith('filter_')}
    original_filter_mode = request.form.get('original_filter_mode', 'pendentes')
    
    query_filter = {}
    
    situacoes_arquivadoras = get_situacoes_que_arquivam()

    if original_filter_mode == 'pendentes':
        query_filter['situacao'] = {'$nin': situacoes_arquivadoras}
    elif original_filter_mode == 'concluidas':
        query_filter['situacao'] = {'$in': situacoes_arquivadoras}

    for key, value in filter_values.items():
        if value:
            query_filter[key] = {'$regex': value, '$options': 'i'}
            
    # <<< LÓGICA DE ORDENAÇÃO ADICIONADA >>>
    # (Mantém a ordenação atual se o usuário estiver apenas filtrando)
    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}

    controles = get_controle_data(query_filter, sort_document=sort_document)
    
    situacoes_para_filtro = get_situacoes_para_dropdown()
    chart_data_json = prepare_chart_data(controles)
    color_map_json = json.dumps(get_color_map_for_user())
    
    return render_template(
        'controle_notas_fiscais.html', 
        controles=list(controles), 
        situacoes_para_filtro=situacoes_para_filtro, 
        filter_mode=original_filter_mode, 
        filter_values=request.form, 
        chart_data=chart_data_json,
        color_map_json=color_map_json,
        filtro_ativo=True,
        arquivadores_json=json.dumps(situacoes_arquivadoras),
        sort_by=sort_by,
        order=order,
        todas_as_colunas=TODAS_AS_COLUNAS_CONTROLE,
        colunas_visiveis=current_user.colunas_visiveis
    )
    
# ======================================================================
# CORREÇÃO 2: LÓGICA DE CRIAÇÃO DE NOVO CONTROLE
# ======================================================================
@app.route('/controle/novo', methods=['GET', 'POST'])
@login_required
def novo_controle():
    itens_for_js = get_itens_para_dropdown_js(somente_vigentes=True)
    situacoes = get_situacoes_para_dropdown()

    if request.method == 'POST':
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()
        
        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento" e "Referência" são obrigatórios.', 'error')
            return render_template('form_controle.html', controle=request.form, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True)

        item_selecionado = itens_collection.find_one({'_id': ObjectId(item_id_str), 'user_id': ObjectId(current_user.id)})
        if not item_selecionado:
            flash("Item selecionado inválido.", "error")
            return render_template('form_controle.html', controle=request.form, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True)

        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        novo_registro_controle = {
            'item_id': ObjectId(item_id_str),
            # Denormalizando dados para facilitar a exibição e busca
            'n_instrumento': instrumento_pai['n_instrumento'],
            'tipo_documento': instrumento_pai['tipo_documento'],
            'contratada': instrumento_pai['contratada'],
            # Objeto agora é SÓ o objeto do instrumento principal.
            'objeto': instrumento_pai['objeto_resumido'],
            # O item não é mais combinado aqui.
            
            'referencia': referencia,
            'nota_fiscal': request.form.get('nota_fiscal', '').strip(),
            'carta_de_correcao': request.form.get('carta_de_correcao', '').strip(),
            'documentacao': request.form.getlist('documentacao'), # Pega todos os checkboxes marcados
            'observacoes': request.form.get('observacoes', '').strip(),
            'situacao': request.form.get('situacao', '').strip(),
            'data_criacao': datetime.now(),
            'user_id': ObjectId(current_user.id)
        }
        controle_collection.insert_one(novo_registro_controle)
        flash('Registro de Controle criado com sucesso!', 'success')
        return redirect(url_for('controle_pendentes'))
        
    return render_template('form_controle.html', controle={}, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True)

# ======================================================================
# CORREÇÃO 3: LÓGICA DE CRIAÇÃO DE CONTROLE RECORRENTE
# ======================================================================
@app.route('/controle/novo_recorrente', methods=['POST'])
@login_required
def novo_controle_recorrente():
    user_id_obj = ObjectId(current_user.id)
    referencia_digitada = request.form.get('referencia_recorrente', '').strip()

    if not referencia_digitada:
        flash('Por favor, digite uma referência.', 'error')
        return redirect(url_for('controle_pendentes'))

    match = re.match(r'^\s*(\d{1,2})\s*(?:[/-]\s*(\d{4}))?\s*$', referencia_digitada)
    if not match:
        flash(f"Formato de referência '{referencia_digitada}' inválido. Use MM/AAAA ou apenas MM.", 'error')
        return redirect(url_for('controle_pendentes'))

    mes_num = int(match.group(1))
    ano_num = int(match.group(2)) if match.group(2) else datetime.now().year
    
    referencia_mensal = f"{mes_num:02d}/{ano_num}"
    referencia_bimestral = f"{(mes_num - 1):02d}-{mes_num:02d}/{ano_num}" if mes_num % 2 == 0 else None

    pipeline_recorrentes = [
        {'$match': {'user_id': user_id_obj, 'vigente': True}},
        {'$lookup': { 'from': 'ITENS_INSTRUMENTO', 'localField': '_id', 'foreignField': 'instrumento_id', 'as': 'itens' }},
        {'$unwind': '$itens'},
        {'$match': {'itens.tipo_frequencia': {'$in': [re.compile('mensal', re.IGNORECASE), re.compile('bimestral', re.IGNORECASE)]}}},
        {'$project': {
            'item_id': '$itens._id',
            'tipo_frequencia': '$itens.tipo_frequencia',
            'n_instrumento': '$n_instrumento',
            'tipo_documento': '$tipo_documento',
            'contratada': '$contratada',
            'objeto_resumido': '$objeto_resumido'
            # Não precisamos mais da descrição do item aqui, pois a função de exibição a busca
        }}
    ]
    
    itens_recorrentes = list(instrumentos_collection.aggregate(pipeline_recorrentes))
    
    created_count, skipped_count = 0, 0
    for item in itens_recorrentes:
        tipo_freq = item.get('tipo_frequencia', '').lower()
        referencia_a_usar = referencia_mensal if 'mensal' in tipo_freq else (referencia_bimestral if 'bimestral' in tipo_freq else None)
        
        if not referencia_a_usar: continue

        if controle_collection.find_one({'item_id': item['item_id'], 'referencia': referencia_a_usar, 'user_id': user_id_obj}):
            skipped_count += 1
            continue

        controle_collection.insert_one({
            'item_id': item['item_id'],
            'n_instrumento': item['n_instrumento'],
            'tipo_documento': item['tipo_documento'],
            'contratada': item['contratada'],
            # Objeto agora é SÓ o objeto do instrumento principal.
            'objeto': item['objeto_resumido'],
            'referencia': referencia_a_usar,
            'nota_fiscal': '', 'carta_de_correcao': '', 'relatorio': '', 'documentacao': '',
            'observacoes': f'Gerado automaticamente a partir de {referencia_digitada}',
            'situacao': '',
            'data_criacao': datetime.now(),
            'user_id': user_id_obj
        })
        created_count += 1
    
    if created_count > 0: flash(f'{created_count} novo(s) registro(s) recorrente(s) criado(s) com sucesso!', 'success')
    if skipped_count > 0: flash(f'{skipped_count} registro(s) foram ignorados pois já existiam para essa referência.', 'info')
    if not created_count and not skipped_count: flash("Nenhum item recorrente (mensal/bimestral) encontrado nos seus instrumentos vigentes.", 'warning')

    return redirect(url_for('controle_pendentes'))

@app.route('/controle/detalhes/<string:controle_id>', methods=['GET', 'POST'])
@login_required
def detalhes_controle(controle_id):
    controle = controle_collection.find_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if not controle:
        flash('Registro de Controle não encontrado ou não pertence a você.', 'error')
        return redirect(url_for('controle_pendentes'))

    if request.method == 'POST':
        # ... (toda a sua lógica de validação e busca de dados continua aqui)
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()

        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento Contratual" e "Referência" são obrigatórios.', 'error')
            # ... (lógica de recarregar a página em caso de erro)
            return render_template(...)
        
        item_selecionado = itens_collection.find_one({'_id': ObjectId(item_id_str), 'user_id': ObjectId(current_user.id)})
        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        update_data = {
            'item_id': item_selecionado['_id'],
            'n_instrumento': instrumento_pai['n_instrumento'],
            'tipo_documento': instrumento_pai['tipo_documento'],
            'contratada': instrumento_pai['contratada'],
            'objeto': instrumento_pai['objeto_resumido'],
            'referencia': referencia,
            'nota_fiscal': request.form.get('nota_fiscal', '').strip(),
            'carta_de_correcao': request.form.get('carta_de_correcao', '').strip(),
            'documentacao': request.form.getlist('documentacao'),
            'observacoes': request.form.get('observacoes', '').strip(),
            'situacao': request.form.get('situacao', '').strip(),
            'data_ultima_atualizacao': datetime.now()
        }

        controle_collection.update_one(
            {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )
        flash('Registro de Controle atualizado com sucesso!', 'success')
        
        # ======================================================================
        # <<< A ÚNICA MUDANÇA É NESTA LINHA >>>
        # Redireciona para a própria página de detalhes, em vez da lista.
        # ======================================================================
        return redirect(url_for('detalhes_controle', controle_id=controle_id))

    # A lógica GET para carregar a página pela primeira vez permanece a mesma
    itens_for_js = get_itens_para_dropdown_js()
    situacoes = get_situacoes_para_dropdown()
    current_item_id_str = str(controle.get('item_id', ''))

    return render_template('form_controle.html', controle=controle, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, current_item_id=current_item_id_str, novo=False)

@app.route('/controle/excluir/<string:controle_id>', methods=['POST'])
@login_required
def excluir_controle(controle_id):
    result = controle_collection.delete_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if result.deleted_count > 0:
        flash('Registro de Controle excluído com sucesso!', 'success')
    else:
        flash('Erro ao excluir ou registro não encontrado.', 'error')
    return redirect(url_for('controle_pendentes'))

@app.route('/exportar/<string:filter_mode>')
@login_required
def exportar_csv(filter_mode):
    """Gera e baixa um arquivo CSV dos registros de controle visíveis na tela."""
    
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    if filter_mode == 'pendentes':
        query_filter = {'situacao': {'$nin': situacoes_arquivadoras}}
    elif filter_mode == 'concluidas':
        query_filter = {'situacao': {'$in': situacoes_arquivadoras}}
    else:
        flash("Modo de filtro inválido para exportação.", "error")
        return redirect(url_for('index'))

    registros = get_controle_data(query_filter)

    colunas = {
        'TIPO DOCUMENTO': 'tipo_documento',
        'Nº INSTRUMENTO': 'n_instrumento',
        'CONTRATADA': 'contratada',
        'OBJETO': 'objeto',
        'NOTA FISCAL': 'nota_fiscal',
        'CARTA DE CORREÇÃO': 'carta_de_correcao',
        'DOCUMENTAÇÃO': 'documentacao',
        'OBSERVAÇÕES': 'observacoes',
        'SITUAÇÃO': 'situacao'
    }

    output = io.StringIO()
    # *** ALTERAÇÃO APLICADA AQUI: Adiciona o BOM (Byte Order Mark) para UTF-8 ***
    # Isso sinaliza ao Excel para usar a codificação correta e exibir os acentos.
    output.write('\ufeff')
    
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
    
    writer.writerow(colunas.keys())

    for registro in registros:
        linha = [registro.get(campo_db, '') for campo_db in colunas.values()]
        writer.writerow(linha)

    output.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"export_controle_{filter_mode}_{timestamp}.csv"

    # A resposta Flask irá codificar a string (incluindo o BOM) para bytes UTF-8
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

# para alterar campo SITUAÇÃO diretamente na tabela de controle geral sem a necessidade de editar o registro
@app.route('/controle/update_situacao_inline', methods=['POST'])
@login_required
def update_situacao_inline():
    """
    Rota para atualizar a situação de um registro de controle via AJAX.
    """
    data = request.get_json()
    controle_id = data.get('controle_id')
    nova_situacao = data.get('nova_situacao')

    if not controle_id or nova_situacao is None:
        return {'status': 'error', 'message': 'Dados incompletos.'}, 400

    result = controle_collection.update_one(
        {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
        {'$set': {'situacao': nova_situacao, 'data_ultima_atualizacao': datetime.now()}}
    )

    if result.matched_count > 0:
        return {'status': 'success', 'message': 'Situação atualizada.'}
    else:
        return {'status': 'error', 'message': 'Registro não encontrado ou não pertence ao usuário.'}, 404

@app.route('/cadastros/instrumentos_contratuais/gerenciar/<string:instrumento_id>', methods=['GET', 'POST'])
@login_required
def gerenciar_instrumento(instrumento_id):
    instrumento = instrumentos_collection.find_one({'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)})
    if not instrumento:
        flash('Instrumento Contratual não encontrado.', 'error')
        return redirect(url_for('instrumentos_contratuais'))

    # Se a requisição for para ATUALIZAR O INSTRUMENTO PRINCIPAL
    if request.method == 'POST' and 'update_instrumento' in request.form:
        instrumentos_collection.update_one(
            {'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)},
            {'$set': {
                'contratada': request.form['contratada'].strip(),
                'objeto_resumido': request.form['objeto_resumido'].strip(),
                'vigente': 'vigente' in request.form
            }}
        )
        flash('Instrumento Contratual atualizado com sucesso!', 'success')
        return redirect(url_for('gerenciar_instrumento', instrumento_id=instrumento_id))

    # Busca os itens associados a este instrumento
    itens = list(itens_collection.find({'instrumento_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)}))
    
    # Este template é a nova página central para gerenciar um instrumento e seus itens.
    # Certifique-se de que o arquivo 'gerenciar_instrumento.html' que sugeri na outra resposta existe.
    return render_template('gerenciar_instrumento.html', instrumento=instrumento, itens=itens)

# app.py - NOVAS ROTAS

@app.route('/instrumento/<string:instrumento_id>/item/novo', methods=['GET', 'POST'])
@login_required
def adicionar_item_instrumento(instrumento_id):
    instrumento = instrumentos_collection.find_one({'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)})
    # <<< ADICIONE ESTAS LINHAS PARA BUSCAR OS TIPOS DE DOCUMENTO >>>
    todos_os_docs = list(documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)}))
    
    if not instrumento:
        flash('Instrumento Contratual não encontrado.', 'error')
        return redirect(url_for('instrumentos_contratuais'))

    if request.method == 'POST':
        descricao = request.form.get('descricao_item', '').strip()
        frequencia = request.form.get('tipo_frequencia', '').strip()
        
        docs_str = request.form.get('documentos_exigidos_hidden', '')
        documentos_exigidos = request.form.getlist('documentos_exigidos')

        if not descricao or not frequencia:
            flash('Descrição e Frequência do item são obrigatórios.', 'error')
            return render_template('form_item.html', instrumento=instrumento, item={}, novo=True)
        
        itens_collection.insert_one({
            'instrumento_id': ObjectId(instrumento_id),
            'descricao_item': descricao,
            'tipo_frequencia': frequencia,
            'user_id': ObjectId(current_user.id),
            'documentos_exigidos': documentos_exigidos # <<< CAMPO NOVO ADICIONADO
        })
        flash('Novo item adicionado com sucesso!', 'success')
        return redirect(url_for('gerenciar_instrumento', instrumento_id=instrumento_id))

    return render_template('form_item.html', instrumento=instrumento, item={}, novo=True, todos_os_docs=todos_os_docs)

@app.route('/item/<string:item_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_item_instrumento(item_id):
    item = itens_collection.find_one({'_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)})
    if not item:
        flash('Item não encontrado.', 'error')
        return redirect(url_for('instrumentos_contratuais'))
    
    instrumento = instrumentos_collection.find_one({'_id': item['instrumento_id']})

    # <<< ADICIONE ESTAS LINHAS PARA BUSCAR OS TIPOS DE DOCUMENTO >>>
    todos_os_docs = list(documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)}))

    if request.method == 'POST':
        descricao = request.form.get('descricao_item', '').strip()
        frequencia = request.form.get('tipo_frequencia', '').strip()
        docs_str = request.form.get('documentos_exigidos_hidden', '')
        # <<< ALTERE A FORMA DE PEGAR OS DOCUMENTOS EXIGIDOS >>>
        documentos_exigidos = request.form.getlist('documentos_exigidos')

        if not descricao or not frequencia:
            flash('Descrição e Frequência do item são obrigatórios.', 'error')
            # É crucial buscar os documentos aqui também para re-renderizar o formulário
            todos_os_docs = list(documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)}))
            return render_template('form_item.html', instrumento=instrumento, item=request.form, novo=True, todos_os_docs=todos_os_docs)

        itens_collection.update_one(
            {'_id': ObjectId(item_id)},
            {'$set': {
                'descricao_item': descricao,
                'tipo_frequencia': frequencia,
                'documentos_exigidos': documentos_exigidos # <<< CAMPO NOVO ADICIONADO
            }}
        )
        flash('Item atualizado com sucesso!', 'success')
        return redirect(url_for('gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))

    return render_template('form_item.html', instrumento=instrumento, item=item, novo=False, todos_os_docs=todos_os_docs)

#if __name__ == '__main__':
#    app.run(debug=True)

if __name__ == '__main__':
    # O site de hospedagem define a porta através de uma variável de ambiente PORT
    port = int(os.environ.get("PORT", 5000))
    # O host '0.0.0.0' é necessário para que o app seja acessível de fora do container online
    app.run(host='0.0.0.0', port=port, debug=True)
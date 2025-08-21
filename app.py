# 1. Bibliotecas Padrão do Python
import os
import json
import re
import io
import csv
from collections import Counter
from datetime import datetime, timedelta

# 2. Bibliotecas de Terceiros (Instaladas via pip)
import certifi
from bson import json_util
from bson.objectid import ObjectId
from flask import Flask, Response, flash, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from pymongo import MongoClient
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.jinja_env.globals.update(datetime=datetime)


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

# Para as configurações de exibição de colunas

TODAS_AS_COLUNAS_CONTROLE = [
    ['tipo_documento', 'Tipo Documento'],
    ['n_instrumento', 'Nº Instrumento'],
    ['contratada', 'Contratada'],
    ['objeto', 'Objeto'],
    ['item_descricao', 'Item'],
    ['referencia', 'Referência'],
    ['nota_fiscal', 'Documento Fiscal'],
    ['carta_de_correcao', 'Carta de Correção'],
    ['documentacao', 'Documentação'],
    ['observacoes', 'Observações'],
    ['situacao', 'Situação']
]

TODAS_AS_COLUNAS_PENDENCIAS = [
    ['instrumento_display', 'Nº / Tipo'], # <<< NOVA COLUNA
    ['contratada', 'Contratada'],         # <<< NOVA COLUNA
    ['pendencia', 'Pendência'],
    ['prazo', 'Prazo'],
    ['responsavel', 'Responsável'],
    ['situacao', 'Situação'],
    ['observacoes', 'Observações']
]

# --- Configuração Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

class User(UserMixin):
    def __init__(self, username, email, password_hash, id=None, theme='theme-blue', 
                 colunas_visiveis=None, colunas_visiveis_pendencias=None, 
                 font_size_preference=None, spacing_preference=None): # <--- PARÂMETROS ADICIONADOS AQUI
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.id = str(id) if id else None
        self.theme = theme
        self.colunas_visiveis = colunas_visiveis or [col[0] for col in TODAS_AS_COLUNAS_CONTROLE]
        self.colunas_visiveis_pendencias = colunas_visiveis_pendencias or [col[0] for col in TODAS_AS_COLUNAS_PENDENCIAS]
        # LINHAS CORRIGIDAS ABAIXO
        self.font_size_preference = font_size_preference or 'media'
        self.spacing_preference = spacing_preference or 'regular'

    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        #print(f"--- DEBUG: Carregando usuário '{user_data['username']}' -> Espaçamento salvo: '{user_data.get('spacing_preference')}' ---")
        return User(
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            id=user_data['_id'],
            theme=user_data.get('theme', 'theme-blue'),
            colunas_visiveis=user_data.get('colunas_visiveis_controle'),
            colunas_visiveis_pendencias=user_data.get('colunas_visiveis_pendencias'),
            font_size_preference=user_data.get('font_size_preference', 'media'),
            spacing_preference=user_data.get('spacing_preference', 'regular')
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
    """Busca apenas os campos necessários dos instrumentos VIGENTES do usuário."""
    instrumentos = list(instrumentos_collection.find(
        {'user_id': ObjectId(current_user.id), 'vigente': True},
        {'n_instrumento': 1, 'tipo_documento': 1, 'contratada': 1, 'objeto_resumido': 1}
    ))
    # <<< Garante que o ObjectId seja sempre convertido para string >>>
    for inst in instrumentos:
        inst['_id'] = str(inst['_id'])
    return instrumentos

def get_pendencias_com_detalhes(query_filter, sort_document):
    """Busca pendências e faz o join com instrumentos para obter detalhes."""
    
    # Separa os filtros: os que são da pendência e os que são do instrumento
    filtros_instrumento = {}
    if 'instrumento_info.n_instrumento' in query_filter:
        filtros_instrumento['instrumento_info.n_instrumento'] = query_filter.pop('instrumento_info.n_instrumento')
    if 'instrumento_info.contratada' in query_filter:
        filtros_instrumento['instrumento_info.contratada'] = query_filter.pop('instrumento_info.contratada')

    pipeline = [
        {'$match': query_filter}, # Primeiro, filtra as pendências
        {'$lookup': {
            'from': 'INSTRUMENTOCONTRATUAL',
            'localField': 'instrumento_id',
            'foreignField': '_id',
            'as': 'instrumento_info'
        }},
        {'$unwind': {'path': '$instrumento_info', 'preserveNullAndEmptyArrays': True}},
        # Agora que os dados foram juntados, podemos aplicar o segundo filtro
        {'$match': filtros_instrumento}, 
        {'$addFields': {
            'contratada': '$instrumento_info.contratada',
            'n_instrumento': '$instrumento_info.n_instrumento', # Adiciona para ordenação
            'instrumento_display': {
                '$concat': [
                    {'$ifNull': ['$instrumento_info.n_instrumento', '']}, ' / ',
                    {'$ifNull': ['$instrumento_info.tipo_documento', '']}
                ]
            }
        }},
        {'$sort': sort_document}
    ]
    pendencias = list(pendencias_collection.aggregate(pipeline))
    
    for p in pendencias:
        if not p.get('instrumento_id'):
            p['instrumento_display'] = ''
    return pendencias

def _gerar_pendencias_csv(query_filter, filename_prefix):
    """Função auxiliar para gerar CSV de pendências."""
    sort_document = {'prazo': 1}
    # get_pendencias_com_detalhes já traz os dados do instrumento
    registros = get_pendencias_com_detalhes(query_filter, sort_document)

    output = io.StringIO()
    output.write('\ufeff')  # BOM para Excel entender UTF-8
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
    
    colunas = ['Nº / Tipo', 'Contratada', 'Pendência', 'Prazo', 'Responsável', 'Situação', 'Observações']
    writer.writerow(colunas)
    
    for r in registros:
        linha = [
            r.get('instrumento_display', 'Pendência Diversa'), # <--- MAIS EFICIENTE
            r.get('contratada', ''),                         # <--- MAIS EFICIENTE
            r.get('pendencia', ''),
            r.get('prazo').strftime('%d/%m/%Y') if r.get('prazo') else '',
            r.get('responsavel', ''),
            r.get('situacao', ''),
            r.get('observacoes', '')
        ]
        writer.writerow(linha)

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.csv"
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

# fim das funções auxiliares

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
                theme=user_data.get('theme', 'theme-blue'),
                font_size_preference=user_data.get('font_size_preference', 'media'),
                spacing_preference=user_data.get('spacing_preference', 'regular')
            )
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Login inválido. Verifique seu nome de usuário e senha.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
#@limiter.limit("5 per minute")
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

# --- Rotas de preferências pessoais ---

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

@app.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    if request.method == 'POST':
        # Valida as opções recebidas do formulário
        font_size = request.form.get('font_size')
        allowed_fonts = ['pequena', 'media', 'grande', 'extra_grande']
        if font_size not in allowed_fonts:
            font_size = 'media' # Valor padrão seguro

        spacing = request.form.get('spacing')
        allowed_spacing = ['compacto', 'regular', 'espacado']
        if spacing not in allowed_spacing:
            spacing = 'regular' # Valor padrão seguro

        #print(f"--- DEBUG: Tentando salvar -> Fonte: '{font_size}', Espaçamento: '{spacing}' ---")

        # Atualiza o documento do usuário no banco de dados
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {
                'font_size_preference': font_size,
                'spacing_preference': spacing
            }}
        )
        flash('Configurações salvas com sucesso!', 'success')
        # É importante recarregar o usuário para que as novas preferências sejam aplicadas
        
        #logout_user()
        #ou
        current_user.font_size_preference = font_size
        current_user.spacing_preference = spacing
        
        return redirect(url_for('login')) 
    
    # Se for GET, apenas exibe a página
    return render_template('configuracoes.html')

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

@app.route('/user/save_pendencias_column_prefs', methods=['POST'])
@login_required
def save_pendencias_column_prefs():
    data = request.get_json()
    colunas = data.get('colunas', [])
    
    colunas_permitidas = [col[0] for col in TODAS_AS_COLUNAS_PENDENCIAS]
    colunas_validas = [c for c in colunas if c in colunas_permitidas]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'colunas_visiveis_pendencias': colunas_validas}}
    )
    return {'status': 'success'}

# --- Rotas Principais ---

@app.route('/')
@login_required
def index():
    try:
        user_id_obj = ObjectId(current_user.id)
        hoje = datetime.now().date()
        data_limite_semana = (datetime.now() + timedelta(days=7)).date()

        # --- Contagens Originais (Instrumentos e Controles) ---
        # Lógica correta para Controles Pendentes
        situacoes_arquivadoras = get_situacoes_que_arquivam()
        controles_pendentes_count = controle_collection.count_documents({
            'user_id': user_id_obj,
            'situacao': {'$nin': situacoes_arquivadoras}
        })

        instrumentos_vigentes_count = instrumentos_collection.count_documents({'user_id': user_id_obj, 'vigente': True})
        total_instrumentos_count = instrumentos_collection.count_documents({'user_id': user_id_obj})
        
        frequencia_pipeline = [
            {'$match': {'user_id': user_id_obj, 'vigente': True}},
            {'$lookup': {'from': 'ITENS_INSTRUMENTO', 'localField': '_id', 'foreignField': 'instrumento_id', 'as': 'itens'}},
            {'$unwind': '$itens'},
            {'$group': {'_id': '$itens.tipo_frequencia', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        frequencias_data = list(instrumentos_collection.aggregate(frequencia_pipeline))

        # --- Novas Consultas para Pendências ---
        pendencias_vencidas_count = pendencias_collection.count_documents({
            'user_id': user_id_obj, 'status': 'Pendente',
            'prazo': {'$lt': datetime.combine(hoje, datetime.min.time())}
        })
        pendencias_a_vencer_count = pendencias_collection.count_documents({
            'user_id': user_id_obj, 'status': 'Pendente',
            'prazo': {
                '$gte': datetime.combine(hoje, datetime.min.time()),
                '$lt': datetime.combine(data_limite_semana, datetime.min.time())
            }
        })
        pipeline_responsavel = [
            {'$match': {'user_id': user_id_obj, 'status': 'Pendente'}},
            {'$group': {'_id': {'$ifNull': ['$responsavel', 'Não Definido']}, 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        pendencias_por_responsavel = list(pendencias_collection.aggregate(pipeline_responsavel))
        
        # --- Junção de todos os dados para enviar ao template ---
        summary_data = {
            'pendentes': controles_pendentes_count,
            'vigentes': instrumentos_vigentes_count,
            'total_instrumentos': total_instrumentos_count,
            'frequencias': frequencias_data,
            'pendencias_vencidas': pendencias_vencidas_count,
            'pendencias_a_vencer': pendencias_a_vencer_count,
            'pendencias_por_responsavel': pendencias_por_responsavel
        }
        
        with open('changelog.json', 'r', encoding='utf-8') as f:
            changelog_data = json.load(f)

    except Exception as e:
        flash(f"Não foi possível carregar os dados do dashboard: {e}", "error")
        summary_data = {
            'pendentes': 0, 'vigentes': 0, 'total_instrumentos': 0, 'frequencias': [],
            'pendencias_vencidas': 0, 'pendencias_a_vencer': 0, 'pendencias_por_responsavel': []
        }
        changelog_data = []

    return render_template('index.html', summary=summary_data, changelog=changelog_data)

# --- CADASTROS DE INSTRUMENTOS ---

@app.route('/cadastros/instrumentos_contratuais', defaults={'filtro': 'vigentes'})
@app.route('/cadastros/instrumentos_contratuais/<string:filtro>')
@login_required
def instrumentos_contratuais(filtro):
    query = {'user_id': ObjectId(current_user.id)}
    if filtro == 'vigentes':
        query['vigente'] = True
    elif filtro == 'extintos':
        query['vigente'] = False
    # Se filtro for 'todos', nenhuma chave 'vigente' é adicionada.

    # <<< LÓGICA ALTERADA PARA USAR AGGREGATION >>>
    pipeline = [
        # 1. Filtra os instrumentos como antes
        {'$match': query},
        # 2. "Junta" os dados da coleção de itens
        {
            '$lookup': {
                'from': 'ITENS_INSTRUMENTO',
                'localField': '_id',
                'foreignField': 'instrumento_id',
                'as': 'itens_associados'
            }
        },
        # 3. Cria o novo campo 'itens_string' com a lista de descrições
        {
            '$addFields': {
                'itens_string': {
                    '$reduce': {
                        'input': '$itens_associados.descricao_item',
                        'initialValue': '',
                        'in': {
                            '$cond': {
                                'if': {'$eq': ['$$value', '']},
                                'then': '$$this',
                                'else': {'$concat': ['$$value', ', ', '$$this']}
                            }
                        }
                    }
                }
            }
        },
        # 4. (Opcional) Remove o array de itens para limpar o resultado
        {
            '$project': {
                'itens_associados': 0
            }
        }
    ]

    instrumentos = instrumentos_collection.aggregate(pipeline)
    return render_template('instrumentos_contratuais.html', instrumentos=list(instrumentos), filtro_ativo=filtro)

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

@app.route('/controle/<string:filter_mode>')
@login_required
def controle_lista(filter_mode):
    # 1. Monta o filtro base de acordo com o modo da página
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    query_filter = {}
    if filter_mode == 'pendentes':
        query_filter['situacao'] = {'$nin': situacoes_arquivadoras}
    elif filter_mode == 'concluidas':
        query_filter['situacao'] = {'$in': situacoes_arquivadoras}
    else:
        # Redireciona para um modo padrão se a URL for inválida
        return redirect(url_for('controle_lista', filter_mode='pendentes'))

    # 2. Adiciona filtros do formulário (vindas da URL via GET)
    filter_values = {}
    filtro_ativo = False
    for key, value in request.args.items():
        if key.startswith('filter_') and value:
            clean_key = key.replace('filter_', '')
            query_filter[clean_key] = {'$regex': value.strip(), '$options': 'i'}
            filter_values[key] = value
            filtro_ativo = True

    # 3. Lógica de Ordenação
    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}

    # 4. Busca os dados
    controles = get_controle_data(query_filter, sort_document=sort_document)
    
    # 5. Prepara dados para o template
    situacoes_para_filtro = get_situacoes_para_dropdown()
    chart_data_json = prepare_chart_data(controles)
    color_map_json = json.dumps(get_color_map_for_user())

    # 6. Renderiza o template
    return render_template(
        'controle_notas_fiscais.html',
        controles=list(controles),
        situacoes_para_filtro=situacoes_para_filtro,
        filter_mode=filter_mode,
        filter_values=filter_values,
        chart_data=chart_data_json,
        color_map_json=color_map_json,
        filtro_ativo=filtro_ativo,
        arquivadores_json=json.dumps(situacoes_arquivadoras),
        sort_by=sort_by,
        order=order,
        todas_as_colunas=TODAS_AS_COLUNAS_CONTROLE,
        colunas_visiveis=current_user.colunas_visiveis
    )

# --- CONTROLE DE PENDÊNCIAS ---

@app.route('/pendencias/<string:page_mode>')
@login_required
def pendencias_lista(page_mode="geral"):
    # Define o filtro base
    query_filter = {'user_id': ObjectId(current_user.id)}
    template_a_renderizar = 'pendencias_geral.html'
    
    if page_mode == 'concluidas':
        query_filter['status'] = 'Concluído'
    elif page_mode == 'diversas':
        query_filter['status'] = 'Pendente'
        query_filter['instrumento_id'] = {'$in': [None, '']}
        template_a_renderizar = 'pendencias_diversos.html' # Ainda usa o template antigo se quiser
    else: # modo 'geral'
        query_filter['status'] = 'Pendente'
        page_mode = 'geral' # Garante um valor padrão
    
    # Adiciona filtros da URL (via GET)
    filter_values = {}
    for key, value in request.args.items():
        if key.startswith('filter_') and value:
            clean_key = key.replace('filter_', '').strip()
            filter_values[key] = value
            if clean_key in ['n_instrumento', 'contratada']:
                query_filter[f'instrumento_info.{clean_key}'] = {'$regex': value, '$options': 'i'}
            else:
                query_filter[clean_key] = {'$regex': value, '$options': 'i'}

    # Lógica de ordenação
    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}

    # Busca os dados
    lista_pendencias = get_pendencias_com_detalhes(query_filter, sort_document)
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for p in lista_pendencias:
        p['vencido'] = p.get('prazo') and p.get('prazo') < hoje

    colunas_visiveis = getattr(current_user, 'colunas_visiveis_pendencias', [c[0] for c in TODAS_AS_COLUNAS_PENDENCIAS])
    
    return render_template(
        template_a_renderizar,
        pendencias=lista_pendencias,
        sort_by=sort_by, order=order,
        filter_values=filter_values,
        todas_as_colunas=TODAS_AS_COLUNAS_PENDENCIAS,
        colunas_visiveis=colunas_visiveis,
        page_mode=page_mode
    )

@app.route('/pendencias/filtrar', methods=['POST'])
@login_required
def pendencias_filtrar():
    page_mode = request.form.get('page_mode', 'geral')
    filter_params = {key: val for key, val in request.form.items() if key.startswith('filter_') and key != 'page_mode'}
    return redirect(url_for('pendencias_lista', page_mode=page_mode, **filter_params))

@app.route('/pendencias/por_instrumento')
@login_required
def pendencias_por_instrumento():
    user_id_obj = ObjectId(current_user.id)
    
    # Pega o filtro opcional da URL (para o dropdown de instrumentos)
    instrumento_filtro_id = request.args.get('instrumento_id')

    # --- Lógica de Filtro e Busca ---
    match_filter = {
        'user_id': user_id_obj,
        'status': 'Pendente',
        'instrumento_id': {'$exists': True, '$ne': None}
    }
    # Se um instrumento específico foi selecionado, adiciona ao filtro
    if instrumento_filtro_id:
        match_filter['instrumento_id'] = ObjectId(instrumento_filtro_id)
        
    pipeline = [
        {'$match': match_filter},
        {'$sort': {'prazo': 1}},
        {'$lookup': {
            'from': 'INSTRUMENTOCONTRATUAL',
            'localField': 'instrumento_id',
            'foreignField': '_id',
            'as': 'instrumento_info'
        }},
        {'$unwind': {'path': '$instrumento_info', 'preserveNullAndEmptyArrays': True}},
        {'$group': {
            '_id': '$instrumento_id',
            'detalhes_instrumento': {'$first': '$instrumento_info'},
            'pendencias': {'$push': {
                '_id': '$_id', 'pendencia': '$pendencia', 'prazo': '$prazo',
                'responsavel': '$responsavel', 'situacao': '$situacao'
            }}
        }},
        {'$sort': {'detalhes_instrumento.n_instrumento': 1}}
    ]
    grupos_de_pendencias = list(pendencias_collection.aggregate(pipeline))

    # --- Lógica de Preparação dos Dados (separar por prazo) ---
    # Define 'hoje' como a meia-noite do dia atual
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for grupo in grupos_de_pendencias:
        if not grupo.get('detalhes_instrumento'):
            grupo['detalhes_instrumento'] = {'n_instrumento': 'Inválido', 'tipo_documento': 'Instrumento', 'contratada': 'Não encontrado', 'objeto_resumido': 'Link quebrado.'}
        
        pendencias_com_prazo = [p for p in grupo['pendencias'] if p.get('prazo')]
        grupo['pendencias_sem_prazo'] = [p for p in grupo['pendencias'] if not p.get('prazo')]
        
        if pendencias_com_prazo:
            grupo['pendencias_vencidas'] = [p for p in pendencias_com_prazo if p['prazo'] < hoje]
            grupo['pendencias_a_vencer'] = [p for p in pendencias_com_prazo if p['prazo'] >= hoje]
        else:
            grupo['pendencias_vencidas'] = []
            grupo['pendencias_a_vencer'] = []
    
    # Busca todos os instrumentos para popular o dropdown de filtro da página
    instrumentos_para_filtro = get_instrumentos_para_dropdown()

    return render_template(
        'pendencias_por_instrumento.html', 
        grupos=grupos_de_pendencias, 
        instrumentos_para_filtro=instrumentos_para_filtro,
        instrumento_filtro_id=instrumento_filtro_id
    )

@app.route('/pendencias/novo', methods=['GET', 'POST'])
@login_required
def nova_pendencia():
    # Pega a origem da URL quando a página é aberta
    origem_url = request.args.get('origem', url_for('pendencias_lista', page_mode='geral'))

    if request.method == 'POST':
        instrumento_id = request.form.get('instrumento_id')
        nova = {
            'pendencia': request.form.get('pendencia'),
            'prazo': datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None,
            'responsavel': request.form.get('responsavel'), 'situacao': request.form.get('situacao'),
            'observacoes': request.form.get('observacoes'), 'status': 'Pendente',
            'user_id': ObjectId(current_user.id), 'data_criacao': datetime.now(),
            'instrumento_id': ObjectId(instrumento_id) if instrumento_id else None
        }
        pendencias_collection.insert_one(nova)
        flash('Nova pendência criada com sucesso!', 'success')

        # O redirect aqui já estava correto, mantemos
        return redirect(url_for('pendencias_lista', page_mode='geral'))

    # Lógica GET
    instrumentos = get_instrumentos_para_dropdown()
    instrumentos_json = json.dumps(instrumentos, default=json_util.default)
    return render_template('form_pendencia.html', pendencia={}, novo=True, instrumentos=instrumentos, instrumentos_json=instrumentos_json, origem=origem_url)

@app.route('/pendencias/detalhes/<string:pendencia_id>', methods=['GET', 'POST'])
@login_required
def detalhes_pendencia(pendencia_id):
    pendencia = pendencias_collection.find_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    if not pendencia:
        flash('Pendência não encontrada.', 'error')
        return redirect(url_for('pendencias_lista', page_mode='geral'))

    # Pega a origem da URL (se existir) ou usa o referrer como fallback
    origem_url = request.args.get('origem', request.referrer or url_for('pendencias_lista', page_mode='geral'))

    if request.method == 'POST':
        # A lógica POST permanece a mesma, mas o redirect fica mais simples
        instrumento_id = request.form.get('instrumento_id')
        update_data = {
            'pendencia': request.form.get('pendencia'),
            'prazo': datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None,
            'responsavel': request.form.get('responsavel'), 'situacao': request.form.get('situacao'),
            'observacoes': request.form.get('observacoes'), 'status': request.form.get('status'),
            'instrumento_id': ObjectId(instrumento_id) if instrumento_id else None
        }
        pendencias_collection.update_one({'_id': ObjectId(pendencia_id)}, {'$set': update_data})
        flash('Pendência atualizada com sucesso!', 'success')
        
        # Lê a origem do campo oculto e a repassa no redirect
        origem_post = request.form.get('origem')
        return redirect(url_for('detalhes_pendencia', pendencia_id=pendencia_id, origem=origem_post))

    # Lógica GET
    instrumentos = get_instrumentos_para_dropdown()
    pendencia_json = json.dumps(pendencia, default=json_util.default)
    return render_template('form_pendencia.html', pendencia=pendencia, novo=False, instrumentos=instrumentos, pendencia_json=pendencia_json, origem=origem_url)

@app.route('/pendencias/excluir/<string:pendencia_id>', methods=['POST'])
@login_required
def excluir_pendencia(pendencia_id):
    pendencias_collection.delete_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    flash('Pendência excluída com sucesso!', 'success')
    return redirect(url_for('pendencias_lista', page_mode='geral'))

    #return redirect(url_for('pendencias_diversos'))

@app.route('/pendencias/exportar/pendentes')
@login_required
def exportar_pendencias_pendentes_csv():
    query_filter = {'user_id': ObjectId(current_user.id), 'status': 'Pendente'}
    return _gerar_pendencias_csv(query_filter, "export_pendencias_pendentes")

@app.route('/pendencias/exportar/concluidas')
@login_required
def exportar_pendencias_concluidas_csv():
    query_filter = {'user_id': ObjectId(current_user.id), 'status': 'Concluído'}
    return _gerar_pendencias_csv(query_filter, "export_pendencias_concluidas")



# ======================================================================
# 2: LÓGICA DE CRIAÇÃO DE NOVO CONTROLE
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
        return redirect(url_for('controle_lista', filter_mode='pendentes'))
        
    return render_template('form_controle.html', controle={}, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True)

# ======================================================================
# 3: LÓGICA DE CRIAÇÃO DE CONTROLE RECORRENTE
# ======================================================================
@app.route('/controle/novo_recorrente', methods=['POST'])
@login_required
def novo_controle_recorrente():
    user_id_obj = ObjectId(current_user.id)
    referencia_digitada = request.form.get('referencia_recorrente', '').strip()

    if not referencia_digitada:
        flash('Por favor, digite uma referência.', 'error')
        return redirect(url_for('controle_lista', filter_mode='pendentes'))

    match = re.match(r'^\s*(\d{1,2})\s*(?:[/-]\s*(\d{4}))?\s*$', referencia_digitada)
    if not match:
        flash(f"Formato de referência '{referencia_digitada}' inválido. Use MM/AAAA ou apenas MM.", 'error')
        return redirect(url_for('controle_lista', filter_mode='pendentes'))

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

    return redirect(url_for('controle_lista', filter_mode='pendentes'))

@app.route('/controle/detalhes/<string:controle_id>', methods=['GET', 'POST'])
@login_required
def detalhes_controle(controle_id):
    controle = controle_collection.find_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if not controle:
        flash('Registro de Controle não encontrado ou não pertence a você.', 'error')
        return redirect(url_for('controle_lista', filter_mode='pendentes'))

    if request.method == 'POST':
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()

        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento" e "Referência" são obrigatórios.', 'error')
            # Recarrega os dados necessários para o template em caso de erro
            itens_for_js = get_itens_para_dropdown_js()
            situacoes = get_situacoes_para_dropdown()
            # Retorna o formulário com os dados que o usuário já preencheu
            return render_template(
                'form_controle.html', 
                controle=request.form, 
                itens_for_js=json.dumps(itens_for_js), 
                situacoes=situacoes, 
                current_item_id=item_id_str, 
                novo=False
            )
        
        # Esta parte agora só executa se a validação acima passar
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
        return redirect(url_for('detalhes_controle', controle_id=controle_id))

    # Lógica GET (quando a página é carregada pela primeira vez)
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
    return redirect(url_for('controle_lista', filter_mode='pendentes'))

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
        'ITEM': 'item_descricao',
        'REFERÊNCIA': 'referencia',
        'DOCUMENTO FISCAL': 'nota_fiscal',
        'CARTA DE CORREÇÃO': 'carta_de_correcao',
        'DOCUMENTAÇÃO': 'documentacao',
        'OBSERVAÇÕES': 'observacoes',
        'SITUAÇÃO': 'situacao'
    }

    output = io.StringIO()
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
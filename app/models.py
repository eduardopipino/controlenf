# 1. Bibliotecas Padrão do Python
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from collections import OrderedDict

# 2. Bibliotecas de Terceiros (Instaladas via pip)
from bson import json_util
from bson.objectid import ObjectId
from flask_login import UserMixin, current_user


from app import db

# Coleções
instrumentos_collection = db['INSTRUMENTOCONTRATUAL']
itens_collection = db['ITENS_INSTRUMENTO']
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

# --- NOVA CONSTANTE PARA OS CAMPOS DOS CARDS ---
TODAS_AS_COLUNAS_CARDS = [
    ['referencia', 'Referência'],
    ['tipo_documento', 'Tipo Documento'],
    ['n_instrumento', 'Contrato'],
    ['contratada', 'Contratada'],
    ['objeto', 'Objeto'],
    ['item_descricao', 'Item'],
    ['nota_fiscal', 'Documento Fiscal'],
    ['carta_de_correcao', 'Carta de Correção'],
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

class User(UserMixin):
    def __init__(self, username, email, password_hash, id=None, theme='theme-blue', 
                 colunas_visiveis=None, colunas_visiveis_pendencias=None, 
                 font_size_preference=None, spacing_preference=None,
                 view_mode_controle=None, card_fields_controle=None,
                 color_coding_controle=None, view_mode_pendencias=None, card_fields_pendencias=None,color_coding_pendencias=None):
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
        self.view_mode_controle = view_mode_controle or 'table'
        self.card_fields_controle = card_fields_controle or [field[0] for field in TODAS_AS_COLUNAS_CARDS[:4]]
        self.color_coding_controle = color_coding_controle or False
        self.view_mode_pendencias = view_mode_pendencias or 'table'
        self.card_fields_pendencias = card_fields_pendencias or ['pendencia', 'responsavel', 'prazo']
        self.color_coding_pendencias = color_coding_pendencias or False

    def get_id(self):
        return self.id

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
            # Envolvemos cada campo em um segundo $ifNull para garantir que o resultado final nunca seja nulo, e sim ""
            'n_instrumento':  {'$ifNull': [{'$ifNull': ['$instrumento_join.n_instrumento', '$n_instrumento']}, ""]},
            'tipo_documento': {'$ifNull': [{'$ifNull': ['$instrumento_join.tipo_documento', '$tipo_documento']}, ""]},
            'contratada':     {'$ifNull': [{'$ifNull': ['$instrumento_join.contratada', '$contratada']}, ""]},
            'objeto':         {'$ifNull': [{'$ifNull': ['$instrumento_join.objeto_resumido', '$objeto']}, ""]},
            'item_descricao': {'$ifNull': ['$item_join.descricao_item', ""]},
            
            # <<< ADICIONAMOS OS CAMPOS DA TABELA CONTROLE PARA GARANTIR QUE NÃO SEJAM NULOS >>>
            'nota_fiscal':      {'$ifNull': ['$nota_fiscal', ""]},
            'referencia':       {'$ifNull': ['$referencia', ""]},
            'observacoes':      {'$ifNull': ['$observacoes', ""]},
            'documentacao':     {'$ifNull': ['$documentacao', []]}, # Documentação deve ser uma lista vazia, não string
            'documentacao_pendente': {
                '$ifNull': [
                    {'$setDifference': [
                        {'$ifNull': ['$item_join.documentos_exigidos', []]},
                        # A MUDANÇA ESTÁ AQUI: Verifica se 'documentacao' é um array.
                        # Se for, usa o campo. Se não for (é uma string), usa uma lista vazia [].
                        {'$cond': {
                            'if': {'$isArray': '$documentacao'},
                            'then': '$documentacao',
                            'else': []
                        }}
                    ]},
                    []
                ]
            }
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

def get_pendencias_com_detalhes(query_filter):
    """Busca pendências e faz o join com instrumentos para obter detalhes."""
    
    filtros_instrumento = {}
    if 'instrumento_info.n_instrumento' in query_filter:
        filtros_instrumento['instrumento_info.n_instrumento'] = query_filter.pop('instrumento_info.n_instrumento')
    if 'instrumento_info.contratada' in query_filter:
        filtros_instrumento['instrumento_info.contratada'] = query_filter.pop('instrumento_info.contratada')

    pipeline = [
        {'$match': query_filter},
        {'$lookup': { 'from': 'INSTRUMENTOCONTRATUAL', 'localField': 'instrumento_id', 'foreignField': '_id', 'as': 'instrumento_info' }},
        {'$unwind': {'path': '$instrumento_info', 'preserveNullAndEmptyArrays': True}},
        {'$match': filtros_instrumento}, 
        {'$addFields': {
            'contratada': '$instrumento_info.contratada',
            'n_instrumento': '$instrumento_info.n_instrumento',
            'instrumento_display': { '$concat': [ {'$ifNull': ['$instrumento_info.n_instrumento', '']}, ' / ', {'$ifNull': ['$instrumento_info.tipo_documento', '']} ] },
        }}
    ]
    
    pendencias = list(pendencias_collection.aggregate(pipeline))
    
    for p in pendencias:
        if not p.get('instrumento_id'):
            p['instrumento_display'] = ''
    return pendencias

 
def get_color_map_for_user():
    """
    Função auxiliar para criar um mapa de Situação -> Cor,
    considerando o tema ativo do usuário.
    """
    situacoes = situacao_collection.find(
        {'user_id': ObjectId(current_user.id)}, 
        {'situacao': 1, 'cor': 1, 'cor_tema_escuro': 1}
    )
    
    color_map = {}
    is_dark_theme = current_user.theme == 'theme-dark'

    for s in situacoes:
        situacao_nome = s['situacao']
        
        if is_dark_theme:
            # Tenta pegar a cor específica do tema escuro.
            dark_color = s.get('cor_tema_escuro')
            # Se uma cor escura foi definida E não é uma string vazia, use-a.
            if dark_color:
                color_map[situacao_nome] = dark_color
            # Caso contrário, use uma cor escura PADRÃO, nunca a cor do tema claro.
            else:
                color_map[situacao_nome] = '#3a3a3a' # Um cinza escuro seguro
        else:
            # Para outros temas, a lógica continua a mesma.
            color_map[situacao_nome] = s.get('cor', '#ffffff')
            
    return color_map

# Função para exibir tabela de controle de notas fiscais em pendências por instrumento conratual

def get_controles_pendentes_por_instrumento(instrumento_id):
    """Busca todos os registros de controle pendentes associados a um instrumento."""
    user_id_obj = ObjectId(current_user.id)
    instrumento_id_obj = ObjectId(instrumento_id)

    # 1. Encontra todos os IDs dos itens que pertencem a este instrumento
    itens_do_instrumento = list(itens_collection.find(
        {'instrumento_id': instrumento_id_obj, 'user_id': user_id_obj},
        {'_id': 1}
    ))
    item_ids = [item['_id'] for item in itens_do_instrumento]

    # Se não houver itens, não há controles para buscar
    if not item_ids:
        return []

    # 2. Busca as situações que arquivam um registro
    situacoes_arquivadoras = get_situacoes_que_arquivam()

    # 3. Busca os controles pendentes que pertencem a qualquer um dos itens encontrados
    pipeline = [
        {'$match': {
            'user_id': user_id_obj,
            'item_id': {'$in': item_ids},
            'situacao': {'$nin': situacoes_arquivadoras}
        }},
        # Faz um join para buscar a descrição do item, que será útil no template
        {'$lookup': {
            'from': 'ITENS_INSTRUMENTO',
            'localField': 'item_id',
            'foreignField': '_id',
            'as': 'item_info'
        }},
        {'$unwind': '$item_info'},
        {'$addFields': {
            'item_descricao': '$item_info.descricao_item',
            'situacao': '$situacao'
        }},
        {'$sort': {'referencia': 1}}
    ]
    
    return list(controle_collection.aggregate(pipeline))

# fim das funções auxiliares

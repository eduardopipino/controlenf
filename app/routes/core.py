# app/routes/core.py
# Este arquivo contém as rotas principais (dashboard) e de configuração do usuário.

# 1. Imports de bibliotecas padrão e de terceiros
from flask import (Blueprint, flash, json, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from bson.objectid import ObjectId
from datetime import datetime, timedelta

# 2. Imports da nossa própria aplicação (dos modelos que criamos)
from app.models import (users_collection, get_situacoes_que_arquivam, controle_collection,
                        instrumentos_collection, pendencias_collection,
                        TODAS_AS_COLUNAS_CONTROLE, TODAS_AS_COLUNAS_PENDENCIAS,
                        quick_notes_collection)

# 3. Criação do Blueprint Principal
# O nome 'core' será usado nos comandos url_for().
core_bp = Blueprint('core', __name__)


@core_bp.route('/')
@login_required
def index():
    # A lógica interna desta função é 100% idêntica à original.
    try:
        user_id_obj = ObjectId(current_user.id)
        hoje = datetime.now().date()
        data_limite_semana = (datetime.now() + timedelta(days=7)).date()

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
        
        summary_data = {
            'pendentes': controles_pendentes_count,
            'vigentes': instrumentos_vigentes_count,
            'total_instrumentos': total_instrumentos_count,
            'frequencias': frequencias_data,
            'pendencias_vencidas': pendencias_vencidas_count,
            'pendencias_a_vencer': pendencias_a_vencer_count,
            'pendencias_por_responsavel': pendencias_por_responsavel
        }
        
        # O arquivo changelog.json deve estar na raiz do projeto para este caminho funcionar.
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


@core_bp.route('/set_theme', methods=['POST'])
@login_required
def set_theme():
    # Rota de API (AJAX), lógica idêntica à original.
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


@core_bp.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    if request.method == 'POST':
        font_size = request.form.get('font_size')
        allowed_fonts = ['pequena', 'media', 'grande', 'extra_grande']
        if font_size not in allowed_fonts:
            font_size = 'media'

        spacing = request.form.get('spacing')
        allowed_spacing = ['compacto', 'regular', 'espacado']
        if spacing not in allowed_spacing:
            spacing = 'regular'

        atalhos = 'atalhos_ativos' in request.form

        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {
                'font_size_preference': font_size,
                'spacing_preference': spacing,
                'atalhos_ativos': atalhos
            }}
        )
        flash('Configurações salvas com sucesso! Para que as alterações tenham efeito completo, por favor, faça login novamente.', 'success')
        
        # Atualiza o objeto do usuário na sessão atual para reflexo imediato
        current_user.font_size_preference = font_size
        current_user.spacing_preference = spacing
        current_user.atalhos_ativos = atalhos
        
        # PONTO DE ATENÇÃO: Redireciona para a própria página de configurações.
        # Forçar um novo login pode ser uma experiência ruim para o usuário.
        # A mensagem flash já informa sobre isso.
        return redirect(url_for('core.configuracoes'))
    
    return render_template('configuracoes.html')


@core_bp.route('/user/save_column_prefs', methods=['POST'])
@login_required
def save_column_prefs():
    # Rota de API (AJAX), lógica idêntica à original.
    data = request.get_json()
    colunas = data.get('colunas', [])
    
    colunas_permitidas = [col[0] for col in TODAS_AS_COLUNAS_CONTROLE]
    colunas_validas = [c for c in colunas if c in colunas_permitidas]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'colunas_visiveis_controle': colunas_validas}}
    )
    # Atualiza o objeto do usuário na sessão atual
    current_user.colunas_visiveis = colunas_validas
    return {'status': 'success'}


@core_bp.route('/user/save_pendencias_column_prefs', methods=['POST'])
@login_required
def save_pendencias_column_prefs():
    # Rota de API (AJAX), lógica idêntica à original.
    data = request.get_json()
    colunas = data.get('colunas', [])
    
    colunas_permitidas = [col[0] for col in TODAS_AS_COLUNAS_PENDENCIAS]
    colunas_validas = [c for c in colunas if c in colunas_permitidas]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'colunas_visiveis_pendencias': colunas_validas}}
    )
    # Atualiza o objeto do usuário na sessão atual
    current_user.colunas_visiveis_pendencias = colunas_validas
    return {'status': 'success'}

@core_bp.route('/user/set_view_preference', methods=['POST'])
@login_required
def set_view_preference():
    data = request.get_json()
    view_mode = data.get('view_mode')
    
    # Valida se o modo de visualização é um dos permitidos
    if view_mode in ['table', 'cards', 'kanban']:
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'view_mode_controle': view_mode}}
        )
        return {'status': 'success'}
    
    return {'status': 'error', 'message': 'Modo de visualização inválido'}, 400

# Adicione este bloco no final de app/routes/core.py

@core_bp.route('/user/save_card_prefs', methods=['POST'])
@login_required
def save_card_prefs():
    data = request.get_json()
    campos = data.get('campos', [])

    # Importa a lista de campos permitidos para validação
    from app.models import TODAS_AS_COLUNAS_CARDS
    campos_permitidos = [field[0] for field in TODAS_AS_COLUNAS_CARDS]
    campos_validos = [c for c in campos if c in campos_permitidos]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'card_fields_controle': campos_validos}}
    )
    return {'status': 'success'}

@core_bp.route('/user/toggle_color_coding', methods=['POST'])
@login_required
def toggle_color_coding():
    # Pega o estado atual e inverte (se for True vira False, e vice-versa)
    novo_estado = not getattr(current_user, 'color_coding_controle', False)
    
    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'color_coding_controle': novo_estado}}
    )
    return {'status': 'success'}

@core_bp.route('/user/set_view_preference_pendencias', methods=['POST'])
@login_required
def set_view_preference_pendencias():
    data = request.get_json()
    view_mode = data.get('view_mode')
    if view_mode in ['table', 'cards', 'kanban']:
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'view_mode_pendencias': view_mode}}
        )
        return {'status': 'success'}
    return {'status': 'error', 'message': 'Modo de visualização inválido'}, 400

@core_bp.route('/user/save_card_prefs_pendencias', methods=['POST'])
@login_required
def save_card_prefs_pendencias():
    data = request.get_json()
    campos = data.get('campos', [])

    # Validação (usando a lista de colunas de pendências)
    campos_permitidos = [field[0] for field in TODAS_AS_COLUNAS_PENDENCIAS]
    campos_validos = [c for c in campos if c in campos_permitidos]

    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'card_fields_pendencias': campos_validos}}
    )
    return {'status': 'success'}

@core_bp.route('/user/toggle_color_coding_pendencias', methods=['POST'])
@login_required
def toggle_color_coding_pendencias():
    novo_estado = not getattr(current_user, 'color_coding_pendencias', False)
    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'color_coding_pendencias': novo_estado}}
    )
    return {'status': 'success'}

@core_bp.route('/user/toggle_nf_pendencias_instrumento', methods=['POST'])
@login_required
def toggle_nf_pendencias_instrumento():
    """ Salva a preferência do usuário para exibir/ocultar NFs na tela por instrumento. """
    try:
        user_data = users_collection.find_one({'_id': ObjectId(current_user.id)}, {'show_nf_pendencias_instrumento': 1})
        current_state = user_data.get('show_nf_pendencias_instrumento', False) # Default é False (oculto)
        new_state = not current_state

        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {'show_nf_pendencias_instrumento': new_state}}
        )
        # Atualiza o objeto do usuário na sessão atual, se necessário (boa prática)
        # Note: Isso pode não ser refletido imediatamente sem recarregar o usuário em algumas configurações.
        current_user.show_nf_pendencias_instrumento = new_state
        return {'status': 'success', 'newState': new_state}
    except Exception as e:
        print(f"Erro ao salvar preferência show_nf_pendencias_instrumento: {e}")
        return {'status': 'error', 'message': 'Erro ao salvar preferência.'}, 500

@core_bp.route('/get_quick_note', methods=['GET'])
@login_required
def get_quick_note():
    """Retorna a nota rápida do usuário atual."""
    note = quick_notes_collection.find_one({'user_id': ObjectId(current_user.id)})
    text = note.get('content', '') if note else ''
    return {'status': 'success', 'text': text}

@core_bp.route('/save_quick_note', methods=['POST'])
@login_required
def save_quick_note():
    """Salva (upsert) a nota rápida do usuário."""
    data = request.get_json()
    text = data.get('text', '')
    
    quick_notes_collection.update_one(
        {'user_id': ObjectId(current_user.id)},
        {'$set': {'content': text}},
        upsert=True
    )
    return {'status': 'success'}

@core_bp.route('/utilitarios/extenso')
@login_required
def utilitarios_extenso():
    return render_template('utilitarios_extenso.html')
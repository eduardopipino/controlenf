from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from bson.objectid import ObjectId
from datetime import datetime
from app.models import (instrumentos_collection, pendencias_collection, 
                        controle_collection, TODAS_AS_COLUNAS_PENDENCIAS, 
                        TODAS_AS_COLUNAS_CONTROLE, users_collection,
                        TODAS_AS_COLUNAS_CARDS, get_controles_pendentes_por_instrumento,
                        itens_collection, get_situacoes_para_dropdown,
                        get_color_map_for_user)

hub_ic_bp = Blueprint('hub_ic', __name__)

@hub_ic_bp.route('/controle_instrumento_contratual')
@login_required
def hub_instrumentos():
    user_id_obj = ObjectId(current_user.id)
    
    # 1. PEGAR O STATUS SEM VALOR PADRÃO (para que retorne None na primeira carga)
    filtro_status = request.args.get('status') 
    
    # SE FOR A PRIMEIRA VEZ (None), FORÇA VIGENTE
    if filtro_status is None:
        filtro_status = 'Vigente'
    
    filtro_contratada = request.args.get('contratada', '').strip()
    
    query = {'user_id': user_id_obj}
    
    # FILTRAGEM (Se for '', não entra em nenhum e mostra todos)
    if filtro_status == 'Vigente':
        query['vigente'] = True
    elif filtro_status == 'Extinto':
        query['vigente'] = False
        
    if filtro_contratada:
        query['contratada'] = {'$regex': filtro_contratada, '$options': 'i'}
        
    instrumentos = list(instrumentos_collection.find(query).sort('n_instrumento', 1))
    
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    hub_dados = []
    
    # NOVOS PARÂMETROS DE ORDENAÇÃO
    sort_pend = request.args.get('sort_pend', 'prazo')
    order_pend = request.args.get('order_pend', 'asc')
    sort_nf = request.args.get('sort_nf', 'data_criacao')
    order_nf = request.args.get('order_nf', 'asc')
    
    for inst in instrumentos:
        inst_id = inst['_id']
        
        pendencias_abertas = list(pendencias_collection.find({
            'instrumento_id': inst_id,
            'user_id': user_id_obj,
            'status': {'$ne': 'Concluído'}
        }))

        # Lógica de Ordenação das Pendências
        rev_pend = (order_pend == 'desc')
        pendencias_abertas.sort(key=lambda x: (x.get(sort_pend) is None, x.get(sort_pend, '')), reverse=rev_pend)
        pendencias_abertas.sort(key=lambda x: x.get('prioridade', False), reverse=True) # Prioridade sempre no topo!

        pendencias_sem_prazo = [p for p in pendencias_abertas if not p.get('prazo')]
        pendencias_com_prazo = [p for p in pendencias_abertas if p.get('prazo')]
        pendencias_vencidas = [p for p in pendencias_com_prazo if p['prazo'] < hoje]
        pendencias_a_vencer = [p for p in pendencias_com_prazo if p['prazo'] >= hoje]
        
        controles_pendentes = get_controles_pendentes_por_instrumento(inst_id)
        
        # Lógica de Ordenação dos Controles/NFs
        rev_nf = (order_nf == 'desc')
        controles_pendentes.sort(key=lambda x: (x.get(sort_nf) is None, x.get(sort_nf, '')), reverse=rev_nf)
        
        itens_do_instrumento = list(itens_collection.find({'instrumento_id': inst_id}))
        
        inst['str_id'] = str(inst_id)
        # Identifica textualmente o status para os badges do HTML
        is_vigente = inst.get('vigente', True)
        inst['status_texto'] = 'Vigente' if is_vigente else 'Extinto'

        hub_dados.append({
            'instrumento': inst,
            'pendencias': pendencias_abertas,
            'pendencias_sem_prazo': pendencias_sem_prazo,
            'pendencias_vencidas': pendencias_vencidas,
            'pendencias_a_vencer': pendencias_a_vencer,
            'controles': controles_pendentes,
            'itens': itens_do_instrumento,
            'stats': {
                'total_pendencias': len(pendencias_abertas),
                'total_controles': len(controles_pendentes),
            }
        })
        
    user_prefs = users_collection.find_one({'_id': user_id_obj}) or {}
    
    # 2. Correção: A visualização agora respeita a URL primeiro, garantindo a mudança de tela
    view_mode_db = user_prefs.get('view_preference_pendencias', 'table')
    view_mode = request.args.get('view', view_mode_db)
    
    colunas_visiveis_pendencias = user_prefs.get('colunas_visiveis_pendencias', [c[0] for c in TODAS_AS_COLUNAS_PENDENCIAS])
    colunas_visiveis_controle = user_prefs.get('colunas_visiveis_controle', [c[0] for c in TODAS_AS_COLUNAS_CONTROLE])
    card_fields_visiveis = user_prefs.get('card_fields_visiveis_pendencias', [c[0] for c in TODAS_AS_COLUNAS_CARDS])

    # Busca se a cor está ativa para as NFs (como no controle) e pega o mapa de cores real
    color_coding_active = getattr(current_user, 'color_coding_controle', False) 
    color_map = get_color_map_for_user()

    return render_template(
        'controle_por_instrumento.html',
        hub_dados=hub_dados,
        filtro_status=filtro_status,
        situacoes_para_filtro=get_situacoes_para_dropdown(), # <<< RESOLVE O SELECT VAZIO
        sort_pend=sort_pend, order_pend=order_pend,          # <<< PARA A ORDENAÇÃO
        sort_nf=sort_nf, order_nf=order_nf,                  # <<< PARA A ORDENAÇÃO
        colunas_visiveis_pendencias=colunas_visiveis_pendencias,
        todas_as_colunas_pendencias=TODAS_AS_COLUNAS_PENDENCIAS,
        colunas_visiveis_controle=colunas_visiveis_controle,
        todas_as_colunas_controle=TODAS_AS_COLUNAS_CONTROLE,
        todas_as_colunas_cards=TODAS_AS_COLUNAS_CARDS,
        card_fields_visiveis=card_fields_visiveis,
        color_coding_active=color_coding_active,             # <<< Envia se está ativo
        color_map=color_map,                                 # <<< Envia as cores reais
        view_mode=view_mode,
        page_mode='hub_ic'
    )
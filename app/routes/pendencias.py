# app/routes/pendencias.py
# Este arquivo contém todas as rotas para o gerenciamento de Pendências,
# incluindo listagem, criação, edição, exclusão e exportação.

# 1. Imports de bibliotecas padrão e de terceiros
from flask import (Blueprint, Response, flash, redirect,
                   render_template, request, url_for, json)
from flask_login import current_user, login_required
from bson.objectid import ObjectId
from datetime import datetime
import io
import csv

# 2. Imports da nossa própria aplicação (modelos e coleções)
from app.models import (pendencias_collection, get_pendencias_com_detalhes,
                        get_instrumentos_para_dropdown, TODAS_AS_COLUNAS_PENDENCIAS,
                        get_controles_pendentes_por_instrumento, get_color_map_for_user,
                        users_collection)

# 3. Criação do Blueprint de Pendências
# O nome 'pendencias' será usado nos comandos url_for().
# O prefixo '/pendencias' será adicionado às URLs deste blueprint
# ao ser registrado em app/__init__.py.
pendencias_bp = Blueprint('pendencias', __name__)


# --- FUNÇÃO AUXILIAR PARA EXPORTAÇÃO (MOVEMOS PARA CÁ) ---
# Como esta função gera uma Resposta HTTP (tarefa do controller),
# é mais apropriado que ela fique aqui do que em models.py.
def _gerar_pendencias_csv(query_filter, filename_prefix):
    """Função auxiliar para gerar CSV de pendências."""
    # Adicionamos uma ordenação padrão para o CSV
    sort_document = {'prazo': 1}
    # get_pendencias_com_detalhes já traz os dados do instrumento
    registros = get_pendencias_com_detalhes(query_filter) # A ordenação em Python não é necessária aqui

    output = io.StringIO()
    output.write('\ufeff')  # BOM para Excel entender UTF-8
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
    
    colunas = ['Nº / Tipo', 'Contratada', 'Pendência', 'Prazo', 'Responsável', 'Situação', 'Observações']
    writer.writerow(colunas)
    
    for r in registros:
        linha = [
            r.get('instrumento_display', 'Pendência Diversa'),
            r.get('contratada', ''),
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

# --- ROTAS PRINCIPAIS DE PENDÊNCIAS ---

@pendencias_bp.route('/<string:page_mode>')
@login_required
def pendencias_lista(page_mode="geral"):
    query_filter = {'user_id': ObjectId(current_user.id)}
    
    if page_mode == 'concluidas':
        query_filter['status'] = 'Concluído'
    elif page_mode == 'diversas':
        query_filter['status'] = 'Pendente'
        query_filter['instrumento_id'] = {'$in': [None, '']}
    else: # modo 'geral'
        query_filter['status'] = 'Pendente'
        page_mode = 'geral'
    
    filter_values = {}
    for key, value in request.args.items():
        if key.startswith('filter_') and value:
            clean_key = key.replace('filter_', '').strip()
            filter_values[key] = value
            if clean_key in ['n_instrumento', 'contratada']:
                query_filter[f'instrumento_info.{clean_key}'] = {'$regex': value, '$options': 'i'}
            else:
                query_filter[clean_key] = {'$regex': value, '$options': 'i'}

    # --- NOVO BLOCO PARA MENSAGEM FLASH ---
    if filter_values:
        nomes_amigaveis = {
            'filter_n_instrumento': 'Nº Instrumento',
            'filter_contratada': 'Contratada',
            'filter_pendencia': 'Pendência',
            'filter_responsavel': 'Responsável',
            'filter_situacao': 'Situação'
        }
        filtros_aplicados = [f"{nomes_amigaveis.get(k, k.replace('filter_', ''))}: '{v}'" for k, v in filter_values.items()]
        mensagem = "Filtro ativo! Exibindo registros onde " + ", ".join(filtros_aplicados) + "."
        flash(mensagem, 'info')
    # --- FIM DO NOVO BLOCO ---

    lista_pendencias_bruta = get_pendencias_com_detalhes(query_filter)

    # --- LÓGICA DE ORDENAÇÃO "4 BUCKETS" EM PYTHON ---
    sort_by = request.args.get('sort_by', 'prazo')
    order = request.args.get('order', 'asc')
    is_reverse = True if order == 'desc' else False

    prioritarios = [p for p in lista_pendencias_bruta if p.get('prioridade')]
    nao_prioritarios = [p for p in lista_pendencias_bruta if not p.get('prioridade')]

    def sort_bucket(bucket, key, is_reverse_order):
        com_valor = [p for p in bucket if p.get(key) and str(p.get(key)).strip() and str(p.get(key)).strip() != '/']
        sem_valor = [p for p in bucket if not p.get(key) or not str(p.get(key)).strip() or str(p.get(key)).strip() == '/']
        
        if key == 'instrumento_display':
            com_valor.sort(key=lambda x: (
                int(x.get('n_instrumento', '0/0').split('/')[1] if '/' in x.get('n_instrumento', '0/0') else 0), 
                int(x.get('n_instrumento', '0/0').split('/')[0] if '/' in x.get('n_instrumento', '0/0') else 0)
            ), reverse=is_reverse_order)
        else:
            com_valor.sort(key=lambda x: x.get(key, ''), reverse=is_reverse_order)
        return com_valor + sem_valor

    prioritarios_ordenados = sort_bucket(prioritarios, sort_by, is_reverse)
    nao_prioritarios_ordenados = sort_bucket(nao_prioritarios, sort_by, is_reverse)
    lista_pendencias = prioritarios_ordenados + nao_prioritarios_ordenados
    
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for p in lista_pendencias:
        p['vencido'] = p.get('prazo') and p.get('prazo') < hoje

    # --- NOVA LÓGICA PARA PREPARAR DADOS PARA O KANBAN ---
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        pendencias_vencidas = []
        pendencias_a_vencer = []
        pendencias_sem_prazo = []
        for p in lista_pendencias:
            p['vencido'] = p.get('prazo') and p.get('prazo') < hoje
            if p['vencido']:
                pendencias_vencidas.append(p)
            elif p.get('prazo'):
                pendencias_a_vencer.append(p)
            else:
                pendencias_sem_prazo.append(p)
        # --- FIM DA NOVA LÓGICA ---

    # 1. Cria a lista de opções para o modal dos cards, JÁ REMOVENDO o campo 'pendencia'
    opcoes_campos_cards = [field for field in TODAS_AS_COLUNAS_PENDENCIAS if field[0] != 'pendencia']

    # 2. Define a lista base para as colunas da tabela
    colunas_para_exibir = TODAS_AS_COLUNAS_PENDENCIAS

    # 3. Carrega as preferências do usuário
    colunas_visiveis = getattr(current_user, 'colunas_visiveis_pendencias', [c[0] for c in colunas_para_exibir])
    card_fields_visiveis = getattr(current_user, 'card_fields_pendencias', ['responsavel', 'prazo'])

    # 4. Se estiver no modo 'diversas', aplica o filtro adicional a TODAS as listas
    if page_mode == 'diversas':
        campos_a_remover = ['instrumento_display', 'contratada']
        colunas_para_exibir = [col for col in colunas_para_exibir if col[0] not in campos_a_remover]
        colunas_visiveis = [col for col in colunas_visiveis if col not in campos_a_remover]
        opcoes_campos_cards = [opt for opt in opcoes_campos_cards if opt[0] not in campos_a_remover] # Filtra a lista já filtrada
        card_fields_visiveis = [field for field in card_fields_visiveis if field not in campos_a_remover]

    view_mode = getattr(current_user, 'view_mode_pendencias', 'table')
    
    # --- NOVAS VARIÁVEIS PARA O TEMPLATE ---
    color_map = get_color_map_for_user()
    opcoes_campos_cards = [field for field in TODAS_AS_COLUNAS_PENDENCIAS if field[0] != 'pendencia']

    return render_template(
        'pendencias_geral.html',
        pendencias=lista_pendencias,
        pendencias_vencidas=pendencias_vencidas,
        pendencias_a_vencer=pendencias_a_vencer,
        pendencias_sem_prazo=pendencias_sem_prazo,
        view_mode=view_mode,
        todas_as_colunas=colunas_para_exibir, # Usa a lista filtrada para a tabela
        colunas_visiveis=colunas_visiveis,     # Usa a lista filtrada para a tabela
        todas_as_colunas_cards=opcoes_campos_cards, # <-- Passa a lista duplamente filtrada
        card_fields_visiveis=card_fields_visiveis, # Usa a lista filtrada para os cards
        order=order,
        filter_values=filter_values,
        page_mode=page_mode,
        color_map=color_map,
        color_coding_active=getattr(current_user, 'color_coding_pendencias', False)
    )

@pendencias_bp.route('/filtrar', methods=['POST'])
@login_required
def pendencias_filtrar():
    page_mode = request.form.get('page_mode', 'geral')
    filter_params = {key: val for key, val in request.form.items() if key.startswith('filter_') and key != 'page_mode'}
    # PONTO DE ATENÇÃO: Redireciona para a rota '.pendencias_lista' (dentro deste blueprint)
    return redirect(url_for('.pendencias_lista', page_mode=page_mode, **filter_params))


@pendencias_bp.route('/por_instrumento')
@login_required
def pendencias_por_instrumento():
    user_id_obj = ObjectId(current_user.id)
    instrumento_filtro_id = request.args.get('instrumento_id')
    match_filter = {
        'user_id': user_id_obj, 'status': 'Pendente',
        'instrumento_id': {'$exists': True, '$ne': None}
    }
    if instrumento_filtro_id:
        match_filter['instrumento_id'] = ObjectId(instrumento_filtro_id)
        
    pipeline = [
        {'$match': match_filter}, {'$sort': {'prazo': 1}},
        {'$lookup': {'from': 'INSTRUMENTOCONTRATUAL', 'localField': 'instrumento_id', 'foreignField': '_id', 'as': 'instrumento_info'}},
        {'$unwind': {'path': '$instrumento_info', 'preserveNullAndEmptyArrays': True}},
        {'$group': {
            '_id': '$instrumento_id',
            'detalhes_instrumento': {'$first': '$instrumento_info'},
            'pendencias': {'$push': {
                '_id': '$_id', 'pendencia': '$pendencia', 'prazo': '$prazo',
                'responsavel': '$responsavel', 'situacao': '$situacao',
                'observacoes': '$observacoes',
                'prioridade': '$prioridade',
                'cor_destaque': '$cor_destaque'
            }}
        }},
        {'$sort': {'detalhes_instrumento.n_instrumento': 1}}
    ]
    grupos_de_pendencias = list(pendencias_collection.aggregate(pipeline))

    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for grupo in grupos_de_pendencias:
        if not grupo.get('detalhes_instrumento'):
            grupo['detalhes_instrumento'] = {'n_instrumento': 'Inválido', 'tipo_documento': 'Instrumento', 'contratada': 'Não encontrado', 'objeto_resumido': 'Link quebrado.'}
        
        pendencias_com_prazo = [p for p in grupo['pendencias'] if p.get('prazo')]
        grupo['pendencias_sem_prazo'] = [p for p in grupo['pendencias'] if not p.get('prazo')]
        grupo['pendencias_vencidas'] = [p for p in pendencias_com_prazo if p['prazo'] < hoje]
        grupo['pendencias_a_vencer'] = [p for p in pendencias_com_prazo if p['prazo'] >= hoje]
    
    # Para cada grupo de instrumento, busca suas notas fiscais pendentes
    for grupo in grupos_de_pendencias:
        grupo['controles_pendentes'] = get_controles_pendentes_por_instrumento(grupo['_id'])

    instrumentos_para_filtro = get_instrumentos_para_dropdown()

    # Busca a preferência do usuário diretamente (poderia vir de current_user se load_user fosse atualizado)
    user_prefs = users_collection.find_one({'_id': ObjectId(current_user.id)}, {'show_nf_pendencias_instrumento': 1})
    show_nf_preference = user_prefs.get('show_nf_pendencias_instrumento', False) # Default False

    return render_template(
        'pendencias_por_instrumento.html', 
        grupos=grupos_de_pendencias, 
        instrumentos_para_filtro=instrumentos_para_filtro,
        instrumento_filtro_id=instrumento_filtro_id,
        show_nf_preference=show_nf_preference
    )

@pendencias_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def nova_pendencia():
    origem_url = request.args.get('origem', url_for('.pendencias_lista', page_mode='geral'))

    if request.method == 'POST':
        instrumento_id = request.form.get('instrumento_id')
        nova = {
            'pendencia': request.form.get('pendencia'),
            'prazo': datetime.strptime(request.form.get('prazo'), '%Y-%m-%d') if request.form.get('prazo') else None,
            'responsavel': request.form.get('responsavel'), 'situacao': request.form.get('situacao'),
            'observacoes': request.form.get('observacoes'), 'status': 'Pendente',
            'user_id': ObjectId(current_user.id), 'data_criacao': datetime.now(),
            'instrumento_id': ObjectId(instrumento_id) if instrumento_id else None,
            'prioridade': False
        }
        pendencias_collection.insert_one(nova)
        flash('Nova pendência criada com sucesso!', 'success')
        # Lê a URL de origem do formulário e redireciona para ela
        origem = request.form.get('origem')
        return redirect(origem or url_for('.pendencias_lista', page_mode='geral'))

    instrumentos = get_instrumentos_para_dropdown()
    instrumentos_json = json.dumps(instrumentos, default=str)
    return render_template('form_pendencia.html', pendencia={}, novo=True, instrumentos=instrumentos, instrumentos_json=instrumentos_json, origem=origem_url)

@pendencias_bp.route('/detalhes/<string:pendencia_id>', methods=['GET', 'POST'])
@login_required
def detalhes_pendencia(pendencia_id):
    pendencia = pendencias_collection.find_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    if not pendencia:
        flash('Pendência não encontrada.', 'error')
        return redirect(url_for('.pendencias_lista', page_mode='geral'))

    origem_url = request.args.get('origem', request.referrer or url_for('.pendencias_lista', page_mode='geral'))

    if request.method == 'POST':
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
        
        origem_post = request.form.get('origem')
        return redirect(url_for('.detalhes_pendencia', pendencia_id=pendencia_id, origem=origem_post))

    instrumentos = get_instrumentos_para_dropdown()
    pendencia_json = json.dumps(pendencia, default=str)
    return render_template('form_pendencia.html', pendencia=pendencia, novo=False, instrumentos=instrumentos, pendencia_json=pendencia_json, origem=origem_url)

@pendencias_bp.route('/excluir/<string:pendencia_id>', methods=['POST'])
@login_required
def excluir_pendencia(pendencia_id):
    pendencias_collection.delete_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    flash('Pendência excluída com sucesso!', 'success')
    # Lê a URL de origem que veio do formulário oculto
    origem = request.form.get('origem')
    return redirect(origem or url_for('.pendencias_lista', page_mode='geral'))

@pendencias_bp.route('/exportar/pendentes')
@login_required
def exportar_pendencias_pendentes_csv():
    query_filter = {'user_id': ObjectId(current_user.id), 'status': 'Pendente'}
    return _gerar_pendencias_csv(query_filter, "export_pendencias_pendentes")

@pendencias_bp.route('/exportar/concluidas')
@login_required
def exportar_pendencias_concluidas_csv():
    query_filter = {'user_id': ObjectId(current_user.id), 'status': 'Concluído'}
    return _gerar_pendencias_csv(query_filter, "export_pendencias_concluidas")

@pendencias_bp.route('/toggle_prioridade/<string:pendencia_id>', methods=['POST'])
@login_required
def toggle_prioridade_pendencia(pendencia_id):
    pendencia = pendencias_collection.find_one({'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)})
    if not pendencia:
        return {'status': 'error', 'message': 'Pendência não encontrada.'}, 404

    nova_prioridade = not pendencia.get('prioridade', False)
    
    pendencias_collection.update_one(
        {'_id': ObjectId(pendencia_id)},
        {'$set': {'prioridade': nova_prioridade}}
    )
    return {'status': 'success', 'nova_prioridade': nova_prioridade}

@pendencias_bp.route('/set_cor_destaque/<string:pendencia_id>', methods=['POST'])
@login_required
def set_cor_destaque(pendencia_id):
    data = request.get_json()
    nova_cor = data.get('cor', None) # Recebe a cor ou None para limpar

    result = pendencias_collection.update_one(
        {'_id': ObjectId(pendencia_id), 'user_id': ObjectId(current_user.id)},
        {'$set': {'cor_destaque': nova_cor}}
    )

    if result.matched_count > 0:
        return {'status': 'success', 'message': 'Cor atualizada.'}
    else:
        return {'status': 'error', 'message': 'Pendência não encontrada.'}, 404

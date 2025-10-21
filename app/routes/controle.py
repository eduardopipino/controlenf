# app/routes/controle.py
# Este arquivo lida com todas as rotas para o gerenciamento de registros de Controle.

# 1. Imports de bibliotecas de terceiros (Flask, etc.)
from flask import (Blueprint, Response, flash, json, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from bson.objectid import ObjectId
import re
import io
import csv
from datetime import datetime

# 2. Imports da nossa própria aplicação (dos modelos que criamos)
from app.models import (controle_collection, get_situacoes_que_arquivam,
                        get_controle_data, get_situacoes_para_dropdown,
                        prepare_chart_data, get_color_map_for_user,
                        get_itens_para_dropdown_js, itens_collection,
                        instrumentos_collection, TODAS_AS_COLUNAS_CONTROLE, TODAS_AS_COLUNAS_CARDS)

EDITABLE_FIELDS = ['referencia', 'nota_fiscal', 'carta_de_correcao', 'observacoes']

# 3. Criação do Blueprint de Controle
# O nome 'controle' será usado nos comandos url_for().
# O prefixo '/controle' será adicionado a todas as URLs deste blueprint
# quando ele for registrado em app/__init__.py.
controle_bp = Blueprint('controle', __name__)

@controle_bp.route('/<string:filter_mode>')
@login_required
def controle_lista(filter_mode):
    
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    
    # O conteúdo desta função permanece idêntico ao original.
    # A única mudança é no decorador acima (@controle_bp.route).

    query_filter = {}
    if filter_mode == 'pendentes':
        query_filter['situacao'] = {'$nin': situacoes_arquivadoras}
    elif filter_mode == 'concluidas':
        query_filter['situacao'] = {'$in': situacoes_arquivadoras}
    else:
        # PONTO DE ATENÇÃO: url_for() agora aponta para '.controle_lista'
        # O '.' no início significa "dentro deste mesmo blueprint".
        return redirect(url_for('.controle_lista', filter_mode='pendentes'))

    filter_values = {}
    filtro_ativo = False
    for key, value in request.args.items():
        if key.startswith('filter_') and value:
            clean_key = key.replace('filter_', '')
            query_filter[clean_key] = {'$regex': value.strip(), '$options': 'i'}
            filter_values[key] = value
            filtro_ativo = True

    if filtro_ativo:
        nomes_amigaveis = {
            'filter_n_instrumento': 'Nº Instrumento',
            'filter_contratada': 'Contratada',
            'filter_objeto': 'Objeto',
            'filter_referencia': 'Referência',
            'filter_situacao': 'Situação'
        }
        filtros_aplicados = [f"{nomes_amigaveis.get(k, k.replace('filter_', ''))}: '{v}'" for k, v in filter_values.items()]
        mensagem = "Filtro ativo! Exibindo registros onde " + ", ".join(filtros_aplicados) + "."
        flash(mensagem, 'info')

    sort_by = request.args.get('sort_by', 'data_criacao')
    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    sort_document = {sort_by: sort_order_mongo}

    controles = get_controle_data(query_filter, sort_document=sort_document)
    
    situacoes_para_filtro = get_situacoes_para_dropdown()
    chart_data_json = prepare_chart_data(controles)
    color_map = get_color_map_for_user()
    
    situacoes_kanban = [s for s in situacoes_para_filtro if s['situacao'] not in situacoes_arquivadoras]
    
    # Converte o ObjectId de cada situação para uma string, tornando-a "JSON serializable"
    for sit in situacoes_para_filtro:
        sit['_id'] = str(sit['_id'])

    view_mode = getattr(current_user, 'view_mode_controle', 'table')
    card_fields_visiveis = getattr(current_user, 'card_fields_controle', [field[0] for field in TODAS_AS_COLUNAS_CARDS[:4]])
    opcoes_campos_cards_controle = [field for field in TODAS_AS_COLUNAS_CARDS if field[0] != 'referencia']

    return render_template(
        'controle_notas_fiscais.html',
        view_mode=view_mode,
        card_fields_visiveis=card_fields_visiveis,
        todas_as_colunas_cards=opcoes_campos_cards_controle,
        controles=list(controles),
        situacoes_para_filtro=situacoes_para_filtro,
        situacoes_kanban=situacoes_kanban,
        filter_mode=filter_mode,
        filter_values=filter_values,
        chart_data=chart_data_json,
        color_map=color_map,
        filtro_ativo=filtro_ativo,
        arquivadores_json=json.dumps(situacoes_arquivadoras),
        sort_by=sort_by,
        order=order,
        todas_as_colunas=TODAS_AS_COLUNAS_CONTROLE,
        colunas_visiveis=current_user.colunas_visiveis,
        color_coding_active=getattr(current_user, 'color_coding_controle', False)
    )

@controle_bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo_controle():
    # Lógica original, sem alterações. Apenas o redirect foi ajustado.
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
            'data_criacao': datetime.now(),
            'user_id': ObjectId(current_user.id)
        }
        controle_collection.insert_one(novo_registro_controle)
        flash('Registro de Controle criado com sucesso!', 'success')
        # PONTO DE ATENÇÃO: Redirecionamento para a rota deste mesmo blueprint
        return redirect(url_for('controle.controle_lista', filter_mode='pendentes'))
        
    return render_template('form_controle.html', controle={}, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True)

@controle_bp.route('/novo_recorrente', methods=['POST'])
@login_required
def novo_controle_recorrente():
    # Lógica 100% idêntica ao original. Apenas o redirect foi ajustado.
    user_id_obj = ObjectId(current_user.id)
    referencia_digitada = request.form.get('referencia_recorrente', '').strip()

    if not referencia_digitada:
        flash('Por favor, digite uma referência.', 'error')
        return redirect(url_for('controle.controle_lista', filter_mode='pendentes'))

    match = re.match(r'^\s*(\d{1,2})\s*(?:[/-]\s*(\d{4}))?\s*$', referencia_digitada)
    if not match:
        flash(f"Formato de referência '{referencia_digitada}' inválido. Use MM/AAAA ou apenas MM.", 'error')
        return redirect(url_for('controle.controle_lista', filter_mode='pendentes'))

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
            'item_id': '$itens._id', 'tipo_frequencia': '$itens.tipo_frequencia',
            'n_instrumento': '$n_instrumento', 'tipo_documento': '$tipo_documento',
            'contratada': '$contratada', 'objeto_resumido': '$objeto_resumido'
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
            'item_id': item['item_id'], 'n_instrumento': item['n_instrumento'],
            'tipo_documento': item['tipo_documento'], 'contratada': item['contratada'],
            'objeto': item['objeto_resumido'], 'referencia': referencia_a_usar,
            'nota_fiscal': '', 'carta_de_correcao': '', 'documentacao': [],
            'observacoes': f'Gerado automaticamente a partir de {referencia_digitada}',
            'situacao': '', 'data_criacao': datetime.now(), 'user_id': user_id_obj
        })
        created_count += 1
    
    if created_count > 0: flash(f'{created_count} novo(s) registro(s) recorrente(s) criado(s) com sucesso!', 'success')
    if skipped_count > 0: flash(f'{skipped_count} registro(s) foram ignorados pois já existiam para essa referência.', 'info')
    if not created_count and not skipped_count: flash("Nenhum item recorrente (mensal/bimestral) encontrado nos seus instrumentos vigentes.", 'warning')

    return redirect(url_for('controle.controle_lista', filter_mode='pendentes'))

@controle_bp.route('/detalhes/<string:controle_id>', methods=['GET', 'POST'])
@login_required
def detalhes_controle(controle_id):
    controle = controle_collection.find_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if not controle:
        flash('Registro de Controle não encontrado ou não pertence a você.', 'error')
        return redirect(url_for('controle.controle_lista', filter_mode='pendentes'))

    if request.method == 'POST':
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()

        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento" e "Referência" são obrigatórios.', 'error')
            itens_for_js = get_itens_para_dropdown_js()
            situacoes = get_situacoes_para_dropdown()
            return render_template(
                'form_controle.html', controle=request.form,
                itens_for_js=json.dumps(itens_for_js), situacoes=situacoes,
                current_item_id=item_id_str, novo=False
            )
        
        item_selecionado = itens_collection.find_one({'_id': ObjectId(item_id_str), 'user_id': ObjectId(current_user.id)})
        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        update_data = {
            'item_id': item_selecionado['_id'], 'n_instrumento': instrumento_pai['n_instrumento'],
            'tipo_documento': instrumento_pai['tipo_documento'], 'contratada': instrumento_pai['contratada'],
            'objeto': instrumento_pai['objeto_resumido'], 'referencia': referencia,
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
        return redirect(url_for('controle.detalhes_controle', controle_id=controle_id))

    itens_for_js = get_itens_para_dropdown_js()
    situacoes = get_situacoes_para_dropdown()
    current_item_id_str = str(controle.get('item_id', ''))

    return render_template('form_controle.html', controle=controle, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, current_item_id=current_item_id_str, novo=False)

@controle_bp.route('/excluir/<string:controle_id>', methods=['POST'])
@login_required
def excluir_controle(controle_id):
    result = controle_collection.delete_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if result.deleted_count > 0:
        flash('Registro de Controle excluído com sucesso!', 'success')
    else:
        flash('Erro ao excluir ou registro não encontrado.', 'error')
    # Linha corrigida: lê a origem diretamente do formulário
    origem = request.form.get('origem')
    return redirect(origem or url_for('.controle_lista', filter_mode='pendentes'))

# A rota /exportar/... fica logicamente agrupada aqui, resultando na URL /controle/exportar/...
@controle_bp.route('/exportar/<string:filter_mode>')
@login_required
def exportar_csv(filter_mode):
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    if filter_mode == 'pendentes':
        query_filter = {'situacao': {'$nin': situacoes_arquivadoras}}
    elif filter_mode == 'concluidas':
        query_filter = {'situacao': {'$in': situacoes_arquivadoras}}
    else:
        flash("Modo de filtro inválido para exportação.", "error")
        # PONTO DE ATENÇÃO: Redireciona para a rota 'index' no blueprint 'core'
        return redirect(url_for('core.index'))

    registros = get_controle_data(query_filter)

    colunas = {
        'TIPO DOCUMENTO': 'tipo_documento', 'Nº INSTRUMENTO': 'n_instrumento',
        'CONTRATADA': 'contratada', 'OBJETO': 'objeto', 'ITEM': 'item_descricao',
        'REFERÊNCIA': 'referencia', 'DOCUMENTO FISCAL': 'nota_fiscal',
        'CARTA DE CORREÇÃO': 'carta_de_correcao', 'DOCUMENTAÇÃO': 'documentacao',
        'OBSERVAÇÕES': 'observacoes', 'SITUAÇÃO': 'situacao'
    }

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)
    writer.writerow(colunas.keys())

    for registro in registros:
        linha = [registro.get(campo_db, '') for campo_db in colunas.values()]
        writer.writerow(linha)

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"export_controle_{filter_mode}_{timestamp}.csv"

    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@controle_bp.route('/update_situacao_inline', methods=['POST'])
@login_required
def update_situacao_inline():
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

# Mesmo que a URL original fosse /item/..., a função CRIA um registro de CONTROLE.
# Portanto, faz mais sentido ela pertencer a este controlador.
# A URL final será /controle/item/criar_controle_rapido.
@controle_bp.route('/item/criar_controle_rapido', methods=['POST'])
@login_required
def criar_controle_rapido():
    data = request.get_json()
    item_id_str = data.get('item_id')
    referencia = data.get('referencia', '').strip()

    if not all([item_id_str, referencia]):
        return {'status': 'error', 'message': 'Item ID e Referência são obrigatórios.'}, 400

    try:
        user_id_obj = ObjectId(current_user.id)
        item_id_obj = ObjectId(item_id_str)

        item_selecionado = itens_collection.find_one({'_id': item_id_obj, 'user_id': user_id_obj})
        if not item_selecionado:
            return {'status': 'error', 'message': 'Item não encontrado.'}, 404
        
        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})
        if not instrumento_pai:
            return {'status': 'error', 'message': 'Instrumento pai não encontrado.'}, 404

        if controle_collection.find_one({'item_id': item_id_obj, 'referencia': referencia, 'user_id': user_id_obj}):
             return {'status': 'error', 'message': f'Já existe um controle para a referência "{referencia}" deste item.'}, 409

        novo_registro_controle = {
            'item_id': item_id_obj, 'n_instrumento': instrumento_pai['n_instrumento'],
            'tipo_documento': instrumento_pai['tipo_documento'], 'contratada': instrumento_pai['contratada'],
            'objeto': instrumento_pai['objeto_resumido'], 'referencia': referencia, 'nota_fiscal': '',
            'carta_de_correcao': '', 'documentacao': [], 'observacoes': 'Gerado via criação rápida.',
            'situacao': '', 'data_criacao': datetime.now(), 'user_id': user_id_obj
        }
        
        controle_collection.insert_one(novo_registro_controle)
        
        flash('Novo registro de controle criado com sucesso!', 'success')
        return {
            'status': 'success', 'message': 'Registro criado!',
            'redirect_url': url_for('controle.controle_lista', filter_mode='pendentes')
        }

    except Exception as e:
        print(f"Erro na criação rápida de controle: {e}")
        return {'status': 'error', 'message': 'Ocorreu um erro interno no servidor.'}, 500

# Adicione este novo bloco de código no final de app/routes/controle.py

@controle_bp.route('/set_situacao/<string:controle_id>', methods=['POST'])
@login_required
def set_situacao_card(controle_id):
    data = request.get_json()
    nova_situacao = data.get('situacao')

    if nova_situacao is None:
        return {'status': 'error', 'message': 'Nenhuma situação fornecida'}, 400

    result = controle_collection.update_one(
        {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
        {'$set': {'situacao': nova_situacao, 'data_ultima_atualizacao': datetime.now()}}
    )

    if result.matched_count > 0:
        return {'status': 'success', 'message': 'Situação atualizada.'}
    else:
        return {'status': 'error', 'message': 'Registro não encontrado.'}, 404

@controle_bp.route('/update_field_inline/<string:controle_id>', methods=['POST'])
@login_required
def update_field_inline(controle_id):
    """ Atualiza um campo específico de um registro de controle via edição inline. """
    data = request.get_json()
    field_name = data.get('field')
    new_value = data.get('value', '').strip() # Pega valor, default '', remove espaços extras

    if not controle_id or not field_name:
        return {'status': 'error', 'message': 'Dados incompletos (ID ou campo faltando).'}, 400

    # Validação: Verifica se o campo está na lista de editáveis
    if field_name not in EDITABLE_FIELDS:
        return {'status': 'error', 'message': f'Campo "{field_name}" não é editável inline.'}, 403 # Forbidden

    try:
        # Prepara o update (apenas o campo recebido)
        update_data = {
            field_name: new_value,
            'data_ultima_atualizacao': datetime.now()
        }

        result = controle_collection.update_one(
            {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )

        if result.matched_count > 0:
            if result.modified_count > 0:
                return {'status': 'success', 'message': 'Campo atualizado.', 'newValue': new_value}
            else:
                # Encontrou mas não modificou (valor era o mesmo)
                return {'status': 'success', 'message': 'Nenhuma alteração detectada.', 'newValue': new_value}
        else:
            return {'status': 'error', 'message': 'Registro não encontrado ou não pertence ao usuário.'}, 404

    except Exception as e:
        print(f"Erro ao atualizar campo inline: {e}") # Log do erro no servidor
        return {'status': 'error', 'message': 'Erro interno ao salvar.'}, 500

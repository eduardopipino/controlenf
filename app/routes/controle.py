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
import time

# 2. Imports da nossa própria aplicação (dos modelos que criamos)
from app.models import (controle_collection, get_situacoes_que_arquivam,
                        get_controle_data, get_situacoes_para_dropdown,
                        prepare_chart_data, get_color_map_for_user,
                        get_itens_para_dropdown_js, itens_collection,
                        instrumentos_collection, TODAS_AS_COLUNAS_CONTROLE, TODAS_AS_COLUNAS_CARDS)

EDITABLE_FIELDS = ['referencia', 'nota_fiscal', 'carta_de_correcao', 'observacoes', 'prazo']

# 3. Criação do Blueprint de Controle
# O nome 'controle' será usado nos comandos url_for().
# O prefixo '/controle' será adicionado a todas as URLs deste blueprint
# quando ele for registrado em app/__init__.py.
controle_bp = Blueprint('controle', __name__)

@controle_bp.route('/<string:filter_mode>')
@login_required
def controle_lista(filter_mode):
    
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    query_filter = {}
    page_mode = 'geral'

    # Mapeamento dos novos filtros de rota
    if filter_mode == 'todas':
        query_filter['situacao'] = {'$nin': situacoes_arquivadoras}
    elif filter_mode == 'por_instrumento':
        query_filter['situacao'] = {'$nin': situacoes_arquivadoras}
        page_mode = 'por_instrumento'
    elif filter_mode == 'concluidas':
        query_filter['situacao'] = {'$in': situacoes_arquivadoras}
        page_mode = 'concluidas'
    else:
        # Fallback caso o usuário acesse um link antigo com 'pendentes'
        return redirect(url_for('.controle_lista', filter_mode='todas'))

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

    # Se estiver agrupando por instrumento, força a ordenação inicial por instrumento
    sort_by = request.args.get('sort_by')
    if not sort_by:
        sort_by = 'n_instrumento' if page_mode == 'por_instrumento' else 'data_criacao'

    order = request.args.get('order', 'asc')
    sort_order_mongo = -1 if order == 'desc' else 1
    
    if sort_by == 'n_instrumento':
        sort_document = {'n_instrumento': sort_order_mongo, 'data_criacao': -1}
    else:
        sort_document = {sort_by: sort_order_mongo}

    controles_raw = get_controle_data(query_filter, sort_document=sort_document)
    controles = list(controles_raw)
    
    # --- CORREÇÃO PENDENTES REAIS E LÓGICA DE VENCIMENTO ---
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for c in controles:
        c['vencido'] = False
        if c.get('prazo') and isinstance(c['prazo'], datetime):
            # Só marca como vencido se não estiver arquivado/concluído
            if c['prazo'] < hoje and c.get('situacao') not in situacoes_arquivadoras:
                c['vencido'] = True

    # Força os registros vencidos para o topo da tabela
    controles.sort(key=lambda x: 0 if x.get('vencido') else 1)

    # --- NOVO BLOCO: Agrupamento para Modo 'por_instrumento' nos Cards ---
    grupos_de_controles = []
    if page_mode == 'por_instrumento':
        from collections import OrderedDict
        grupos_dict = OrderedDict()
        for c in controles:
            if c.get('n_instrumento'):
                grupo_key = f"{c.get('tipo_documento', 'Instrumento')} Nº {c.get('n_instrumento', '')} - {c.get('contratada', '')}"
            else:
                grupo_key = "Sem Instrumento Vinculado"
            
            if grupo_key not in grupos_dict:
                grupos_dict[grupo_key] = {
                    'detalhes': {'instrumento_display': grupo_key},
                    'controles': []
                }
            grupos_dict[grupo_key]['controles'].append(c)
        grupos_de_controles = list(grupos_dict.values())

    # Ordena as situações em ordem alfabética para a interface
    situacoes_para_filtro = sorted(get_situacoes_para_dropdown(), key=lambda x: x.get('situacao', '').lower())
    chart_data_json = prepare_chart_data(controles)
    color_map = get_color_map_for_user()
    
    situacoes_kanban = [s for s in situacoes_para_filtro if s['situacao'] not in situacoes_arquivadoras]
    
    for sit in situacoes_para_filtro:
        sit['_id'] = str(sit['_id'])

    # Prioriza a leitura rápida da URL para UX instantânea; faz fallback para o BD
    view_mode = request.args.get('view', getattr(current_user, 'view_mode_controle', 'table'))
    card_fields_visiveis = getattr(current_user, 'card_fields_controle', [field[0] for field in TODAS_AS_COLUNAS_CARDS[:4]])
    opcoes_campos_cards_controle = [field for field in TODAS_AS_COLUNAS_CARDS if field[0] != 'referencia']

    return render_template(
        'controle_notas_fiscais.html',
        view_mode=view_mode,
        card_fields_visiveis=card_fields_visiveis,
        todas_as_colunas_cards=opcoes_campos_cards_controle,
        controles=list(controles),
        grupos_de_controles=grupos_de_controles, # <<< Passa a variável
        situacoes_para_filtro=situacoes_para_filtro,
        situacoes_kanban=situacoes_kanban,
        filter_mode=filter_mode,
        page_mode=page_mode,                     # <<< Passa a variável
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
    # 1. Tenta pegar a origem (de onde o usuário clicou em 'Novo')
    origem = request.args.get('origem') or request.form.get('origem')

    itens_for_js = get_itens_para_dropdown_js(somente_vigentes=True)
    situacoes = sorted(get_situacoes_para_dropdown(), key=lambda x: x.get('situacao', '').lower())

    if request.method == 'POST':
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()
        
        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento" e "Referência" são obrigatórios.', 'error')
            # Passa a origem de volta para o formulário em caso de erro
            return render_template('form_controle.html', controle=request.form, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True, origem=origem)

        item_selecionado = itens_collection.find_one({'_id': ObjectId(item_id_str), 'user_id': ObjectId(current_user.id)})
        if not item_selecionado:
            flash("Item selecionado inválido.", "error")
            return render_template('form_controle.html', controle=request.form, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True, origem=origem)

        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        # --- Tratamento do campo Prazo ---
        prazo_str = request.form.get('prazo', '').strip()
        prazo_dt = None
        if prazo_str:
            try:
                prazo_dt = datetime.strptime(prazo_str, '%Y-%m-%d')
            except ValueError:
                flash('Data de prazo inválida.', 'error')

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
            'prazo': prazo_dt, # <<< ADICIONADO AQUI
            'situacao': request.form.get('situacao', '').strip(),
            'data_criacao': datetime.now(),
            'user_id': ObjectId(current_user.id)
        }

        controle_collection.insert_one(novo_registro_controle)
        flash('Registro de Controle criado com sucesso!', 'success')
        
        # 2. Se houver uma origem guardada, redireciona de volta para ela!
        if origem:
            return redirect(origem)
        return redirect(url_for('controle.controle_lista', filter_mode='todas'))
        
    # Envia a origem para o HTML ao carregar a página pela primeira vez
    return render_template('form_controle.html', controle={}, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, novo=True, origem=origem)


@controle_bp.route('/novo_recorrente', methods=['POST'])
@login_required
def novo_controle_recorrente():
    # Como os recorrentes são criados num modal, a forma mais fácil de 
    # lembrar de onde o usuário veio é capturando o "referrer" da requisição.
    origem = request.referrer or url_for('controle.controle_lista', filter_mode='todas')

    user_id_obj = ObjectId(current_user.id)
    referencia_digitada = request.form.get('referencia_recorrente', '').strip()

    if not referencia_digitada:
        flash('Por favor, digite uma referência.', 'error')
        return redirect(origem) # Volta para a origem

    match = re.match(r'^\s*(\d{1,2})\s*(?:[/-]\s*(\d{4}))?\s*$', referencia_digitada)
    if not match:
        flash(f"Formato de referência '{referencia_digitada}' inválido. Use MM/AAAA ou apenas MM.", 'error')
        return redirect(origem) # Volta para a origem

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

    return redirect(origem) # Volta para a origem

@controle_bp.route('/detalhes/<string:controle_id>', methods=['GET', 'POST'])
@login_required
def detalhes_controle(controle_id):
    # 1. Captura a origem da URL ou do formulário POST
    origem = request.args.get('origem') or request.form.get('origem')

    controle = controle_collection.find_one({'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)})
    if not controle:
        flash('Registro de Controle não encontrado ou não pertence a você.', 'error')
        return redirect(origem or url_for('controle.controle_lista', filter_mode='todas'))

    if request.method == 'POST':
        item_id_str = request.form.get('item_id')
        referencia = request.form.get('referencia', '').strip()

        if not all([item_id_str, referencia]):
            flash('Os campos "Item do Instrumento" e "Referência" são obrigatórios.', 'error')
            itens_for_js = get_itens_para_dropdown_js()
            situacoes = sorted(get_situacoes_para_dropdown(), key=lambda x: x.get('situacao', '').lower())
            return render_template(
                'form_controle.html', controle=request.form,
                itens_for_js=json.dumps(itens_for_js), situacoes=situacoes,
                current_item_id=item_id_str, novo=False, origem=origem # <<< Envia a origem em caso de erro
            )
        
        item_selecionado = itens_collection.find_one({'_id': ObjectId(item_id_str), 'user_id': ObjectId(current_user.id)})
        instrumento_pai = instrumentos_collection.find_one({'_id': item_selecionado['instrumento_id']})

        # --- Tratamento do campo Prazo ---
        prazo_str = request.form.get('prazo', '').strip()
        prazo_dt = None
        if prazo_str:
            try:
                prazo_dt = datetime.strptime(prazo_str, '%Y-%m-%d')
            except ValueError:
                flash('Data de prazo inválida.', 'error')

        update_data = {
            'item_id': item_selecionado['_id'], 'n_instrumento': instrumento_pai['n_instrumento'],
            'tipo_documento': instrumento_pai['tipo_documento'], 'contratada': instrumento_pai['contratada'],
            'objeto': instrumento_pai['objeto_resumido'], 'referencia': referencia,
            'nota_fiscal': request.form.get('nota_fiscal', '').strip(),
            'carta_de_correcao': request.form.get('carta_de_correcao', '').strip(),
            'documentacao': request.form.getlist('documentacao'),
            'observacoes': request.form.get('observacoes', '').strip(),
            'prazo': prazo_dt, # <<< ADICIONADO AQUI
            'situacao': request.form.get('situacao', '').strip(),
            'data_ultima_atualizacao': datetime.now()
        }

        controle_collection.update_one(
            {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )
        flash('Registro de Controle atualizado com sucesso!', 'success')
        
        # 2. Mantém a origem na URL ao recarregar a página após salvar!
        return redirect(url_for('controle.detalhes_controle', controle_id=controle_id, origem=origem))

    itens_for_js = get_itens_para_dropdown_js()
    situacoes = sorted(get_situacoes_para_dropdown(), key=lambda x: x.get('situacao', '').lower())
    current_item_id_str = str(controle.get('item_id', ''))

    # 3. Envia a variável origem para o HTML
    return render_template('form_controle.html', controle=controle, itens_for_js=json.dumps(itens_for_js), situacoes=situacoes, current_item_id=current_item_id_str, novo=False, origem=origem)

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
    return redirect(origem or url_for('.controle_lista', filter_mode='todas'))

# A rota /exportar/... fica logicamente agrupada aqui, resultando na URL /controle/exportar/...
@controle_bp.route('/exportar/<string:filter_mode>')
@login_required
def exportar_csv(filter_mode):
    situacoes_arquivadoras = get_situacoes_que_arquivam()
    if filter_mode in ['todas', 'por_instrumento']: # <<< MODIFICADO AQUI
        query_filter = {'situacao': {'$nin': situacoes_arquivadoras}}
    elif filter_mode == 'concluidas':
        query_filter = {'situacao': {'$in': situacoes_arquivadoras}}
    else:
        flash("Modo de filtro inválido para exportação.", "error")
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
    cor_temporaria = data.get('cor_temporaria')

    if not controle_id or nova_situacao is None:
        return {'status': 'error', 'message': 'Dados incompletos.'}, 400

    # 1. Prepara o que vai ser atualizado ($set)
    update_dict = {'situacao': nova_situacao, 'data_ultima_atualizacao': datetime.now()}
    
    # 2. Prepara o que vai ser apagado ($unset)
    unset_dict = {}

    if cor_temporaria:
        update_dict['cor_temporaria'] = cor_temporaria
    else:
        # Se não enviou cor, significa que escolheu uma situação padrão. 
        # Então mandamos apagar qualquer cor temporária antiga do banco.
        unset_dict['cor_temporaria'] = ""

    # 3. Monta a instrução final para o banco
    update_query = {'$set': update_dict}
    if unset_dict:
        update_query['$unset'] = unset_dict

    result = controle_collection.update_one(
        {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
        update_query
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
            'redirect_url': url_for('controle.controle_lista', filter_mode='todas')
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
    cor_temporaria = data.get('cor_temporaria') # <<< Pega a nova cor

    if nova_situacao is None: # (ou not controle_id)
        return {'status': 'error', 'message': '...'}, 400

    # Monta o dicionário dinamicamente
    update_dict = {'situacao': nova_situacao, 'data_ultima_atualizacao': datetime.now()}
    unset_dict = {}

    if cor_temporaria:
        update_dict['cor_temporaria'] = cor_temporaria
    else:
        # Se não enviou cor temporária, ele escolheu algo da lista padrão.
        # Precisamos apagar qualquer cor temporária antiga deste registro.
        unset_dict['cor_temporaria'] = ""

    update_query = {'$set': update_dict}
    if unset_dict:
        update_query['$unset'] = unset_dict

    result = controle_collection.update_one(
        {'_id': ObjectId(controle_id), 'user_id': ObjectId(current_user.id)},
        update_query
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
    new_value = data.get('value', '').strip() 
    return_value = new_value # <<< NOVO: Variável separada para devolver à tela

    if not controle_id or not field_name:
        return {'status': 'error', 'message': 'Dados incompletos.'}, 400

    if field_name not in EDITABLE_FIELDS:
        return {'status': 'error', 'message': f'Campo "{field_name}" não é editável inline.'}, 403

    try:
        # --- NOVA LÓGICA: Tratamento do Prazo ---
        if field_name == 'prazo':
            if new_value:
                try:
                    new_value = datetime.strptime(new_value, '%Y-%m-%d')
                    return_value = new_value.strftime('%d/%m/%Y') # Formata para a tela
                except ValueError:
                    return {'status': 'error', 'message': 'Data inválida.'}, 400
            else:
                new_value = None
                return_value = ""

        # Prepara o update 
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
                return {'status': 'success', 'message': 'Campo atualizado.', 'newValue': return_value} # <<< ALTERADO
            else:
                return {'status': 'success', 'message': 'Nenhuma alteração.', 'newValue': return_value} # <<< ALTERADO
        else:
            return {'status': 'error', 'message': 'Registro não encontrado.'}, 404

    except Exception as e:
        print(f"Erro ao atualizar campo inline: {e}") # Log do erro no servidor
        return {'status': 'error', 'message': 'Erro interno ao salvar.'}, 500

@controle_bp.route('/get_documentacao/<string:controle_id>', methods=['GET'])
@login_required
def get_documentacao_inline(controle_id):
    """
    Busca as opções de documentação de um item e os documentos já salvos
    para um registro de controle específico.
    """
    try:
        user_id_obj = ObjectId(current_user.id)
        controle = controle_collection.find_one(
            {'_id': ObjectId(controle_id), 'user_id': user_id_obj},
            {'item_id': 1, 'documentacao': 1, 'documentacao_pendente': 1, 'documentos_excluidos': 1} # <-- Adicionado aqui
        )
        if not controle:
            return {'status': 'error', 'message': 'Registro de controle não encontrado.'}, 404

        item = itens_collection.find_one(
            {'_id': controle['item_id'], 'user_id': user_id_obj},
            {'documentos_exigidos': 1} 
        )
        if not item:
            return {'status': 'error', 'message': 'Item de instrumento não encontrado.'}, 404

        opcoes_originais = item.get('documentos_exigidos', [])
        salvos = controle.get('documentacao', [])
        pendentes = controle.get('documentacao_pendente', [])
        
        # --- A MÁGICA ACONTECE AQUI ---
        # Busca os excluídos no banco e os remove das opções do modal
        excluidos = controle.get('documentos_excluidos', [])
        opcoes = [opt for opt in opcoes_originais if opt not in excluidos]
        # ------------------------------

        return {'status': 'success', 'opcoes': opcoes, 'salvos': salvos, 'pendentes': pendentes}

    except Exception as e:
        print(f"Erro ao buscar documentação inline: {e}")
        return {'status': 'error', 'message': 'Erro interno no servidor.'}, 500

@controle_bp.route('/update_documentacao_inline/<string:controle_id>', methods=['POST'])
@login_required
def update_documentacao_inline(controle_id):
    """
    Atualiza a lista de 'documentacao' e recalcula 'documentacao_pendente' e 'documentos_excluidos'
    para um registro de controle específico.
    """
    data = request.get_json()
    novos_documentos = data.get('documentacao', [])
    novos_pendentes = data.get('documentacao_pendente')

    if not isinstance(novos_documentos, list):
        return {'status': 'error', 'message': 'Formato de dados inválido.'}, 400

    try:
        user_id_obj = ObjectId(current_user.id)
        controle = controle_collection.find_one(
            {'_id': ObjectId(controle_id), 'user_id': user_id_obj},
            {'item_id': 1} 
        )
        if not controle:
            return {'status': 'error', 'message': 'Registro de controle não encontrado.'}, 404

        item = itens_collection.find_one(
            {'_id': controle['item_id'], 'user_id': user_id_obj},
            {'documentos_exigidos': 1} 
        )
        if not item:
            return {'status': 'error', 'message': 'Item de instrumento não encontrado.'}, 404

        opcoes_originais = item.get('documentos_exigidos', [])
        
        if novos_pendentes is None:
            novos_pendentes = [opt for opt in opcoes_originais if opt not in novos_documentos]

        # --- A MÁGICA ACONTECE AQUI ---
        # Deduz os excluídos: eram exigidos no contrato original, mas não vieram nem como salvos nem como pendentes da tela!
        excluidos = [opt for opt in opcoes_originais if opt not in novos_documentos and opt not in novos_pendentes]
        # ------------------------------

        # Atualiza o registro no banco
        update_data = {
            'documentacao': novos_documentos,
            'documentacao_pendente': novos_pendentes,
            'documentos_excluidos': excluidos, # <<< Grava a lista de apagados no banco
            'data_ultima_atualizacao': datetime.now()
        }
        
        controle_collection.update_one(
            {'_id': ObjectId(controle_id), 'user_id': user_id_obj},
            {'$set': update_data}
        )

        return {
            'status': 'success',
            'message': 'Documentação atualizada.',
            'novos_documentos': novos_documentos,
            'novos_pendentes': novos_pendentes
        }

    except Exception as e:
        print(f"Erro ao salvar documentação inline: {e}")
        return {'status': 'error', 'message': 'Erro interno ao salvar.'}, 500
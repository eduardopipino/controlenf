# app/routes/instrumentos.py
# Este arquivo contém todas as rotas para o CRUD (Create, Read, Update, Delete)
# de Instrumentos Contratuais e seus Itens de faturamento.

# 1. Imports de bibliotecas de terceiros
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from bson.objectid import ObjectId

# 2. Imports da nossa própria aplicação (modelos e coleções)
from app.models import (instrumentos_collection, itens_collection,
                        controle_collection, documentacao_tipos_collection)

# 3. Criação do Blueprint de Instrumentos
# O nome 'instrumentos' será usado nos comandos url_for().
# O prefixo '/cadastros' será adicionado às URLs deste blueprint
# ao ser registrado em app/__init__.py.
instrumentos_bp = Blueprint('instrumentos', __name__)


@instrumentos_bp.route('/instrumentos_contratuais', defaults={'filtro': 'vigentes'})
@instrumentos_bp.route('/instrumentos_contratuais/<string:filtro>')
@login_required
def instrumentos_contratuais(filtro):
    query = {'user_id': ObjectId(current_user.id)}
    if filtro == 'vigentes':
        query['vigente'] = True
    elif filtro == 'extintos':
        query['vigente'] = False
    
    pipeline = [
        {'$match': query},
        {'$lookup': {
            'from': 'ITENS_INSTRUMENTO',
            'localField': '_id',
            'foreignField': 'instrumento_id',
            'as': 'itens_associados'
        }},
        {'$addFields': {
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
        }},
        {'$project': {
            'itens_associados': 0
        }}
    ]
    instrumentos = instrumentos_collection.aggregate(pipeline)
    return render_template('instrumentos_contratuais.html', instrumentos=list(instrumentos), filtro_ativo=filtro)


@instrumentos_bp.route('/instrumentos_contratuais/novo', methods=['GET', 'POST'])
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
            'vigente': 'vigente' in request.form,
            'user_id': ObjectId(current_user.id)
        }
        result = instrumentos_collection.insert_one(novo_instrumento)
        
        flash('Instrumento Contratual criado! Agora, adicione os itens de faturamento.', 'success')
        # PONTO DE ATENÇÃO: Redireciona para a rota 'gerenciar_instrumento' deste mesmo blueprint
        return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=str(result.inserted_id)))

    return render_template('form_instrumento.html', instrumento={}, novo=True)


@instrumentos_bp.route('/instrumentos_contratuais/gerenciar/<string:instrumento_id>', methods=['GET', 'POST'])
@login_required
def gerenciar_instrumento(instrumento_id):
    instrumento = instrumentos_collection.find_one({'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)})
    if not instrumento:
        flash('Instrumento Contratual não encontrado.', 'error')
        return redirect(url_for('instrumentos.instrumentos_contratuais'))

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
        return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=instrumento_id))

    itens = list(itens_collection.find({'instrumento_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)}))
    
    return render_template('gerenciar_instrumento.html', instrumento=instrumento, itens=itens)


@instrumentos_bp.route('/instrumentos_contratuais/excluir/<string:instrumento_id>', methods=['POST'])
@login_required
def excluir_instrumento_contratual(instrumento_id):
    user_id_obj = ObjectId(current_user.id)
    instrumento_id_obj = ObjectId(instrumento_id)

    itens_do_instrumento = list(itens_collection.find(
        {'instrumento_id': instrumento_id_obj, 'user_id': user_id_obj},
        {'_id': 1}
    ))
    
    if itens_do_instrumento:
        item_ids = [item['_id'] for item in itens_do_instrumento]
        controle_em_uso = controle_collection.find_one({
            'item_id': {'$in': item_ids},
            'user_id': user_id_obj
        })

        if controle_em_uso:
            flash('Não é possível excluir. Existem registros de controle vinculados a itens deste instrumento.', 'error')
            return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=instrumento_id))

    instrumentos_collection.delete_one({'_id': instrumento_id_obj, 'user_id': user_id_obj})
    itens_collection.delete_many({'instrumento_id': instrumento_id_obj, 'user_id': user_id_obj})
    
    flash('Instrumento Contratual e todos os seus itens foram excluídos com sucesso!', 'success')
    return redirect(url_for('instrumentos.instrumentos_contratuais'))


# --- ROTAS PARA OS ITENS DE UM INSTRUMENTO ---

@instrumentos_bp.route('/instrumento/<string:instrumento_id>/item/novo', methods=['GET', 'POST'])
@login_required
def adicionar_item_instrumento(instrumento_id):
    instrumento = instrumentos_collection.find_one({'_id': ObjectId(instrumento_id), 'user_id': ObjectId(current_user.id)})
    todos_os_docs = list(documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)}))
    
    if not instrumento:
        flash('Instrumento Contratual não encontrado.', 'error')
        return redirect(url_for('instrumentos.instrumentos_contratuais'))

    if request.method == 'POST':
        descricao = request.form.get('descricao_item', '').strip()
        frequencia = request.form.get('tipo_frequencia', '').strip()
        documentos_exigidos = request.form.getlist('documentos_exigidos')

        if not descricao or not frequencia:
            flash('Descrição e Frequência do item são obrigatórios.', 'error')
            return render_template('form_item.html', instrumento=instrumento, item={}, novo=True, todos_os_docs=todos_os_docs)
        
        itens_collection.insert_one({
            'instrumento_id': ObjectId(instrumento_id),
            'descricao_item': descricao,
            'tipo_frequencia': frequencia,
            'user_id': ObjectId(current_user.id),
            'documentos_exigidos': documentos_exigidos
        })
        flash('Novo item adicionado com sucesso!', 'success')
        return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=instrumento_id))

    return render_template('form_item.html', instrumento=instrumento, item={}, novo=True, todos_os_docs=todos_os_docs)


@instrumentos_bp.route('/item/<string:item_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_item_instrumento(item_id):
    item = itens_collection.find_one({'_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)})
    if not item:
        flash('Item não encontrado.', 'error')
        return redirect(url_for('instrumentos.instrumentos_contratuais'))
    
    instrumento = instrumentos_collection.find_one({'_id': item['instrumento_id']})
    todos_os_docs = list(documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)}))

    if request.method == 'POST':
        descricao = request.form.get('descricao_item', '').strip()
        frequencia = request.form.get('tipo_frequencia', '').strip()
        documentos_exigidos = request.form.getlist('documentos_exigidos')

        if not descricao or not frequencia:
            flash('Descrição e Frequência do item são obrigatórios.', 'error')
            return render_template('form_item.html', instrumento=instrumento, item=request.form, novo=False, todos_os_docs=todos_os_docs)

        itens_collection.update_one(
            {'_id': ObjectId(item_id)},
            {'$set': {
                'descricao_item': descricao,
                'tipo_frequencia': frequencia,
                'documentos_exigidos': documentos_exigidos
            }}
        )
        flash('Item atualizado com sucesso!', 'success')
        return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))

    return render_template('form_item.html', instrumento=instrumento, item=item, novo=False, todos_os_docs=todos_os_docs)


@instrumentos_bp.route('/itens/<string:item_id>/excluir', methods=['POST'])
@login_required
def excluir_item_instrumento(item_id):
    item = itens_collection.find_one({'_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)})
    if not item:
        flash('Item não encontrado.', 'error')
        return redirect(url_for('instrumentos.instrumentos_contratuais'))

    if controle_collection.find_one({'item_id': ObjectId(item_id), 'user_id': ObjectId(current_user.id)}):
        flash('Não é possível excluir este item, pois ele está sendo usado em registros de controle.', 'error')
        return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))

    itens_collection.delete_one({'_id': ObjectId(item_id)})
    flash('Item excluído com sucesso.', 'success')
    return redirect(url_for('instrumentos.gerenciar_instrumento', instrumento_id=str(item['instrumento_id'])))
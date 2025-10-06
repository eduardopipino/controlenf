# app/routes/cadastros_gerais.py
# Este arquivo agrupa as rotas para cadastros auxiliares,
# como Situações e Tipos de Documento.

# 1. Imports de bibliotecas e de nossa aplicação
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from bson.objectid import ObjectId

from app.models import (situacao_collection, controle_collection,
                        documentacao_tipos_collection)


# 2. Criação do Blueprint
# Note que o nome do blueprint é 'cadastros'.
cadastros_bp = Blueprint('cadastros', __name__)


# --- ROTAS DE CADASTRO DE SITUAÇÃO ---

@cadastros_bp.route('/situacao')
@login_required
def cadastros_situacao():
    situacoes = situacao_collection.find({'user_id': ObjectId(current_user.id)})
    return render_template('situacao.html', situacoes=list(situacoes))

@cadastros_bp.route('/situacao/novo', methods=['GET', 'POST'])
@login_required
def nova_situacao():
    if request.method == 'POST':
        situacao_nome = request.form['situacao'].strip()
        cor_situacao = request.form.get('cor_situacao', '#ffffff').strip()
        arquiva = 'arquiva_registro' in request.form
        cor_tema_escuro = request.form.get('cor_tema_escuro', '#3a3a3a').strip()

        if not situacao_nome:
            flash('O nome da situação não pode ser vazio.', 'error')
            return render_template('form_situacao.html', situacao=request.form, novo=True)
        if situacao_collection.find_one({'situacao': situacao_nome, 'user_id': ObjectId(current_user.id)}):
            flash('Você já possui uma situação com este nome.', 'error')
            return render_template('form_situacao.html', situacao=request.form, novo=True)

        situacao_collection.insert_one({
            'situacao': situacao_nome, 'cor': cor_situacao,
            'cor_tema_escuro': cor_tema_escuro,
            'user_id': ObjectId(current_user.id),
            'arquiva_registro': arquiva
        })
        flash('Situação criada com sucesso!', 'success')
        # PONTO DE ATENÇÃO: Redireciona para a rota '.cadastros_situacao' deste blueprint
        return redirect(url_for('.cadastros_situacao'))
        
    return render_template('form_situacao.html', situacao={}, novo=True)

@cadastros_bp.route('/situacao/editar/<string:situacao_id>', methods=['GET', 'POST'])
@login_required
def editar_situacao(situacao_id):
    situacao = situacao_collection.find_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    if not situacao:
        flash('Situação não encontrada ou não pertence a você.', 'error')
        return redirect(url_for('.cadastros_situacao'))
    
    if request.method == 'POST':
        nova_situacao_nome = request.form['situacao'].strip()
        nova_cor_situacao = request.form.get('cor_situacao', '#ffffff').strip()
        arquiva = 'arquiva_registro' in request.form
        nova_cor_tema_escuro = request.form.get('cor_tema_escuro', '#3a3a3a').strip()

        if not nova_situacao_nome:
            flash('O nome da situação não pode ser vazio.', 'error')
            return render_template('form_situacao.html', situacao=situacao, novo=False)
        
        controle_collection.update_many(
            {'situacao': situacao['situacao'], 'user_id': ObjectId(current_user.id)},
            {'$set': {'situacao': nova_situacao_nome}}
        )
        
        situacao_collection.update_one(
            {'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)},
            {'$set': {'situacao': nova_situacao_nome, 'cor': nova_cor_situacao, 'cor_tema_escuro': nova_cor_tema_escuro, 'arquiva_registro': arquiva}}
        )
        flash('Situação atualizada com sucesso!', 'success')
        return redirect(url_for('.cadastros_situacao'))

    return render_template('form_situacao.html', situacao=situacao, novo=False)

@cadastros_bp.route('/situacao/excluir/<string:situacao_id>', methods=['POST'])
@login_required
def excluir_situacao(situacao_id):
    situacao = situacao_collection.find_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    if not situacao:
        flash('Situação não encontrada.', 'error')
        return redirect(url_for('.cadastros_situacao'))

    if controle_collection.find_one({'situacao': situacao['situacao'], 'user_id': ObjectId(current_user.id)}):
        flash('Não é possível excluir. Esta situação está em uso por registros de controle.', 'error')
        return redirect(url_for('.cadastros_situacao'))
        
    situacao_collection.delete_one({'_id': ObjectId(situacao_id), 'user_id': ObjectId(current_user.id)})
    flash('Situação excluída com sucesso!', 'success')
    return redirect(url_for('.cadastros_situacao'))


# --- ROTAS DE CADASTRO DE TIPOS DE DOCUMENTO ---

@cadastros_bp.route('/documentacao')
@login_required
def cadastros_documentacao():
    documentos = documentacao_tipos_collection.find({'user_id': ObjectId(current_user.id)})
    return render_template('cadastros_documentacao.html', documentos=list(documentos))

@cadastros_bp.route('/documentacao/novo', methods=['GET', 'POST'])
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
            return redirect(url_for('.cadastros_documentacao'))
        else:
            flash('O nome do documento não pode ser vazio.', 'error')
    return render_template('form_documentacao.html', documento={}, novo=True)

@cadastros_bp.route('/documentacao/excluir/<string:doc_id>', methods=['POST'])
@login_required
def excluir_tipo_documento(doc_id):
    documentacao_tipos_collection.delete_one({'_id': ObjectId(doc_id), 'user_id': ObjectId(current_user.id)})
    flash('Tipo de documento excluído com sucesso!', 'success')
    return redirect(url_for('.cadastros_documentacao'))
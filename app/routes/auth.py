# app/routes/auth.py
# Este arquivo contém todas as rotas relacionadas à autenticação: login, registro, logout e troca de senha.

# 1. Imports de bibliotecas de terceiros (Flask, Flask-Login, etc.)
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId

# 2. Imports da nossa própria aplicação (dos modelos que criamos)
from app.models import User, users_collection, documentacao_tipos_collection, situacao_collection

# 3. Criação do Blueprint de Autenticação
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.index'))
    
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
                spacing_preference=user_data.get('spacing_preference', 'regular'),
                view_mode_controle=user_data.get('view_mode_controle'),
                card_fields_controle=user_data.get('card_fields_controle'),
                color_coding_controle=user_data.get('color_coding_controle', False),
                view_mode_pendencias=user_data.get('view_mode_pendencias'),
                card_fields_pendencias=user_data.get('card_fields_pendencias'),
                color_coding_pendencias=user_data.get('color_coding_pendencias', False)
            )
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('core.index'))
        else:
            flash('Login inválido. Verifique seu nome de usuário e senha.', 'error')
            
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('core.index'))

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
        
        # --- Bloco de criação de dados padrão para o novo usuário ---
        result = users_collection.insert_one({
            'username': username, 'email': email,
            'password_hash': hashed_password, 'theme': 'theme-blue'
        })
        novo_user_id = result.inserted_id

        # 1. Inserir Documentos Padrão
        documentos_padrao = [
            "Relatório", "TRP", "Relatório de Conformidade/Inconformidade", "TRD",
            "Certificado de garantia", "Planilhas", "Boleto", "Declaração IN 1234/2012",
            "ART", "Trabalhista/Previdenciária", "Certificado de curso"
        ]
        docs_para_inserir = [{'nome': nome, 'user_id': novo_user_id} for nome in documentos_padrao]
        if docs_para_inserir:
            documentacao_tipos_collection.insert_many(docs_para_inserir)

        # 2. Inserir Situações Padrão
        situacoes_padrao = [
            {'n': 'Conferência Relatório', 'c': '#c6e7fb', 'ce': '#0040ff', 'a': False},
            {'n': 'Emissão de Termos',     'c': '#feffc7', 'ce': '#d1c000', 'a': False},
            {'n': 'Fazer',                 'c': '#d1ffd9', 'ce': '#00bd1f', 'a': False},
            {'n': 'Aguardar',              'c': '#d6d9ff', 'ce': '#7300ff', 'a': False},
            {'n': 'Liquidação',            'c': '#ffdbb3', 'ce': '#ff8800', 'a': False},
            {'n': 'Cobrar',                'c': '#ffc2b3', 'ce': '#ff0000', 'a': False},
            {'n': 'Cancelado',             'c': '#c7c7c7', 'ce': '#3d3d3d', 'a': True},
            {'n': 'Financeiro',            'c': '#c2c2c2', 'ce': '#636363', 'a': True}
        ]
        situacoes_para_inserir = [{
            'situacao': s['n'], 'cor': s['c'], 'cor_tema_escuro': s['ce'],
            'arquiva_registro': s['a'], 'user_id': novo_user_id
        } for s in situacoes_padrao]
        if situacoes_para_inserir:
            situacao_collection.insert_many(situacoes_para_inserir)

        flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', form_data={})


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('auth.login'))


# --- NOVA ROTA: ALTERAÇÃO DE SENHA ---
@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    # 1. Captura as variáveis do formulário submetido via Modal
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # 2. Valida se preencheu todos os campos
    if not all([current_password, new_password, confirm_password]):
        flash('Todos os campos de senha são obrigatórios.', 'error')
        return redirect(url_for('core.configuracoes'))

    # 3. Valida se a nova senha e a confirmação batem
    if new_password != confirm_password:
        flash('A nova senha e a confirmação não coincidem.', 'error')
        return redirect(url_for('core.configuracoes'))

    # 4. Busca os dados atuais do utilizador na Base de Dados
    user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})

    # 5. Verifica se a senha "Atual" (Ex: a 1234 que o admin deu) está correta
    if not check_password_hash(user_data['password_hash'], current_password):
        flash('A senha atual inserida está incorreta.', 'error')
        return redirect(url_for('core.configuracoes'))

    # 6. Se passar por tudo, criptografa a nova senha
    hashed_password = generate_password_hash(new_password)
    
    # 7. Atualiza no MongoDB
    users_collection.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$set': {'password_hash': hashed_password}}
    )

    # 8. Manda mensagem de sucesso e recarrega a página
    flash('Sua senha foi alterada com segurança!', 'success')
    return redirect(url_for('core.configuracoes'))
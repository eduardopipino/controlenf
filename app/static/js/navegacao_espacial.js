// static/js/navegacao_espacial.js

document.addEventListener('DOMContentLoaded', function() {
    if (window.APP_DATA && window.APP_DATA.atalhosAtivos === false) return; // KILL SWITCH

    let navActive = false;
    let selectedElement = null; // A Linha ou o Card
    let editMode = false;
    let selectedField = null;   // O Campo dentro da Linha/Card
    let editableFields = [];

    // --- OUVINTE GLOBAL DE TECLAS ---
    document.addEventListener('keydown', function(e) {
        
        const isTextInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
        const modalAtivo = document.querySelector('.modal-overlay.active');

        // LÓGICA 1: Tratamento Especial para o Modal Extra do Input
        if (e.target.id === 'novoDocumentoExtra' && e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('btnAdicionarDocExtra')?.click();
            e.target.blur();
            return;
        }

        // LÓGICA 2: Modais Gerais (Enter = Salvar/Acionar, Esc = Cancelar)
        if (modalAtivo) {
            if (e.key === 'Escape') {
                e.preventDefault();
                modalAtivo.querySelector('.btn-cancel-modal')?.click();
                return;
            }
            if (e.key === 'Enter' && !isTextInput && !e.target.closest('.btn-remove-doc')) {
                // Se não estiver dentro de um textarea, clica no botão principal de salvar
                e.preventDefault();
                const saveBtn = modalAtivo.querySelector('button:not(.btn-cancel-modal):not(.btn-modal-add-extra)');
                if (saveBtn) saveBtn.click();
                return;
            }
            
            // Navegação por setas dentro das listas do modal (Documentação ou Colunas)
            if (['ArrowDown', 'ArrowUp'].includes(e.key) && !isTextInput) {
                e.preventDefault();
                navegarModal(modalAtivo, e.key);
                return;
            }
            if (e.key === ' ' && modalAtivo.querySelector('.keyboard-focused-modal-item')) {
                e.preventDefault(); // Espaço marca/desmarca checkbox
                modalAtivo.querySelector('.keyboard-focused-modal-item input[type="checkbox"]')?.click();
                return;
            }
            if (e.key === 'Delete' && modalAtivo.querySelector('.keyboard-focused-modal-item')) {
                e.preventDefault(); // Delete remove item de documentação
                modalAtivo.querySelector('.keyboard-focused-modal-item .btn-remove-doc')?.dispatchEvent(new Event('click', { bubbles: true }));
                return;
            }
        }

        // Proteção: não intercepta atalhos se estiver digitando texto comum, exceto com Alt ou navegando no editMode
        if (isTextInput && !e.altKey && e.key !== 'Escape' && !editMode) return;

        // Construção da string do atalho (ex: "alt+n")
        let atalho = '';
        if (e.altKey) atalho += 'alt+';
        if (e.key !== 'Alt' && e.key !== 'Control' && e.key !== 'Shift') {
            atalho += e.key.toLowerCase();
        }

        // LÓGICA 3: Dicionário de Atalhos da Página
        if (window.MEUS_ATALHOS && window.MEUS_ATALHOS[atalho]) {
            e.preventDefault();
            const acao = window.MEUS_ATALHOS[atalho];
            if (typeof acao === 'string') document.getElementById(acao)?.click();
            else acao();
            return;
        }

        // LÓGICA 4: Navegação Espacial e Edição
        if (e.key === 'Escape') {
            if (editMode) {
                // Sai do modo de edição e volta pra navegação de linha
                editMode = false;
                limparFocoCampos();
            } else if (navActive) {
                // Sai da navegação de linha
                navActive = false;
                if(selectedElement) selectedElement.classList.remove('keyboard-focused-row');
                selectedElement = null;
            } else {
                // Limpa a busca
                document.getElementById('buscaRapidaInput').value = '';
                document.getElementById('buscaRapidaInput').blur();
                document.getElementById('buscaRapidaInput').dispatchEvent(new Event('keyup'));
            }
            return;
        }

        // Alt + ArrowDown: Inicia a seleção na primeira linha/card visível
        if (atalho === 'alt+arrowdown') {
            e.preventDefault();
            iniciarNavegacao();
            return;
        }

        // Setas direcionais (Sem Alt)
        if (['arrowdown', 'arrowup', 'arrowleft', 'arrowright'].includes(atalho) && navActive) {
            e.preventDefault();
            if (editMode) navegarCampos(atalho);
            else navegarElementos(atalho);
            return;
        }

        // Alt + E (Editar campo)
        if (atalho === 'alt+e' && navActive) {
            e.preventDefault();
            if (!editMode) iniciarEdicaoContextual();
            return;
        }

        // Enter no Modo de Edição (Gatilho para DblClick)
        if (atalho === 'enter' && editMode && selectedField) {
            e.preventDefault();
            const event = new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window });
            selectedField.dispatchEvent(event);
            return;
        }

        // Alt + D (Ver Detalhes)
        if (atalho === 'alt+d' && navActive && selectedElement) {
            e.preventDefault();
            const btnLupa = selectedElement.querySelector('.action-icon-link, .card-action-icon[title*="Detalhe"]');
            if (btnLupa) window.location.href = btnLupa.href;
            return;
        }
    });

    // --- FUNÇÕES DE MOTOR DE NAVEGAÇÃO ESPACIAL ---

    function obterElementosVisiveis() {
        return Array.from(document.querySelectorAll('.clickable-row, .data-card')).filter(el => {
            return window.getComputedStyle(el).display !== 'none' && el.offsetWidth > 0;
        });
    }

    function iniciarNavegacao() {
        const elementos = obterElementosVisiveis();
        if (elementos.length === 0) return;
        navActive = true; editMode = false; limparFocoCampos();
        if(selectedElement) selectedElement.classList.remove('keyboard-focused-row');
        selectedElement = elementos[0];
        selectedElement.classList.add('keyboard-focused-row');
        selectedElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function navegarElementos(direcao) {
        const elementos = obterElementosVisiveis();
        let idx = elementos.indexOf(selectedElement);
        if (idx === -1) return iniciarNavegacao();

        if (direcao === 'arrowdown' || direcao === 'arrowright') {
            idx = Math.min(idx + 1, elementos.length - 1);
        } else if (direcao === 'arrowup' || direcao === 'arrowleft') {
            idx = Math.max(idx - 1, 0);
        }

        selectedElement.classList.remove('keyboard-focused-row');
        selectedElement = elementos[idx];
        selectedElement.classList.add('keyboard-focused-row');
        selectedElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function iniciarEdicaoContextual() {
        if (!selectedElement) return;
        editableFields = Array.from(selectedElement.querySelectorAll('.editable-cell, .editable-card-field, .situacao-dropdown')).filter(el => window.getComputedStyle(el).display !== 'none');
        if (editableFields.length === 0) return;
        
        editMode = true;
        limparFocoCampos();
        selectedField = editableFields[0];
        selectedField.classList.add('keyboard-focused-field');
    }

    function navegarCampos(direcao) {
        let idx = editableFields.indexOf(selectedField);
        if (direcao === 'arrowright' || direcao === 'arrowdown') {
            idx = Math.min(idx + 1, editableFields.length - 1);
        } else if (direcao === 'arrowleft' || direcao === 'arrowup') {
            idx = Math.max(idx - 1, 0);
        }
        limparFocoCampos();
        selectedField = editableFields[idx];
        selectedField.classList.add('keyboard-focused-field');
    }

    function limparFocoCampos() {
        document.querySelectorAll('.keyboard-focused-field').forEach(el => el.classList.remove('keyboard-focused-field'));
    }

    // Navegação Interna de Modais
    function navegarModal(modal, direcao) {
        const itens = Array.from(modal.querySelectorAll('.doc-inline-row, .modal-checklist-item'));
        if (itens.length === 0) return;
        
        let atual = modal.querySelector('.keyboard-focused-modal-item');
        let idx = atual ? itens.indexOf(atual) : -1;

        if (atual) atual.classList.remove('keyboard-focused-modal-item');

        if (direcao === 'ArrowDown') idx = Math.min(idx + 1, itens.length - 1);
        else if (direcao === 'ArrowUp') idx = Math.max(idx - 1, 0);

        const novoFoco = itens[idx];
        novoFoco.classList.add('keyboard-focused-modal-item');
        novoFoco.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});
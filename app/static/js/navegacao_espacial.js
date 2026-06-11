// static/js/navegacao_espacial.js

document.addEventListener('DOMContentLoaded', function() {
    // KILL SWITCH GLOBAL E TOLERANTE
    let atalhosLigados = true;
    if (typeof window.ATALHOS_ATIVOS_GLOBAL !== 'undefined' && window.ATALHOS_ATIVOS_GLOBAL === false) atalhosLigados = false;
    if (window.APP_DATA && window.APP_DATA.atalhosAtivos === false) atalhosLigados = false;
    if (window.APP_DATA_PENDENCIAS && window.APP_DATA_PENDENCIAS.atalhosAtivos === false) atalhosLigados = false;
    if (!atalhosLigados) return;

    let menuNavActive = false; // Estado do Menu Principal
    let navActive = false;
    let selectedElement = null; // A Linha ou o Card
    let editMode = false;
    let selectedField = null;   // O Campo dentro da Linha/Card
    let editableFields = [];

    // --- OUVINTE GLOBAL DE TECLAS ---
    document.addEventListener('keydown', function(e) {
        
        const isTextInput = ['INPUT', 'TEXTAREA'].includes(e.target.tagName);
        const modalAtivo = document.querySelector('.modal-overlay.active');

        // === CONTROLE DE NAVEGAÇÃO DO MENU PRINCIPAL ===
        if (menuNavActive) {
            // Se estiver no menu, domina as setas, o Enter e o Esc
            if (['Escape', 'Enter', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                e.preventDefault();
                if (e.key === 'Escape') sairNavegacaoMenu();
                else if (e.key === 'Enter') acionarMenuAtual();
                else navegarMenu(e.key);
                return; // Para a execução do script aqui
            }
        }

        // === NAVEGAÇÃO DO MENU DE CONTEXTO DOS CARDS (AMBAS AS PÁGINAS) ===
        // Procura tanto o menu de Notas Fiscais quanto o de Pendências
        const contextMenu = document.getElementById('situacaoContextMenu') || document.getElementById('colorContextMenu');
        const contextMenuAtivo = contextMenu && contextMenu.style.display === 'block';

        if (contextMenuAtivo) {
            // Se apertar uma dessas teclas, intercepta a ação
            if (['Escape', 'Enter', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
                e.preventDefault(); // Impede a tela de rolar
                
                if (e.key === 'Escape') {
                    contextMenu.style.display = 'none';
                    return;
                }
                
                const itens = Array.from(contextMenu.querySelectorAll('.context-menu-item'));
                let atual = contextMenu.querySelector('.keyboard-focused-context-item');
                
                if (e.key === 'Enter') {
                    if (atual) atual.click(); // Simula o clique do mouse na opção
                    else contextMenu.style.display = 'none'; 
                    return;
                }
                
                // Lógica de descer e subir
                let idx = atual ? itens.indexOf(atual) : -1;
                if (e.key === 'ArrowDown') idx = Math.min(idx + 1, itens.length - 1);
                else if (e.key === 'ArrowUp') idx = Math.max(idx - 1, 0);
                
                if (atual) atual.classList.remove('keyboard-focused-context-item');
                if (itens[idx]) itens[idx].classList.add('keyboard-focused-context-item');
                return;
            }
        }
        // === FIM DO NOVO BLOCO ===
		
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
            
            // CORREÇÃO AQUI: O Enter salva o modal mesmo dentro do input (a menos que seja um Textarea para pular linha)
            const isTextArea = e.target.tagName === 'TEXTAREA';
            if (e.key === 'Enter' && !isTextArea && !e.target.closest('.btn-remove-doc')) {
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

        // === ALT + M (Focar Menu Principal) ===
        if (atalho === 'alt+m') {
            e.preventDefault();
            iniciarNavegacaoMenu();
            return;
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
            // Nova Exceção: Se estiver num Select, o Esc apenas tira o foco dele
            if (document.activeElement && document.activeElement.tagName === 'SELECT') {
                document.activeElement.blur();
                return;
            }
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
            
            // PROTEÇÃO TOTAL: Se o cursor estiver dentro de QUALQUER campo de edição, deixa o navegador agir!
            const tagAtiva = document.activeElement ? document.activeElement.tagName : '';
            if (['SELECT', 'INPUT', 'TEXTAREA'].includes(tagAtiva)) return;

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

        // Enter no Modo de Edição (Gatilho para DblClick ou Select)
        if (atalho === 'enter' && editMode && selectedField) {
            
            // 1. Se JÁ for um Select (como ocorre na Tabela)
            const selectElement = selectedField.tagName === 'SELECT' ? selectedField : selectedField.querySelector('select');
            
            if (selectElement) {
                if (document.activeElement === selectElement) selectElement.blur(); // Confirma/Sai
                else { e.preventDefault(); selectElement.focus(); } // Entra
                return;
            }

            // 2. Para os Cards: Dispara o clique que cria o campo dinamicamente
            e.preventDefault();
            const event = new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window });
            selectedField.dispatchEvent(event);

            // 3. A MÁGICA: Dá tempo para o HTML nascer e puxa o foco para ele!
            setTimeout(() => {
                const campoDinamico = selectedField.querySelector('select, input, textarea');
                if (campoDinamico) campoDinamico.focus();
            }, 50);
            
            return;
        }

        // Alt + D (Ver Detalhes)
        if (atalho === 'alt+d' && navActive && selectedElement) {
            e.preventDefault();
            const btnLupa = selectedElement.querySelector('.action-icon-link, .card-action-icon[title*="Detalhe"]');
            if (btnLupa) window.location.href = btnLupa.href;
            return;
        }

        // Alt + P (Ativar/Desativar Prioridade)
        if (atalho === 'alt+p' && navActive && selectedElement) {
            e.preventDefault();
            // Procura o ícone de prioridade da tabela ou do card da linha focada
            const btnPrioridade = selectedElement.querySelector('.coluna-prioridade, .card-priority-toggle');
            if (btnPrioridade) btnPrioridade.click();
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

    // --- FUNÇÕES DE NAVEGAÇÃO DO MENU PRINCIPAL ---

    function iniciarNavegacaoMenu() {
        // Desliga a navegação da tabela/cards para não haver conflito
        navActive = false; editMode = false; limparFocoCampos();
        if(selectedElement) selectedElement.classList.remove('keyboard-focused-row');
        
        menuNavActive = true;
        const topItens = obterItensMenuTopo();
        if (topItens.length > 0) focarItemMenu(topItens[0]);
    }

    function sairNavegacaoMenu() {
        menuNavActive = false;
        limparFocoMenu();
    }

    function obterItensMenuTopo() {
        // Encontra todos os links principais e o botão do Notepad no topo
        return Array.from(document.querySelectorAll('#main-nav-menu > .nav-item > .nav-link, #main-nav-menu > .nav-item > .notepad-btn'));
    }

    function focarItemMenu(elemento) {
        limparFocoMenu();
        if (!elemento) return;
        elemento.classList.add('keyboard-focused-menu-item');
        
        // Magia: Se for um link de um dropdown, abre o dropdown pai adicionando a classe "open" (que já existe no seu base.html)
        const parentLi = elemento.closest('.nav-item.dropdown');
        if (parentLi) parentLi.classList.add('open'); 
        
        elemento.focus(); // Informa os Leitores de Ecrã (Acessibilidade)
    }

    function limparFocoMenu() {
        document.querySelectorAll('.keyboard-focused-menu-item').forEach(el => el.classList.remove('keyboard-focused-menu-item'));
        document.querySelectorAll('#main-nav-menu .dropdown.open').forEach(el => el.classList.remove('open'));
    }

    function navegarMenu(tecla) {
        const focado = document.querySelector('.keyboard-focused-menu-item');
        if (!focado) return iniciarNavegacaoMenu();

        const topItens = obterItensMenuTopo();
        const isTopLevel = topItens.includes(focado);
        const parentDropdown = focado.closest('.nav-item.dropdown');
        const dropdownItens = parentDropdown ? Array.from(parentDropdown.querySelectorAll('.dropdown-item')) : [];

        if (tecla === 'ArrowRight' || tecla === 'ArrowLeft') {
            // Caminha para a esquerda ou direita na barra superior (Faz loop infinito)
            let idx = isTopLevel ? topItens.indexOf(focado) : topItens.indexOf(parentDropdown.querySelector('.dropbtn'));
            if (tecla === 'ArrowRight') idx = (idx + 1) % topItens.length;
            else idx = (idx - 1 + topItens.length) % topItens.length;
            focarItemMenu(topItens[idx]);
        } 
        else if (tecla === 'ArrowDown') {
            // Abre o dropdown e vai para o primeiro item, OU desce pela lista
            if (isTopLevel && dropdownItens.length > 0) focarItemMenu(dropdownItens[0]);
            else if (!isTopLevel) {
                let idx = Math.min(dropdownItens.indexOf(focado) + 1, dropdownItens.length - 1);
                focarItemMenu(dropdownItens[idx]);
            }
        }
        else if (tecla === 'ArrowUp') {
            // Sobe pela lista. Se estiver no topo da lista, volta para a barra superior
            if (!isTopLevel) {
                let idx = dropdownItens.indexOf(focado);
                if (idx > 0) focarItemMenu(dropdownItens[idx - 1]);
                else focarItemMenu(parentDropdown.querySelector('.dropbtn'));
            }
        }
    }

    function acionarMenuAtual() {
        const focado = document.querySelector('.keyboard-focused-menu-item');
        if (focado) {
            focado.click(); // O JS clica por si!
            // Fecha a navegação de menu se não for apenas um abridor de dropdown
            if (!focado.classList.contains('dropbtn')) sairNavegacaoMenu();
        }
    }
});
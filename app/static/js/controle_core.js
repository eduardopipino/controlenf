// static/js/controle_core.js

document.addEventListener('DOMContentLoaded', function() {
    let currentEditInput = null;

    // ==========================================
    // 0. PINTURA INICIAL DAS PÍLULAS DE SITUAÇÃO
    // ==========================================
    if (window.APP_DATA && window.APP_DATA.colorCodingIsActive) {
        document.querySelectorAll('.situacao-dropdown').forEach(dropdown => {
            const sit = dropdown.value;
            if (sit && window.APP_DATA.colorMap[sit]) {
                dropdown.style.backgroundColor = window.APP_DATA.colorMap[sit];
            }
        });
    }

    // Função auxiliar para dar feedback visual (piscar verde/cinza)
    function flashElement(element) {
        if (!element) return;
        const isDarkTheme = document.body.classList.contains('theme-dark');
        const originalBg = element.style.backgroundColor;
        const flashColor = isDarkTheme ? '#3a3a3a' : '#e0e0e0';
        element.style.transition = 'background-color 0.3s ease-in-out';
        element.style.backgroundColor = flashColor;
        setTimeout(() => {
            element.style.backgroundColor = originalBg || '';
            setTimeout(() => { element.style.transition = ''; }, 300);
        }, 700);
    }

    // Função auxiliar para o Modal Customizado (Substitui o prompt)
    function showCustomPrompt(titleText) {
        return new Promise((resolve) => {
            const modal = document.getElementById('customPromptModal');
            const title = document.getElementById('customPromptTitle');
            const input = document.getElementById('customPromptInput');
            const colorInput = document.getElementById('customPromptColor');
            const btnConfirm = document.getElementById('btnCustomPromptConfirm');
            const btnCancel = document.getElementById('btnCustomPromptCancel');

            title.textContent = titleText;
            input.value = '';
            colorInput.value = '#e2e8f0'; // Reseta para cinza claro no JS
            modal.classList.add('active');
            setTimeout(() => input.focus(), 100);

            function cleanup() {
                modal.classList.remove('active');
                btnConfirm.removeEventListener('click', onConfirm);
                btnCancel.removeEventListener('click', onCancel);
                input.removeEventListener('keydown', onKey);
            }
            function onConfirm() { 
                cleanup(); 
                resolve({ nome: input.value, cor: colorInput.value }); 
            }
            function onCancel() { cleanup(); resolve(null); }
            function onKey(e) {
                if (e.key === 'Enter') { e.preventDefault(); onConfirm(); }
                if (e.key === 'Escape') onCancel();
            }

            btnConfirm.addEventListener('click', onConfirm);
            btnCancel.addEventListener('click', onCancel);
            input.addEventListener('keydown', onKey);
        });
    }

    // ==========================================
    // 1. ATUALIZAÇÃO RÁPIDA DE SITUAÇÃO (SELECT DA TABELA)
    // ==========================================
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('situacao-dropdown')) {
            const dropdown = e.target;
            const controleId = dropdown.dataset.id;
            const novaSituacaoRaw = dropdown.value;
            const linhaDaTabela = document.getElementById(`controle-row-${controleId}`);
            
            function saveSituacao(sitParaSalvar, corCustomizada = null) {
                dropdown.setAttribute('data-last-value', sitParaSalvar);
                fetch(`/controle/update_situacao_inline`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        controle_id: controleId, 
                        nova_situacao: sitParaSalvar,
                        cor_temporaria: corCustomizada // <<< Envia a cor
                    }),
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        flashElement(linhaDaTabela);
                        if (window.APP_DATA && window.APP_DATA.colorCodingIsActive) {
                            if (corCustomizada) {
                                dropdown.style.backgroundColor = corCustomizada; // Pinta a temporária
                            } else {
                                dropdown.style.backgroundColor = window.APP_DATA.colorMap[sitParaSalvar] || '';
                            }
                        }
                    } else alert('Erro ao atualizar situação.');
                }).catch(error => console.error('Erro de rede:', error));
            }
            
            if (novaSituacaoRaw === '*custom*') {
                showCustomPrompt("Digite a nova situação para este registro:").then(promptValue => {
                    if (!promptValue || !promptValue.nome || promptValue.nome.trim() === '') {
                        dropdown.value = dropdown.getAttribute('data-last-value') || "";
                        return;
                    }
                    const novaSituacao = promptValue.nome.trim();
                    const novaCor = promptValue.cor;
                    
                    const newOpt = new Option(novaSituacao, novaSituacao, true, true);
                    dropdown.add(newOpt, dropdown.options[dropdown.options.length - 1]);
                    saveSituacao(novaSituacao, novaCor); // <<< Passa a cor para salvar
                });
            } else {
                saveSituacao(novaSituacaoRaw);
            }
        }
    });

    // ==========================================
    // 2. EDIÇÃO INLINE (TABELA E CARDS UNIFICADO)
    // ==========================================
    document.addEventListener('dblclick', function(e) {
        // Verifica se clicou na Tabela
        let td = e.target.closest('td.editable-cell');
        let cardField = e.target.closest('.data-card[data-type="controle"] .editable-card-field');
        
        let container, fieldName, originalValue, valueElement, isCard = false;

        if (td && td.closest('.tabela-controle-shared')) {
            container = td;
            fieldName = td.dataset.fieldName;
            valueElement = td.querySelector('span.card-value');
            if (!valueElement) return;
            originalValue = valueElement.textContent.trim();
        } else if (cardField) {
            container = cardField;
            isCard = true;
            fieldName = cardField.dataset.fieldName;
            valueElement = cardField.querySelector('.card-field-value');
            if (!valueElement && cardField.tagName !== 'H4') return;
            originalValue = valueElement ? valueElement.textContent.trim() : cardField.textContent.replace(cardField.querySelector('strong')?.textContent || '', '').trim();
        } else {
            return; // Não clicou em nada editável
        }

        // Bloqueia se já houver edição aberta
        if (container.querySelector('input, textarea') || currentEditInput) {
            if (currentEditInput) currentEditInput.focus();
            return;
        }

        const controleId = (isCard ? container.closest('.data-card') : container.closest('tr')).dataset.id;

        // SE FOR DOCUMENTAÇÃO, ABRE O MODAL
        if (fieldName === 'documentacao') {
            abrirModalDocumentacao(controleId);
            return;
        }

        // Se for situação no Card, abre o Menu de Contexto (O Select da Tabela já funciona)
        if (isCard && fieldName === 'situacao') {
            abrirMenuDeContexto(e, container.closest('.data-card'));
            return;
        }

        // Prepara o Input
        let inputElement = document.createElement(fieldName === 'observacoes' ? 'textarea' : 'input');
        if (fieldName === 'observacoes') {
            inputElement.style.height = '60px';
            inputElement.style.resize = 'vertical';
        } else {
            inputElement.type = 'text';
        }
        
        inputElement.value = originalValue;
        inputElement.style.width = '100%';
        inputElement.style.boxSizing = 'border-box';
        if (isCard) inputElement.style.flexGrow = '1';

        const backupHTML = container.innerHTML;
        currentEditInput = inputElement;

        // Limpa o container e adiciona o Input (preservando o Label se for Card)
        if (isCard) {
            container.innerHTML = '';
            if (container.tagName === 'H4') container.appendChild(document.createTextNode('Referência: '));
            else if (backupHTML.includes('<strong>')) container.innerHTML = backupHTML.split('</strong>')[0] + '</strong> ';
            container.appendChild(inputElement);
        } else {
            container.innerHTML = '';
            container.appendChild(inputElement);
        }

        inputElement.focus();
        if (inputElement.select) inputElement.select();

        // Lógica de Salvar/Cancelar
        function cancelarEdicao() {
            container.innerHTML = backupHTML;
            currentEditInput = null;
        }

        function salvarEdicao() {
            const newValue = inputElement.value.trim();
            if (newValue === originalValue) return cancelarEdicao();

            fetch(`/controle/update_field_inline/${controleId}`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ field: fieldName, value: newValue })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    if (isCard) {
                        if (container.tagName === 'H4') container.innerHTML = `Referência: <span class="card-field-value">${data.newValue}</span>`;
                        else container.innerHTML = `${backupHTML.split('</strong>')[0]}</strong> <span class="card-field-value">${data.newValue}</span>`;
                    } else {
                        container.innerHTML = `<span class="card-value">${data.newValue}</span>`;
                    }
                    currentEditInput = null;
                    flashElement(isCard ? container.closest('.data-card') : container);
                } else {
                    alert(`Erro ao salvar: ${data.message}`);
                    cancelarEdicao();
                }
            }).catch(err => { alert('Erro de rede.'); cancelarEdicao(); });
        }

        inputElement.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); salvarEdicao(); }
            else if (e.key === 'Escape') cancelarEdicao();
        });
        inputElement.addEventListener('blur', () => { setTimeout(() => { if (currentEditInput === inputElement) cancelarEdicao(); }, 150); });
    });

    // ==========================================
    // 3. MODAL DE DOCUMENTAÇÃO
    // ==========================================
    function criarLinhaDocumento(valor, isChecked, isExtra) {
        const div = document.createElement('div');
        div.className = 'doc-inline-row';
        const extra = isExtra ? 'style="font-style: italic;"' : '';
        div.innerHTML = `<label class="doc-inline-label"><input type="checkbox" name="doc_inline_pref" value="${valor}" ${isChecked ? 'checked' : ''}> <span ${extra}>${valor}${isExtra ? ' (Extra)' : ''}</span></label>
        <svg class="btn-remove-doc" viewBox="0 0 24 24" width="18px" fill="currentColor" style="cursor: pointer;"><path d="M16 9v10H8V9h8m-1.5-6h-5l-1 1H5v2h14V4h-3.5l-1-1zM18 7H6v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7z"/></svg>`;
        return div;
    }

    function abrirModalDocumentacao(controleId) {
        const docModal = document.getElementById('documentacaoModal');
        const docChecklist = document.getElementById('documentacao-checklist');
        if (!docModal || !docChecklist) return;

        document.getElementById('documentacaoModalControleId').value = controleId;
        docChecklist.innerHTML = '<p>Carregando...</p>';
        docModal.classList.add('active');

        fetch(`/controle/get_documentacao/${controleId}`)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    docChecklist.innerHTML = '';
                    if (data.opcoes.length === 0) docChecklist.innerHTML = '<p>Nenhuma opção cadastrada.</p>';
                    data.opcoes.forEach(opt => docChecklist.appendChild(criarLinhaDocumento(opt, data.salvos.includes(opt), false)));
                    data.salvos.forEach(salvo => { if (!data.opcoes.includes(salvo)) docChecklist.appendChild(criarLinhaDocumento(salvo, true, true)); });
                    if (data.pendentes) data.pendentes.forEach(pend => { if (!data.opcoes.includes(pend)) docChecklist.appendChild(criarLinhaDocumento(pend, false, true)); });
                    window.opcoesOriginaisModal = data.opcoes || [];
                }
            });
    }

    // Ações dentro do modal via Event Delegation
    document.addEventListener('click', function(e) {
        if (e.target.closest('.btn-remove-doc')) {
            e.target.closest('.doc-inline-row').remove();
        }
        else if (e.target.id === 'btnAdicionarDocExtra') {
            const input = document.getElementById('novoDocumentoExtra');
            const val = input.value.trim();
            if (val) {
                document.getElementById('documentacao-checklist').appendChild(criarLinhaDocumento(val, true, true));
                input.value = '';
            }
        }
        else if (e.target.id === 'btnSalvarDocumentacao') {
            const controleId = document.getElementById('documentacaoModalControleId').value;
            const docChecklist = document.getElementById('documentacao-checklist');
            const selecionados = Array.from(docChecklist.querySelectorAll('input:checked')).map(cb => cb.value);
            const pendentes = Array.from(docChecklist.querySelectorAll('input:not(:checked)')).map(cb => cb.value);
            const atuais = Array.from(docChecklist.querySelectorAll('input')).map(cb => cb.value);
            const ignorados = (window.opcoesOriginaisModal || []).filter(opt => !atuais.includes(opt));

            e.target.textContent = '...';
            fetch(`/controle/update_documentacao_inline/${controleId}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ documentacao: selecionados, documentacao_pendente: pendentes, documentacao_ignorada: ignorados })
            }).then(r => r.json()).then(data => {
                if (data.status === 'success') {
                    let novoHtml = data.novos_documentos.join(', ');
                    if (data.novos_documentos.length > 0 && data.novos_pendentes.length > 0) novoHtml += ', ';
                    if (data.novos_pendentes.length > 0) novoHtml += `<span class="texto-pendente">(pendente: ${data.novos_pendentes.join(', ')})</span>`;
                    
                    const td = document.querySelector(`.tabela-controle-shared tr[data-id="${controleId}"] td[data-field-name="documentacao"] span.card-value`);
                    const p = document.querySelector(`.data-card[data-id="${controleId}"] p[data-field-name="documentacao"] span.card-field-value`);
                    if (td) { td.innerHTML = novoHtml; flashElement(td.closest('td')); }
                    if (p) { p.innerHTML = novoHtml; flashElement(p.closest('.data-card')); }
                    document.getElementById('documentacaoModal').classList.remove('active');
                } else alert('Erro.');
                e.target.textContent = 'Salvar';
            });
        }
    });

    // ==========================================
    // 4. MENU DE CONTEXTO E KANBAN (SITUAÇÃO CARDS)
    // ==========================================
    const situacaoContextMenu = document.getElementById('situacaoContextMenu');
    const situacaoOptionsContainer = document.getElementById('situacao-options-container');
    let activeCard = null;

    function abrirMenuDeContexto(event, card) {
        event.preventDefault();
        activeCard = card;
        situacaoOptionsContainer.innerHTML = '<li class="context-menu-item" data-situacao="">-- Nenhuma --</li>';
        
        // Pega as situações do select da tabela invisível (forma fácil de obter sem Jinja)
        document.querySelectorAll('select.situacao-dropdown option').forEach(opt => {
            // Ignora o *custom* (pois já está fixo no HTML) e evita duplicados
            if (opt.value && opt.value !== '*custom*' && !Array.from(situacaoOptionsContainer.children).some(li => li.dataset.situacao === opt.value)) {
                situacaoOptionsContainer.innerHTML += `<li class="context-menu-item" data-situacao="${opt.value}">${opt.textContent}</li>`;
            }
        });

        situacaoContextMenu.style.display = 'block';
        situacaoContextMenu.style.top = `${event.pageY}px`;
        situacaoContextMenu.style.left = `${event.pageX}px`;
    }

    document.addEventListener('contextmenu', e => {
        const card = e.target.closest('.data-card[data-type="controle"]');
        if (card) abrirMenuDeContexto(e, card);
    });

    document.addEventListener('click', e => {
        if (situacaoContextMenu) situacaoContextMenu.style.display = 'none';
        
        const menuItem = e.target.closest('.context-menu-item');
        if (menuItem && activeCard) {
            let novaSitRaw = menuItem.dataset.situacao;
            
            function performSetSituacao(sitParaSalvar) {
                fetch(`/controle/set_situacao/${activeCard.dataset.id}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ situacao: sitParaSalvar })
                }).then(r => r.json()).then(data => {
                    if (data.status === 'success') {
                        const situacaoField = activeCard.querySelector('p[data-field-name="situacao"] .card-field-value');
                        if (situacaoField) situacaoField.textContent = sitParaSalvar;
                        if (window.APP_DATA && window.APP_DATA.colorCodingIsActive) activeCard.style.backgroundColor = window.APP_DATA.colorMap[sitParaSalvar] || '';
                        
                        if (window.APP_DATA && window.APP_DATA.arquivadores.includes(sitParaSalvar)) {
                            activeCard.style.opacity = '0'; setTimeout(() => activeCard.remove(), 400);
                        }
                    }
                });
            }

            if (novaSitRaw === '*custom*') {
                showCustomPrompt("Digite a nova situação para este registro:").then(promptValue => {
                    if (!promptValue || !promptValue.nome || promptValue.nome.trim() === '') return;
                    const novaSituacao = promptValue.nome.trim();
                    const novaCor = promptValue.cor;
                    
                    fetch(`/controle/set_situacao/${activeCard.dataset.id}`, {
                        method: 'POST', 
                        headers: { 'Content-Type': 'application/json' }, 
                        body: JSON.stringify({ situacao: novaSituacao, cor_temporaria: novaCor })
                    }).then(r => r.json()).then(data => {
                        if (data.status === 'success') {
                            const situacaoField = activeCard.querySelector('p[data-field-name="situacao"] .card-field-value');
                            if (situacaoField) situacaoField.textContent = novaSituacao;
                            if (window.APP_DATA && window.APP_DATA.colorCodingIsActive) {
                                activeCard.style.backgroundColor = novaCor; // Pinta com a cor do modal
                            }
                        }
                    });
                });
            } else {
                performSetSituacao(novaSitRaw);
            }
        }
    });

    // Lógica Drag and Drop para o Kanban
    document.querySelectorAll('.kanban-cards').forEach(column => {
        if (typeof Sortable !== 'undefined') {
            new Sortable(column, {
                group: 'kanban', animation: 150,
                onEnd: function (evt) {
                    const card = evt.item;
                    const novaSit = evt.to.parentElement.dataset.situacao || "";
                    fetch(`/controle/set_situacao/${card.dataset.id}`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ situacao: novaSit })
                    }).then(r => r.json()).then(d => {
                        if (d.status === 'success') {
                            const p = card.querySelector('p[data-field-name="situacao"] .card-field-value');
                            if (p) p.textContent = novaSit;
                            if (window.APP_DATA.colorCodingIsActive) card.style.backgroundColor = window.APP_DATA.colorMap[novaSit] || '';
                            if (window.APP_DATA.arquivadores.includes(novaSit)) card.remove();
                        } else location.reload();
                    });
                }
            });
        }
    });

});
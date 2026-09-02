// static/js/pendencias_core.js

document.addEventListener('DOMContentLoaded', function() {
    let currentEditInput = null;
    let isPriorityFetchLocked = false;
    const contextMenu = document.getElementById('colorContextMenu');
    const colorPicker = document.getElementById('hiddenColorPicker');
    let activeItem = null;

    // --- FUNÇÕES AUXILIARES ---
    function flashElement(element) {
        if (!element) return;
        const isDarkTheme = document.body.classList.contains('theme-dark');
        const flashClass = element.tagName === 'TD' ? 'td-feedback-flash' : 'card-feedback-flash';
        const flashColor = isDarkTheme ? '#3a3a3a' : '#e0e0e0';
        const originalBg = element.style.backgroundColor;
        
        element.classList.add(flashClass);
        element.style.backgroundColor = flashColor;
        setTimeout(() => {
            element.style.backgroundColor = originalBg || '';
            setTimeout(() => element.classList.remove(flashClass), 300);
        }, 700);
    }

    function convertDateToISO(dateString) {
        if (!dateString) return ''; 
        const parts = dateString.split('/');
        if (parts.length === 3 && parts[2] && parts[1] && parts[0]) return `${parts[2]}-${parts[1]}-${parts[0]}`;
        return ''; 
    }

    // <<< NOVA FUNÇÃO >>>
    function autoCompletarData(valorIncompleto) {
        let val = valorIncompleto.replace(/\s/g, '');
        if (!val || val === '/' || val === '//') return '';
        let parts = val.split('/');
        let hoje = new Date();
        
        let d = parts[0] && parts[0].length > 0 ? parts[0].padStart(2, '0') : '';
        let m = parts[1] && parts[1].length > 0 ? parts[1].padStart(2, '0') : String(hoje.getMonth() + 1).padStart(2, '0');
        let y = parts[2] && parts[2].length > 0 ? parts[2] : String(hoje.getFullYear());
        
        if (y.length === 2) y = '20' + y; 
        
        // NOVA VALIDAÇÃO MATEMÁTICA DA DATA
        let numY = parseInt(y, 10);
        let numM = parseInt(m, 10);
        let numD = parseInt(d, 10);
        let dataTeste = new Date(numY, numM - 1, numD);
        
        // Verifica se a data é real (Rejeita dia 32, ou 30 de fevereiro, etc)
        if (dataTeste.getFullYear() === numY && dataTeste.getMonth() === numM - 1 && dataTeste.getDate() === numD) {
            return `${d}/${m}/${y}`;
        } else {
            return 'INVALIDA';
        }
    }

    function parseDateFromDDMMYYYY(dateString) {
        if (!dateString) return null;
        const parts = dateString.split('/');
        if (parts.length === 3) {
            const date = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0])); 
            date.setHours(0, 0, 0, 0);
            return date;
        }
        return null;
    }

    // ==========================================
    // 1. EDIÇÃO INLINE (TABELA E CARDS)
    // ==========================================
    document.body.addEventListener('dblclick', function(e) {
        let td = e.target.closest('td.editable-cell');
        let cardField = e.target.closest('.data-card[data-type="pendencia"] .editable-card-field');
        
        let container, fieldName, originalValue, valueElement, isCard = false;

        if (td && td.closest('.tabela-pendencias-shared')) {
            container = td; fieldName = td.dataset.fieldName;
            valueElement = td.querySelector('span.card-value');
            if (!valueElement) return;
            originalValue = valueElement.textContent.trim();
        } else if (cardField && cardField.closest('.data-card')) {
            container = cardField; isCard = true; fieldName = cardField.dataset.fieldName;
            valueElement = cardField.querySelector('.card-field-value');
            if (!valueElement && cardField.tagName !== 'H4') return;
            originalValue = valueElement ? valueElement.textContent.trim() : cardField.textContent.replace(cardField.querySelector('strong')?.textContent || '', '').trim();
        } else { return; }

        if (container.querySelector('input, textarea') || currentEditInput) {
            if (currentEditInput) currentEditInput.focus();
            return;
        }

        const pendenciaId = (isCard ? container.closest('.data-card') : container.closest('tr')).dataset.id;
        
        let inputElement = document.createElement(fieldName === 'observacoes' ? 'textarea' : (fieldName === 'prazo' ? 'input' : 'input'));
        if (fieldName === 'observacoes') {
            inputElement.style.height = isCard ? '60px' : Math.max(valueElement.offsetHeight, 60) + 'px';
            inputElement.style.resize = 'vertical';
        } else if (fieldName === 'prazo') {
            inputElement.type = 'text';
            inputElement.value = originalValue;
        } else {
            inputElement.type = 'text';
            inputElement.value = originalValue;
        }

        inputElement.style.width = '100%';
        inputElement.style.boxSizing = 'border-box';
        if (isCard && fieldName !== 'observacoes') inputElement.style.flexGrow = '1';

        const backupHTML = container.innerHTML;
        currentEditInput = inputElement;

        container.innerHTML = '';
        if (isCard) {
            if (container.tagName === 'H4') {} 
            else if (backupHTML.includes('<strong>')) container.innerHTML = backupHTML.split('</strong>')[0] + '</strong> ';
        }
        container.appendChild(inputElement);

        let dateMask = null;
        let fp = null;
        let saveInProgress = false; 

        if (fieldName === 'prazo' && typeof IMask !== 'undefined' && typeof flatpickr !== 'undefined') {
            dateMask = IMask(inputElement, { mask: '00/00/0000', lazy: false, placeholderChar: ' ' });
            if (originalValue) dateMask.value = originalValue;
            fp = flatpickr(inputElement, {
                dateFormat: "d/m/Y", allowInput: true, locale: "pt",
                onChange: function(selectedDates, dateStr) { 
                    if (dateStr && dateStr.length === 10) {
                        dateMask.value = dateStr;
                        inputElement.value = dateStr;
                        saveInProgress = true; 
                        salvarEdicao(); 
                        setTimeout(() => { if (fp) { fp.close(); fp.destroy(); } }, 50);
                    }
                }
            });
        }

        inputElement.focus();
        if (inputElement.select) inputElement.select();

        function cancelarEdicao() {
            container.innerHTML = backupHTML;
            currentEditInput = null;
        }

        function salvarEdicao() {
            const newValue = inputElement.value.trim();
            if (newValue === originalValue) return cancelarEdicao();

            let valueToSend = newValue;
            if (fieldName === 'prazo' && newValue) valueToSend = convertDateToISO(newValue);

            fetch(`/pendencias/update_field_inline/${pendenciaId}`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ field: fieldName, value: valueToSend })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    if (isCard) {
                        if (container.tagName === 'H4') container.innerHTML = `<span class="card-field-value">${data.newValue || 'Pendência sem título'}</span>`;
                        else container.innerHTML = `${backupHTML.split('</strong>')[0]}</strong> <span class="card-field-value">${data.newValue || ''}</span>`;
                    } else {
                        container.innerHTML = `<span class="card-value">${data.newValue}</span>`;
                    }
                    currentEditInput = null;
                    flashElement(isCard ? container.closest('.data-card') : container);
                    
                    // --- NOVA LÓGICA DE VENCIMENTO IMEDIATO ---
                    const rowOrCard = isCard ? container.closest('.data-card') : container.closest('tr');
                    if (fieldName === 'prazo') {
                        const hoje = new Date();
                        hoje.setHours(0, 0, 0, 0);
                        const dataPrazo = parseDateFromDDMMYYYY(data.newValue);
                        
                        // Remove a classe por garantia
                        rowOrCard.classList.remove('pendencia-vencida');
                        
                        // Se for menor que hoje, pinta de vermelho!
                        if (dataPrazo && dataPrazo < hoje) {
                            rowOrCard.classList.add('pendencia-vencida');
                        }
                    }

                    // Movimentação Kanban (se aplicável)
                    if (fieldName === 'prazo' && isCard && window.APP_DATA_PENDENCIAS?.viewMode === 'kanban') {
                        const cardElement = container.closest('.data-card');
                        const currentCol = cardElement.closest('.kanban-column');
                        if (currentCol) {
                            const hoje = new Date(); hoje.setHours(0,0,0,0);
                            const newPrazoDate = parseDateFromDDMMYYYY(data.newValue);
                            let targetColumnId = !newPrazoDate ? 'kanban-column-sem-prazo' : (newPrazoDate < hoje ? 'kanban-column-vencido' : 'kanban-column-a-vencer');
                            if (currentCol.id !== targetColumnId) {
                                const targetCol = document.getElementById(targetColumnId);
                                if (targetCol) {
                                    cardElement.style.opacity = '0';
                                    setTimeout(() => { targetCol.querySelector('.kanban-cards').appendChild(cardElement); cardElement.style.opacity = '1'; }, 300);
                                }
                            }
                        }
                    }
                } else { alert(`Erro: ${data.message}`); cancelarEdicao(); }
            }).catch(err => { alert('Erro de rede.'); cancelarEdicao(); });
        }

        inputElement.addEventListener('keydown', e => {
            if (e.key === 'Enter') { 
                if (inputElement.tagName === 'TEXTAREA' && e.shiftKey) return; 
                e.preventDefault(); 
                e.stopPropagation();
                
                if (fieldName === 'prazo') {
                    let valCompletado = autoCompletarData(inputElement.value);
                    
                    // SE A DATA NÃO EXISTIR, PINTA DE VERMELHO E TRAVA!
                    if (valCompletado === 'INVALIDA') {
                        inputElement.style.border = '2px solid #e74c3c';
                        return; // O "return" aqui impede o salvamento
                    }

                    if (valCompletado) {
                        if (dateMask) dateMask.value = valCompletado;
                        if (fp) fp.setDate(valCompletado, false, "d/m/Y"); // Trocado para 'false'
                        inputElement.value = valCompletado;
                    } else {
                        inputElement.value = '';
                    }
                    
                    if (fp) { fp.close(); fp.destroy(); }
                }
                
                saveInProgress = true; 
                salvarEdicao(); 
            }
            else if (e.key === 'Escape') cancelarEdicao();
        }, true);
        inputElement.addEventListener('blur', () => { setTimeout(() => { if (!saveInProgress && currentEditInput === inputElement) cancelarEdicao(); }, 150); });
    });

    // ==========================================
    // 2. CONCLUIR PENDÊNCIA (FLASH + SHRINK)
    // ==========================================
    document.body.addEventListener('click', function(e) {
        const btnConcluir = e.target.closest('.btn-concluir-action');
        if (!btnConcluir) return;
        e.preventDefault(); e.stopPropagation();

        const pendenciaId = btnConcluir.dataset.id;
        btnConcluir.style.backgroundColor = '#27ae60'; btnConcluir.style.borderColor = '#27ae60'; btnConcluir.style.color = 'white';

        fetch(`/pendencias/update_field_inline/${pendenciaId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: 'status', value: 'Concluído' })
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                const elementToAnimate = btnConcluir.closest('tr, .data-card');
                if (elementToAnimate) {
                    elementToAnimate.style.transition = 'background-color 0.3s ease';
                    elementToAnimate.style.backgroundColor = document.body.classList.contains('theme-dark') ? '#1e4620' : '#d4edda';
                    
                    const accordion = elementToAnimate.closest('.hub-accordion'); // Integração com o Hub
                    if(accordion) {
                        const badge = accordion.querySelector('.badge-pendencia');
                        if(badge) { let num = parseInt(badge.textContent.replace(/\D/g,'')) - 1; badge.textContent = `⏳ ${Math.max(0, num)} Pendências`; }
                    }

                    setTimeout(() => {
                        elementToAnimate.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
                        elementToAnimate.style.opacity = '0'; elementToAnimate.style.transform = 'scaleY(0)';
                        if(elementToAnimate.tagName === 'TR') elementToAnimate.querySelectorAll('td').forEach(td => { td.style.padding = '0'; td.style.fontSize = '0'; });
                        else { elementToAnimate.style.height = '0'; elementToAnimate.style.padding = '0'; elementToAnimate.style.margin = '0'; }
                        setTimeout(() => elementToAnimate.remove(), 400);
                    }, 400);
                }
            } else { alert('Erro: ' + data.message); btnConcluir.style.backgroundColor = ''; }
        });
    });

    // ==========================================
    // 3. TOGGLE DE PRIORIDADE
    // ==========================================
    document.body.addEventListener('click', function(e) {
        const toggle = e.target.closest('.coluna-prioridade, .card-priority-toggle');
        if (!toggle || toggle.closest('.card-quick-add-form') || toggle.id === 'inlineCreatePriorityToggle') return;
        
        e.preventDefault(); e.stopPropagation();
        if (isPriorityFetchLocked) return;
        isPriorityFetchLocked = true;
        
        const pendenciaId = toggle.dataset.id;
        fetch(`/pendencias/toggle_prioridade/${pendenciaId}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                const isActivating = data.nova_prioridade;
                const elementToMove = toggle.closest('tr, .data-card');
                if (!elementToMove) return;

                // Alternar estado visual
                if (elementToMove.tagName === 'TR') {
                    elementToMove.classList.toggle('prioridade-ativa', isActivating);
                    const icon = elementToMove.querySelector('.card-priority-toggle');
                    if(icon) icon.classList.toggle('active', isActivating);
                } else { toggle.classList.toggle('active', isActivating); }

                // Movimentação visual no DOM (Apenas se for página principal de pendências, não no hub)
                if (window.APP_DATA_PENDENCIAS) {
                    let targetContainer = elementToMove.tagName === 'TR' ? elementToMove.closest('tbody') : null;
                    if (!targetContainer && window.APP_DATA_PENDENCIAS.viewMode === 'cards') {
                        if (window.APP_DATA_PENDENCIAS.pageMode === 'por_instrumento') {
                            const group = elementToMove.closest('.instrumento-group-section');
                            if (group) targetContainer = isActivating ? group.querySelector('.card-grid') : group.querySelectorAll('.card-grid')[1] || group.querySelector('.card-grid');
                        } else {
                            targetContainer = isActivating ? document.querySelector('.priority-section .card-grid') : document.querySelector('.card-grid:not(.priority-section .card-grid)');
                        }
                    } else if (!targetContainer && window.APP_DATA_PENDENCIAS.viewMode === 'kanban') {
                        targetContainer = elementToMove.closest('.kanban-cards');
                    }

                    if (targetContainer) {
                        elementToMove.style.opacity = '0';
                        setTimeout(() => {
                            if (elementToMove.tagName === 'TR') {
                                // LÓGICA PARA A TABELA
                                if (isActivating) {
                                    const topBtn = targetContainer.querySelector('#row-btn-add-inline-top');
                                    const inlineForm = targetContainer.querySelector('#inline-create-template');
                                    let refNode = null;
                                    if (topBtn) {
                                        refNode = topBtn.nextElementSibling;
                                        if (inlineForm && inlineForm.style.display !== 'none' && refNode === inlineForm) {
                                            refNode = inlineForm.nextElementSibling;
                                        }
                                    }
                                    if (refNode) targetContainer.insertBefore(elementToMove, refNode);
                                    else targetContainer.prepend(elementToMove);
                                } else {
                                    const bottomBtn = targetContainer.querySelector('#row-btn-add-inline');
                                    if (bottomBtn) targetContainer.insertBefore(elementToMove, bottomBtn);
                                    else targetContainer.appendChild(elementToMove);
                                }
                            } else {
                                // LÓGICA CORRIGIDA PARA OS CARDS (Respeitando as Adições Rápidas)
                                if (isActivating) {
                                    // Se existir botão rápido de topo (Mobile), insere LOGO ABAIXO dele
                                    const topCard = targetContainer.querySelector('.card-quick-add-container-top-mobile');
                                    if (topCard) targetContainer.insertBefore(elementToMove, topCard.nextElementSibling);
                                    else targetContainer.prepend(elementToMove);
                                } else {
                                    // Desativando prioridade: Inserir LOGO ACIMA do card de adição rápida inferior
                                    const bottomCard = targetContainer.querySelector('#card-quick-add-container, .card-quick-add-container-group');
                                    if (bottomCard) targetContainer.insertBefore(elementToMove, bottomCard);
                                    else targetContainer.appendChild(elementToMove);
                                }
                            }
                            elementToMove.style.opacity = '1';
                        }, 300);
                    }
                }
            } else alert('Erro.');
        }).finally(() => { setTimeout(()=> isPriorityFetchLocked=false, 300); });
    });

    // ==========================================
    // 4. MENU DE CORES (CONTEXT MENU)
    // ==========================================
    if (contextMenu && colorPicker) {
        document.body.addEventListener('contextmenu', function(e) {
            // Só atua se for na tabela de pendências ou num card EXCLUSIVO de Pendência
            const item = e.target.closest('.tabela-pendencias-shared tbody tr.clickable-row, .data-card[data-type="pendencia"]');
            if (!item || !item.querySelector('.btn-concluir-action')) return; // Confirma se é uma pendência
            
            e.preventDefault(); activeItem = item;
            contextMenu.style.top = `${e.pageY}px`; contextMenu.style.left = `${e.pageX}px`;
            contextMenu.style.display = 'block';
        });

        window.addEventListener('click', () => contextMenu.style.display = 'none');
        
        document.getElementById('chooseColorOption')?.addEventListener('click', () => {
            if(activeItem) {
                const bg = getComputedStyle(activeItem).backgroundColor;
                if(bg !== 'rgba(0, 0, 0, 0)' && bg.startsWith('rgb')) {
                    const rgb = bg.match(/\d+/g);
                    if(rgb) colorPicker.value = "#" + ((1 << 24) + (parseInt(rgb[0]) << 16) + (parseInt(rgb[1]) << 8) + parseInt(rgb[2])).toString(16).slice(1).toUpperCase();
                }
            }
            colorPicker.click();
        });
        document.getElementById('clearColorOption')?.addEventListener('click', () => activeItem ? saveColor(activeItem.dataset.id, null) : null);
        colorPicker.addEventListener('change', (e) => activeItem ? saveColor(activeItem.dataset.id, e.target.value) : null);

        function saveColor(id, color) {
            fetch(`/pendencias/set_cor_destaque/${id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cor: color }) })
            .then(r => r.json()).then(d => { if(d.status === 'success') activeItem.style.backgroundColor = color || ''; else alert('Erro.'); });
        }
    }

    // ==========================================
    // 5. ADIÇÃO RÁPIDA (CARDS & TABELA)
    // ==========================================
    window.setupQuickAddCard = function(containerSelector, formSelector, triggerSelector, toggleSelector, btnCancelSelector, btnSaveSelector, defaultPriority = false) {
        document.body.addEventListener('click', function(e) {
            const trigger = e.target.closest(triggerSelector);
            if (trigger) {
                document.querySelectorAll('.card-quick-add-form').forEach(f => { f.style.display = 'none'; f.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(i => i.value = ''); });
                document.querySelectorAll('.card-quick-add-trigger').forEach(t => t.style.display = 'flex');
                const container = trigger.closest(containerSelector); const form = container.querySelector(formSelector);
                trigger.style.display = 'none'; form.style.display = 'flex';
                
                const priorityToggle = form.querySelector(toggleSelector);
                form.dataset.priority = defaultPriority ? 'true' : 'false';
                form.style.borderLeftColor = defaultPriority ? '#e74c3c' : 'var(--border-base)';
                if (priorityToggle) { if (defaultPriority) priorityToggle.classList.add('active'); else priorityToggle.classList.remove('active'); }
                form.querySelector('[name="pendencia"]')?.focus();
            }

            const toggle = e.target.closest(toggleSelector);
            if (toggle && toggle.closest('.card-quick-add-form')) {
                const form = toggle.closest(formSelector);
                let isPriority = form.dataset.priority === 'true'; isPriority = !isPriority;
                form.dataset.priority = isPriority; toggle.classList.toggle('active', isPriority);
                form.style.borderLeftColor = isPriority ? '#e74c3c' : 'var(--border-base)';
            }

            const btnCancel = e.target.closest(btnCancelSelector);
            if (btnCancel) {
                const container = btnCancel.closest(containerSelector);
                container.querySelector(formSelector).style.display = 'none';
                container.querySelector(triggerSelector).style.display = 'flex';
            }

            const btnSave = e.target.closest(btnSaveSelector);
            if (btnSave) {
                const form = btnSave.closest(formSelector);
                const payload = { prioridade: form.dataset.priority === 'true' };
                form.querySelectorAll('input, textarea, select').forEach(i => { if (i.name) payload[i.name] = i.value; });
                if (!payload.pendencia.trim()) { alert("O título é obrigatório."); return; }
                btnSave.disabled = true; btnSave.textContent = "...";
                fetch(window.APP_DATA_PENDENCIAS?.urlQuickCreate || "/pendencias/quick_create_inline", {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
                }).then(r => r.json()).then(data => {
                    if (data.status === 'success') window.location.reload(); 
                    else { alert("Erro: " + data.message); btnSave.disabled = false; btnSave.textContent = "Salvar"; }
                });
            }
        });
        
        document.body.addEventListener('keydown', function(e) {
            const form = e.target.closest(formSelector);
            if (form && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
                if (e.key === 'Enter') { if (e.target.tagName === 'TEXTAREA' && e.shiftKey) return; e.preventDefault(); form.querySelector(btnSaveSelector)?.click(); }
                else if (e.key === 'Escape') { e.preventDefault(); form.querySelector(btnCancelSelector)?.click(); }
            }
        });
    }

    // Inicialização da Tabela Inline
    const templateInlineCreate = document.getElementById('inline-create-template');

    if (templateInlineCreate) {
        let isInlinePriority = false;
        templateInlineCreate.addEventListener('keydown', function(e) {
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
                if (e.key === 'Enter') { 
                    if (e.target.tagName === 'TEXTAREA' && e.shiftKey) return; // Permite quebra de linha com Shift+Enter
                    e.preventDefault(); 
                    const btnSave = templateInlineCreate.querySelector('.btn-save-inline');
                    if (btnSave && !btnSave.disabled) btnSave.click(); // Simula o clique no botão Salvar
                }
                else if (e.key === 'Escape') { 
                    e.preventDefault(); 
                    closeInlineForm(); 
                }
            }
        });
        document.body.addEventListener('click', function(e) {
            if (e.target.closest('#btnShowInlineCreateTop')) openInlineForm(true);
            else if (e.target.closest('#btnShowInlineCreate')) openInlineForm(false);
            else if (e.target.closest('#inlineCreatePriorityToggle')) {
                isInlinePriority = !isInlinePriority; e.target.closest('#inlineCreatePriorityToggle').classList.toggle('active', isInlinePriority);
            }
            else if (e.target.closest('.btn-cancel-inline')) closeInlineForm();
            else if (e.target.closest('.btn-save-inline')) {
                const payload = { prioridade: isInlinePriority };
                templateInlineCreate.querySelectorAll('input, textarea, select').forEach(el => { if (el.name) payload[el.name] = el.value; });
                if (!payload.pendencia || payload.pendencia.trim() === '') { alert("Por favor, digite a pendência."); return; }
                const btnSave = e.target.closest('.btn-save-inline'); btnSave.disabled = true;
                fetch(window.APP_DATA_PENDENCIAS?.urlQuickCreate || "/pendencias/quick_create_inline", {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
                }).then(r => r.json()).then(d => { if(d.status==='success') window.location.reload(); else {alert("Erro: "+d.message); btnSave.disabled=false;} });
            }
        });
        
        function openInlineForm(isTop) {
            const rowBtnAddInlineTop = document.getElementById('row-btn-add-inline-top');
            const rowBtnAddInline = document.getElementById('row-btn-add-inline');
            if (isTop) { rowBtnAddInlineTop.after(templateInlineCreate); rowBtnAddInlineTop.style.display = 'none'; if (rowBtnAddInline) rowBtnAddInline.style.display = 'table-row'; } 
            else { rowBtnAddInline.before(templateInlineCreate); rowBtnAddInline.style.display = 'none'; if (rowBtnAddInlineTop) rowBtnAddInlineTop.style.display = 'table-row'; }
            templateInlineCreate.style.display = 'table-row'; templateInlineCreate.querySelector('[name="pendencia"]')?.focus();
            isInlinePriority = false; document.getElementById('inlineCreatePriorityToggle')?.classList.remove('active');
        }
        function closeInlineForm() {
            templateInlineCreate.querySelectorAll('input, textarea, select').forEach(el => el.value = '');
            templateInlineCreate.style.display = 'none';
            document.getElementById('row-btn-add-inline-top').style.display = 'table-row';
            document.getElementById('row-btn-add-inline').style.display = 'table-row';
        }
    }
});